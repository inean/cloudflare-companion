import asyncio
import re
from collections.abc import Callable, Generator
from logging import Logger
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, call, patch
from urllib.parse import urlparse

import docker
import docker.client
import docker.errors
import pytest

from dns_synchub.events.types import Event, EventSubscriber
from dns_synchub.pollers import PollerData
from dns_synchub.pollers.docker import DockerError, DockerPoller
from dns_synchub.settings import Settings


class MockDockerEvents:
    def __init__(self, data: list[dict[str, str]]):
        self.data = data
        self.close = MagicMock()
        self.reset()

    def __iter__(self) -> 'MockDockerEvents':
        return self

    def __next__(self) -> dict[str, str]:
        try:
            return next(self.iter)
        except StopIteration:
            raise docker.errors.NotFound('No more events')

    def reset(self) -> None:
        self.iter = iter(self.data)


@pytest.fixture
def settings() -> Settings:
    return Settings(cf_token='token', dry_run=True)


@pytest.fixture
def logger() -> Logger:
    return MagicMock(spec=Logger)


@pytest.fixture
def containers() -> dict[str, Any]:
    data: dict[str, dict[str, Any]] = {
        str(id_): {
            'Id': id_,
            'Config': {
                'Labels': {
                    'traefik.http.routers.example.rule': f'Host(`subdomain{id_}.example.ltd`)'
                }
            },
        }
        for id_ in range(1, 5)
    }
    data['1']['Config']['Labels']['traefik.constraint'] = 'enable'
    data['2']['Config']['Labels']['traefik.constraint'] = 'disable'
    return data


@pytest.fixture(autouse=True)
def mock_requests_get(
    request: pytest.FixtureRequest, containers: dict[str, Any]
) -> Generator[Any, None, Any] | Callable[..., Any]:
    for mark in request.node.iter_markers():
        if mark.name == 'skip_fixture' and request.fixturename in mark.args:
            yield
            return
    with patch('requests.Session.get') as mock_get:

        def side_effect(url: str, *args: Any, **kwargs: dict[str, Any]) -> MagicMock:
            return_value: dict[str, Any] | list[dict[str, Any]] | None = None
            # Process URLs
            match urlparse(url).path:
                case '/version':
                    return_value = {'ApiVersion': '1.41'}
                case '/v1.41/info':
                    return_value = {'Name': 'Mock Docker'}
                case '/v1.41/containers/json':
                    return_value = [{'Id': id_} for id_ in containers.keys()]
                case details if match := re.search(r'/v1.41/containers/([^/]+)/json', details):
                    return_value = containers[match.group(1)]
                case other:
                    raise AssertionError(f'Unexpected URL: {other}')

            # Create a MagicMock object to mock the response
            response = MagicMock()
            response.json.return_value = return_value
            return response

        mock_get.side_effect = side_effect
        yield mock_get


@pytest.fixture
def docker_poller(
    logger: MagicMock, settings: Settings, containers: dict[str, Any]
) -> Generator[DockerPoller, None, None]:
    events = [{'status': 'start', 'id': id_} for id_ in containers.keys()]
    docker_client = docker.DockerClient(base_url='unix:///')
    with patch.object(docker_client, 'events', return_value=MockDockerEvents(events)):
        yield DockerPoller(logger, settings=settings, client=docker_client)


@pytest.mark.skip_fixture('mock_requests_get')
def test_docker_init_with_bad_engine(
    logger: MagicMock, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(DockerError) as err:
        monkeypatch.setenv('DOCKER_HOST', 'unix:///')
        DockerPoller(logger, settings=settings).client
    assert str(err.value) == 'Could not connect to Docker'


def test_init(logger: MagicMock, settings: Settings) -> None:
    poller = DockerPoller(logger, settings=settings)
    assert poller.poll_sec == settings.docker_poll_seconds
    assert poller.tout_sec == settings.docker_timeout_seconds
    assert poller.filter_label == settings.docker_filter_label
    assert poller.filter_value == settings.docker_filter_value


def test_init_from_env(logger: MagicMock, settings: Settings) -> None:
    poller = DockerPoller(logger, settings=settings)
    assert isinstance(poller.client, docker.DockerClient)


def test_init_from_client(logger: MagicMock, settings: Settings) -> None:
    client = docker.DockerClient(base_url='unix:///')
    poller = DockerPoller(logger, settings=settings, client=client)
    assert poller.client == client


@pytest.mark.asyncio
async def test_fetch(docker_poller: DockerPoller) -> None:
    data = await docker_poller.fetch()
    assert data.source == 'docker'
    assert data.hosts == [f'subdomain{i}.example.ltd' for i in range(1, 5)]


@pytest.mark.asyncio
async def test_fetch_filter_by_label(docker_poller: DockerPoller) -> None:
    docker_poller.filter_label = re.compile(r'traefik.constraint')
    data = await docker_poller.fetch()
    assert data.source == 'docker'
    assert data.hosts == [f'subdomain{i}.example.ltd' for i in range(1, 3)]


@pytest.mark.asyncio
async def test_fetch_filter_by_value(docker_poller: DockerPoller) -> None:
    docker_poller.filter_label = re.compile(r'traefik.constraint')
    docker_poller.filter_value = re.compile(r'enable')
    data = await docker_poller.fetch()
    assert data.source == 'docker'
    assert data.hosts == [f'subdomain{i}.example.ltd' for i in range(1, 2)]


@pytest.mark.asyncio
async def test_run(docker_poller: DockerPoller) -> None:
    callback_mock = MagicMock(spec=EventSubscriber)
    callback_mock.__call__ = AsyncMock(return_value=None)  # type: ignore

    await docker_poller.events.subscribe(callback_mock)
    assert 0 == callback_mock.call_count

    # Check timeout was reached
    await docker_poller.start(timeout=0.1)
    logger = cast(MagicMock, docker_poller.logger)
    assert any('Run timeout' in str(arg) for arg in logger.info.call_args_list)

    # Docker Client asserts
    await asyncio.gather(docker_poller.start(), docker_poller.stop())
    docker_client_events = cast(MagicMock, docker_poller.client.events)
    docker_client_events.assert_called_once()
    docker_client_events.return_value.close.assert_called_once()

    #  Check callback calls. First run will fetch all containers plus events
    expected_calls = (
        []
        + [call(Event(PollerData([f'subdomain{i}.example.ltd' for i in range(1, 5)], 'docker')))]
        + [call(Event(PollerData([f'subdomain{i}.example.ltd'], 'docker'))) for i in range(1, 5)]
    )
    assert callback_mock.__call__.call_count == len(expected_calls)
    callback_mock.__call__.assert_has_calls(expected_calls, any_order=False)

    # Check the rest of the runs will not perform a fetch
    expected_calls.pop(0)
    callback_mock.__call__.reset_mock()
    docker_client_events.return_value.reset()
    loop = asyncio.get_event_loop()
    loop.call_later(0.1, lambda: asyncio.create_task(docker_poller.stop()))
    await docker_poller.start()
    assert callback_mock.__call__.call_count == len(expected_calls)
    callback_mock.__call__.assert_has_calls(expected_calls, any_order=False)


@pytest.mark.asyncio
async def test_run_canceled(docker_poller: DockerPoller) -> None:
    async def cancel(task: asyncio.Task[Any]) -> None:
        await asyncio.sleep(0.1)
        task.cancel()

    poller_task = asyncio.create_task(docker_poller.start())
    tasks = [poller_task, asyncio.create_task(cancel(poller_task))]
    await asyncio.gather(*tasks)

    # Check timeout was reached
    # Check timeout was reached
    logger = cast(MagicMock, docker_poller.logger)
    logger.info.assert_any_call('DockerPoller: Run was cancelled')

    # Docker Client asserts
    docker_client_events = cast(MagicMock, docker_poller.client.events)
    docker_client_events.assert_called_once()
    docker_client_events.return_value.close.assert_called_once()

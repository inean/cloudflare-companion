import asyncio
import re
from logging import Logger
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import docker
import docker.client
import docker.errors
import pytest

from dns_synchub.pollers.docker import DockerError, DockerPoller
from dns_synchub.settings import Settings


class MockDockerEvents:
    def __init__(self, data: list[dict[str, str]]):
        self.data = iter(data)
        self.close = MagicMock()

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return next(self.data)
        except StopIteration:
            raise docker.errors.NotFound("No more events")


@pytest.fixture
def settings():
    return Settings(cf_token="token")


@pytest.fixture
def logger():
    return MagicMock(spec=Logger)


@pytest.fixture
def containers() -> dict[str, Any]:
    data: dict[str, dict[str, Any]] = {
        str(id_): {
            "Id": id_,
            "Config": {
                "Labels": {
                    "traefik.http.routers.example.rule": f"Host(`subdomain{id_}.example.ltd`)"
                }
            },
        }
        for id_ in range(1, 5)
    }
    data["1"]["Config"]["Labels"]["traefik.constraint"] = "enable"
    data["2"]["Config"]["Labels"]["traefik.constraint"] = "disable"
    return data


@pytest.fixture(autouse=True)
def mock_requests_get(request: pytest.FixtureRequest, containers: dict[str, Any]):
    if "skip_mock_requests_get" in request.keywords:
        yield
        return
    with patch("requests.Session.get") as mock_get:

        def side_effect(url: str, *args: Any, **kwargs: dict[str, Any]):
            # Process URLs
            match urlparse(url).path:
                case "/version":
                    return_value = {"ApiVersion": "1.41"}
                case "/v1.41/info":
                    return_value = {"Name": "Mock Docker"}
                case "/v1.41/containers/json":
                    return_value = [{"Id": id_} for id_ in containers.keys()]
                case details if (match := re.search(r"/v1.41/containers/([^/]+)/json", details)):
                    return_value = containers[match.group(1)]  # type: ignore
                case other:
                    raise AssertionError(f"Unexpected URL: {other}")

            # Create a MagicMock object to mock the response
            response = MagicMock()
            response.json.return_value = return_value
            return response

        mock_get.side_effect = side_effect
        yield mock_get


@pytest.fixture
@pytest.mark.usefixtures("mock_requests_get")
def docker_poller(logger: MagicMock, settings: Settings, containers: dict[str, Any]):
    events = [{"status": "start", "id": id_} for id_ in containers.keys()]
    docker_client = docker.DockerClient(base_url="unix:///")
    with patch.object(docker_client, "events", return_value=MockDockerEvents(events)):
        yield DockerPoller(logger, settings=settings, client=docker_client)


@pytest.mark.skip_mock_requests_get
def test_docker_init_with_bad_engine(
    logger: MagicMock,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
):
    with pytest.raises(DockerError) as err:
        monkeypatch.setenv("DOCKER_HOST", "unix:///")
        DockerPoller(logger, settings=settings).client
    assert str(err.value) == "Could not connect to Docker"


def test_init(logger: MagicMock, settings: Settings):
    poller = DockerPoller(logger, settings=settings)
    assert poller.poll_sec == settings.docker_poll_seconds
    assert poller.tout_sec == settings.docker_timeout_seconds
    assert poller.filter_label == settings.docker_filter_label
    assert poller.filter_value == settings.docker_filter_value


def test_init_from_env(logger: MagicMock, settings: Settings):
    poller = DockerPoller(logger, settings=settings)
    assert isinstance(poller.client, docker.DockerClient)


def test_init_from_client(logger: MagicMock, settings: Settings):
    client = docker.DockerClient(base_url="unix:///")
    poller = DockerPoller(logger, settings=settings, client=client)
    assert poller.client == client


@pytest.mark.asyncio
async def test_fetch(docker_poller: DockerPoller):
    hosts, source = await docker_poller.fetch()
    assert source == "docker"
    assert hosts == [f"subdomain{i}.example.ltd" for i in range(1, 5)]


@pytest.mark.asyncio
async def test_fetch_filter_by_label(docker_poller: DockerPoller):
    docker_poller.filter_label = re.compile(r"traefik.constraint")
    hosts, source = await docker_poller.fetch()
    assert source == "docker"
    assert hosts == [f"subdomain{i}.example.ltd" for i in range(1, 3)]


@pytest.mark.asyncio
async def test_fetch_filter_by_value(docker_poller: DockerPoller):
    docker_poller.filter_label = re.compile(r"traefik.constraint")
    docker_poller.filter_value = re.compile(r"enable")
    hosts, source = await docker_poller.fetch()
    assert source == "docker"
    assert hosts == [f"subdomain{i}.example.ltd" for i in range(1, 2)]


@pytest.mark.asyncio
async def test_run(docker_poller: DockerPoller):
    callback_mock = MagicMock()
    await docker_poller.events.subscribe(callback_mock)
    assert 0 == callback_mock.call_count

    await docker_poller.run(timeout=0.1)

    # Check timeout was reached
    assert any("Run timeout" in str(arg) for arg in docker_poller.logger.info.call_args_list)

    # Docker Client asserts
    docker_poller.client.events.assert_called_once()
    docker_poller.client.events.return_value.close.assert_called_once()

    # Check data
    callback_mock.assert_called_once()
    hosts, source = callback_mock.call_args[0]
    assert source == "docker"
    assert hosts == [f"subdomain{i}.example.ltd" for i in range(1, 5)]


@pytest.mark.asyncio
async def test_run_canceled(docker_poller: DockerPoller):
    async def cancel(task: asyncio.Task[Any]) -> None:
        await asyncio.sleep(0.1)
        task.cancel()

    poller_task = asyncio.create_task(docker_poller.run())
    tasks = [poller_task, asyncio.create_task(cancel(poller_task))]
    await asyncio.gather(*tasks)

    # Check timeout was reached
    docker_poller.logger.info.assert_any_call("DockerPoller: Run was cancelled")

    # Docker Client asserts
    docker_poller.client.events.assert_called_once()
    docker_poller.client.events.return_value.close.assert_called_once()

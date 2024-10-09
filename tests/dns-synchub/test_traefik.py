from collections.abc import Generator
from logging import Logger
from unittest.mock import MagicMock, patch

import pytest

from dns_synchub.pollers.traefik import TraefikPoller
from dns_synchub.settings import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(cf_token='token', dry_run=True)


@pytest.fixture
def mock_logger() -> Logger:
    return MagicMock(spec=Logger)


@pytest.fixture
def mock_api_no_routers() -> Generator[MagicMock, None, None]:
    with patch('requests.Session.get') as mock_get:
        mock_get.return_value.ok = True
        mock_get.return_value.json.return_value = []
        yield mock_get


@pytest.fixture
def traefik_poller(mock_logger: MagicMock, settings: Settings) -> TraefikPoller:
    return TraefikPoller(mock_logger, settings=settings)


def test_init(mock_logger: MagicMock, settings: Settings) -> None:
    poller = TraefikPoller(mock_logger, settings=settings)
    assert poller.poll_sec == settings.traefik_poll_seconds
    assert poller.tout_sec == settings.traefik_timeout_seconds
    assert poller.poll_url == f'{settings.traefik_poll_url}/api/http/routers'
    assert 'docker' in poller.excluded_providers


@pytest.mark.asyncio
async def test_no_routers(traefik_poller: TraefikPoller, mock_api_no_routers: MagicMock) -> None:
    data = await traefik_poller.fetch()
    assert data.source == 'traefik'
    assert data.hosts == []

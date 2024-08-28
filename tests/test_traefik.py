from logging import Logger
from unittest.mock import MagicMock, patch

import pytest

from dns_synchub.pollers.traefik import TraefikPoller
from dns_synchub.settings import Settings


@pytest.fixture
def settings():
    return Settings(cf_token="token")


@pytest.fixture
def mock_logger():
    return MagicMock(spec=Logger)


@pytest.fixture
def mock_api_no_routers():
    with patch("requests.get") as mock_get:
        mock_get.return_value.ok = True
        mock_get.return_value.json.return_value = []
        yield mock_get


@pytest.fixture
def traefik_poller(mock_logger: MagicMock, settings: Settings):
    return TraefikPoller(mock_logger, settings=settings)


def test_init(mock_logger: MagicMock, settings: Settings):
    poller = TraefikPoller(mock_logger, settings=settings)
    assert poller.poll_sec == settings.traefik_poll_seconds
    assert poller.tout_sec == settings.traefik_timeout_seconds
    assert poller.poll_url == f"{settings.traefik_poll_url}/api/http/routers"
    assert "docker" in poller.excluded_providers


@pytest.mark.asyncio
async def test_no_routers(traefik_poller: TraefikPoller, mock_api_no_routers: MagicMock):
    hosts, source = await traefik_poller.fetch()
    assert source == "traefik"
    assert hosts == []

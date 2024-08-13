from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Assuming the function check_container_t2 is imported from the module
from cloudflare_companion import check_container_t2
from pollers.docker import DockerContainer, DockerPoller


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.docker_poll_seconds = 10
    settings.traefik_filter_label = "traefik.enable"
    settings.traefik_filter_value = "true"
    return settings


@pytest.fixture
def mock_logger():
    logger = MagicMock()
    return logger


@pytest.fixture
def mock_containers():
    container1 = MagicMock(spec=DockerContainer)
    container1.hosts = ["host1.example.com"]
    container1.labels = {"traefik.enable": True}

    container2 = MagicMock(spec=DockerContainer)
    container2.hosts = ["host2.example.com"]
    container2.labels = {"traefik.enable": False}

    return [container1, container2]


@pytest.fixture
def mock_docker_poller_cls(mock_containers):
    def mock_is_enabled(container):
        return next(iter(container.labels.values()))

    with patch("cloudflare_companion.DockerPoller", autospec=True) as MockDockerPoller:
        mock_object = Mock(spec=DockerPoller)
        mock_object.fetch = AsyncMock(return_value=mock_containers)

        mock_object._is_enabled = mock_is_enabled
        MockDockerPoller.return_value = mock_object
        yield MockDockerPoller


@pytest.mark.asyncio
def test_check_container_t2(mock_docker_poller_cls, mock_settings, mock_logger):
    poller = mock_docker_poller_cls(mock_logger, settings=mock_settings)
    mappings = check_container_t2(poller, None)
    assert mappings == {"host1.example.com": 1}


@pytest.mark.asyncio
async def test_check_container_t2_no_containers(mock_settings, mock_logger):
    poller = DockerPoller(mock_logger, settings=mock_settings)
    mappings = check_container_t2(poller, [])
    assert mappings == {}


@pytest.mark.asyncio
def test_check_container_t2_disabled_container(mock_settings, mock_logger):
    poller = DockerPoller(mock_logger, settings=mock_settings)
    poller._is_enabled = MagicMock(return_value=False)
    mappings = check_container_t2(poller, None)
    assert mappings == {}

import logging
import re
from unittest.mock import MagicMock, patch

import pytest
from cloudflare_companion import check_traefik
from settings import Settings


@pytest.fixture
def mock_logger():
    logger = logging.getLogger("cloudflare_companion")
    return logger


@pytest.fixture
def mock_settings():
    settings = MagicMock(spec=Settings)
    settings.traefik_poll_url = "http://mock-traefik/api"
    settings.traefik_poll_seconds = 30
    settings.traefik_timeout_seconds = 5
    settings.traefik_filter = None
    settings.traefik_filter_label = None
    settings.traefik_included_hosts = [re.compile(".*")]
    settings.traefik_excluded_hosts = []
    return settings


def test_check_traefik_no_routers(mock_settings, mock_logger):
    with patch("requests.get") as mock_get:
        mock_get.return_value.ok = True
        mock_get.return_value.json.return_value = []

        mappings = check_traefik(mock_settings, [], [], mock_logger)
        assert mappings == {}


def test_check_traefik_no_matching_hosts(mock_settings, mock_logger):
    with patch("requests.get") as mock_get:
        mock_get.return_value.ok = True
        mock_get.return_value.json.return_value = [
            {
                "status": "enabled",
                "name": "router1",
                "rule": "Host(`nonmatching.com`)",
            }
        ]

        mappings = check_traefik(mock_settings, [re.compile("example.com")], [], mock_logger)
        assert mappings == {}


def test_check_traefik_matching_hosts(mock_settings, mock_logger):
    with patch("requests.get") as mock_get:
        mock_get.return_value.ok = True
        mock_get.return_value.json.return_value = [
            {
                "status": "enabled",
                "name": "router1",
                "rule": "Host(`example.com`)",
            }
        ]

        mappings = check_traefik(mock_settings, [re.compile("example.com")], [], mock_logger)
        assert mappings == {"example.com": 2}


def test_check_traefik_multiple_matching_hosts(mock_settings, mock_logger):
    with patch("requests.get") as mock_get:
        mock_get.return_value.ok = True
        mock_get.return_value.json.return_value = [
            {
                "status": "enabled",
                "name": "router1",
                "rule": "Host(`example.com`) || Host(`another.com`)",
            }
        ]

        domains = ["example.com", "another.com"]
        compiled_domains = list(map(re.compile, domains))

        mappings = check_traefik(mock_settings, compiled_domains, [], mock_logger)
        assert mappings == {"another.com": 2, "example.com": 2}


def test_check_traefik_excluded_hosts(mock_settings, mock_logger):
    with patch("requests.get") as mock_get:
        mock_get.return_value.ok = True
        mock_get.return_value.json.return_value = [
            {
                "status": "enabled",
                "name": "router1",
                "rule": "Host(`example.com`)",
            }
        ]

        # Compile the domains using map and re.compile
        compiled_domains = list(map(re.compile, ["example.com"]))
        compiled_excluded_domains = list(map(re.compile, ["example.com"]))

        mappings = check_traefik(
            mock_settings, compiled_domains, compiled_excluded_domains, mock_logger
        )
        assert mappings == {}

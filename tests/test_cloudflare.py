# test_cloudflare_companion.py


from unittest.mock import MagicMock, patch

import CloudFlare
import pytest
from cloudflare_companion import (
    DomainsModel,
    Settings,
    point_domain,
)


@pytest.fixture
def mock_cloudflare():
    cf = MagicMock()
    cf.zones.dns_records.get = MagicMock()
    cf.zones.dns_records.put = MagicMock()
    cf.zones.dns_records.post = MagicMock()
    return cf


@pytest.fixture
def mock_settings():
    settings = MagicMock(spec=Settings)
    settings.rc_type = "CNAME"
    settings.refresh_entries = True
    settings.dry_run = False
    return settings


@pytest.fixture
def mock_domain_infos():
    domain_info = MagicMock(spec=DomainsModel)
    domain_info.name = "example.com"
    domain_info.target_domain = "target.example.com"
    domain_info.zone_id = "zone_id"
    domain_info.ttl = 1
    domain_info.proxied = False
    domain_info.comment = "Test comment"
    domain_info.excluded_sub_domains = []
    return [domain_info]


def test_point_domain_target_domain_match(
    mock_cloudflare, mock_settings, mock_domain_infos
):
    result = point_domain(
        mock_cloudflare, mock_settings, "target.example.com", mock_domain_infos
    )
    assert result is True
    mock_cloudflare.zones.dns_records.get.assert_not_called()


def test_point_domain_excluded_domain(
    mock_cloudflare, mock_settings, mock_domain_infos
):
    mock_domain_infos[0].excluded_sub_domains = ["sub"]
    result = point_domain(
        mock_cloudflare, mock_settings, "sub.example.com", mock_domain_infos
    )
    assert result is True
    mock_cloudflare.zones.dns_records.get.assert_not_called()


def test_point_domain_create_new_record(
    mock_cloudflare, mock_settings, mock_domain_infos
):
    mock_cloudflare.zones.dns_records.get.return_value = []
    result = point_domain(
        mock_cloudflare, mock_settings, "new.example.com", mock_domain_infos
    )
    assert result is True
    mock_cloudflare.zones.dns_records.post.assert_called_once()


def test_point_domain_update_existing_record(
    mock_cloudflare, mock_settings, mock_domain_infos
):
    mock_cloudflare.zones.dns_records.get.return_value = [{"id": "record_id"}]
    result = point_domain(
        mock_cloudflare, mock_settings, "existing.example.com", mock_domain_infos
    )
    assert result is True
    mock_cloudflare.zones.dns_records.put.assert_called_once()


def test_point_domain_rate_limit_retry(
    mock_cloudflare, mock_settings, mock_domain_infos
):
    mock_cloudflare.zones.dns_records.get.side_effect = [
        CloudFlare.exceptions.CloudFlareAPIError("Rate limited"),
        CloudFlare.exceptions.CloudFlareAPIError("Rate limited"),
        [],
    ]
    with patch("time.sleep", return_value=None):
        result = point_domain(
            mock_cloudflare,
            mock_settings,
            "rate_limited.example.com",
            mock_domain_infos,
        )
    assert result is True
    assert mock_cloudflare.zones.dns_records.get.call_count == 3


def test_point_domain_dry_run(mock_cloudflare, mock_settings, mock_domain_infos):
    mock_settings.dry_run = True
    mock_cloudflare.zones.dns_records.get.return_value = []
    result = point_domain(
        mock_cloudflare, mock_settings, "dryrun.example.com", mock_domain_infos
    )
    assert result is True
    mock_cloudflare.zones.dns_records.post.assert_not_called()

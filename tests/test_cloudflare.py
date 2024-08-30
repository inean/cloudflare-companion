from copy import deepcopy
from logging import Logger
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from CloudFlare import CloudFlare  # type: ignore
from CloudFlare.exceptions import CloudFlareAPIError  # type: ignore
from dns_synchub.mappers import CloudFlareMapper, Settings
from dns_synchub.settings import DomainsModel


@pytest.fixture
def settings():
    records: list[DomainsModel] = []
    for i in range(1, 5):
        entry = DomainsModel(
            zone_id=f"{i}",
            name=f"region{i}.example.ltd",
            target_domain=f"target{i}.example.ltd",
            comment=f"Test comment {i}",
        )
        records.append(entry)

    return Settings(cf_token="token", dry_run=True, domains=records)


@pytest.fixture
def mock_logger():
    return MagicMock(spec=Logger)


@pytest.fixture
def mock_cf_client():
    def create_response(requests: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
        requests = requests if isinstance(requests, list) else [requests]
        response: dict[str, Any] = {
            "success": True,
            "result": [
                {
                    **(
                        lambda req: (
                            req.setdefault("zone_id", "default_zone_id"),
                            req.setdefault("ttl", "auto"),
                            deepcopy(req),
                        )[2]
                    )(request),
                    "created_on": "2014-01-01T05:20:00.12345Z",
                    "modified_on": "2014-01-01T05:20:00.12345Z",
                    "meta": {"auto_added": True, "source": "primary"},
                    "proxiable": True,
                }
                for request in requests
            ],
        }
        return response["result"]

    def filter_response(
        response: list[dict[str, Any]], params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return [
            record
            for record in response
            if all(
                (value in record[key] if isinstance(value, str) else record[key] == value)
                for key, value in params.items()
            )
        ]

    # Example usage
    requests: list[dict[str, Any]] = [
        {
            "content": f"198.51.100.{i}",
            "name": f"subdomain{i}.region{i}.example.ltd",
            "proxied": False,
            "type": "A",
            "comment": "Domain verification record",
            "id": f"023e105f4ecef8ad9ca31a8372d0c353{i}",
            "tags": [],
            "ttl": 60,
        }
        for i in range(1, 5)
    ]

    def get_side_effect(_, params: dict[str, Any]) -> list[dict[str, Any]]:
        return filter_response(create_response(requests), params)

    def post_side_effect(zone_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return create_response({**data, "zone_id": zone_id, "id": "record_id"}).pop()

    def put_side_effect(zone_id: str, record_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return create_response({**data, "zone_id": zone_id, "id": record_id}).pop()

    cf = MagicMock()
    cf.zones.dns_records.get.side_effect = get_side_effect
    cf.zones.dns_records.post.side_effect = post_side_effect
    cf.zones.dns_records.put.side_effect = put_side_effect
    return cf


@pytest.fixture(autouse=True)
def mock_tenacity():
    with patch("asyncio.sleep"):
        yield


def test_init(mock_logger: MagicMock, settings: Settings):
    mapper = CloudFlareMapper(mock_logger, settings=settings)
    assert mapper.dry_run == settings.dry_run
    assert mapper.rc_type == settings.rc_type
    assert mapper.refresh_entries == settings.refresh_entries
    assert mapper.domains == settings.domains
    assert mapper.tout_sec == settings.cf_timeout_seconds
    assert mapper.sync_sec == settings.cf_sync_seconds

    assert isinstance(mapper.client, CloudFlare)
    mock_logger.debug.assert_called_once()


def test_init_with_client(mock_logger: MagicMock, settings: Settings):
    client = CloudFlare()
    mapper = CloudFlareMapper(mock_logger, settings=settings, client=client)
    assert mapper.client == client
    mock_logger.debug.assert_not_called()


@pytest.mark.asyncio
async def test_call(mock_logger: MagicMock, settings: Settings, mock_cf_client: MagicMock):
    mapper = CloudFlareMapper(mock_logger, settings=settings, client=mock_cf_client)
    events = (["subdomain.example.ltd"], "manual")

    with patch.object(mapper, "sync", new_callable=AsyncMock) as mock_sync:
        await mapper(*events)
        mock_sync.assert_called_once_with("subdomain.example.ltd", "manual")


@pytest.mark.asyncio
async def test_get_records(mock_logger: MagicMock, settings: Settings, mock_cf_client: MagicMock):
    zone_id, name = ("zone_id", "example.ltd")

    mapper = CloudFlareMapper(mock_logger, settings=settings, client=mock_cf_client)
    zones = await mapper.get_records(zone_id, name=name)
    mock_cf_client.zones.dns_records.get.assert_called_with(zone_id, params={"name": name})
    assert len(zones) == 4


@pytest.mark.asyncio
async def test_post_record(mock_logger: MagicMock, settings: Settings, mock_cf_client: MagicMock):
    mapper = CloudFlareMapper(mock_logger, settings=settings, client=mock_cf_client)
    zone_id, zone = "zone_id", {"type": "A", "name": "example.ltd", "content": "1.2.3.4"}

    # Dry run
    await mapper.post_record(zone_id, **zone)
    mock_cf_client.zones.dns_records.post.assert_not_called()
    cast(MagicMock, mapper.logger.info).assert_called_once()

    with patch.object(mapper, "dry_run", False):
        # Client call
        await mapper.post_record(zone_id, **zone)
        mock_cf_client.zones.dns_records.post.assert_called_with(zone_id, data=zone)

        # retry Call
        with pytest.raises(CloudFlareAPIError, match="Rate limited"):
            rate_error = CloudFlareAPIError(-1, "Rate limited")
            cast(MagicMock, mock_cf_client.zones.dns_records.post).side_effect = rate_error
            await mapper.post_record(zone_id, **zone)


@pytest.mark.asyncio
async def test_put_record(mock_logger: MagicMock, settings: Settings, mock_cf_client: MagicMock):
    mapper = CloudFlareMapper(mock_logger, settings=settings, client=mock_cf_client)
    zone_id, record_id = "zone_id", "record_id"
    zone = {"type": "A", "name": "example.ltd", "content": "1.2.3.4"}

    # Dry run call
    await mapper.put_record(zone_id, record_id, **zone)
    mock_cf_client.zones.dns_records.put.assert_not_called()
    cast(MagicMock, mapper.logger.info).assert_called_once()

    with patch.object(mapper, "dry_run", False):
        # Client call
        await mapper.put_record(zone_id, record_id, **zone)
        mock_cf_client.zones.dns_records.put.assert_called_with(zone_id, record_id, data=zone)


@pytest.mark.asyncio
async def test_sync_with_target_domain(
    mock_logger: MagicMock, settings: Settings, mock_cf_client: MagicMock
):
    mapper = CloudFlareMapper(mock_logger, settings=settings, client=mock_cf_client)
    host = settings.domains[0].target_domain
    assert isinstance(host, str)

    result = await mapper.sync(host, "manual")
    assert result is None
    mock_logger.info.assert_not_called()


@pytest.mark.asyncio
async def test_sync_with_non_subdomain(
    mock_logger: MagicMock, settings: Settings, mock_cf_client: MagicMock
):
    mapper = CloudFlareMapper(mock_logger, settings=settings, client=mock_cf_client)
    host = "nonexistent.example.ltd"

    result = await mapper.sync(host, "manual")
    assert result is None
    mock_logger.info.assert_not_called()


@pytest.mark.asyncio
async def test_sync_with_excluded_domain(
    mock_logger: MagicMock, settings: Settings, mock_cf_client: MagicMock
):
    settings.domains[0].excluded_sub_domains = ["excluded"]
    mapper = CloudFlareMapper(mock_logger, settings=settings, client=mock_cf_client)
    host = f"excluded.{settings.domains[0].name}"

    result = await mapper.sync(host, "manual")
    assert result is None
    mock_logger.info.assert_called_with(f"Ignoring {host}: Match excluded sub domain: excluded")


@pytest.mark.asyncio
async def test_sync_with_existing_record(
    mock_logger: MagicMock, settings: Settings, mock_cf_client: MagicMock
):
    mapper = CloudFlareMapper(mock_logger, settings=settings, client=mock_cf_client)
    host = settings.domains[0].name
    mapper.refresh_entries = False

    result = await mapper.sync(host, "manual")
    assert result is not None
    mock_logger.info.assert_called_with(f"Record {host} found. Not refreshing. Skipping...")


@pytest.mark.asyncio
async def test_sync_with_record_creation(
    mock_logger: MagicMock, settings: Settings, mock_cf_client: MagicMock
):
    mapper = CloudFlareMapper(mock_logger, settings=settings, client=mock_cf_client)
    host = "newsubdomain.region1.example.ltd"
    mock_cf_client.zones.dns_records.get.return_value = []

    # dry run
    result = await mapper.sync(host, "manual")
    mock_cf_client.zones.dns_records.post.assert_not_called()
    cast(MagicMock, mapper.logger.info).assert_called_once()

    with patch.object(mapper, "dry_run", False):
        result = await mapper.sync(host, "manual")
        assert result is not None
        mock_cf_client.zones.dns_records.post.assert_called_once()


@pytest.mark.asyncio
async def test_sync_with_record_update(
    mock_logger: MagicMock, settings: Settings, mock_cf_client: MagicMock
):
    mapper = CloudFlareMapper(mock_logger, settings=settings, client=mock_cf_client)
    host = f"subdomain{settings.domains[0].zone_id}.{settings.domains[0].name}"
    mapper.refresh_entries = True

    # dry run
    result = await mapper.sync(host, "manual")
    mock_cf_client.zones.dns_records.put.assert_not_called()
    cast(MagicMock, mapper.logger.info).assert_called_once()

    with patch.object(mapper, "dry_run", False):
        result = await mapper.sync(host, "manual")
        assert isinstance(result, DomainsModel)
        mock_cf_client.zones.dns_records.put.assert_called_once()


@pytest.mark.asyncio
async def test_sync_with_cloudflare_api_error(
    mock_logger: MagicMock, settings: Settings, mock_cf_client: MagicMock
):
    mapper = CloudFlareMapper(mock_logger, settings=settings, client=mock_cf_client)
    host = f"newsubdomain.{settings.domains[0].name}"

    mock_cf_client.zones.dns_records.post.side_effect = CloudFlareAPIError(1000, "API Error")
    with patch.object(mapper, "dry_run", False):
        result = await mapper.sync(host, "manual")
        assert result is None
        mock_logger.error.assert_called_with(f"Sync Error for {host}: API Error [Code 1000]")

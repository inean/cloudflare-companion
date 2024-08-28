from logging import Logger
from unittest.mock import AsyncMock, MagicMock, patch

import CloudFlare  # type: ignore
import pytest
from dns_synchub.mappers import CloudFlareMapper, Settings
from dns_synchub.settings import DomainsModel


@pytest.fixture
def settings():
    records: list[DomainsModel] = []
    for i in range(5):
        entry = DomainsModel(
            zone_id="zone_id",
            name=f"subdomain{i}",
            target_domain=f"target{i}.example.ltd",
            comment=f"Test comment {i}",
        )
        records.append(entry)

    return Settings(cf_token="token", domains=records)


@pytest.fixture
def mock_logger():
    return MagicMock(spec=Logger)


@pytest.fixture
def mock_cloudflare_client():
    cf = MagicMock()
    cf.zones.dns_records.get = MagicMock()
    cf.zones.dns_records.put = MagicMock()
    cf.zones.dns_records.post = MagicMock()
    return cf


def test_init(mock_logger: MagicMock, settings: Settings):
    mapper = CloudFlareMapper(mock_logger, settings=settings)
    assert mapper.dry_run == settings.dry_run
    assert mapper.rc_type == settings.rc_type
    assert mapper.refresh_entries == settings.refresh_entries
    assert mapper.domains == settings.domains
    assert mapper.tout_sec == settings.cf_timeout_seconds
    assert mapper.sync_sec == settings.cf_sync_seconds

    assert isinstance(mapper.client, CloudFlare.CloudFlare)
    mock_logger.debug.assert_called_once()


def test_init_with_client(mock_logger: MagicMock, settings: Settings):
    client = CloudFlare.CloudFlare()
    mapper = CloudFlareMapper(mock_logger, settings=settings, client=client)
    assert mapper.client == client
    mock_logger.debug.assert_not_called()


@pytest.mark.asyncio
async def test_call(mock_logger: MagicMock, settings: Settings, mock_cloudflare_client: MagicMock):
    mapper = CloudFlareMapper(mock_logger, settings=settings, client=mock_cloudflare_client)
    events = (["subdomain.example.ltd"], "manual")

    with patch.object(mapper, "sync", new_callable=AsyncMock) as mock_sync:
        await mapper(*events)
        mock_sync.assert_called_once_with("subdomain.example.ltd", "manual", settings.domains)


def test_get_records(mock_logger: MagicMock, settings: Settings, mock_cloudflare_client: MagicMock):
    mapper = CloudFlareMapper(mock_logger, settings=settings, client=mock_cloudflare_client)
    zone_id = "zone_id"
    name = "example.com"

    async def run_test():
        await mapper.get_records(zone_id, name)
        mock_cloudflare_client.zones.dns_records.get.assert_called_with(
            zone_id, params={"name": name}
        )

    asyncio.run(run_test())


def test_post_record(mock_logger: MagicMock, settings: Settings, mock_cloudflare_client: MagicMock):
    mapper = CloudFlareMapper(mock_logger, settings=settings, client=mock_cloudflare_client)
    zone_id = "zone_id"
    data = {"type": "A", "name": "example.com", "content": "1.2.3.4"}

    mapper.post_record(zone_id, data)
    mock_cloudflare_client.zones.dns_records.post.assert_called_with(zone_id, data=data)


def test_put_record(mock_logger: MagicMock, settings: Settings, mock_cloudflare_client: MagicMock):
    mapper = CloudFlareMapper(mock_logger, settings=settings, client=mock_cloudflare_client)
    zone_id = "zone_id"
    record_id = "record_id"
    data = {"type": "A", "name": "example.com", "content": "1.2.3.4"}

    mapper.put_record(zone_id, record_id, data)
    mock_cloudflare_client.zones.dns_records.put.assert_called_with(zone_id, record_id, data=data)


def test_sync(mock_logger: MagicMock, settings: Settings, mock_cloudflare_client: MagicMock):
    mapper = CloudFlareMapper(mock_logger, settings=settings, client=mock_cloudflare_client)
    name = "example.com"
    source = "source"
    domain_infos = settings.domains

    async def run_test():
        await mapper.sync(name, source, domain_infos)
        mock_logger.info.assert_called()

    asyncio.run(run_test())

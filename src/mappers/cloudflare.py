from __future__ import annotations

import asyncio

from CloudFlare import CloudFlare
from CloudFlare import exceptions as CloudFlareExceptions
from settings import DomainsModel, Settings
from typing_extensions import deprecated

from mappers import DataMapper, MapperConfig


class CloudFlareException(Exception):
    pass


class CloudFlareMapper(DataMapper[CloudFlare]):
    config: MapperConfig = {
        "delay_sync": 0,
        "max_retries": 5,
    }

    def __init__(self, logger, *, settings: Settings, client: CloudFlare | None = None):
        if client is None:
            assert settings.cf_token is not None
            client = CloudFlare(
                email=settings.cf_email,
                token=settings.cf_token,
                debug=settings.log_level.upper() == "VERBOSE",
            )
            logger.debug(f"CloudFlare API Mode: {'Scoped' if not settings.cf_email else 'Global'}")

        # Set up the client and logger
        self.client = client

        # Extract required settings
        self.dry_run = settings.dry_run
        self.rc_type = settings.rc_type
        self.refresh_entries = settings.refresh_entries
        self.domains = settings.domains

        # Initialize the parent class
        super(CloudFlareMapper, self).__init__(logger, settings=settings, client=client)

    async def __call__(self, names: list[str], source: str):
        result = []
        for name in names:
            result.append(await self.sync(name, source, self.domains))
        return result

    async def get_records(self, zone_id: str, name: str):
        for retry in range(self.config["max_retries"]):
            try:
                return self.client.zones.dns_records.get(zone_id, params={"name": name})
            except CloudFlareExceptions.CloudFlareAPIError as err:
                if "Rate limited" not in str(err):
                    raise err
                # Exponential backoff
                sleep_time = 2 ** (retry + 1)
                self.logger.warning(f"Max Rate limit reached. Retry in {sleep_time} seconds...")
                asyncio.sleep(sleep_time)
        raise CloudFlareException("Max retries exceeded")

    def post_record(self, zone_id, data):
        if self.dry_run:
            self.logger.info(f"DRY-RUN: POST to Cloudflare {zone_id}:, {data}")
        else:
            self.client.zones.dns_records.post(zone_id, data=data)
            self.logger.info(f"Created new record in zone {zone_id} with data {data}")

    def put_record(self, zone_id, record_id, data):
        if self.dry_run:
            self.logger.info(f"DRY-RUN: PUT to Cloudflare {zone_id}, {record_id}:, {data}")
        else:
            self.client.zones.dns_records.put(zone_id, record_id, data=data)
            self.logger.info(f"Updated record {record_id} in zone {zone_id} with data {data}")

    # Start Program to update the Cloudflare
    async def sync(self, name: str, source, domain_infos: list[DomainsModel]):
        def is_domain_excluded(logger, name, dom: DomainsModel):
            for sub_dom in dom.excluded_sub_domains:
                if f"{sub_dom}.{dom.name}" in name:
                    logger.info(f"Ignoring {name}: It falls until excluded sub domain: {sub_dom}")
                    return True
            return False

        ok = True
        for domain_info in domain_infos:
            # Don't update the domain if it's the same as the target domain, which sould be used on tunnel
            if name == domain_info.target_domain:
                continue
            # Skip if it's not a subdomain of the domain we're looking for
            if name.find(domain_info.name) < 0:
                continue
            # Skip if the domain is exclude list
            if is_domain_excluded(self.logger, name, domain_info):
                continue
            # Fetch the records for the domain, if any
            if (records := await self.get_records(domain_info.zone_id, name)) is None:
                ok = False
                continue
            # Prepare data for the new record
            data = {
                "type": self.rc_type,
                "name": name,
                "content": domain_info.target_domain,
                "ttl": int(domain_info.ttl),
                "proxied": domain_info.proxied,
                "comment": domain_info.comment,
            }
            try:
                # Update the record if it already exists
                if self.refresh_entries and len(records) > 0:
                    for record in records:
                        self.put_record(domain_info.zone_id, record["id"], data)
                # Create a new record if it doesn't exist yet
                else:
                    self.post_record(domain_info.zone_id, data)
            except CloudFlareExceptions.CloudFlareAPIError as ex:
                self.logger.error("** %s - %d %s" % (name, ex, ex))
                ok = False
        return ok

    # Start Program to update the Cloudflare
    @deprecated("Use update_zones instead")
    def point_domain(self, name, domain_infos: list[DomainsModel]):
        return asyncio.run(self.sync(name, domain_infos))

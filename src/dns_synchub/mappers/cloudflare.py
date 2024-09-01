from __future__ import annotations

import asyncio
from functools import partial, wraps
from logging import Logger
from typing import Any, Awaitable, Callable, cast

from CloudFlare import CloudFlare  # type: ignore
from CloudFlare import exceptions as CloudFlareExceptions  # type: ignore
from tenacity import (  # type: ignore
    AsyncRetrying,
    RetryCallState,
    RetryError,
    retry_if_exception_message,
    stop_after_attempt,
    wait_exponential,
)
from typing_extensions import override

from dns_synchub.mappers import Mapper
from dns_synchub.settings import DomainsModel, PollerSourceType, Settings


class CloudFlareException(Exception):
    pass


def dry_run(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    @wraps(func)
    async def wrapper(self: CloudFlareMapper, zone_id: str, *args: Any, **data: Any) -> Any:
        if self.dry_run:
            self.logger.info(f"DRY-RUN: {func.__name__} in zone {zone_id}:, {data}")
            return {**data, "zone_id": zone_id}
        return await func(self, zone_id, *args, **data)

    return wrapper


def retry(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    def log_before_sleep(logger, retry_state: RetryCallState):
        assert retry_state.next_action
        sleep_time = retry_state.next_action.sleep
        logger.warning(f"Max Rate limit reached. Retry in {sleep_time} seconds...")

    @wraps(func)
    async def wrapper(self: CloudFlareMapper, *args: Any, **kwargs: Any) -> Any:
        assert isinstance(self, CloudFlareMapper)

        retry = AsyncRetrying(
            stop=stop_after_attempt(self.config["stop"]),
            wait=wait_exponential(multiplier=self.config["wait"], max=self.tout_sec),
            retry=retry_if_exception_message(match="Rate limited"),
            before_sleep=partial(log_before_sleep, self.logger),
        )
        try:
            async for attempt_ctx in retry:
                with attempt_ctx:
                    try:
                        return await func(self, *args, **kwargs)
                    except Exception as err:
                        att = attempt_ctx.retry_state.attempt_number
                        self.logger.debug(f"CloduFlare {func.__name__} attempt {att} failed:{err}")
                        raise
        except RetryError as err:
            last_error = err.last_attempt.result()
            raise CloudFlareException("Operation failed") from last_error

    return wrapper


class CloudFlareMapper(Mapper[CloudFlare]):
    def __init__(self, logger: Logger, *, settings: Settings, client: CloudFlare | None = None):
        if client is None:
            assert settings.cf_token is not None
            client = CloudFlare(
                token=settings.cf_token,
                debug=settings.log_level.upper() == "VERBOSE",
            )
            logger.debug("CloudFlare Scoped API client started")

        self.tout_sec = settings.cf_timeout_seconds
        self.sync_sec = settings.cf_sync_seconds

        # Initialize the parent class
        super(CloudFlareMapper, self).__init__(logger, settings=settings, client=client)

    @override
    async def __call__(self, hosts: list[str], source: PollerSourceType):
        tasks = [asyncio.create_task(self.sync(host, source)) for host in hosts]
        try:
            _, pending = await asyncio.wait(tasks, timeout=self.tout_sec)
            if pending:
                for task in pending:
                    task.cancel()
                self.logger.warning("Timeout reached. Cancelling pending tasks...")
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            raise

    @retry
    async def get_records(self, zone_id: str, **filter: str) -> list[dict[str, Any]]:
        assert self.client is not None
        return await asyncio.to_thread(self.client.zones.dns_records.get, zone_id, params=filter)

    @dry_run
    @retry
    async def post_record(self, zone_id: str, **data: str) -> dict[str, Any]:
        assert self.client is not None
        result = await asyncio.to_thread(self.client.zones.dns_records.post, zone_id, data=data)
        self.logger.info(f"Created new record in zone {zone_id}: {result}")
        return result

    @dry_run
    @retry
    async def put_record(self, zone_id: str, record_id: str, **data: str) -> dict[str, Any]:
        assert self.client is not None
        result = await asyncio.to_thread(
            self.client.zones.dns_records.put, zone_id, record_id, data=data
        )
        self.logger.info(f"Updated record {record_id} in zone {zone_id} with data {data}")
        return result

    # Start Program to update the Cloudflare
    @override
    async def sync(self, host: str, source: PollerSourceType) -> DomainsModel | None:
        def is_domain_excluded(host: str, domain: DomainsModel):
            for sub_dom in domain.excluded_sub_domains:
                if f"{sub_dom}.{domain.name}" in host:
                    self.logger.info(f"Ignoring {host}: Match excluded sub domain: {sub_dom}")
                    return True
            return False

        for domain_info in self.domains:
            # Don't update the domain if it's the same as the target domain, which sould be used on tunnel
            if host == domain_info.target_domain:
                continue
            # Skip if it's not a subdomain of the domain we're looking for
            if host.find(domain_info.name) < 0:
                continue
            # Skip if the domain is in exclude list
            if is_domain_excluded(host, domain_info):
                continue
            # Skip if already present and refresh entries is not required
            records = await self.get_records(domain_info.zone_id, name=host)
            if records and not self.refresh_entries:
                assert len(records) == 1
                self.logger.info(f"Record {host} found. Not refreshing. Skipping...")
                return DomainsModel(**records.pop())
            # Prepare data for the new record
            data = cast(
                dict[str, str],
                {
                    "type": self.rc_type,
                    "name": host,
                    "content": domain_info.target_domain,
                    "ttl": str(domain_info.ttl) if domain_info.ttl is not None else "auto",
                    "proxied": str(domain_info.proxied),
                    "comment": domain_info.comment,
                    "tag": f"poller:{source}",
                },
            )
            result = None
            try:
                # Update the record if it already exists
                if records:
                    assert len(records) == 1
                    assert self.refresh_entries
                    result = await self.put_record(domain_info.zone_id, records.pop()["id"], **data)
                # Create a new record if it doesn't exist yet
                else:
                    result = await self.post_record(domain_info.zone_id, **data)
            except CloudFlareExceptions.CloudFlareAPIError as err:
                self.logger.error(f"Sync Error for {host}: {str(err)} [Code {int(err)}]")
            finally:
                return DomainsModel(**result) if result else None

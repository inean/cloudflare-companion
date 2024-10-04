from abc import ABC
from logging import Logger
from typing import (
    Generic,
    Protocol,
    TypedDict,
    TypeVar,
    runtime_checkable,
)

from dns_synchub.settings import Settings
from dns_synchub.telemetry import (
    TelemetryAttributes as Attrs,
    TelemetryConstants as Constants,
    TelemetrySpans as Spans,
)
from dns_synchub.tracer import StatusCode, telemetry_tracer
from dns_synchub.types import (
    Domains,
    EventSubscriber,
    EventSubscriberType,
    PollerSourceType,
)

T = TypeVar('T')  # Client backemd
E = TypeVar('E')  # Event type accepted
R = TypeVar('R')  # Result type


@runtime_checkable
class MapperProtocol(EventSubscriber[E], Protocol[E, R]):
    async def sync(self, data: E) -> list[R] | None: ...


class MapperConfig(TypedDict):
    wait: int
    """Factor to multiply the backoff time by"""
    stop: int
    """Max number of retries to attempt before exponential backoff fails"""
    delay: float
    """Delay in seconds before syncing mappings"""


class BaseMapper(ABC, MapperProtocol[E, R], Generic[E, R]):
    config: MapperConfig = {
        'stop': 3,
        'wait': 4,
        'delay': 0,
    }

    def __init__(self, logger: Logger):
        self.logger = logger
        self.tracer = telemetry_tracer().get_tracer('otel.instrumentation.mappers')


class Mapper(BaseMapper[E, Domains], Generic[E, T]):
    def __init__(self, logger: Logger, *, settings: Settings, client: T | None = None):
        # init client
        self._client: T | None = client

        # Domain defaults
        self.dry_run = settings.dry_run
        self.rc_type = settings.rc_type
        self.refresh_entries = settings.refresh_entries

        # Computed from settings
        self.domains = settings.domains
        self.included_hosts = settings.included_hosts
        self.excluded_hosts = settings.excluded_hosts

        super().__init__(logger)

    @property
    def client(self) -> T:
        assert self._client is not None, 'Client is not initialized'
        return self._client


from dns_synchub.mappers.cloudflare import CloudFlareMapper  # noqa: E402

__all__ = [
    'CloudFlareMapper',
    'Attrs',
    'Constants',
    'Spans',
    'EventSubscriberType',
    'PollerSourceType',
    'StatusCode',
]

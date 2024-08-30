import logging
from abc import ABC, abstractmethod
from typing import Generic, TypedDict, TypeVar

from dns_synchub.settings import DomainsModel, PollerSourceType, Settings


class MapperConfig(TypedDict):
    wait: int
    """Factor to multiply the backoff time by"""
    stop: int
    """Max number of retries to attempt before exponential backoff fails"""
    delay: float
    """Delay in seconds before syncing mappings"""


class BaseMapper(ABC):
    config: MapperConfig = {
        "stop": 3,
        "wait": 4,
        "delay": 0,
    }

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.mappings = {}

    @abstractmethod
    async def __call__(self, hosts: list[str], source: PollerSourceType): ...

    @abstractmethod
    async def sync(self, host: str, source: PollerSourceType) -> DomainsModel | None: ...


T = TypeVar("T")


class Mapper(BaseMapper, Generic[T]):
    def __init__(self, logger: logging.Logger, *, settings: Settings, client: T | None = None):
        # init client
        self.client: T | None = client

        # Domain defaults
        self.dry_run = settings.dry_run
        self.rc_type = settings.rc_type
        self.refresh_entries = settings.refresh_entries

        # Computed from settings
        self.domains = settings.domains
        self.included_hosts = settings.included_hosts
        self.excluded_hosts = settings.excluded_hosts

        super(Mapper, self).__init__(logger)


from dns_synchub.mappers.cloudflare import CloudFlareMapper  # noqa: E402

__all__ = ["CloudFlareMapper"]

import logging
from abc import ABC, abstractmethod
from typing import Any, Generic, TypedDict, TypeVar

from dns_synchub.settings import Settings


class MapperConfig(TypedDict, total=False):
    delay_sync: float
    """Delay in seconds before syncing mappings"""
    max_retries: int
    """Max number of retries to attempt before exponential backoff fails"""


class Mapper(ABC):
    config: MapperConfig = {
        "delay_sync": 0,
    }

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.mappings = {}

    @abstractmethod
    def __call__(self, data): ...

    @abstractmethod
    async def sync(self): ...


T = TypeVar("T")


class DataMapper(Mapper, Generic[T]):
    def __init__(self, logger, *, settings: Settings, client: Any):
        super(DataMapper, self).__init__(logger)

        # init client
        self.client: T = client

        # Computed from settings
        self.domains = settings.domains
        self.included_hosts = settings.included_hosts
        self.excluded_hosts = settings.excluded_hosts


from dns_synchub.mappers.cloudflare import CloudFlareMapper  # noqa: E402

__all__ = ["CloudFlareMapper"]

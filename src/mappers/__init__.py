import asyncio
import logging
from abc import abstractmethod
from typing import TypedDict

from events import EventEmitter
from internal._singleton import Singleton
from settings import Settings


class MapperConfig(TypedDict, total=False):
    delay_sync: float
    """Delay in seconds before syncing mappings"""
    max_retries: int
    """Max number of retries to attempt before exponential backoff fails"""


class Mapper(EventEmitter):
    config: MapperConfig = {
        "delay_sync": 0,
    }

    def __init__(self, logger: logging.Logger, *, settings: Settings):
        super(Mapper, self).__init__(logger)
        self.logger = logger
        self.mappings = {}
        self.domains = settings.domains

    async def put(self, name, value, wait_for: float = 0):
        if wait_for > 0:
            self.logger.info(f"Wait {wait_for} secs before adding mapping {name} -> {value}")
            await asyncio.sleep(wait_for)
        self.mappings[name] = value
        self.logger.info(f"Added mapping {name} -> {value}")

    @abstractmethod
    async def sync(self): ...


class DataMapper(Mapper, metaclass=Singleton): ...


from mappers.cloudflare import CloudFlareMapper  # noqa: E402

__all__ = ["CloudFlareMapper"]

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, ClassVar, Generic, TypeVar

from events import EventEmitter
from settings import Settings
from typing_extensions import override


class PollerSource(Enum):
    MANUAL = "manual"
    DOCKER = "docker"
    TRAEFIK = "traefik"


class Poller(ABC):
    source: ClassVar[PollerSource]

    def __init__(self, logger: logging.Logger):
        """
        Initializes the Poller with a logger and a client.

        Args:
            logger (logging.Logger): The logger instance for logging.
            client (Any): The client instance for making requests.
        """
        self.logger = logger
        self.events = EventEmitter[Poller](logger)

    # Poller methods
    @abstractmethod
    async def fetch(self):
        """
        Abstract method to fetch data.
        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    async def _watch(self, *, timeout: float | None = None):
        """
        Abstract method to watch for changes. This method must emit signals
        whenever new data is available.

        Args:
            timeout (float | None): The timeout duration in seconds. If None,
                                    the method will wait indefinitely.

        Must be implemented by subclasses.
        """
        pass

    async def run(self, timeout: float | None = None):
        """
        Starts the Poller and watches for changes.

        Args:
            timeout (float | None): The timeout duration in seconds. If None,
                                    the method will wait indefinitely.
        """
        name = self.__class__.__name__
        self.logger.info(f"Starting {name}: Watching Traefik every {self.poll_sec}")
        # self.fetch is called for the firstime, whehever a a client subscribe to
        # this poller, so there's no need to initialy fetch data
        if timeout:
            until = datetime.now() + timedelta(seconds=timeout)
            self.logger.debug(f"{name}: Stop programed at {until}")
            try:
                await asyncio.wait_for(self._watch, timeout)
            except asyncio.TimeoutError:
                self.logger.info(f"{name}: Run timeout '{until}'reached")
        else:
            # Run indefinitely.
            await self._watch()

    # Event related methods
    @override
    async def subscribe(self, callback: Callable):
        # Fetch data and store locally if required
        self._subscribers or self.set_data(await self.fetch())
        # Register subscriber
        super(Poller, self).subscribe(callback)


T = TypeVar("T")


class DataPoller(Poller, Generic[T]):
    def __init__(self, logger, *, settings: Settings, client: Any):
        super(DataPoller, self).__init__(logger)

        # init client
        self.client: T = client

        # Computed from settings
        self.included_hosts = settings.traefik_included_hosts
        self.excluded_hosts = settings.traefik_excluded_hosts


# ruff: noqa: E402

from pollers.docker import DockerPoller
from pollers.traefik import TraefikPoller

# run: enable

__all__ = ["TraefikPoller", "DockerPoller"]

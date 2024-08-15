from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Generic, Literal, TypedDict, TypeVar
from weakref import ref as WeakRef

from events import EventEmitter
from settings import Settings
from typing_extensions import override


class PollerEventEmitter(EventEmitter[Callable]):
    def __init__(self, logger: logging.Logger, *, poller: Poller):
        self.poller = WeakRef(poller)
        super(PollerEventEmitter, self).__init__(logger, name=poller.config["source"])

    # Event related methods
    @override
    async def subscribe(self, callback: Callable, backoff: float = 0):
        # Register subscriber
        await super(PollerEventEmitter, self).subscribe(callback, backoff=backoff)
        # Fetch data and store locally if required
        self.set_data(await self.poller().fetch(), callback=callback)


PollerSource = Literal["manual", "docker", "traefik"]


class PollerConfig(TypedDict, total=False):
    max_retries: int
    """Max number of retries to attempt before exponential backoff fails"""
    backoff_factor: int
    """Factor to multiply the backoff time by"""
    source: PollerSource
    """The source of the poller"""


class Poller(ABC):
    config: PollerConfig = {
        "max_retries": 0,
        "backoff_factor": 4,
    }

    def __init__(self, logger: logging.Logger):
        """
        Initializes the Poller with a logger and a client.

        Args:
            logger (logging.Logger): The logger instance for logging.
            client (Any): The client instance for making requests.
        """
        self.logger = logger
        self.events = PollerEventEmitter(logger, poller=self)

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
        self.logger.info(f"Starting {name}: Watching for changes")
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

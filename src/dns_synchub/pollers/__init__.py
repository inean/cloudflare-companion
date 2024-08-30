from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from logging import Logger
from typing import Any, Callable, Generic, TypedDict, TypeVar
from weakref import ref as WeakRef

from typing_extensions import override

from dns_synchub.events import EventEmitter
from dns_synchub.settings import PollerSourceType, Settings


class PollerConfig(TypedDict):
    stop: int
    """Max number of retries to attempt before exponential backoff fails"""
    wait: int
    """Factor to multiply the backoff time by"""
    source: PollerSourceType
    """The source of the poller"""


class PollerEvents(EventEmitter[Callable[..., Any]]):
    def __init__(self, logger: Logger, *, poller: Poller[Any]):
        self.poller = WeakRef(poller)
        assert "source" in poller.config
        super(PollerEvents, self).__init__(logger, name=poller.config["source"])

    # Event related methods
    @override
    async def subscribe(self, callback: Callable[..., Any], backoff: float = 0):
        # Register subscriber
        await super(PollerEvents, self).subscribe(callback, backoff=backoff)
        # Fetch data and store locally if required
        self.set_data(await self.poller().fetch(), callback=callback)  # type: ignore


class BasePoller(ABC):
    config: PollerConfig = {
        "stop": 3,
        "wait": 4,
        "source": "manual",
    }

    def __init__(self, logger: Logger):
        """
        Initializes the Poller with a logger and a client.

        Args:
            logger (Logger): The logger instance for logging.
            client (Any): The client instance for making requests.
        """
        self.logger = logger

    # Poller methods
    @abstractmethod
    async def fetch(self) -> tuple[list[str], PollerSourceType]:
        """
        Abstract method to fetch data.
        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    async def _watch(self):
        """
        Abstract method to watch for changes. This method must emit signals
        whenever new data is available.

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
        watch_task = asyncio.create_task(self._watch())
        if timeout is not None:
            until = datetime.now() + timedelta(seconds=timeout)
            self.logger.debug(f"{name}: Stop programed at {until}")
        try:
            await asyncio.wait_for(watch_task, timeout)
        except asyncio.TimeoutError:
            self.logger.info(f"{name}: Run timeout '{timeout}s' reached")
        except asyncio.CancelledError:
            self.logger.info(f"{name}: Run was cancelled")
        finally:
            watch_task.cancel()
            try:
                await watch_task
            except asyncio.CancelledError:
                self.logger.info(f"{name}: Watch task was cancelled")


T = TypeVar("T")


class Poller(BasePoller, Generic[T]):
    def __init__(self, logger: Logger, *, settings: Settings, client: T | None = None):
        super(Poller, self).__init__(logger)

        # init client
        self._client: T | None = client

        self.events = PollerEvents(logger, poller=self)

        # Computed from settings
        self.included_hosts = settings.included_hosts
        self.excluded_hosts = settings.excluded_hosts

    @property
    def client(self) -> T:
        assert self._client is not None, "Client is not initialized"
        return self._client

    @abstractmethod
    async def fetch(self) -> tuple[list[str], PollerSourceType]:
        """
        Abstract method to fetch data.
        Must be implemented by subclasses.
        """
        pass


# ruff: noqa: E402

from dns_synchub.pollers.docker import DockerPoller
from dns_synchub.pollers.traefik import TraefikPoller

# run: enable

__all__ = ["TraefikPoller", "DockerPoller"]

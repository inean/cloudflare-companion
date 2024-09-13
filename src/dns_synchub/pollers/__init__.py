from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from logging import Logger
from typing import (
    Any,
    ClassVar,
    Generic,
    NotRequired,
    Protocol,
    TypedDict,
    TypeVar,
    runtime_checkable,
)
from weakref import ref as WeakRef

from typing_extensions import override

from dns_synchub.events import EventEmitter
from dns_synchub.settings import Settings
from dns_synchub.types import EventSubscriberType, PollerSourceType

T = TypeVar('T')


@dataclass
class PollerData(Generic[T]):
    hosts: list[str]
    source: T


@runtime_checkable
class PollerProtocol(Protocol[T]):
    events: EventEmitter[PollerData[T]]

    async def fetch(self) -> PollerData[T]: ...

    async def start(self, timeout: float | None = None) -> None: ...

    async def stop(self) -> None: ...


class PollerConfig(TypedDict, Generic[T]):
    stop: int
    """Max number of retries to attempt before exponential backoff fails"""
    wait: int
    """Factor to multiply the backoff time by"""
    source: NotRequired[T]
    """The source of the poller"""


class BasePoller(ABC, PollerProtocol[T], Generic[T]):
    # Generic Typed ClassVars are not supported.
    # See https://github.com/python/typing/discussions/1424 for
    # open discussion about support
    config: ClassVar[PollerConfig[T]] = {  # type: ignore
        'stop': 3,
        'wait': 4,
    }

    def __init__(self, logger: Logger):
        """
        Initializes the Poller with a logger and a client.

        Args:
            logger (Logger): The logger instance for logging.
            client (Any): The client instance for making requests.
        """
        self.logger = logger
        self._wtask: asyncio.Task[None]

    @abstractmethod
    async def _watch(self) -> None:
        """
        Abstract method to watch for changes. This method must emit signals
        whenever new data is available.

        Must be implemented by subclasses.
        """
        pass

    async def start(self, timeout: float | None = None) -> None:
        """
        Starts the Poller and watches for changes.

        Args:
            timeout (float | None): The timeout duration in seconds. If None,
                                    the method will wait indefinitely.
        """
        name = self.__class__.__name__
        self.logger.info(f'Starting {name}: Watching for changes')
        # self.fetch is called for the firstime, whehever a a client subscribe to
        # this poller, so there's no need to initialy fetch data
        self._wtask = asyncio.create_task(self._watch())
        if timeout is not None:
            until = datetime.now() + timedelta(seconds=timeout)
            self.logger.debug(f'{name}: Stop programed at {until}')
        try:
            await asyncio.wait_for(self._wtask, timeout)
        except TimeoutError:
            self.logger.info(f"{name}: Run timeout '{timeout}s' reached")
        except asyncio.CancelledError:
            self.logger.info(f'{name}: Run was cancelled')
        finally:
            await self.stop()

    async def stop(self) -> None:
        name = self.__class__.__name__
        if self._wtask and not self._wtask.done():
            self.logger.info(f'Stopping {name}: Cancelling watch task')
            self._wtask.cancel()
            try:
                await self._wtask
            except asyncio.CancelledError:
                self.logger.info(f'{name}: Watch task was cancelled')


class PollerEventEmitter(EventEmitter[PollerData[PollerSourceType]]):
    def __init__(self, logger: Logger, *, poller: Poller[Any]):
        assert 'source' in poller.config
        self.poller = WeakRef(poller)
        super().__init__(logger, origin=poller.config['source'])

    # Event related methods
    @override
    async def subscribe(
        self, callback: EventSubscriberType[PollerData[PollerSourceType]], backoff: float = 0
    ) -> None:
        # Register subscriber
        await super().subscribe(callback, backoff=backoff)
        # Fetch data and store locally if required
        if poller := self.poller():
            self.set_data(await poller.fetch(), callback=callback)


class Poller(BasePoller[PollerSourceType], Generic[T]):
    def __init__(self, logger: Logger, *, settings: Settings, client: T | None = None):
        # init client
        self._client: T | None = client

        self.events = PollerEventEmitter(logger, poller=self)

        # Computed from settings
        self.included_hosts = settings.included_hosts
        self.excluded_hosts = settings.excluded_hosts

        super().__init__(logger)

    @property
    def client(self) -> T:
        assert self._client is not None, 'Client is not initialized'
        return self._client


# ruff: noqa: E402

from dns_synchub.pollers.docker import DockerPoller
from dns_synchub.pollers.traefik import TraefikPoller

# ruff: enable

__all__ = ['TraefikPoller', 'DockerPoller']

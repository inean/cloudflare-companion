import asyncio
from abc import ABC, abstractmethod
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
    final,
    runtime_checkable,
)
from weakref import ref as WeakRef

from typing_extensions import override

from dns_synchub.events import EventEmitter
from dns_synchub.events.types import EventSubscriberType
from dns_synchub.settings import Settings
from dns_synchub.telemetry_constants import (
    TelemetryAttributes as Attrs,
    TelemetryConstants as Constants,
    TelemetrySpans as Spans,
)
from dns_synchub.tracer import StatusCode, telemetry_tracer

from .types import PollerSourceType

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
    #
    # See https://github.com/python/typing/discussions/1424 for details
    #
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
        self.tracer = telemetry_tracer().get_tracer('otel.instrumentation.pollers')
        self._wtask: asyncio.Task[None]

    @abstractmethod
    async def _watch(self) -> None:
        """
        Abstract method to watch for changes. This method must emit signals
        whenever new data is available.

        Must be implemented by subclasses.
        """
        pass

    @final
    async def start(self, timeout: float | None = None) -> None:
        """
        Starts the Poller and watches for changes.

        Args:
            timeout (float | None): The timeout duration in seconds. If None,
                                    the method will wait indefinitely.
        """
        name = self.__class__.__name__

        with self.tracer.start_as_current_span(
            Spans.POLLER_START,
            attributes={
                Attrs.POLLER_CLASS: name,
                Attrs.TIMEOUT_VALUE: timeout or Constants.TIMEOUT_ENDLESS,
            },
        ) as span:
            self.logger.info(f'Starting {name}: Watching for changes')
            # self.fetch is called for the firstime, whehever a a client subscribe to
            # this poller, so there's no need to initially fetch data
            self._wtask = asyncio.create_task(self._watch())
            if timeout is not None:
                until = datetime.now() + timedelta(seconds=timeout)
                span.set_attribute(Attrs.TIMEOUT_STOP_AT, f'{until}')
                self.logger.debug(f'{name}: Stop programmed at {until}')
            try:
                await asyncio.wait_for(self._wtask, timeout)
            except asyncio.CancelledError:
                span.set_attribute(Attrs.STATE_CANCELLED, True)
                self.logger.info(f'{name}: Run was cancelled')
            except TimeoutError:
                span.set_attribute(Attrs.TIMEOUT_REACHED, True)
                self.logger.info(f"{name}: Run timeout '{timeout}s' reached")
            finally:
                await self.stop()

    @final
    async def stop(self) -> None:
        name = self.__class__.__name__
        with self.tracer.start_as_current_span(
            Spans.POLLER_STOP,
            attributes={
                Attrs.POLLER_CLASS: name,
            },
        ) as span:
            span.set_attribute(Attrs.STATE_RUNNING, False)
            if self._wtask and not self._wtask.done():
                span.set_attribute(Attrs.STATE_RUNNING, True)
                self.logger.info(f'Stopping {name}: Cancelling watch task')
                self._wtask.cancel()
                try:
                    with self.tracer.start_as_current_span(Spans.ASYNCIO_CANCEL):
                        await self._wtask
                except asyncio.CancelledError:
                    span.add_event(Attrs.STATE_CANCELLED)
                    self.logger.info(f'{name}: Watch task was cancelled')


class PollerEventEmitter(EventEmitter[PollerData[PollerSourceType]]):
    def __init__(self, logger: Logger, *, poller: 'Poller[Any]'):
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

__all__ = ['TraefikPoller', 'DockerPoller', 'StatusCode']

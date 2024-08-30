from __future__ import annotations

import asyncio
import time
from logging import Logger
from typing import (
    Callable,
    Coroutine,
    Generic,
    Protocol,
    TypeAlias,
    TypeVar,
)

from dns_synchub.settings import PollerSourceType

PollerSourceEvent: TypeAlias = tuple[list[str], PollerSourceType]


class EventSubscriber(Protocol):
    def __call__(self, hosts: list[str], source: PollerSourceType) -> None: ...


class AsyncEventSubscriber(Protocol):
    async def __call__(self, hosts: list[str], source: PollerSourceType) -> None: ...


T = TypeVar(
    "T",
    bound=Callable[[list[str], PollerSourceType], None]
    | Coroutine[None, None, None]
    | EventSubscriber
    | AsyncEventSubscriber,
)

EventSubscriberType = tuple[asyncio.Queue[PollerSourceEvent], float, float]


class EventEmitter(Generic[T]):
    def __init__(self, logger: Logger, *, name: str):
        self.logger = logger
        self.logger_name = name
        # Subscribers
        self._subscribers: dict[T, EventSubscriberType] = {}

    def __iter__(self):
        return iter(self._subscribers.values())

    def __len__(self) -> int:
        return len(self._subscribers)

    async def subscribe(self, callback: T, backoff: float = 0):
        """
        Subscribes to events from this Poller.

        Args:
            callback (Callable): The callback function to be called when an event is emitted.
            backoff (float): The backoff time in seconds to wait before calling the callback again.
        """
        # Check if callback is already subscribed
        assert callback not in self._subscribers
        assert callable(callback)
        # Register subscriber
        self._subscribers[callback] = (asyncio.Queue(), backoff, time.time())

    def unsubscribe(self, callback: T):
        """
        Unsubscribes from events.

        Args:
            callback (Callable): The callback function to be removed from subscribers.
        """
        self._subscribers.pop(callback, None)

    async def emit(self, timeout: float | None = None):
        """
        Triggers an event and notifies all subscribers.
        Calls each subscriber's callback with the data.
        """

        async def invoke(
            callback: T,
            queue: asyncio.Queue[PollerSourceEvent],
            backoff: float,
            last_called: float,
        ) -> tuple[T, EventSubscriberType]:
            while not queue.empty():
                current_time = time.time()
                if current_time - last_called >= backoff:
                    # Get callback function
                    func: T = getattr(callback, "__call__", callback)
                    assert callable(func)
                    # Get data from queue
                    data: PollerSourceEvent = await queue.get()
                    # Invoke
                    if asyncio.iscoroutinefunction(func):
                        await func(*data)
                    else:
                        func(*data)
                else:
                    # Wait for backoff time and try emit again
                    await asyncio.sleep(backoff - (current_time - last_called))
            return callback, (queue, backoff, last_called)

        tasks: list[asyncio.Task[tuple[T, EventSubscriberType]]] = []
        for callback, args in self._subscribers.items():
            task = asyncio.create_task(invoke(callback, *args))
            tasks.append(task)
        try:
            # Await for tasks to complete
            for task in asyncio.as_completed(tasks, timeout=timeout):
                callback, data = await task
                self._subscribers[callback] = data

        except asyncio.TimeoutError:
            self.logger.warning(f"{self.logger_name}: Emit timeout reached.")
            # Cancel all tasks
            [task.cancel() for task in tasks]
            asyncio.gather(*tasks, return_exceptions=True)
            pass

    # Data related methods
    def set_data(self, data: PollerSourceEvent, *, callback: T | None = None):
        if callback is None:
            for queue, _, _ in self._subscribers.values():
                queue.put_nowait(data)
            return
        assert callback in self._subscribers
        queue, _, _ = self._subscribers[callback]
        queue.put_nowait(data)

    def has_data(self, callback: T):
        return callback in self._subscribers and not self._subscribers[callback][0].empty()

    def get_data(self, callback: T) -> PollerSourceEvent:
        queue, _, _ = self._subscribers[callback]
        return queue.get_nowait()

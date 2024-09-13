import asyncio
from collections.abc import Iterator
from logging import Logger
import time
from typing import (
    Generic,
    TypeVar,
)

from dns_synchub.types import (
    Event,
    EventSubscriber,
    EventSubscriberDataType,
    EventSubscriberType,
)

T_co = TypeVar('T_co')


class EventEmitter(Generic[T_co]):
    def __init__(self, logger: Logger, *, origin: str):
        self.logger = logger
        self.origin = origin
        # Subscribers
        self._subscribers: dict[EventSubscriberType[T_co], EventSubscriberDataType[T_co]] = {}

    def __iter__(self) -> Iterator[EventSubscriberDataType[T_co]]:
        return iter(self._subscribers.values())

    def __len__(self) -> int:
        return len(self._subscribers)

    async def subscribe(self, callback: EventSubscriberType[T_co], backoff: float = 0) -> None:
        # Check if callback is already subscribed
        assert callback not in self._subscribers
        # Register subscriber
        self._subscribers[callback] = (asyncio.Queue[Event[T_co]](), backoff, time.time())

    def unsubscribe(self, callback: EventSubscriberType[T_co]) -> None:
        self._subscribers.pop(callback, None)

    async def emit(self, timeout: float | None = None) -> None:
        async def invoke(
            callback: EventSubscriberType[T_co],
            data: EventSubscriberDataType[T_co],
        ) -> tuple[EventSubscriberType[T_co], EventSubscriberDataType[T_co]]:
            # Unpack data
            queue, backoff, last_called = data
            # Emit data until queue is empty
            while not queue.empty():
                # Wait for backoff time
                await asyncio.sleep(max(0, backoff - (time.time() - last_called)))
                # Get callback function
                func = callback
                if isinstance(callback, EventSubscriber):
                    func = callback.__call__
                assert callable(func)
                # Get data from queue
                event: Event[T_co] = await queue.get()
                # Invoke
                assert asyncio.iscoroutinefunction(func)
                await func(event)
                # Update last called time
                last_called = time.time()

            return callback, (queue, backoff, last_called)

        tasks = []
        for callback, args in self._subscribers.items():
            task = asyncio.create_task(invoke(callback, args))
            tasks.append(task)
        try:
            # Await for tasks to complete
            for completed in asyncio.as_completed(tasks, timeout=timeout):
                callback, data = await completed
                self._subscribers[callback] = data
        except TimeoutError:
            self.logger.warning(f'{self.origin}: Emit timeout reached.')
            # Cancel all tasks
            [task.cancel() for task in tasks]
            asyncio.gather(*tasks, return_exceptions=True)

    # Data related methods
    def set_data(self, data: T_co, *, callback: EventSubscriberType[T_co] | None = None) -> None:
        event = Event[T_co](data=data)
        if callback:
            assert callback in self._subscribers
            queue, _, _ = self._subscribers[callback]
            queue.put_nowait(event)
        else:
            # Broadcast data to all subscribers
            for queue, _, _ in self._subscribers.values():
                queue.put_nowait(event)

    def has_data(self, callback: EventSubscriberType[T_co]) -> bool:
        return callback in self._subscribers and not self._subscribers[callback][0].empty()

    def get_data(self, callback: EventSubscriberType[T_co]) -> T_co | None:
        queue, _, _ = self._subscribers[callback]
        event = queue.get_nowait()
        return event.data if event else None

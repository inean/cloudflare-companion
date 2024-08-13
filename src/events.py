from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Iterator
from typing import Generic, TypeVar

T = TypeVar("T", bound=Callable)


class EventEmitter(Generic[T]):
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self._subscribers: dict[T, tuple] = {}

    def __iter__(self) -> Iterator[tuple[T, tuple]]:
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
        # Register subscriber
        assert callback not in self._subscribers
        assert callable(callback)
        self._subscribers.setdefault(callback, (asyncio.Queue(), backoff, time.time()))

    def unsubscribe(self, callback: T):
        """
        Unsubscribes from events.

        Args:
            callback (Callable): The callback function to be removed from subscribers.
        """
        self._subscribers.pop(callback, None)

    async def emit(self, timeout: float = 0):
        """
        Triggers an event and notifies all subscribers.
        Calls each subscriber's callback with the data.
        """

        async def invoke(callback: T, queue: asyncio.Queue, backoff, last_called):
            while not queue.empty():
                current_time = time.time()
                if current_time - last_called >= backoff:
                    data = await queue.get()
                    if asyncio.iscoroutinefunction(callback):
                        await callback(data)
                    else:
                        assert callable(callback)
                        callback(data)
                    # Update last called time
                    return queue, backoff, current_time
                else:
                    # Wait for backoff time and try emit again
                    await asyncio.sleep(backoff - (current_time - last_called))
            return callback, (queue, backoff, last_called)

        tasks = []
        for callback, (queue, backoff, last_called) in self._subscribers.items():
            task = asyncio.create_task(invoke(callback, queue, backoff, last_called))
            tasks.append(task)
        try:
            # Await for tasks to complete
            for task in asyncio.as_completed(tasks, timeout=timeout):
                callback, data = await task
                self._subscribers[callback] = data
        except asyncio.TimeoutError:
            self.logger.warning("Emit timeout reached.")
            pass

    # Data related methods
    def set_data(self, data):
        """
        Sets the data for all subscribers.

        Args:
            data: The data to be set for subscribers.
        """
        for queue, _, _ in self._subscribers.values():
            queue.put_nowait(data)

    def has_data(self, callback: Callable):
        """
        Checks if there is data available for a specific subscriber.

        Args:
            callback (Callable): The callback function to check for data.

        Returns:
            bool: True if there is data available, False otherwise.
        """
        return callback in self._subscribers and not self._subscribers[callback][0].empty()

    async def get_data(self, callback: Callable):
        """
        Gets the data for a specific subscriber.

        Args:
            callback (Callable): The callback function to get data for.

        Returns:
            The data for the specified callback.
        """
        if callback in self._subscribers:
            return await self._subscribers[callback][0].get()

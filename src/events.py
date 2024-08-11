from __future__ import annotations

import asyncio
from collections.abc import Callable


class EventEmitter:
    def __init__(self):
        self._subscribers = {}

    async def subscribe(self, callback: Callable):
        """
        Subscribes to events from this Poller.

        Args:
            callback (Callable): The callback function to be called when an event is emitted.
        """
        # Register subscriber
        self._subscribers.setdefault(callback, asyncio.Queue())

    def unsubscribe(self, callback: Callable):
        """
        Unsubscribes from events.

        Args:
            callback (Callable): The callback function to be removed from subscribers.
        """
        self._subscribers.pop(callback, None)

    async def emit(self):
        """
        Triggers an event and notifies all subscribers.
        Calls each subscriber's callback with the data.
        """
        for callback, queue in self._subscribers.items():
            while not queue.empty():
                data = await queue.get()
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)

    # Data related methods
    def set_data(self, data):
        """
        Sets the data for all subscribers.

        Args:
            data: The data to be set for subscribers.
        """
        for queue in self._subscribers.values():
            queue.put_nowait(data)

    def has_data(self, callback: Callable):
        """
        Checks if there is data available for a specific subscriber.

        Args:
            callback (Callable): The callback function to check for data.

        Returns:
            bool: True if there is data available, False otherwise.
        """
        return callback in self._subscribers and not self._subscribers[callback].empty()

    async def get_data(self, callback: Callable):
        """
        Gets the data for a specific subscriber.

        Args:
            callback (Callable): The callback function to get data for.

        Returns:
            The data for the specified callback.
        """
        if callback in self._subscribers:
            return await self._subscribers[callback].get()

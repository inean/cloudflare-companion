from __future__ import annotations

import asyncio
import logging

from .events import EventEmitter
from .mappers import Mapper
from .pollers import Poller, PollerSource


class DataManager:
    def __init__(self, *, logger: logging.Logger):
        self.logger = logger
        self.tasks: list[asyncio.Task] = []

        # Subscribers
        self.pollers: set[tuple[Poller, float]] = set()
        self.mappers: EventEmitter[Mapper] = EventEmitter(logger, name="Manager")

        # Data
        self.data: dict[PollerSource, list[str]] = {}

    async def __call__(self, names: list[str], source: PollerSource):
        # Store new data for mappers in each mappers queue
        self.mappers.set_data((names, source))
        # Combine data previously received from pollers
        self._combine_data({source: names})
        await self.mappers.emit()

    def _combine_data(self, data: dict[PollerSource, list[str]]) -> dict[PollerSource, list[str]]:
        """Combine data from multiple pollers."""
        for source, values in data.items():
            assert isinstance(values, list)
            self.data.setdefault(source, [])
            self.data[source].extend(values)
            self.data[source] = list(set(self.data[source]))

    def add_poller(self, poller: Poller, backoff: float = 0):
        """Add a DataPoller to the manager."""
        assert not any(poller == p for p, _ in self.pollers)
        self.pollers.add((poller, backoff))

    async def add_mapper(self, mapper: Mapper, backoff: float = 0):
        """Add a Mapper to the manager."""
        await self.mappers.subscribe(mapper, backoff=backoff)

    async def start(self, timeout: float | None = None):
        """Start all pollers by fetching initial data and subscribing to events."""
        assert len(self.tasks) == 0
        # Loop pollers
        for poller, backoff in self.pollers:
            # Register itelf to be called when new data is available
            await poller.events.subscribe(self, backoff=backoff)
            # Ask poller to start monitoring data
            self.tasks.append(asyncio.create_task(poller.run(timeout=timeout)))
        # Add mappers emission to tasks that mast run concurrently
        if len(self.mappers) > 0:
            self.tasks.append(asyncio.create_task(self.mappers.emit(timeout=timeout)))
        try:
            # wait until timeout is reached or tasks are canceled
            await asyncio.gather(*self.tasks)
        except asyncio.CancelledError:
            # Gracefully stop monitoring
            await self.stop()
        finally:
            # Clear tasks
            self.tasks.clear()

    async def stop(self):
        """Unsubscribe all pollers from their event systems."""
        # This could be extended to stop any running background tasks if needed
        if pending := [task for task in self.tasks if task.cancel()]:
            self.logger.info("Stopping running pollers...")
            await asyncio.gather(*pending, return_exceptions=True)
        self.tasks.clear()

    def aggregate_data(self):
        """Aggregate and return the latest data from all pollers."""
        for poller, _ in self.pollers:
            try:
                names, source = poller.events.get_data()
                self._combine_data({source: names})
            except asyncio.QueueEmpty:
                pass
        # Return the combined data
        return self.data

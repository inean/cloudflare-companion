from __future__ import annotations

import asyncio
import logging

from events import EventEmitter
from mappers import Mapper
from pollers import Poller


class DataManager:
    def __init__(self, *, logger: logging.Logger):
        self.tasks = []
        self.logger = logger

        # Subscribers
        self.pollers: set[tuple[Poller, float]] = set()
        self.mappers: EventEmitter[Mapper] = EventEmitter(logger)

    def __call__(self, data):
        # Data can come from pollers or mappers
        raise NotImplementedError

    def _combine_data(self, all_data):
        """Combine data from multiple pollers. Customize as needed."""
        combined = {}
        for data in all_data:
            if data:
                combined.update(data)  # Example combination logic
        return combined

    def add_poller(self, poller: Poller, backoff: float | None = None):
        """Add a DataPoller to the manager."""
        assert not any(poller == p for p, _ in self.pollers)
        self.pollers.add((poller, backoff))

    def add_mapper(self, mapper: Mapper, backoff: float | None = None):
        """Add a Mapper to the manager."""
        self.mappers.subscribe(mapper, backoff=backoff)

    async def start(self, timeout: float | None = None):
        """Start all pollers by fetching initial data and subscribing to events."""
        assert len(self.tasks) == 0
        # Loop pollers
        for poller, backoff in self.pollers:
            # Register itelf to be called when new data is available
            poller.events.subscribe(self, backoff=backoff)
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
        except KeyboardInterrupt:
            # Handle keyboard interruption
            self.logger.info("Keyboard interruption detected. Stopping tasks...")
            await self.stop()
        finally:
            # Clear tasks
            self.tasks.clear()

    async def stop(self):
        """Unsubscribe all pollers from their event systems."""
        # This could be extended to stop any running background tasks if needed
        [task.cancel() for task in self.tasks]
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()

    async def aggregate_data(self):
        """Aggregate and return the latest data from all pollers."""
        tasks = [poller.events.get_data(self) for poller, _ in self.pollers]
        all_data = await asyncio.gather(*tasks)
        return self._combine_data(all_data)

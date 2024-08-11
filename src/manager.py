from __future__ import annotations

import asyncio
import logging

from mappers import Mapper
from pollers import Poller


class DataManager:
    def __init__(self, *logger: logging.Logger):
        self.tasks = []
        self.logger = logger

        # Subscribers
        self.pollers: list[Poller] = []
        self.mappers: list[Mapper] = []

    def __call__(self, data):
        raise NotImplementedError

    def _combine_data(self, all_data):
        """Combine data from multiple pollers. Customize as needed."""
        combined = {}
        for data in all_data:
            if data:
                combined.update(data)  # Example combination logic
        return combined

    def add_poller(self, poller: Poller):
        """Add a DataPoller to the manager."""
        self.pollers.append(poller)

    def add_mapper(self, mapper: Mapper):
        """Add a Mapper to the manager."""
        self.mappers.append(mapper)

    async def start(self, timeout: float | None = None):
        """Start all pollers by fetching initial data and subscribing to events."""
        assert len(self.tasks) == 0
        # Loop pollers
        for poller in self.pollers:
            # Register itelf to be called when new data is available
            poller.subscribe(self)
            # Ask poller to start monitoring data
            self.tasks.append(poller.run(timeout=timeout))
        # Loop mappers
        for mapper in self.mappers:
            # Register itelf to be called when new data is available
            mapper.subscribe(self)
            # Ask mapper to start monitoring data
            self.tasks.append(mapper.sync())
        try:
            # wait until timeout is reached or tasks are anceled
            await asyncio.gather(*self.tasks)
        except asyncio.CancelledError:
            # Gracefully stop monitoring
            await self.stop()
        except KeyboardInterrupt:
            # Handle keyboard interruption
            self.logger.info("Keyboard interruption detected. Stopping tasks...")
            await self.stop()

    async def stop(self):
        """Unsubscribe all pollers from their event systems."""
        # This could be extended to stop any running background tasks if needed
        tasks = [task.cancel() for task in self.tasks]
        await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()

    async def aggregate_data(self):
        """Aggregate and return the latest data from all pollers."""
        tasks = [poller.get_data() for poller in self.pollers]
        all_data = await asyncio.gather(*tasks)
        return self._combine_data(all_data)

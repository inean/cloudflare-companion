import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from dns_synchub.events import EventEmitter
from dns_synchub.manager import DataManager
from dns_synchub.mappers import Mapper
from dns_synchub.pollers import Poller


@pytest.fixture
def mock_logger():
    return MagicMock(spec=logging.Logger)


@pytest.fixture
def mock_poller():
    poller = MagicMock(spec=Poller)
    poller.events = MagicMock(spec=EventEmitter)
    poller.run = AsyncMock()
    return poller


@pytest.fixture
def mock_poller_infinity(mock_poller):
    async def run_indenfinitely(timeout):
        while True:
            await asyncio.sleep(1)

    # Patch the run method to run indefinitely
    mock_poller.run = AsyncMock(side_effect=run_indenfinitely)
    return mock_poller


@pytest.fixture
def mock_mapper():
    return MagicMock(spec=Mapper)


@pytest.fixture
def data_manager(mock_logger):
    class MockList(list):
        def clear(self): ...

    manager = DataManager(logger=mock_logger)
    manager.tasks = MockList()
    manager.tasks.clear = MagicMock(spec=list.clear, return_value=None)
    return manager


def test_initialization(data_manager, mock_logger):
    assert data_manager.logger == mock_logger
    assert data_manager.tasks == []
    assert isinstance(data_manager.pollers, set)
    assert isinstance(data_manager.mappers, EventEmitter)


def test_add_poller(data_manager, mock_poller):
    data_manager.add_poller(mock_poller, backoff=5.0)
    assert (mock_poller, 5.0) in data_manager.pollers


@pytest.mark.asyncio
async def test_add_mapper(data_manager: DataManager, mock_mapper):
    data_manager.mappers = MagicMock(spec=EventEmitter)
    await data_manager.add_mapper(mock_mapper, backoff=5.0)
    data_manager.mappers.subscribe.assert_called_once_with(mock_mapper, backoff=5.0)


@pytest.mark.asyncio
async def test_start(data_manager, mock_poller, mock_mapper):
    mock_event_emitter = MagicMock(spec=EventEmitter)
    mock_event_emitter.__len__.return_value = 1
    data_manager.mappers = mock_event_emitter
    data_manager.add_mapper(mock_mapper, backoff=5.0)
    data_manager.add_poller(mock_poller, backoff=5.0)
    # Patch the clear method of the specific list instance
    await data_manager.start(timeout=10.0)
    mock_poller.run.assert_awaited_once_with(timeout=10.0)
    assert len(data_manager.tasks) == 2  # One for poller and one for mappers.emit
    data_manager.tasks.clear.assert_called_once()


@pytest.mark.asyncio
async def test_start_no_mapper(data_manager, mock_poller):
    data_manager.add_poller(mock_poller, backoff=5.0)
    await data_manager.start(timeout=10.0)
    mock_poller.run.assert_awaited_once_with(timeout=10.0)
    assert len(data_manager.tasks) == 1  # Only one task for poller


@pytest.mark.asyncio
async def test_start_no_pollers(data_manager, mock_mapper):
    mock_event_emitter = MagicMock(spec=EventEmitter)
    mock_event_emitter.__len__.return_value = 1
    data_manager.mappers = mock_event_emitter

    data_manager.add_mapper(mock_mapper, backoff=5.0)
    await data_manager.start(timeout=10.0)
    data_manager.mappers.emit.assert_awaited_once_with(timeout=10.0)
    assert len(data_manager.tasks) == 1  # Only one task for mappers.emit


@pytest.mark.asyncio
async def test_start_cancel_interrupt(data_manager, mock_poller_infinity):
    data_manager.add_poller(mock_poller_infinity, backoff=5.0)
    with patch.object(data_manager, "stop", new_callable=AsyncMock) as mock_stop:
        with patch("asyncio.gather", side_effect=asyncio.exceptions.CancelledError):
            await data_manager.start(timeout=10.0)
    mock_stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop(data_manager, mock_poller_infinity):
    # Restore patched tasks list to a valid one
    data_manager.tasks = []
    data_manager.add_poller(mock_poller_infinity, backoff=5.0)
    asyncio.create_task(data_manager.start(timeout=10.0))
    await asyncio.sleep(0.1)
    await data_manager.stop()
    assert len(data_manager.tasks) == 0


def test_aggregate_data(data_manager, mock_poller):
    data_manager.add_poller(mock_poller, backoff=5.0)
    mock_poller.events.get_data = Mock(return_value=(["value"], "source"))
    combined_data = data_manager.aggregate_data()
    assert combined_data == {"source": ["value"]}

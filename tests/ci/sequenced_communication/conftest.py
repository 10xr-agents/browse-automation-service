"""
Pytest configuration for Sequenced Communication tests.

Provides fixtures for testing:
- CommandConsumer
- StatePublisher
- SequenceTracker
- DedupCache
- StateDiffEngine
- BrowserSessionManager with sequenced components
"""

from unittest.mock import AsyncMock

import pytest

from navigator.session.manager import BrowserSessionManager
from navigator.streaming.broadcaster import EventBroadcaster


@pytest.fixture(scope='function')
def mock_redis_streams_client():
	"""Create a mock Redis async client for streams testing."""
	mock_redis = AsyncMock()
	
	# Stream operations
	mock_redis.xadd = AsyncMock(return_value=b"1234567890-0")
	mock_redis.xreadgroup = AsyncMock(return_value=[])
	mock_redis.xgroup_create = AsyncMock(return_value=True)
	mock_redis.xack = AsyncMock(return_value=1)
	mock_redis.xpending_range = AsyncMock(return_value=[])
	mock_redis.xclaim = AsyncMock(return_value=[])
	mock_redis.ping = AsyncMock(return_value=True)
	
	# Stream data structure for testing
	mock_redis._stream_data: dict[str, list[tuple[bytes, dict[bytes, bytes]]]] = {}
	mock_redis._consumer_groups: dict[str, set[str]] = {}
	
	return mock_redis


@pytest.fixture(scope='function')
def event_broadcaster():
	"""Create an EventBroadcaster instance."""
	return EventBroadcaster(redis_client=None, use_websocket=False)


@pytest.fixture(scope='function')
def browser_session_manager(event_broadcaster):
	"""Create a BrowserSessionManager instance."""
	return BrowserSessionManager(event_broadcaster=event_broadcaster)


@pytest.fixture(scope='function')
def sequence_tracker():
	"""Create a SequenceTracker instance."""
	from navigator.state.sequence_tracker import SequenceTracker
	return SequenceTracker()


@pytest.fixture(scope='function')
def dedup_cache():
	"""Create a DedupCache instance."""
	from navigator.state.dedup_cache import DedupCache
	return DedupCache(ttl_seconds=300)


@pytest.fixture(scope='function')
def state_diff_engine():
	"""Create a StateDiffEngine instance."""
	from navigator.state.diff_engine import StateDiffEngine
	return StateDiffEngine()

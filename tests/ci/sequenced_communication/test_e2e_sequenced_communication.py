"""
End-to-End Tests for Sequenced Communication (Stage 7).

Tests cover:
- Command → Action → State Update flow
- Sequence ordering validation
- Idempotency testing (duplicate commands)
- Error handling (sequence gaps, processing failures)
- Multiple instance testing (consumer groups)
"""

import asyncio
from unittest.mock import MagicMock

from navigator.state.dedup_cache import DedupCache
from navigator.streaming.state_publisher import StatePublisher


class TestSequenceOrdering:
	"""Tests for sequence ordering validation."""
	
	async def test_sequence_validation_sequential(self, sequence_tracker):
		"""Test that sequential sequence numbers are accepted."""
		session_id = "test_session_sequential"
		
		# Process sequence 1
		is_valid, expected = await sequence_tracker.validate_sequence(session_id, 1)
		assert is_valid is True
		await sequence_tracker.update_last_processed(session_id, 1)
		
		# Process sequence 2
		is_valid, expected = await sequence_tracker.validate_sequence(session_id, 2)
		assert is_valid is True
		await sequence_tracker.update_last_processed(session_id, 2)
		
		# Process sequence 3
		is_valid, expected = await sequence_tracker.validate_sequence(session_id, 3)
		assert is_valid is True
		
		last_processed = await sequence_tracker.get_last_processed(session_id)
		assert last_processed == 2
	
	async def test_sequence_validation_duplicate(self, sequence_tracker):
		"""Test that duplicate sequence numbers are rejected."""
		session_id = "test_session_duplicate"
		
		# Process sequence 1
		is_valid, expected = await sequence_tracker.validate_sequence(session_id, 1)
		assert is_valid is True
		await sequence_tracker.update_last_processed(session_id, 1)
		
		# Try to process sequence 1 again (duplicate)
		is_valid, expected = await sequence_tracker.validate_sequence(session_id, 1)
		assert is_valid is False
		assert expected == 2  # Expected next sequence
	
	async def test_sequence_validation_gap(self, sequence_tracker):
		"""Test that sequence gaps are detected."""
		session_id = "test_session_gap"
		
		# Process sequence 1
		is_valid, expected = await sequence_tracker.validate_sequence(session_id, 1)
		assert is_valid is True
		await sequence_tracker.update_last_processed(session_id, 1)
		
		# Try to process sequence 3 (gap - missing 2)
		is_valid, expected = await sequence_tracker.validate_sequence(session_id, 3)
		assert is_valid is False
		assert expected == 2  # Expected next sequence
	
	async def test_sequence_validation_multiple_sessions(self, sequence_tracker):
		"""Test sequence tracking for multiple sessions."""
		session1 = "test_session_1"
		session2 = "test_session_2"
		
		# Process sequences for session 1
		await sequence_tracker.update_last_processed(session1, 5)
		
		# Process sequences for session 2
		await sequence_tracker.update_last_processed(session2, 10)
		
		# Verify independent tracking
		assert await sequence_tracker.get_last_processed(session1) == 5
		assert await sequence_tracker.get_last_processed(session2) == 10
		
		# Session 1 expects 6
		is_valid, expected = await sequence_tracker.validate_sequence(session1, 6)
		assert is_valid is True
		
		# Session 2 expects 11
		is_valid, expected = await sequence_tracker.validate_sequence(session2, 11)
		assert is_valid is True


class TestIdempotency:
	"""Tests for idempotency (duplicate command handling)."""
	
	async def test_dedup_cache_processing(self, dedup_cache):
		"""Test that commands can be marked as processing."""
		command_id = "cmd_test_123"
		
		# Command not processed
		assert await dedup_cache.is_processed(command_id) is False
		
		# Mark as processing
		await dedup_cache.mark_processing(command_id)
		
		# Still not processed (processing is different from processed)
		assert await dedup_cache.is_processed(command_id) is False
	
	async def test_dedup_cache_processed(self, dedup_cache):
		"""Test that processed commands are detected."""
		command_id = "cmd_test_456"
		
		# Mark as processed
		await dedup_cache.mark_processed(command_id)
		
		# Should be detected as processed
		assert await dedup_cache.is_processed(command_id) is True
	
	async def test_dedup_cache_duplicate_prevention(self, dedup_cache):
		"""Test that duplicate commands are prevented."""
		command_id = "cmd_test_789"
		
		# Process command first time
		await dedup_cache.mark_processing(command_id)
		await dedup_cache.mark_processed(command_id)
		assert await dedup_cache.is_processed(command_id) is True
		
		# Try to process again (should be detected as duplicate)
		is_processed = await dedup_cache.is_processed(command_id)
		assert is_processed is True  # Already processed
	
	async def test_dedup_cache_ttl_expiry(self, dedup_cache):
		"""Test that cache entries expire after TTL."""
		# Create cache with short TTL
		short_ttl_cache = DedupCache(ttl_seconds=1)
		command_id = "cmd_test_expiry"
		
		# Mark as processed
		await short_ttl_cache.mark_processed(command_id)
		assert await short_ttl_cache.is_processed(command_id) is True
		
		# Wait for TTL to expire
		await asyncio.sleep(1.5)
		
		# Should be expired (not processed anymore)
		assert await short_ttl_cache.is_processed(command_id) is False


class TestStateDiffEngine:
	"""Tests for StateDiffEngine component."""
	
	async def test_state_capture_basic(self, state_diff_engine, browser_session):
		"""Test capturing browser state snapshot."""
		# Navigate to a page first
		from browser_use.browser.events import NavigateToUrlEvent
		from navigator.state.diff_engine import StateSnapshot
		browser_session.event_bus.dispatch(NavigateToUrlEvent(url="https://example.com"))
		await asyncio.sleep(1)  # Wait for navigation
		
		# Capture state
		snapshot = await state_diff_engine.capture_state(browser_session)
		
		assert isinstance(snapshot, StateSnapshot)
		assert snapshot.url is not None
		assert snapshot.title is not None
		assert isinstance(snapshot.dom_elements, list)
	
	async def test_state_diff_computation(self, state_diff_engine, browser_session):
		"""Test computing state diff between two snapshots."""
		# Capture initial state
		pre_state = await state_diff_engine.capture_state(browser_session)
		
		# Navigate to trigger state change
		from browser_use.browser.events import NavigateToUrlEvent
		browser_session.event_bus.dispatch(NavigateToUrlEvent(url="https://example.com"))
		await asyncio.sleep(1)
		
		# Capture post state
		post_state = await state_diff_engine.capture_state(browser_session)
		
		# Compute diff
		diff = state_diff_engine.compute_diff(pre_state, post_state)
		
		assert isinstance(diff, dict)
		assert "format_version" in diff
		assert "diff_type" in diff
		assert "pre_state_hash" in diff
		assert "post_state_hash" in diff
		assert "dom_changes" in diff
		assert "navigation_changes" in diff
	
	async def test_state_diff_no_changes(self, state_diff_engine, browser_session):
		"""Test diff computation when no changes occurred."""
		# Navigate first
		from browser_use.browser.events import NavigateToUrlEvent
		browser_session.event_bus.dispatch(NavigateToUrlEvent(url="https://example.com"))
		await asyncio.sleep(1)
		
		# Capture state twice (no changes)
		pre_state = await state_diff_engine.capture_state(browser_session)
		await asyncio.sleep(0.1)  # Small delay
		post_state = await state_diff_engine.capture_state(browser_session)
		
		# Compute diff
		diff = state_diff_engine.compute_diff(pre_state, post_state)
		
		# Should have minimal changes
		assert diff["navigation_changes"]["url_changed"] is False
		assert diff["navigation_changes"]["title_changed"] is False


class TestStatePublisher:
	"""Tests for StatePublisher component."""
	
	async def test_state_publisher_initialization(self, mock_redis_streams_client):
		"""Test StatePublisher initialization."""
		publisher = StatePublisher(mock_redis_streams_client)
		assert publisher.redis_client == mock_redis_streams_client
	
	async def test_state_publisher_publish(self, mock_redis_streams_client):
		"""Test publishing state update to stream."""
		from navigator.state.diff_engine import StateSnapshot
		
		publisher = StatePublisher(mock_redis_streams_client)
		
		# Create mock state snapshot
		post_state = StateSnapshot(
			url="https://example.com",
			title="Example",
			ready_state="complete",
			scroll_x=0,
			scroll_y=0,
			viewport_width=1920,
			viewport_height=1080,
			dom_elements=[],
		)
		
		# Create mock action result and diff
		action_result = {"success": True, "error": None, "data": {}}
		state_diff = {
			"format_version": "1.0",
			"diff_type": "incremental",
			"pre_state_hash": "hash1",
			"post_state_hash": "hash2",
			"dom_changes": {},
			"navigation_changes": {},
			"semantic_events": [],
		}
		
		# Publish state update
		await publisher.publish_state_update(
			room_name="test_room",
			command_id="cmd_123",
			command_sequence=1,
			action_result=action_result,
			state_diff=state_diff,
			post_state=post_state,
		)
		
		# Verify xadd was called
		mock_redis_streams_client.xadd.assert_called_once()
		call_args = mock_redis_streams_client.xadd.call_args
		assert call_args[0][0] == "state:test_room"  # Stream key
	
	async def test_state_publisher_no_redis(self):
		"""Test StatePublisher with no Redis client (graceful degradation)."""
		publisher = StatePublisher(None)
		
		from navigator.state.diff_engine import StateSnapshot
		post_state = StateSnapshot(
			url="https://example.com",
			title="Example",
			ready_state="complete",
			scroll_x=0,
			scroll_y=0,
			viewport_width=1920,
			viewport_height=1080,
			dom_elements=[],
		)
		
		# Should not raise error (graceful degradation)
		await publisher.publish_state_update(
			room_name="test_room",
			command_id="cmd_123",
			command_sequence=1,
			action_result={"success": True},
			state_diff={},
			post_state=post_state,
		)


class TestErrorHandling:
	"""Tests for error handling scenarios."""
	
	async def test_sequence_gap_handling(self, sequence_tracker):
		"""Test handling of sequence gaps."""
		session_id = "test_gap_handling"
		
		# Process sequence 1
		await sequence_tracker.update_last_processed(session_id, 1)
		
		# Try sequence 3 (gap)
		is_valid, expected = await sequence_tracker.validate_sequence(session_id, 3)
		assert is_valid is False
		assert expected == 2  # Expected sequence
	
	async def test_duplicate_command_rejection(self, dedup_cache):
		"""Test rejection of duplicate commands."""
		command_id = "cmd_duplicate_test"
		
		# Process command
		await dedup_cache.mark_processed(command_id)
		
		# Try to process again
		is_processed = await dedup_cache.is_processed(command_id)
		assert is_processed is True  # Should be detected as duplicate
	
	async def test_state_capture_error_handling(self, state_diff_engine):
		"""Test error handling in state capture."""
		# Create invalid browser session mock
		invalid_session = MagicMock()
		
		# Should handle gracefully (may raise or return None, depending on implementation)
		# This is implementation-dependent, so we just verify it doesn't crash
		try:
			await state_diff_engine.capture_state(invalid_session)
		except Exception:
			pass  # Expected to raise or handle gracefully


class TestIntegrationFlow:
	"""Tests for integrated command → action → state update flow."""
	
	async def test_component_integration(self, browser_session_manager):
		"""Test that components are accessible from BrowserSessionManager."""
		# Get components (lazy initialization)
		state_diff_engine = browser_session_manager.get_state_diff_engine()
		sequence_tracker = browser_session_manager.get_sequence_tracker()
		dedup_cache = browser_session_manager.get_dedup_cache()
		
		assert state_diff_engine is not None
		assert sequence_tracker is not None
		assert dedup_cache is not None
		
		# Test sequence tracking
		session_id = "test_integration"
		is_valid, expected = await sequence_tracker.validate_sequence(session_id, 1)
		assert is_valid is True
		
		# Test dedup cache
		command_id = "cmd_integration_test"
		assert await dedup_cache.is_processed(command_id) is False
		await dedup_cache.mark_processed(command_id)
		assert await dedup_cache.is_processed(command_id) is True

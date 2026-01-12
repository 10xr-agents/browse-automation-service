"""
Tests for Presentation Flow Manager (Steps 1.1-1.4).

Tests cover:
- Basic structure (Step 1.1)
- Timeout management (Step 1.2)
- BullMQ integration (Step 1.3)
- Browser Session Manager integration (Step 1.4)
"""

import asyncio
import time

import pytest

from navigator.presentation.flow_manager import PresentationFlowManager, SessionState


class TestPresentationFlowManagerBasic:
	"""Tests for Presentation Flow Manager basic structure (Step 1.1)."""

	async def test_create_flow_manager(self, flow_manager):
		"""Test creating a PresentationFlowManager instance."""
		assert flow_manager is not None
		assert flow_manager.timeout_minutes == 1  # Testing timeout
		assert len(flow_manager.sessions) == 0
		assert flow_manager._shutdown is False

	async def test_start_session(self, flow_manager):
		"""Test starting a new session."""
		session_id = await flow_manager.start_session(room_name="test_room")
		assert session_id is not None
		assert session_id in flow_manager.sessions
		
		session = flow_manager.get_session(session_id)
		assert session is not None
		assert session.room_name == "test_room"
		assert session.state == SessionState.ACTIVE

	async def test_start_session_with_id(self, flow_manager):
		"""Test starting a session with a specific ID."""
		custom_id = "custom_session_id_12345"
		session_id = await flow_manager.start_session(room_name="test_room", session_id=custom_id)
		assert session_id == custom_id
		assert session_id in flow_manager.sessions

	async def test_duplicate_session_id(self, flow_manager):
		"""Test that starting a session with duplicate ID raises error."""
		session_id = await flow_manager.start_session(room_name="test_room", session_id="test_id")
		
		with pytest.raises(ValueError, match="already exists"):
			await flow_manager.start_session(room_name="test_room2", session_id="test_id")

	async def test_close_session(self, flow_manager):
		"""Test closing a session."""
		session_id = await flow_manager.start_session(room_name="test_room")
		
		await flow_manager.close_session(session_id)
		
		# Session should be removed
		assert session_id not in flow_manager.sessions

	async def test_get_session(self, flow_manager):
		"""Test getting a session by ID."""
		session_id = await flow_manager.start_session(room_name="test_room")
		
		session = flow_manager.get_session(session_id)
		assert session is not None
		assert session.room_name == "test_room"
		
		# Non-existent session
		assert flow_manager.get_session("non_existent") is None

	async def test_list_sessions(self, flow_manager):
		"""Test listing all sessions."""
		session_id1 = await flow_manager.start_session(room_name="room1")
		session_id2 = await flow_manager.start_session(room_name="room2")
		
		sessions = flow_manager.list_sessions()
		assert len(sessions) == 2
		assert {s.session_id for s in sessions} == {session_id1, session_id2}

	async def test_has_session(self, flow_manager):
		"""Test checking if a session exists."""
		session_id = await flow_manager.start_session(room_name="test_room")
		
		assert flow_manager.has_session(session_id) is True
		assert flow_manager.has_session("non_existent") is False


class TestPresentationFlowManagerTimeout:
	"""Tests for Presentation Flow Manager timeout management (Step 1.2)."""

	async def test_timeout_detection(self):
		"""Test that expired sessions are detected and closed."""
		# Use very short timeout for testing (5 seconds)
		manager = PresentationFlowManager(timeout_minutes=5/60)  # 5 seconds
		
		session_id = await manager.start_session(room_name="test_room")
		
		# Manually set created_at to past time (simulate expired session)
		session = manager.get_session(session_id)
		session.created_at = time.time() - 10  # 10 seconds ago
		
		# Trigger cleanup
		await manager._cleanup_expired_sessions()
		
		# Session should be closed
		assert session_id not in manager.sessions
		
		await manager.shutdown()

	async def test_active_session_not_closed(self, flow_manager):
		"""Test that active (non-expired) sessions are not closed."""
		session_id = await flow_manager.start_session(room_name="test_room")
		
		# Trigger cleanup (session should not be expired)
		await flow_manager._cleanup_expired_sessions()
		
		# Session should still exist
		assert session_id in flow_manager.sessions

	async def test_shutdown_stops_cleanup_loop(self, flow_manager):
		"""Test that shutdown stops the cleanup loop."""
		session_id = await flow_manager.start_session(room_name="test_room")
		
		await flow_manager.shutdown()
		
		# Cleanup task should be cancelled
		if flow_manager._cleanup_task:
			assert flow_manager._cleanup_task.done() or flow_manager._cleanup_task.cancelled()
		
		assert flow_manager._shutdown is True


class TestPresentationFlowManagerQueue:
	"""Tests for Presentation Flow Manager queue integration (Step 1.3)."""

	async def test_enqueue_action_in_memory(self, flow_manager):
		"""Test enqueueing an action in in-memory queue."""
		session_id = await flow_manager.start_session(room_name="test_room")
		
		action = {"type": "navigate", "params": {"url": "https://example.com"}}
		await flow_manager.enqueue_action(session_id, action)
		
		# Verify action was enqueued (check internal queue)
		assert hasattr(flow_manager, '_in_memory_queue')
		assert session_id in flow_manager._in_memory_queue
		assert len(flow_manager._in_memory_queue[session_id]) == 1
		assert flow_manager._in_memory_queue[session_id][0] == action

	async def test_enqueue_action_nonexistent_session(self, flow_manager):
		"""Test that enqueueing action for non-existent session raises error."""
		action = {"type": "click", "params": {"index": 0}}
		
		with pytest.raises(ValueError, match="does not exist"):
			await flow_manager.enqueue_action("non_existent", action)

	async def test_process_queue_in_memory(self, flow_manager):
		"""Test processing queue in in-memory mode."""
		session_id = await flow_manager.start_session(room_name="test_room")
		
		action1 = {"type": "navigate", "params": {"url": "https://example.com"}}
		action2 = {"type": "click", "params": {"index": 0}}
		
		await flow_manager.enqueue_action(session_id, action1)
		await flow_manager.enqueue_action(session_id, action2)
		
		# Process queue
		await flow_manager.process_queue(session_id)
		
		# Queue should be cleared after processing
		assert session_id not in flow_manager._in_memory_queue or len(flow_manager._in_memory_queue.get(session_id, [])) == 0

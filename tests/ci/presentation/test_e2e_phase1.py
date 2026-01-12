"""
End-to-End Tests for Phase 1 (Presentation Flow).

Tests the complete Phase 1 flow:
- Start presentation session
- Execute various actions
- Queue management
- Event broadcasting
- Session persistence
"""

import asyncio
import json
import time

import pytest

from navigator.action.command import ActionResult


class TestPhase1E2E:
	"""End-to-end tests for Phase 1 complete flow."""

	async def test_complete_presentation_flow(self, flow_manager, action_registry, base_url):
		"""Test complete presentation flow: start session, execute actions, close session."""
		# 1. Start presentation session
		session_id = await flow_manager.start_session(room_name="e2e_test_room")
		assert session_id is not None
		assert flow_manager.has_session(session_id)
		
		# 2. Execute basic actions
		navigate_result = await action_registry.execute_action(
			"navigate",
			{"url": f"{base_url}/test"}
		)
		assert navigate_result.success is True
		await asyncio.sleep(0.5)
		
		wait_result = await action_registry.execute_action("wait", {"seconds": 0.1})
		assert wait_result.success is True
		
		# 3. Execute extended actions
		zoom_result = await action_registry.execute_action("zoom_in", {})
		assert isinstance(zoom_result, ActionResult)
		
		# 4. Close session
		await flow_manager.close_session(session_id)
		assert not flow_manager.has_session(session_id)

	async def test_action_queue_integration(self, flow_manager, action_registry, base_url):
		"""Test action queue integration with flow manager."""
		session_id = await flow_manager.start_session(room_name="queue_test_room")
		
		# Enqueue multiple actions
		actions = [
			{"type": "navigate", "params": {"url": f"{base_url}/test"}},
			{"type": "wait", "params": {"seconds": 0.1}},
			{"type": "scroll", "params": {"direction": "down", "amount": 500}},
		]
		
		for action in actions:
			await flow_manager.enqueue_action(session_id, action)
		
		# Verify actions were enqueued
		assert session_id in flow_manager._in_memory_queue
		assert len(flow_manager._in_memory_queue[session_id]) == 3
		
		# Process queue (this is a placeholder - actual execution would require integration)
		await flow_manager.process_queue(session_id)
		
		await flow_manager.close_session(session_id)

	async def test_event_broadcasting_integration(self, event_broadcaster_with_redis, mock_redis_client):
		"""Test event broadcasting integration."""
		broadcaster = event_broadcaster_with_redis
		
		# Simulate presentation flow events
		await broadcaster.broadcast_presentation_started("test_room", session_id="test_session")
		await broadcaster.broadcast_action_queued("test_room", {"type": "click"}, session_id="test_session")
		await broadcaster.broadcast_action_processing("test_room", {"type": "click"}, session_id="test_session")
		await broadcaster.broadcast_presentation_ending("test_room", session_id="test_session")
		
		# Verify all events were published to Redis
		assert mock_redis_client.publish.call_count == 4
		
		# Verify all events use correct channel
		for call in mock_redis_client.publish.call_args_list:
			channel = call[0][0]
			assert channel == "browser:events:test_session"

	async def test_session_persistence_integration(self, session_store, mock_redis_client):
		"""Test session persistence integration."""
		session_id = "e2e_persistence_session"
		session_state = {
			"room_name": "e2e_room",
			"state": "active",
			"created_at": time.time(),
			"metadata": {"test": "data"}
		}
		
		# Save session
		await session_store.save_session(session_id, session_state, ttl=3600)
		mock_redis_client.setex.assert_called_once()
		
		# Mock load
		mock_redis_client.get.return_value = json.dumps(session_state).encode('utf-8')
		
		# Load session
		loaded = await session_store.load_session(session_id)
		assert loaded == session_state
		
		# Delete session
		await session_store.delete_session(session_id)
		mock_redis_client.delete.assert_called_once()

	async def test_complete_flow_with_all_components(
		self,
		flow_manager,
		action_registry,
		event_broadcaster_with_redis,
		session_store,
		base_url,
		mock_redis_client
	):
		"""Test complete flow with all Phase 1 components integrated."""
		# 1. Start session
		session_id = await flow_manager.start_session(room_name="complete_flow_room")
		
		# 2. Save session state
		session_state = {
			"room_name": "complete_flow_room",
			"session_id": session_id,
			"state": "active",
			"created_at": time.time()
		}
		await session_store.save_session(session_id, session_state)
		
		# 3. Broadcast presentation started
		await event_broadcaster_with_redis.broadcast_presentation_started(
			room_name="complete_flow_room",
			session_id=session_id
		)
		
		# 4. Execute actions
		await action_registry.execute_action("navigate", {"url": f"{base_url}/test"})
		await asyncio.sleep(0.5)
		
		# 5. Broadcast action events
		await event_broadcaster_with_redis.broadcast_action_queued(
			room_name="complete_flow_room",
			action={"type": "click", "params": {"index": 0}},
			session_id=session_id
		)
		
		# 6. Close session
		await flow_manager.close_session(session_id)
		
		# 7. Verify events were broadcast
		assert mock_redis_client.publish.call_count >= 2
		
		# 8. Verify session can be loaded
		mock_redis_client.get.return_value = json.dumps(session_state).encode('utf-8')
		loaded = await session_store.load_session(session_id)
		assert loaded is not None

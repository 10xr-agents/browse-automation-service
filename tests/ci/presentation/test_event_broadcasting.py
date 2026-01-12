"""
Tests for Event Broadcasting (Step 1.16).

Tests cover:
- Redis Pub/Sub integration
- WebSocket fallback
- New event types
"""

import json

import pytest

from navigator.streaming.broadcaster import EventBroadcaster


class TestEventBroadcasting:
	"""Tests for EventBroadcaster with Redis Pub/Sub (Step 1.16)."""

	async def test_create_event_broadcaster(self, event_broadcaster):
		"""Test creating an EventBroadcaster instance."""
		assert event_broadcaster is not None
		assert event_broadcaster.redis_client is None
		assert event_broadcaster.use_websocket is False

	async def test_create_event_broadcaster_with_redis(self, event_broadcaster_with_redis, mock_redis_client):
		"""Test creating an EventBroadcaster with Redis."""
		broadcaster = event_broadcaster_with_redis
		assert broadcaster.redis_client is not None
		assert broadcaster.redis_client == mock_redis_client

	async def test_broadcast_event_with_redis(self, event_broadcaster_with_redis, mock_redis_client):
		"""Test broadcasting an event via Redis Pub/Sub."""
		broadcaster = event_broadcaster_with_redis
		
		await broadcaster.broadcast_event(
			room_name="test_room",
			event={"type": "test_event", "data": "test"},
			session_id="test_session"
		)
		
		# Verify Redis publish was called
		mock_redis_client.publish.assert_called_once()
		call_args = mock_redis_client.publish.call_args
		assert call_args[0][0] == "browser:events:test_session"  # Channel
		
		# Verify event JSON was published
		event_json = call_args[0][1]
		event_data = json.loads(event_json)
		assert event_data["type"] == "test_event"
		assert event_data["data"] == "test"

	async def test_broadcast_presentation_started(self, event_broadcaster_with_redis, mock_redis_client):
		"""Test broadcasting presentation_started event."""
		await event_broadcaster_with_redis.broadcast_presentation_started(
			room_name="test_room",
			session_id="test_session"
		)
		
		mock_redis_client.publish.assert_called_once()
		call_args = mock_redis_client.publish.call_args
		event_data = json.loads(call_args[0][1])
		assert event_data["type"] == "presentation_started"
		assert event_data["session_id"] == "test_session"

	async def test_broadcast_all_new_event_types(self, event_broadcaster_with_redis, mock_redis_client):
		"""Test broadcasting all new event types."""
		broadcaster = event_broadcaster_with_redis
		
		# Test all new event types
		await broadcaster.broadcast_presentation_started("room1", session_id="s1")
		await broadcaster.broadcast_presentation_paused("room1", session_id="s1")
		await broadcaster.broadcast_presentation_resumed("room1", session_id="s1")
		await broadcaster.broadcast_presentation_timeout_warning("room1", 5, session_id="s1")
		await broadcaster.broadcast_presentation_ending("room1", session_id="s1")
		await broadcaster.broadcast_action_queued("room1", {"type": "click"}, session_id="s1")
		await broadcaster.broadcast_action_processing("room1", {"type": "click"}, session_id="s1")
		await broadcaster.broadcast_presentation_mode_enabled("room1", True, session_id="s1")
		await broadcaster.broadcast_page_loaded("room1", "https://example.com", session_id="s1")
		await broadcaster.broadcast_dom_updated("room1", "added", session_id="s1")
		await broadcaster.broadcast_element_hovered("room1", 0, session_id="s1")
		await broadcaster.broadcast_mouse_moved("room1", 100, 200, session_id="s1")
		
		# Verify all events were published
		assert mock_redis_client.publish.call_count == 13
		
		# Verify channel naming
		all_calls = mock_redis_client.publish.call_args_list
		for call in all_calls:
			channel = call[0][0]
			assert channel.startswith("browser:events:")
			assert channel == "browser:events:s1"

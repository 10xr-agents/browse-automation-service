"""
Tests for Session Persistence (Step 1.17).

Tests cover:
- Save and load session
- Session serialization/deserialization
- TTL handling
"""

import json

import pytest

from navigator.presentation.session_store import SessionStore


class TestSessionPersistence:
	"""Tests for SessionStore (Step 1.17)."""

	async def test_create_session_store(self, session_store, mock_redis_client):
		"""Test creating a SessionStore instance."""
		assert session_store is not None
		assert session_store.redis_client == mock_redis_client
		assert session_store.key_prefix == "browser:session:"

	async def test_save_session(self, session_store, mock_redis_client):
		"""Test saving a session to Redis."""
		session_id = "test_session_123"
		session_state = {
			"room_name": "test_room",
			"state": "active",
			"created_at": 1234567890.0
		}
		
		await session_store.save_session(session_id, session_state, ttl=3600)
		
		# Verify setex was called
		mock_redis_client.setex.assert_called_once()
		call_args = mock_redis_client.setex.call_args
		assert call_args[0][0] == "browser:session:test_session_123"  # Key
		assert call_args[0][1] == 3600  # TTL
		
		# Verify session JSON
		session_json = call_args[0][2]
		loaded_state = json.loads(session_json)
		assert loaded_state == session_state

	async def test_load_session_exists(self, session_store, mock_redis_client):
		"""Test loading an existing session from Redis."""
		session_id = "test_session_123"
		session_state = {
			"room_name": "test_room",
			"state": "active"
		}
		
		# Mock Redis get to return session JSON
		mock_redis_client.get.return_value = json.dumps(session_state).encode('utf-8')
		
		loaded = await session_store.load_session(session_id)
		
		assert loaded == session_state
		mock_redis_client.get.assert_called_once_with("browser:session:test_session_123")

	async def test_load_session_not_exists(self, session_store, mock_redis_client):
		"""Test loading a non-existent session from Redis."""
		mock_redis_client.get.return_value = None
		
		loaded = await session_store.load_session("non_existent")
		
		assert loaded is None

	async def test_delete_session(self, session_store, mock_redis_client):
		"""Test deleting a session from Redis."""
		session_id = "test_session_123"
		
		await session_store.delete_session(session_id)
		
		mock_redis_client.delete.assert_called_once_with("browser:session:test_session_123")

	async def test_list_sessions(self, session_store, mock_redis_client):
		"""Test listing all sessions from Redis."""
		# Mock Redis keys to return session keys
		mock_keys = [
			b"browser:session:session1",
			b"browser:session:session2",
			b"browser:session:session3"
		]
		mock_redis_client.keys.return_value = mock_keys
		
		session_ids = await session_store.list_sessions()
		
		assert len(session_ids) == 3
		assert set(session_ids) == {"session1", "session2", "session3"}
		mock_redis_client.keys.assert_called_once_with("browser:session:*")

	async def test_save_load_roundtrip(self, session_store, mock_redis_client):
		"""Test saving and loading a session (roundtrip)."""
		session_id = "test_session_roundtrip"
		session_state = {
			"room_name": "test_room",
			"state": "active",
			"custom_data": {"key": "value", "number": 42}
		}
		
		# Mock get to return what was saved
		def mock_setex(key, ttl, value):
			mock_redis_client.get.return_value = value.encode('utf-8')
		
		mock_redis_client.setex.side_effect = mock_setex
		
		await session_store.save_session(session_id, session_state)
		loaded = await session_store.load_session(session_id)
		
		assert loaded == session_state

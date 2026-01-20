"""
Event Broadcaster for Browser Automation Service

Broadcasts browser events to voice agent via Redis Pub/Sub (primary) and WebSocket (fallback).
Supports multiple WebSocket connections per room for redundancy.
Redis Pub/Sub provides high-performance, low-latency event broadcasting.
"""

import asyncio
import json
import logging
import time
from typing import Any

try:
	from fastapi import WebSocket, WebSocketDisconnect
	from fastapi.websockets import WebSocketState

	FASTAPI_AVAILABLE = True
except ImportError:
	FASTAPI_AVAILABLE = False
	logging.warning('FastAPI not installed. Install with: pip install fastapi websockets')

logger = logging.getLogger(__name__)


class EventBroadcaster:
	"""Broadcasts browser events via Redis Pub/Sub (primary) and WebSocket (fallback)."""

	def __init__(self, redis_client: Any | None = None, use_websocket: bool = True):
		"""
		Initialize event broadcaster.
		
		Args:
			redis_client: Optional Redis client (from redis.asyncio). If None, only WebSocket is used.
			use_websocket: Whether to use WebSocket as fallback (default: True)
		"""
		self.redis_client = redis_client
		self.use_websocket = use_websocket

		# Store WebSocket connections per room: room_name -> set of WebSocket connections
		self.room_websockets: dict[str, set[WebSocket]] = {}
		self._lock = asyncio.Lock()

		logger.debug(
			f"EventBroadcaster initialized (redis: {'enabled' if redis_client else 'disabled'}, "
			f"websocket: {'enabled' if use_websocket else 'disabled'})"
		)

	async def register_websocket(self, websocket: WebSocket, room_name: str) -> None:
		"""Register a WebSocket connection for a room.

		Args:
			websocket: WebSocket connection
			room_name: LiveKit room name
		"""
		if not FASTAPI_AVAILABLE:
			raise ImportError('FastAPI not installed. Install with: pip install fastapi websockets')

		logger.debug(f'[EventBroadcaster] Accepting WebSocket connection for room: {room_name}')
		await websocket.accept()

		async with self._lock:
			if room_name not in self.room_websockets:
				self.room_websockets[room_name] = set()
				logger.debug(f'[EventBroadcaster] Created new room entry: {room_name}')
			self.room_websockets[room_name].add(websocket)

		logger.info(f'[EventBroadcaster] ✅ WebSocket registered for room: {room_name} (total connections: {len(self.room_websockets[room_name])})')

	async def unregister_websocket(self, websocket: WebSocket, room_name: str) -> None:
		"""Unregister a WebSocket connection.

		Args:
			websocket: WebSocket connection to remove
			room_name: LiveKit room name
		"""
		async with self._lock:
			if room_name in self.room_websockets:
				self.room_websockets[room_name].discard(websocket)
				if not self.room_websockets[room_name]:
					del self.room_websockets[room_name]

		logger.info(f'WebSocket unregistered for room: {room_name}')

	async def broadcast_event(self, room_name: str, event: dict[str, Any], session_id: str | None = None) -> None:
		"""Broadcast an event via Redis Pub/Sub (if available) and/or WebSocket.

		Args:
			room_name: LiveKit room name
			event: Event dictionary to broadcast
			session_id: Optional session ID for Redis channel (defaults to room_name)
		"""
		event_type = event.get('type', 'unknown')
		logger.debug(f'[EventBroadcaster] Broadcasting event: {event_type} to room: {room_name}')

		# Ensure event has timestamp
		if 'timestamp' not in event:
			event['timestamp'] = time.time()

		# Broadcast via Redis Pub/Sub (primary)
		if self.redis_client:
			try:
				channel = f"browser:events:{session_id or room_name}"
				event_json = json.dumps(event)
				await self.redis_client.publish(channel, event_json)
				logger.debug(f'Published event {event_type} to Redis channel: {channel}')
			except Exception as e:
				logger.error(f'Error publishing event to Redis: {e}', exc_info=True)
				# Continue to WebSocket fallback

		# Broadcast via WebSocket (fallback)
		if self.use_websocket:
			if not FASTAPI_AVAILABLE:
				logger.warning('[EventBroadcaster] FastAPI not available, cannot broadcast via WebSocket')
				return

			async with self._lock:
				websockets = self.room_websockets.get(room_name, set()).copy()

			if not websockets:
				logger.debug(f'No WebSocket connections for room: {room_name}')
				return

			# Send event to all connections
			disconnected = set()
			for websocket in websockets:
				try:
					# Check if websocket is still connected
					if websocket.client_state == WebSocketState.DISCONNECTED:
						disconnected.add(websocket)
						continue

					await websocket.send_json(event)
				except WebSocketDisconnect:
					disconnected.add(websocket)
				except Exception as e:
					logger.error(f'Error sending event to WebSocket: {e}', exc_info=True)
					disconnected.add(websocket)

			# Clean up disconnected websockets
			if disconnected:
				async with self._lock:
					if room_name in self.room_websockets:
						self.room_websockets[room_name] -= disconnected
						if not self.room_websockets[room_name]:
							del self.room_websockets[room_name]

			logger.debug(f'Broadcasted event {event_type} to {len(websockets) - len(disconnected)} WebSocket connections in room: {room_name}')

	async def broadcast_page_navigation(self, room_name: str, url: str) -> None:
		"""Broadcast page navigation event.

		Args:
			room_name: LiveKit room name
			url: New page URL
		"""
		await self.broadcast_event(
			room_name,
			{
				'type': 'page_navigation',
				'url': url,
			},
		)

	async def broadcast_action_error(self, room_name: str, error: str, action: dict[str, Any]) -> None:
		"""Broadcast action error event.

		Args:
			room_name: LiveKit room name
			error: Error message
			action: Action that failed
		"""
		await self.broadcast_event(
			room_name,
			{
				'type': 'action_error',
				'error': error,
				'action': action,
			},
		)

	async def broadcast_dom_change(self, room_name: str, change_type: str) -> None:
		"""Broadcast DOM change event.

		Args:
			room_name: LiveKit room name
			change_type: Type of DOM change
		"""
		await self.broadcast_event(
			room_name,
			{
				'type': 'dom_change',
				'change_type': change_type,
			},
		)

	async def broadcast_page_load_complete(self, room_name: str, url: str) -> None:
		"""Broadcast page load complete event.

		Args:
			room_name: LiveKit room name
			url: Page URL that finished loading
		"""
		await self.broadcast_event(
			room_name,
			{
				'type': 'page_load_complete',
				'url': url,
			},
		)

	async def broadcast_browser_error(self, room_name: str, error: str) -> None:
		"""Broadcast browser error event.

		Args:
			room_name: LiveKit room name
			error: Error message
		"""
		await self.broadcast_event(
			room_name,
			{
				'type': 'browser_error',
				'error': error,
			},
		)

	async def broadcast_action_completed(self, room_name: str, action: dict[str, Any]) -> None:
		"""Broadcast action completed event.

		Args:
			room_name: LiveKit room name
			action: Action that completed
		"""
		await self.broadcast_event(
			room_name,
			{
				'type': 'action_completed',
				'action': action,
			},
		)

	async def broadcast_screen_content(self, room_name: str, screen_content: dict[str, Any]) -> None:
		"""Broadcast screen content update event.

		Args:
			room_name: LiveKit room name
			screen_content: Screen content data (url, title, dom_summary, scroll position, cursor position, etc.)
		"""
		await self.broadcast_event(
			room_name,
			{
				'type': 'screen_content_update',
				'screen_content': screen_content,
			},
		)

	def get_connection_count(self, room_name: str) -> int:
		"""Get number of WebSocket connections for a room.

		Args:
			room_name: LiveKit room name

		Returns:
			Number of connections
		"""
		return len(self.room_websockets.get(room_name, set()))

	# Step 1.16: New event types for Redis Pub/Sub

	async def broadcast_presentation_started(self, room_name: str, session_id: str | None = None) -> None:
		"""Broadcast presentation started event."""
		await self.broadcast_event(
			room_name,
			{'type': 'presentation_started', 'room_name': room_name, 'session_id': session_id or room_name},
			session_id=session_id,
		)

	async def broadcast_presentation_paused(self, room_name: str, session_id: str | None = None) -> None:
		"""Broadcast presentation paused event."""
		await self.broadcast_event(
			room_name,
			{'type': 'presentation_paused', 'room_name': room_name, 'session_id': session_id or room_name},
			session_id=session_id,
		)

	async def broadcast_presentation_resumed(self, room_name: str, session_id: str | None = None) -> None:
		"""Broadcast presentation resumed event."""
		await self.broadcast_event(
			room_name,
			{'type': 'presentation_resumed', 'room_name': room_name, 'session_id': session_id or room_name},
			session_id=session_id,
		)

	async def broadcast_presentation_timeout_warning(self, room_name: str, minutes_remaining: int, session_id: str | None = None) -> None:
		"""Broadcast presentation timeout warning event."""
		await self.broadcast_event(
			room_name,
			{
				'type': 'presentation_timeout_warning',
				'room_name': room_name,
				'session_id': session_id or room_name,
				'minutes_remaining': minutes_remaining,
			},
			session_id=session_id,
		)

	async def broadcast_presentation_ending(self, room_name: str, session_id: str | None = None) -> None:
		"""Broadcast presentation ending event."""
		await self.broadcast_event(
			room_name,
			{'type': 'presentation_ending', 'room_name': room_name, 'session_id': session_id or room_name},
			session_id=session_id,
		)

	async def broadcast_action_queued(self, room_name: str, action: dict[str, Any], session_id: str | None = None) -> None:
		"""Broadcast action queued event."""
		await self.broadcast_event(
			room_name,
			{
				'type': 'action_queued',
				'room_name': room_name,
				'session_id': session_id or room_name,
				'action': action,
			},
			session_id=session_id,
		)

	async def broadcast_action_processing(self, room_name: str, action: dict[str, Any], session_id: str | None = None) -> None:
		"""Broadcast action processing event."""
		await self.broadcast_event(
			room_name,
			{
				'type': 'action_processing',
				'room_name': room_name,
				'session_id': session_id or room_name,
				'action': action,
			},
			session_id=session_id,
		)

	async def broadcast_presentation_mode_enabled(self, room_name: str, enabled: bool, session_id: str | None = None) -> None:
		"""Broadcast presentation mode enabled/disabled event."""
		await self.broadcast_event(
			room_name,
			{
				'type': 'presentation_mode_enabled',
				'room_name': room_name,
				'session_id': session_id or room_name,
				'enabled': enabled,
			},
			session_id=session_id,
		)

	async def broadcast_page_loaded(self, room_name: str, url: str, session_id: str | None = None) -> None:
		"""Broadcast page loaded event."""
		await self.broadcast_event(
			room_name,
			{'type': 'page_loaded', 'room_name': room_name, 'session_id': session_id or room_name, 'url': url},
			session_id=session_id,
		)

	async def broadcast_dom_updated(self, room_name: str, change_type: str, session_id: str | None = None) -> None:
		"""Broadcast DOM updated event."""
		await self.broadcast_event(
			room_name,
			{
				'type': 'dom_updated',
				'room_name': room_name,
				'session_id': session_id or room_name,
				'change_type': change_type,
			},
			session_id=session_id,
		)

	async def broadcast_element_hovered(self, room_name: str, element_index: int, session_id: str | None = None) -> None:
		"""Broadcast element hovered event."""
		await self.broadcast_event(
			room_name,
			{
				'type': 'element_hovered',
				'room_name': room_name,
				'session_id': session_id or room_name,
				'element_index': element_index,
			},
			session_id=session_id,
		)

	async def broadcast_mouse_moved(self, room_name: str, x: int, y: int, session_id: str | None = None) -> None:
		"""Broadcast mouse moved event."""
		await self.broadcast_event(
			room_name,
			{
				'type': 'mouse_moved',
				'room_name': room_name,
				'session_id': session_id or room_name,
				'x': x,
				'y': y,
			},
			session_id=session_id,
		)

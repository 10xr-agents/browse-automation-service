"""
State Publisher for Browser Agent

Publishes state updates to Redis Streams after action execution.
"""

import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
	from navigator.state.diff_engine import StateSnapshot

logger = logging.getLogger(__name__)


def generate_update_id() -> str:
	"""Generate unique update identifier."""
	return f"update_{uuid.uuid4().hex}"


class StatePublisher:
	"""Publishes state updates to Redis Streams."""

	def __init__(self, redis_client: Any | None = None):
		"""Initialize state publisher.
		
		Args:
			redis_client: Redis async client (from redis.asyncio). If None, publishing is disabled.
		"""
		self.redis_client = redis_client
		logger.debug(f"StatePublisher initialized (redis: {'enabled' if redis_client else 'disabled'})")

	async def publish_state_update(
		self,
		room_name: str,
		command_id: str,
		command_sequence: int,
		action_result: dict[str, Any],
		state_diff: dict[str, Any],
		post_state: "StateSnapshot",
		received_at_ms: int | None = None,
	) -> None:
		"""Publish state update to stream.
		
		Args:
			room_name: Session identifier (room_name)
			command_id: Command identifier that triggered this update
			command_sequence: Sequence number of the command
			action_result: Action result dictionary (from execute_action)
			state_diff: State diff dictionary (from StateDiffEngine)
			post_state: Post-action state snapshot
			received_at_ms: Timestamp when command was received (optional)
		"""
		if not self.redis_client:
			logger.debug("Redis client not available, skipping state update publish")
			return

		try:
			# Generate update ID
			update_id = generate_update_id()

			# Get timestamps
			now_ms = int(time.time() * 1000)
			received_at = received_at_ms or now_ms

			# Build current state summary
			current_state_summary = {
				"url": post_state.url,
				"title": post_state.title,
				"page_type": "unknown",  # TODO: Detect page type
				"ready_state": post_state.ready_state,
				"scroll_position": {"x": post_state.scroll_x, "y": post_state.scroll_y},
				"viewport": {
					"width": post_state.viewport_width,
					"height": post_state.viewport_height,
				},
				"interactive_elements_count": len(post_state.dom_elements),
				"forms_count": 0,  # TODO: Count forms
				"state_hash": state_diff.get("post_state_hash", ""),
			}

			# Build state update envelope
			state_update = {
				"version": "1.0",
				"type": "state_update",
				"update_id": update_id,
				"session_id": room_name,
				"room_name": room_name,
				"sequence_number": command_sequence,
				"command_id": command_id,
				"command_sequence": command_sequence,
				"received_at_ms": received_at,
				"generated_at_ms": now_ms,
				"action_result": {
					"success": action_result.get("success", False),
					"error": action_result.get("error"),
					"duration_ms": 0,  # TODO: Track duration
					"data": action_result.get("data", {}),
				},
				"state_diff": state_diff,
				"current_state_summary": current_state_summary,
				"screenshot": {
					"captured": False,  # TODO: Add screenshot support
					"url": None,
					"content_hash": None,
					"width": post_state.viewport_width,
					"height": post_state.viewport_height,
					"format": "png",
					"size_bytes": 0,
				},
				"accessibility_summary": {
					"landmarks_count": 0,  # TODO: Extract from DOM
					"interactive_elements_count": len(post_state.dom_elements),
					"heading_structure": [],  # TODO: Extract headings
					"focused_element": None,  # TODO: Track focus
				},
			}

			# Publish to stream
			stream_key = f"state:{room_name}"

			# Convert to bytes for Redis (JSON encode the entire message)
			state_update_json = json.dumps(state_update)
			stream_data = {
				b"state_update": state_update_json.encode('utf-8'),
			}

			message_id = await self.redis_client.xadd(
				stream_key,
				stream_data,
				maxlen=10000,  # Keep last 10k messages
				approximate=True,
			)

			logger.debug(f"Published state update {update_id} to stream {stream_key} (message_id: {message_id})")

		except Exception as e:
			logger.error(f"Failed to publish state update to stream: {e}", exc_info=True)
			# Don't raise - state update publishing is non-critical

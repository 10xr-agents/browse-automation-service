"""
Command Consumer for Browser Agent

Consumes commands from Redis Streams, validates sequence numbers, and executes actions.
"""

import asyncio
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Import Redis exception types for better error handling
try:
	import redis.exceptions
	REDIS_EXCEPTIONS_AVAILABLE = True
except ImportError:
	REDIS_EXCEPTIONS_AVAILABLE = False


class CommandConsumer:
	"""Consumes commands from Redis Streams."""

	def __init__(
		self,
		redis_client: Any,
		instance_id: str,
		session_manager: Any,  # BrowserSessionManager
		sequence_tracker: Any,  # SequenceTracker
		dedup_cache: Any,  # DedupCache
		state_diff_engine: Any,  # StateDiffEngine
		state_publisher: Any,  # StatePublisher
		consumer_group: str = "browser_agent_cluster",
	):
		"""Initialize command consumer.
		
		Args:
			redis_client: Redis async client (from redis.asyncio)
			instance_id: Instance identifier (used as consumer name)
			session_manager: BrowserSessionManager instance
			sequence_tracker: SequenceTracker instance
			dedup_cache: DedupCache instance
			state_diff_engine: StateDiffEngine instance
			state_publisher: StatePublisher instance
			consumer_group: Consumer group name
		"""
		self.redis_client = redis_client
		self.instance_id = instance_id
		self.consumer_name = f"browser_agent_{instance_id}"
		self.consumer_group = consumer_group
		self.session_manager = session_manager
		self.sequence_tracker = sequence_tracker
		self.dedup_cache = dedup_cache
		self.state_diff_engine = state_diff_engine
		self.state_publisher = state_publisher

		self._consuming = False
		self._consume_tasks: dict[str, asyncio.Task] = {}
		self._active_sessions: set[str] = set()

	async def start_consuming(self, session_id: str) -> None:
		"""Start consuming commands for a session.
		
		Args:
			session_id: Session identifier (room_name)
		"""
		if session_id in self._consume_tasks:
			logger.debug(f"Command consumer already consuming for session {session_id}")
			return

		self._active_sessions.add(session_id)
		stream_key = f"commands:{session_id}"

		# Create consumer group if doesn't exist
		try:
			await self.redis_client.xgroup_create(
				stream_key,
				self.consumer_group,
				id="0",  # Start from beginning
				mkstream=True,  # Create stream if doesn't exist
			)
			logger.info(f"Created consumer group {self.consumer_group} for stream {stream_key}")
		except Exception as e:
			# Group might already exist
			logger.debug(f"Consumer group might already exist: {e}")

		# Start consumption task
		self._consuming = True
		task = asyncio.create_task(self._consume_loop(session_id, stream_key))
		self._consume_tasks[session_id] = task
		logger.info(f"Started command consumer for session {session_id}")

	async def stop_consuming(self, session_id: str) -> None:
		"""Stop consuming commands for a session.
		
		Args:
			session_id: Session identifier
		"""
		self._active_sessions.discard(session_id)

		if session_id in self._consume_tasks:
			task = self._consume_tasks.pop(session_id)
			task.cancel()
			try:
				await task
			except asyncio.CancelledError:
				pass
			logger.info(f"Stopped command consumer for session {session_id}")

	async def _consume_loop(self, session_id: str, stream_key: str) -> None:
		"""Consumption loop for a session."""
		logger.info(f"Starting consume loop for session {session_id}")

		while session_id in self._active_sessions:
			try:
				# Claim pending messages (from failed consumers)
				await self._claim_pending_messages(stream_key)

				# Read new messages (blocking read, timeout 1 second)
				messages = await self.redis_client.xreadgroup(
					self.consumer_group,
					self.consumer_name,
					{stream_key: ">"},  # ">" means new messages
					count=1,
					block=1000,  # Block for 1 second
				)

				if messages:
					for stream, message_list in messages:
						for message_id, data in message_list:
							await self._process_message(session_id, stream_key, message_id, data)

			except asyncio.CancelledError:
				break
			except Exception as e:
				# Check if it's a Redis connection error - stop consuming if Redis is unavailable
				if REDIS_EXCEPTIONS_AVAILABLE and isinstance(e, redis.exceptions.ConnectionError):
					logger.warning(f"Redis connection unavailable for session {session_id}, stopping consumer: {e}")
					break  # Stop consuming if Redis is unavailable
				# Also check error message for connection failures
				error_str = str(e).lower()
				if 'connection' in error_str and ('refused' in error_str or 'failed' in error_str or 'connect call failed' in error_str):
					logger.warning(f"Redis connection unavailable for session {session_id}, stopping consumer: {e}")
					break  # Stop consuming if Redis is unavailable
				logger.debug(f"Error in consume loop for session {session_id}: {e}")
				await asyncio.sleep(1)  # Backoff on error

		logger.info(f"Consume loop ended for session {session_id}")

	async def _claim_pending_messages(self, stream_key: str) -> None:
		"""Claim pending messages that have exceeded idle timeout."""
		try:
			# Get pending messages
			pending = await self.redis_client.xpending_range(
				stream_key,
				self.consumer_group,
				min="-",
				max="+",
				count=100,
			)

			if not pending:
				return

			# Claim messages idle > 60 seconds
			min_idle_time_ms = 60000  # 60 seconds
			message_ids = [msg[b"message_id"] if isinstance(msg, dict) else msg for msg in pending]

			if message_ids:
				claimed = await self.redis_client.xclaim(
					stream_key,
					self.consumer_group,
					self.consumer_name,
					min_idle_time=min_idle_time_ms,
					message_ids=message_ids,
				)

				if claimed:
					logger.debug(f"Claimed {len(claimed)} pending messages from stream {stream_key}")

		except Exception as e:
			logger.debug(f"Error claiming pending messages: {e}")
			# Don't fail on claim errors - continue processing

	async def _process_message(
		self, session_id: str, stream_key: str, message_id: bytes, data: dict[bytes, bytes]
	) -> None:
		"""Process a command message.
		
		Args:
			session_id: Session identifier
			stream_key: Stream key
			message_id: Redis message ID
			data: Message data (bytes dict)
		"""
		try:
			# Parse command envelope from Redis Streams data
			# Commands are stored as individual fields in the stream
			command_data: dict[str, Any] = {}

			for key, value in data.items():
				key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
				val_bytes = value if isinstance(value, bytes) else str(value).encode('utf-8')
				val_str = val_bytes.decode('utf-8')

				# Parse JSON fields
				if key_str in ['command', 'trace_context']:
					try:
						command_data[key_str] = json.loads(val_str)
					except json.JSONDecodeError:
						command_data[key_str] = val_str
				# Parse numeric fields
				elif key_str in ['sequence_number', 'timestamp_ms', 'timeout_ms']:
					try:
						command_data[key_str] = int(val_str)
					except ValueError:
						command_data[key_str] = 0
				# Simple string fields
				else:
					command_data[key_str] = val_str

			command_id = command_data.get("command_id", "")
			session_id_from_cmd = command_data.get("session_id") or command_data.get("room_name", session_id)
			seq_num = command_data.get("sequence_number", 0)
			command = command_data.get("command", {})
			if isinstance(command, str):
				try:
					command = json.loads(command)
				except json.JSONDecodeError:
					command = {}

			action_type = command.get("action_type", "")
			params = command.get("params", {})

			logger.debug(
				f"Processing command {command_id} for session {session_id} "
				f"(seq: {seq_num}, action: {action_type})"
			)

			# Validate sequence number
			is_valid, expected_seq = await self.sequence_tracker.validate_sequence(session_id, seq_num)

			if not is_valid:
				if seq_num < expected_seq:
					# Duplicate (already processed)
					logger.warning(f"Duplicate command {command_id} (seq: {seq_num}, expected: {expected_seq})")
					# Acknowledge to remove from PEL
					await self.redis_client.xack(stream_key, self.consumer_group, message_id)
					return
				else:
					# Gap detected (seq_num > expected)
					logger.error(
						f"Sequence gap detected for session {session_id}: "
						f"received {seq_num}, expected {expected_seq}"
					)
					# TODO: Publish error event requesting retransmission
					# For now, don't acknowledge (allows redelivery)
					return

			# Check deduplication cache
			if await self.dedup_cache.is_processed(command_id):
				logger.warning(f"Command {command_id} already processed (dedup cache hit)")
				# Acknowledge to remove from PEL
				await self.redis_client.xack(stream_key, self.consumer_group, message_id)
				await self.sequence_tracker.update_last_processed(session_id, seq_num)
				return

			# Mark as processing
			await self.dedup_cache.mark_processing(command_id)
			received_at_ms = int(time.time() * 1000)

			try:
				# Execute action via session manager
				# Capture state before action
				session_info = self.session_manager.sessions.get(session_id)
				if not session_info:
					raise ValueError(f"Session not found: {session_id}")

				pre_state = await self.state_diff_engine.capture_state(session_info.browser_session)

				# Execute action
				action_result = await self.session_manager.execute_action(
					session_id,
					action_type,
					params,
				)

				# Capture state after action
				post_state = await self.state_diff_engine.capture_state(session_info.browser_session)

				# Compute state diff
				state_diff = self.state_diff_engine.compute_diff(pre_state, post_state)

				# Publish state update
				await self.state_publisher.publish_state_update(
					room_name=session_id,
					command_id=command_id,
					command_sequence=seq_num,
					action_result=action_result,
					state_diff=state_diff,
					post_state=post_state,
					received_at_ms=received_at_ms,
				)

				# Mark as processed
				await self.dedup_cache.mark_processed(command_id)

				# Acknowledge message
				await self.redis_client.xack(stream_key, self.consumer_group, message_id)

				# Update sequence tracker
				await self.sequence_tracker.update_last_processed(session_id, seq_num)

				logger.debug(f"Successfully processed command {command_id} for session {session_id}")

			except Exception as e:
				logger.error(f"Error processing command {command_id}: {e}", exc_info=True)
				# For transient errors, don't acknowledge (allows redelivery)
				# For permanent errors, acknowledge after publishing error event
				# TODO: Publish error event
				# For now, don't acknowledge on error (allows retry)
				# Remove from processing state
				# await self.dedup_cache.clear_processing(command_id)  # TODO: Add this method

		except Exception as e:
			logger.error(f"Error processing message: {e}", exc_info=True)
			# Don't acknowledge on parsing errors (allows retry)

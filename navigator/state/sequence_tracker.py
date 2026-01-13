"""
Sequence Tracker for Browser Agent

Tracks last processed sequence number per session for command consumption validation.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


class SequenceTracker:
	"""Tracks last processed sequence number per session."""
	
	def __init__(self):
		"""Initialize sequence tracker."""
		self._last_processed: dict[str, int] = {}
		self._lock = asyncio.Lock()
	
	async def get_last_processed(self, session_id: str) -> int:
		"""Get last processed sequence number for session.
		
		Args:
			session_id: Session identifier (room_name)
			
		Returns:
			Last processed sequence number (0 if session not found)
		"""
		async with self._lock:
			return self._last_processed.get(session_id, 0)
	
	async def update_last_processed(self, session_id: str, seq_num: int) -> None:
		"""Update last processed sequence number for session.
		
		Args:
			session_id: Session identifier
			seq_num: Sequence number that was processed
		"""
		async with self._lock:
			current = self._last_processed.get(session_id, 0)
			if seq_num > current:
				self._last_processed[session_id] = seq_num
				logger.debug(f"Updated last processed sequence for {session_id}: {seq_num}")
	
	async def validate_sequence(self, session_id: str, seq_num: int) -> tuple[bool, int | None]:
		"""Validate sequence number matches expected.
		
		Args:
			session_id: Session identifier
			seq_num: Sequence number to validate
			
		Returns:
			Tuple of (is_valid, expected_seq_num)
			- is_valid: True if sequence number matches expected (last_processed + 1)
			- expected_seq_num: Expected sequence number (None if valid)
		"""
		async with self._lock:
			last_processed = self._last_processed.get(session_id, 0)
			expected = last_processed + 1
			
			if seq_num == expected:
				return True, None
			elif seq_num < expected:
				# Duplicate (already processed)
				logger.warning(f"Duplicate sequence number {seq_num} for {session_id} (expected: {expected})")
				return False, expected
			else:
				# Gap detected (seq_num > expected)
				logger.warning(f"Sequence gap detected for {session_id}: received {seq_num}, expected {expected}")
				return False, expected
	
	async def clear_session(self, session_id: str) -> None:
		"""Clear sequence tracking for session.
		
		Args:
			session_id: Session identifier
		"""
		async with self._lock:
			self._last_processed.pop(session_id, None)
			logger.debug(f"Cleared sequence tracking for {session_id}")

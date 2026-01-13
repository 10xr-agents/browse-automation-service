"""
Deduplication Cache for Browser Agent

Tracks processed commands for idempotency (prevents duplicate action execution).
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class DedupCache:
	"""Tracks processed commands for idempotency."""
	
	def __init__(self, ttl_seconds: int = 300):
		"""Initialize deduplication cache.
		
		Args:
			ttl_seconds: Time-to-live for cache entries in seconds (default: 5 minutes)
		"""
		self.ttl_seconds = ttl_seconds
		self._cache: dict[str, tuple[str, float]] = {}  # command_id -> (status, timestamp)
		self._lock = asyncio.Lock()
		self._last_cleanup = time.time()
		self._cleanup_interval = 60.0  # Cleanup every 60 seconds
	
	async def is_processed(self, command_id: str) -> bool:
		"""Check if command already processed.
		
		Args:
			command_id: Command identifier
			
		Returns:
			True if command is marked as processed, False otherwise
		"""
		await self._cleanup_expired()
		
		async with self._lock:
			if command_id not in self._cache:
				return False
			
			status, timestamp = self._cache[command_id]
			
			# Check if expired
			if time.time() - timestamp > self.ttl_seconds:
				del self._cache[command_id]
				return False
			
			return status == "processed"
	
	async def mark_processing(self, command_id: str) -> None:
		"""Mark command as processing.
		
		Args:
			command_id: Command identifier
		"""
		async with self._lock:
			self._cache[command_id] = ("processing", time.time())
			logger.debug(f"Marked command {command_id} as processing")
	
	async def mark_processed(self, command_id: str) -> None:
		"""Mark command as processed.
		
		Args:
			command_id: Command identifier
		"""
		async with self._lock:
			self._cache[command_id] = ("processed", time.time())
			logger.debug(f"Marked command {command_id} as processed")
	
	async def _cleanup_expired(self) -> None:
		"""Clean up expired cache entries."""
		now = time.time()
		
		# Only cleanup every cleanup_interval seconds
		if now - self._last_cleanup < self._cleanup_interval:
			return
		
		async with self._lock:
			expired = [
				command_id
				for command_id, (status, timestamp) in self._cache.items()
				if now - timestamp > self.ttl_seconds
			]
			
			for command_id in expired:
				del self._cache[command_id]
			
			if expired:
				logger.debug(f"Cleaned up {len(expired)} expired cache entries")
			
			self._last_cleanup = now
	
	async def clear(self) -> None:
		"""Clear all cache entries."""
		async with self._lock:
			self._cache.clear()
			logger.debug("Cleared deduplication cache")

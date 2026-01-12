"""
Session Persistence for Presentation Flow

Provides optional Redis-based session persistence for presentation sessions.
Allows sessions to survive service restarts.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class SessionStore:
	"""
	Session persistence store using Redis.
	
	Provides save/load functionality for presentation session state.
	Optional - can be used to persist sessions across service restarts.
	"""
	
	def __init__(self, redis_client: Any, key_prefix: str = "browser:session:"):
		"""
		Initialize the session store.
		
		Args:
			redis_client: Redis client (from redis.asyncio)
			key_prefix: Prefix for Redis keys (default: "browser:session:")
		"""
		self.redis_client = redis_client
		self.key_prefix = key_prefix
		logger.debug(f"SessionStore initialized (prefix: {key_prefix})")
	
	async def save_session(self, session_id: str, session_state: dict[str, Any], ttl: int = 21600) -> None:
		"""
		Save session state to Redis.
		
		Args:
			session_id: Session ID
			session_state: Session state dictionary
			ttl: Time-to-live in seconds (default: 21600 = 6 hours)
		"""
		if not self.redis_client:
			logger.warning("Redis client not available, cannot save session")
			return
		
		try:
			key = f"{self.key_prefix}{session_id}"
			session_json = json.dumps(session_state)
			await self.redis_client.setex(key, ttl, session_json)
			logger.debug(f"Saved session {session_id[:8]}... to Redis (TTL: {ttl}s)")
		except Exception as e:
			logger.error(f"Error saving session {session_id[:8]}... to Redis: {e}", exc_info=True)
			raise
	
	async def load_session(self, session_id: str) -> dict[str, Any] | None:
		"""
		Load session state from Redis.
		
		Args:
			session_id: Session ID
		
		Returns:
			Session state dictionary or None if not found
		"""
		if not self.redis_client:
			logger.warning("Redis client not available, cannot load session")
			return None
		
		try:
			key = f"{self.key_prefix}{session_id}"
			session_json = await self.redis_client.get(key)
			if session_json is None:
				logger.debug(f"Session {session_id[:8]}... not found in Redis")
				return None
			
			if isinstance(session_json, bytes):
				session_json = session_json.decode('utf-8')
			
			session_state = json.loads(session_json)
			logger.debug(f"Loaded session {session_id[:8]}... from Redis")
			return session_state
		except Exception as e:
			logger.error(f"Error loading session {session_id[:8]}... from Redis: {e}", exc_info=True)
			return None
	
	async def delete_session(self, session_id: str) -> None:
		"""
		Delete session from Redis.
		
		Args:
			session_id: Session ID
		"""
		if not self.redis_client:
			logger.warning("Redis client not available, cannot delete session")
			return
		
		try:
			key = f"{self.key_prefix}{session_id}"
			await self.redis_client.delete(key)
			logger.debug(f"Deleted session {session_id[:8]}... from Redis")
		except Exception as e:
			logger.error(f"Error deleting session {session_id[:8]}... from Redis: {e}", exc_info=True)
	
	async def list_sessions(self) -> list[str]:
		"""
		List all session IDs in Redis.
		
		Returns:
			List of session IDs
		"""
		if not self.redis_client:
			logger.warning("Redis client not available, cannot list sessions")
			return []
		
		try:
			pattern = f"{self.key_prefix}*"
			keys = await self.redis_client.keys(pattern)
			# Remove prefix to get session IDs
			session_ids = [key.decode('utf-8').replace(self.key_prefix, '') for key in keys]
			logger.debug(f"Found {len(session_ids)} sessions in Redis")
			return session_ids
		except Exception as e:
			logger.error(f"Error listing sessions from Redis: {e}", exc_info=True)
			return []

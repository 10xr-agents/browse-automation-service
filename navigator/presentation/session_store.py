"""
Session Persistence for Presentation Flow

Provides MongoDB-based session persistence for presentation sessions.
All collections use the 'brwsr_auto_svc_' prefix.
Allows sessions to survive service restarts.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from navigator.storage.mongodb import get_collection

logger = logging.getLogger(__name__)


class SessionStore:
	"""
	Session persistence store using MongoDB.
	
	Provides save/load functionality for presentation session state.
	Optional - can be used to persist sessions across service restarts.
	"""
	
	def __init__(self, use_mongodb: bool = True, default_ttl_hours: int = 6):
		"""
		Initialize the session store.
		
		Args:
			use_mongodb: Whether to use MongoDB (True by default, falls back to in-memory if unavailable)
			default_ttl_hours: Default time-to-live in hours (default: 6 hours)
		"""
		self.use_mongodb = use_mongodb
		self.default_ttl_hours = default_ttl_hours
		self._in_memory_sessions: dict[str, dict[str, Any]] = {}
		
		if use_mongodb:
			logger.info("SessionStore initialized with MongoDB")
		else:
			logger.debug("SessionStore initialized with in-memory storage")
	
	async def save_session(self, session_id: str, session_state: dict[str, Any], ttl: int = 21600) -> None:
		"""
		Save session state to MongoDB.
		
		Args:
			session_id: Session ID
			session_state: Session state dictionary
			ttl: Time-to-live in seconds (default: 21600 = 6 hours)
		"""
		expires_at = datetime.utcnow() + timedelta(seconds=ttl)
		
		session_document = {
			'session_id': session_id,
			'session_state': session_state,
			'expires_at': expires_at,
			'updated_at': datetime.utcnow(),
		}
		
		if self.use_mongodb:
			try:
				collection = await get_collection('sessions')
				if collection is None:
					# Fallback to in-memory
					self._in_memory_sessions[session_id] = {
						'session_state': session_state,
						'expires_at': expires_at,
					}
					logger.debug(f"Saved session {session_id[:8]}... to in-memory (MongoDB unavailable) (TTL: {ttl}s)")
					return
				
				# Upsert by session_id
				await collection.update_one(
					{'session_id': session_id},
					{'$set': session_document},
					upsert=True
				)
				logger.debug(f"Saved session {session_id[:8]}... to MongoDB (TTL: {ttl}s)")
			except Exception as e:
				logger.error(f"Error saving session {session_id[:8]}... to MongoDB: {e}", exc_info=True)
				# Fallback to in-memory
				self._in_memory_sessions[session_id] = {
					'session_state': session_state,
					'expires_at': expires_at,
				}
				logger.debug(f"Saved session {session_id[:8]}... to in-memory (fallback)")
		else:
			self._in_memory_sessions[session_id] = {
				'session_state': session_state,
				'expires_at': expires_at,
			}
			logger.debug(f"Saved session {session_id[:8]}... to in-memory (TTL: {ttl}s)")
	
	async def load_session(self, session_id: str) -> dict[str, Any] | None:
		"""
		Load session state from MongoDB.
		
		Args:
			session_id: Session ID
		
		Returns:
			Session state dictionary or None if not found or expired
		"""
		if self.use_mongodb:
			try:
				collection = await get_collection('sessions')
				if collection is None:
					# Fallback to in-memory
					return self._load_from_memory(session_id)
				
				doc = await collection.find_one({'session_id': session_id})
				if doc is None:
					logger.debug(f"Session {session_id[:8]}... not found in MongoDB")
					return None
				
				# Check expiration
				expires_at = doc.get('expires_at')
				if expires_at and expires_at < datetime.utcnow():
					logger.debug(f"Session {session_id[:8]}... expired")
					await self.delete_session(session_id)
					return None
				
				session_state = doc.get('session_state', {})
				logger.debug(f"Loaded session {session_id[:8]}... from MongoDB")
				return session_state
			except Exception as e:
				logger.error(f"Error loading session {session_id[:8]}... from MongoDB: {e}", exc_info=True)
				# Fallback to in-memory
				return self._load_from_memory(session_id)
		else:
			return self._load_from_memory(session_id)
	
	def _load_from_memory(self, session_id: str) -> dict[str, Any] | None:
		"""Load session from in-memory storage."""
		session_data = self._in_memory_sessions.get(session_id)
		if session_data is None:
			logger.debug(f"Session {session_id[:8]}... not found in in-memory storage")
			return None
		
		# Check expiration
		expires_at = session_data.get('expires_at')
		if expires_at and expires_at < datetime.utcnow():
			logger.debug(f"Session {session_id[:8]}... expired")
			self._in_memory_sessions.pop(session_id, None)
			return None
		
		return session_data.get('session_state')
	
	async def delete_session(self, session_id: str) -> None:
		"""
		Delete session from MongoDB.
		
		Args:
			session_id: Session ID
		"""
		if self.use_mongodb:
			try:
				collection = await get_collection('sessions')
				if collection:
					await collection.delete_one({'session_id': session_id})
					logger.debug(f"Deleted session {session_id[:8]}... from MongoDB")
			except Exception as e:
				logger.error(f"Error deleting session {session_id[:8]}... from MongoDB: {e}", exc_info=True)
		
		# Also delete from in-memory
		self._in_memory_sessions.pop(session_id, None)
		logger.debug(f"Deleted session {session_id[:8]}... from in-memory")
	
	async def list_sessions(self) -> list[str]:
		"""
		List all active session IDs.
		
		Returns:
			List of session IDs
		"""
		if self.use_mongodb:
			try:
				collection = await get_collection('sessions')
				if collection is None:
					# Fallback to in-memory
					return self._list_from_memory()
				
				# Get all non-expired sessions
				now = datetime.utcnow()
				cursor = collection.find({
					'expires_at': {'$gt': now}
				})
				
				session_ids = []
				async for doc in cursor:
					session_ids.append(doc.get('session_id'))
				
				logger.debug(f"Found {len(session_ids)} active sessions in MongoDB")
				return session_ids
			except Exception as e:
				logger.error(f"Error listing sessions from MongoDB: {e}", exc_info=True)
				# Fallback to in-memory
				return self._list_from_memory()
		else:
			return self._list_from_memory()
	
	def _list_from_memory(self) -> list[str]:
		"""List sessions from in-memory storage."""
		now = datetime.utcnow()
		session_ids = [
			session_id for session_id, session_data in self._in_memory_sessions.items()
			if session_data.get('expires_at', datetime.max) > now
		]
		logger.debug(f"Found {len(session_ids)} active sessions in in-memory storage")
		return session_ids
	
	async def cleanup_expired_sessions(self) -> int:
		"""
		Clean up expired sessions from MongoDB.
		
		Returns:
			Number of sessions deleted
		"""
		if self.use_mongodb:
			try:
				collection = await get_collection('sessions')
				if collection:
					now = datetime.utcnow()
					result = await collection.delete_many({
						'expires_at': {'$lt': now}
					})
					deleted_count = result.deleted_count
					logger.debug(f"Cleaned up {deleted_count} expired sessions from MongoDB")
					return deleted_count
			except Exception as e:
				logger.error(f"Error cleaning up expired sessions: {e}", exc_info=True)
		
		# Also clean up in-memory
		now = datetime.utcnow()
		expired_ids = [
			session_id for session_id, session_data in self._in_memory_sessions.items()
			if session_data.get('expires_at', datetime.max) <= now
		]
		for session_id in expired_ids:
			self._in_memory_sessions.pop(session_id, None)
		
		return len(expired_ids)

"""
Presentation Flow Manager

Manages browser automation sessions for presentation/agent flows,
handling session lifecycle, timeouts, and action queue management.
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SessionState(str, Enum):
	"""Session state enumeration."""
	ACTIVE = "active"
	PAUSED = "paused"
	CLOSED = "closed"


class PresentationSession:
	"""Represents a presentation session."""
	
	def __init__(self, session_id: str, room_name: str, created_at: float | None = None):
		self.session_id = session_id
		self.room_name = room_name
		self.state: SessionState = SessionState.ACTIVE
		self.created_at: float = created_at if created_at is not None else time.time()
	
	def __repr__(self) -> str:
		return f"PresentationSession(id={self.session_id[:8]}..., room={self.room_name}, state={self.state.value})"


class PresentationFlowManager:
	"""
	Manages presentation flow sessions for browser automation.
	
	This manager handles:
	- Session lifecycle (start, pause, resume, close)
	- Session state tracking
	- Session timeout management (6 hours default)
	"""
	
	def __init__(
		self, 
		timeout_minutes: int = 360, 
		command_queue: Any | None = None,
		browser_session_manager: Any | None = None,
	):
		"""
		Initialize the presentation flow manager.
		
		Args:
			timeout_minutes: Session timeout in minutes (default: 360 = 6 hours)
			command_queue: Optional BullMQ Queue for command processing. If None, uses in-memory queue.
			browser_session_manager: Optional BrowserSessionManager instance. If None, will create one.
		"""
		self.sessions: dict[str, PresentationSession] = {}
		self.timeout_minutes = timeout_minutes
		self.timeout_seconds = timeout_minutes * 60
		self._cleanup_task: asyncio.Task[Any] | None = None
		self._shutdown = False
		self.command_queue = command_queue
		self._queue_workers: dict[str, Any] = {}  # session_id -> worker
		
		# Browser session manager integration
		if browser_session_manager is None:
			from navigator.session.manager import BrowserSessionManager
			from navigator.streaming.broadcaster import EventBroadcaster
			# Create browser session manager with event broadcaster
			self.browser_session_manager = BrowserSessionManager(event_broadcaster=EventBroadcaster())
		else:
			self.browser_session_manager = browser_session_manager
		
		logger.debug(f"PresentationFlowManager initialized (timeout: {timeout_minutes} minutes, queue: {'BullMQ' if command_queue else 'in-memory'})")
	
	async def start_session(self, room_name: str, session_id: str | None = None) -> str:
		"""
		Start a new presentation session.
		
		Args:
			room_name: Name of the room/agent session
			session_id: Optional session ID (generated if not provided)
		
		Returns:
			Session ID
		"""
		from uuid_extensions import uuid7str
		
		if session_id is None:
			session_id = uuid7str()
		
		if session_id in self.sessions:
			raise ValueError(f"Session {session_id} already exists")
		
		session = PresentationSession(session_id=session_id, room_name=room_name)
		self.sessions[session_id] = session
		
		# Start cleanup task if not already running
		if self._cleanup_task is None or self._cleanup_task.done():
			from browser_use.utils import create_task_with_error_handling
			self._cleanup_task = create_task_with_error_handling(
				self._cleanup_loop(), 
				name='presentation_cleanup_loop', 
				suppress_exceptions=True
			)
		
		logger.info(f"Started presentation session: {session_id[:8]}... (room: {room_name}, timeout: {self.timeout_minutes} minutes)")
		return session_id
	
	async def close_session(self, session_id: str) -> None:
		"""
		Close a presentation session.
		
		Args:
			session_id: Session ID to close
		"""
		if session_id not in self.sessions:
			logger.warning(f"Attempted to close non-existent session: {session_id[:8]}...")
			return
		
		session = self.sessions[session_id]
		session.state = SessionState.CLOSED
		
		# Close browser session if exists
		room_name = session.room_name
		if self.browser_session_manager:
			browser_session = self.browser_session_manager.get_session(room_name)
			if browser_session:
				try:
					await self.browser_session_manager.close_session(room_name)
					logger.debug(f"Closed browser session for room: {room_name}")
				except Exception as e:
					logger.error(f"Error closing browser session for room {room_name}: {e}", exc_info=True)
		
		# Stop queue worker if exists
		if session_id in self._queue_workers:
			try:
				worker = self._queue_workers[session_id]
				if hasattr(worker, 'close'):
					await worker.close()
				del self._queue_workers[session_id]
			except Exception as e:
				logger.error(f"Error closing queue worker for session {session_id[:8]}...: {e}", exc_info=True)
		
		# Remove from active sessions
		del self.sessions[session_id]
		
		logger.info(f"Closed presentation session: {session_id[:8]}... (room: {session.room_name})")
	
	def get_session(self, session_id: str) -> PresentationSession | None:
		"""
		Get a session by ID.
		
		Args:
			session_id: Session ID
		
		Returns:
			PresentationSession or None if not found
		"""
		return self.sessions.get(session_id)
	
	def has_session(self, session_id: str) -> bool:
		"""
		Check if a session exists.
		
		Args:
			session_id: Session ID
		
		Returns:
			True if session exists, False otherwise
		"""
		return session_id in self.sessions
	
	def list_sessions(self) -> list[PresentationSession]:
		"""
		List all active sessions.
		
		Returns:
			List of PresentationSession objects
		"""
		return list(self.sessions.values())
	
	def get_browser_session(self, session_id: str) -> Any | None:
		"""
		Get browser session for a presentation session.
		
		Args:
			session_id: Presentation session ID
		
		Returns:
			BrowserSessionInfo or None if not found
		"""
		session = self.get_session(session_id)
		if not session:
			return None
		
		if self.browser_session_manager:
			return self.browser_session_manager.get_session(session.room_name)
		return None
	
	async def _cleanup_expired_sessions(self) -> None:
		"""Check for and clean up expired sessions."""
		if self._shutdown:
			return
		
		current_time = time.time()
		expired_sessions = []
		
		for session_id, session in list(self.sessions.items()):
			elapsed = current_time - session.created_at
			if elapsed > self.timeout_seconds:
				expired_sessions.append(session_id)
		
		for session_id in expired_sessions:
			try:
				logger.info(f"Session {session_id[:8]}... expired (timeout: {self.timeout_minutes} minutes)")
				await self.close_session(session_id)
			except Exception as e:
				logger.error(f"Error closing expired session {session_id[:8]}...: {e}", exc_info=True)
	
	async def _cleanup_loop(self) -> None:
		"""Background task loop to periodically clean up expired sessions."""
		logger.debug("Started timeout cleanup loop")
		while not self._shutdown:
			try:
				await self._cleanup_expired_sessions()
				# Check every 2 minutes
				await asyncio.sleep(120)
			except asyncio.CancelledError:
				logger.debug("Cleanup loop cancelled")
				break
			except Exception as e:
				logger.error(f"Error in cleanup loop: {e}", exc_info=True)
				await asyncio.sleep(120)
	
	async def enqueue_action(self, session_id: str, action: dict[str, Any]) -> None:
		"""
		Enqueue an action for a session.
		
		Args:
			session_id: Session ID
			action: Action data (dict with type and params)
		"""
		if session_id not in self.sessions:
			raise ValueError(f"Session {session_id} does not exist")
		
		if self.command_queue:
			# Use BullMQ queue
			try:
				from bullmq.types import JobOptions
				job_id = f"{session_id}_{int(time.time() * 1000)}"
				await self.command_queue.add(
					"browser_action",
					{"session_id": session_id, "action": action},
					job_id=job_id,
					opts=JobOptions(removeOnComplete=True, attempts=3)
				)
				logger.debug(f"Enqueued action via BullMQ for session {session_id[:8]}...")
			except ImportError:
				logger.error("BullMQ not available. Install with: uv add bullmq")
				raise
		else:
			# In-memory queue (for development/testing)
			if not hasattr(self, '_in_memory_queue'):
				self._in_memory_queue: dict[str, list[dict[str, Any]]] = {}
			if session_id not in self._in_memory_queue:
				self._in_memory_queue[session_id] = []
			self._in_memory_queue[session_id].append(action)
			logger.debug(f"Enqueued action in-memory for session {session_id[:8]}...")
	
	async def process_queue(self, session_id: str) -> None:
		"""
		Process queued actions for a session (starts worker if using BullMQ).
		
		Args:
			session_id: Session ID
		"""
		if session_id not in self.sessions:
			raise ValueError(f"Session {session_id} does not exist")
		
		if self.command_queue:
			# BullMQ queue processing
			try:
				from bullmq import QueueWorker
				
				# Create worker if not exists
				if session_id not in self._queue_workers:
					async def processor(job: Any):
						"""Process a job from the queue."""
						data = job.data
						if data.get("session_id") == session_id:
							action = data.get("action", {})
							logger.debug(f"Processing action from queue: {action.get('type')} for session {session_id[:8]}...")
							# Action execution will be handled by integration with ActionDispatcher
							# This is a placeholder - actual execution happens in Step 1.4
							return {"processed": True, "action": action}
						return {"skipped": True}
					
					worker = QueueWorker(
						"browser_commands",
						processor,
						{
							"concurrency": 1,
							"limiter": {"max": 1, "duration": 1000}
						}
					)
					self._queue_workers[session_id] = worker
					logger.debug(f"Created BullMQ worker for session {session_id[:8]}...")
			except ImportError:
				logger.error("BullMQ not available. Install with: uv add bullmq")
				raise
		else:
			# In-memory queue processing
			if hasattr(self, '_in_memory_queue') and session_id in self._in_memory_queue:
				queue = self._in_memory_queue[session_id]
				logger.debug(f"Processing {len(queue)} actions from in-memory queue for session {session_id[:8]}...")
				# Clear queue after processing (actual execution happens in Step 1.4)
				self._in_memory_queue[session_id] = []
	
	async def shutdown(self) -> None:
		"""Shutdown the flow manager and stop background tasks."""
		logger.debug("Shutting down PresentationFlowManager")
		self._shutdown = True
		
		# Stop queue workers
		for session_id, worker in list(self._queue_workers.items()):
			try:
				if hasattr(worker, 'close'):
					await worker.close()
			except Exception as e:
				logger.error(f"Error closing queue worker for session {session_id[:8]}...: {e}", exc_info=True)
		self._queue_workers.clear()
		
		# Cancel cleanup task
		if self._cleanup_task and not self._cleanup_task.done():
			self._cleanup_task.cancel()
			try:
				await self._cleanup_task
			except asyncio.CancelledError:
				pass
		
		# Close all sessions
		for session_id in list(self.sessions.keys()):
			try:
				await self.close_session(session_id)
			except Exception as e:
				logger.error(f"Error closing session during shutdown: {e}", exc_info=True)

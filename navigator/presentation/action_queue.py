"""
Action Queue Management for Presentation Flow

Provides reliable action queue using BullMQ (with in-memory fallback).
Handles action queuing, processing, rate limiting, and retry logic.
"""

import asyncio
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ActionQueue:
	"""
	Action queue for reliable action processing.
	
	Supports BullMQ for persistent queues (requires Redis) or in-memory queues for development.
	Provides rate limiting and retry logic with exponential backoff.
	"""
	
	def __init__(
		self,
		queue: Any | None = None,
		max_actions_per_second: int | None = None,
		max_retries: int = 3,
		retry_backoff_base: float = 2.0,
		action_processor: Callable[[dict[str, Any]], Any] | None = None,
	):
		"""
		Initialize the action queue.
		
		Args:
			queue: Optional BullMQ Queue instance. If None, uses in-memory queue.
			max_actions_per_second: Optional rate limit (max actions per second). If None, no rate limiting.
			max_retries: Maximum number of retries for failed actions (default: 3)
			retry_backoff_base: Base for exponential backoff (default: 2.0)
			action_processor: Optional callback function to process actions. If None, actions are just queued.
		"""
		self.queue = queue
		self.max_actions_per_second = max_actions_per_second
		self.max_retries = max_retries
		self.retry_backoff_base = retry_backoff_base
		self.action_processor = action_processor
		
		# Rate limiting
		if max_actions_per_second:
			self._rate_limiter = asyncio.Semaphore(max_actions_per_second)
			self._min_delay = 1.0 / max_actions_per_second
		else:
			self._rate_limiter = None
			self._min_delay = 0.0
		
		# In-memory queue (fallback)
		self._in_memory_queue: list[dict[str, Any]] = []
		self._in_memory_processing = False
		self._failed_actions: dict[str, int] = {}  # job_id -> retry_count
		
		# Worker tracking (for BullMQ)
		self._worker: Any | None = None
		
		logger.debug(
			f"ActionQueue initialized (queue: {'BullMQ' if queue else 'in-memory'}, "
			f"rate_limit: {max_actions_per_second}, max_retries: {max_retries})"
		)
	
	async def enqueue_action(
		self,
		action: dict[str, Any],
		job_id: str | None = None,
		priority: int = 0,
		delay: float = 0.0,
	) -> str:
		"""
		Enqueue an action for processing.
		
		Args:
			action: Action data (dict with type and params)
			job_id: Optional job ID. If None, generates one.
			priority: Job priority (higher = processed first, default: 0)
			delay: Delay in seconds before processing (default: 0.0)
		
		Returns:
			Job ID
		"""
		if job_id is None:
			job_id = f"action_{int(time.time() * 1000)}"
		
		if self.queue:
			# Use BullMQ queue
			try:
				from bullmq.types import JobOptions
				
				opts = JobOptions(
					removeOnComplete=True,
					attempts=self.max_retries + 1,  # attempts includes initial try
					priority=priority,
					delay=int(delay * 1000) if delay > 0 else None,
				)
				
				await self.queue.add(
					"browser_action",
					action,
					job_id=job_id,
					opts=opts,
				)
				logger.debug(f"Enqueued action via BullMQ: {job_id}")
				return job_id
			except ImportError:
				logger.warning("BullMQ not available, falling back to in-memory queue")
				# Fall through to in-memory queue
		
		# In-memory queue (fallback or no queue provided)
		self._in_memory_queue.append({
			"job_id": job_id,
			"action": action,
			"priority": priority,
			"delay": delay,
			"enqueued_at": time.time(),
		})
		logger.debug(f"Enqueued action in-memory: {job_id}")
		return job_id
	
	async def process_queue(self) -> list[dict[str, Any]]:
		"""
		Process queued actions.
		
		For BullMQ: Starts a worker if not already running.
		For in-memory: Processes all queued actions.
		
		Returns:
			List of processing results
		"""
		if self.queue:
			# BullMQ queue processing
			try:
				from bullmq import QueueWorker
				
				if self._worker is None:
					# Create worker
					async def processor(job: Any):
						"""Process a job from the queue."""
						action = job.data
						job_id = job.id
						
						logger.debug(f"Processing action from BullMQ queue: {job_id}")
						
						# Apply rate limiting
						if self._rate_limiter:
							async with self._rate_limiter:
								await asyncio.sleep(self._min_delay)
								result = await self._process_action(action, job_id)
						else:
							result = await self._process_action(action, job_id)
						
						return result
					
					self._worker = QueueWorker(
						"browser_actions",
						processor,
						{
							"concurrency": 1,
							"limiter": {"max": self.max_actions_per_second or 1, "duration": 1000} if self.max_actions_per_second else None,
						}
					)
					logger.debug("Started BullMQ worker")
				
				# Worker is already running, return empty results (processing happens in background)
				return []
			except ImportError:
				logger.warning("BullMQ not available, falling back to in-memory processing")
				# Fall through to in-memory processing
		
		# In-memory queue processing
		if self._in_memory_processing:
			logger.debug("Queue processing already in progress")
			return []
		
		self._in_memory_processing = True
		results = []
		
		try:
			# Sort by priority (higher first) and delay
			sorted_queue = sorted(
				self._in_memory_queue,
				key=lambda x: (x["priority"], -x.get("enqueued_at", 0)),
				reverse=True,
			)
			
			for item in sorted_queue:
				job_id = item["job_id"]
				action = item["action"]
				delay = item.get("delay", 0.0)
				
				# Apply delay if specified
				if delay > 0:
					await asyncio.sleep(delay)
				
				# Apply rate limiting
				if self._rate_limiter:
					async with self._rate_limiter:
						await asyncio.sleep(self._min_delay)
						result = await self._process_action(action, job_id)
				else:
					result = await self._process_action(action, job_id)
				
				results.append(result)
			
			# Clear processed items
			self._in_memory_queue = []
			
		finally:
			self._in_memory_processing = False
		
		return results
	
	async def _process_action(self, action: dict[str, Any], job_id: str) -> dict[str, Any]:
		"""
		Process a single action with retry logic.
		
		Args:
			action: Action data
			job_id: Job ID
		
		Returns:
			Processing result
		"""
		retry_count = self._failed_actions.get(job_id, 0)
		
		try:
			if self.action_processor:
				result = await self.action_processor(action)
				# Clear failed count on success
				if job_id in self._failed_actions:
					del self._failed_actions[job_id]
				return {"success": True, "job_id": job_id, "result": result}
			else:
				# No processor, just return success
				return {"success": True, "job_id": job_id, "action": action}
		
		except Exception as e:
			logger.error(f"Error processing action {job_id}: {e}", exc_info=True)
			
			# Check if we should retry
			if retry_count < self.max_retries:
				retry_count += 1
				self._failed_actions[job_id] = retry_count
				
				# Calculate exponential backoff delay
				backoff_delay = self.retry_backoff_base ** retry_count
				
				logger.debug(f"Retrying action {job_id} (attempt {retry_count}/{self.max_retries}) after {backoff_delay}s")
				await asyncio.sleep(backoff_delay)
				
				# Retry the action
				return await self._process_action(action, job_id)
			else:
				# Max retries reached
				logger.error(f"Action {job_id} failed after {self.max_retries} retries")
				return {
					"success": False,
					"job_id": job_id,
					"error": str(e),
					"retries": retry_count,
				}
	
	async def close(self) -> None:
		"""Close the queue and stop processing."""
		if self._worker:
			try:
				if hasattr(self._worker, 'close'):
					await self._worker.close()
			except Exception as e:
				logger.error(f"Error closing BullMQ worker: {e}", exc_info=True)
			self._worker = None
		
		logger.debug("ActionQueue closed")

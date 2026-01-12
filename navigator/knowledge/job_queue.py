"""
BullMQ Job Queue Integration for Knowledge Retrieval

Provides durable job queue for long-running knowledge retrieval tasks.
"""

import logging
from typing import Any

try:
	from bullmq import Job, Queue, Worker
	from redis.asyncio import Redis

	BULLMQ_AVAILABLE = True
except ImportError:
	BULLMQ_AVAILABLE = False
	logging.warning('BullMQ not installed. Install with: pip install bullmq redis')

logger = logging.getLogger(__name__)

# Global queue and worker instances
_knowledge_queue: Queue | None = None
_knowledge_worker: Worker | None = None
_redis_client: Redis | None = None


async def get_redis_client() -> Redis | None:
	"""Get or create Redis client."""
	global _redis_client
	if _redis_client is None:
		try:
			from redis.asyncio import Redis
			_redis_client = Redis.from_url("redis://localhost:6379", decode_responses=False)
			await _redis_client.ping()
			logger.info("Redis client connected")
			return _redis_client
		except Exception as e:
			logger.warning(f"Redis not available: {e}")
			return None
	return _redis_client


async def get_knowledge_queue() -> Queue | None:
	"""
	Get or create BullMQ queue for knowledge retrieval jobs.
	
	Returns:
		Queue instance or None if BullMQ not available
	"""
	global _knowledge_queue
	
	if not BULLMQ_AVAILABLE:
		return None
	
	if _knowledge_queue is None:
		redis_client = await get_redis_client()
		if redis_client is None:
			return None
		
		# BullMQ Queue initialization - use connection string
		_knowledge_queue = Queue("knowledge-retrieval", connection="redis://localhost:6379")
		logger.info("BullMQ knowledge retrieval queue created")
	
	return _knowledge_queue


async def add_exploration_job(
	start_url: str,
	max_pages: int | None = None,
	max_depth: int = 3,
	strategy: str = "BFS",
	job_id: str | None = None,
) -> str:
	"""
	Add a knowledge retrieval job to the queue.
	
	Args:
		start_url: Starting URL for exploration
		max_pages: Maximum number of pages to explore
		max_depth: Maximum exploration depth
		strategy: Exploration strategy (BFS or DFS)
		job_id: Optional job ID (auto-generated if None)
	
	Returns:
		Job ID
	"""
	from uuid_extensions import uuid7str
	
	if not job_id:
		job_id = uuid7str()
	
	queue = await get_knowledge_queue()
	if queue is None:
		raise RuntimeError("BullMQ queue not available. Install bullmq and redis.")
	
	job_data = {
		'start_url': start_url,
		'max_pages': max_pages,
		'max_depth': max_depth,
		'strategy': strategy,
		'job_id': job_id,
	}
	
	job = await queue.add(f"explore-{job_id}", job_data, {
		'jobId': job_id,
		'removeOnComplete': False,  # Keep completed jobs for inspection
		'removeOnFail': False,  # Keep failed jobs for debugging
	})
	
	logger.info(f"Added exploration job to queue: {job_id}")
	return job_id


async def start_knowledge_worker(
	pipeline_factory: callable,
) -> Worker | None:
	"""
	Start BullMQ worker to process knowledge retrieval jobs.
	
	Args:
		pipeline_factory: Factory function to create KnowledgePipeline instances
	
	Returns:
		Worker instance or None if BullMQ not available
	"""
	global _knowledge_worker
	
	if not BULLMQ_AVAILABLE:
		return None
	
	if _knowledge_worker is not None:
		logger.warning("Knowledge worker already started")
		return _knowledge_worker
	
	redis_client = await get_redis_client()
	if redis_client is None:
		return None
	
	async def process_job(job: Job):
		"""Process a knowledge retrieval job."""
		job_data = job.data
		job_id = job_data.get('job_id') or job.id
		start_url = job_data.get('start_url')
		max_pages = job_data.get('max_pages')
		max_depth = job_data.get('max_depth', 3)
		strategy_str = job_data.get('strategy', 'BFS')
		
		logger.info(f"Processing knowledge retrieval job: {job_id}")
		
		try:
			# Create pipeline
			pipeline = pipeline_factory()
			
			# Map strategy string to enum
			from navigator.knowledge.pipeline import ExplorationStrategy
			strategy = ExplorationStrategy.BFS if strategy_str.upper() == 'BFS' else ExplorationStrategy.DFS
			
			# Update pipeline strategy if needed
			pipeline.exploration_engine.strategy = strategy
			pipeline.exploration_engine.max_depth = max_depth
			
			# Run exploration
			result = await pipeline.explore_and_store(
				start_url=start_url,
				max_pages=max_pages,
				job_id=job_id,
			)
			
			# Store result in job data
			await job.updateData({
				**job_data,
				'result': result,
				'status': 'completed' if result.get('error') is None else 'failed',
			})
			
			logger.info(f"Job {job_id} completed: {result.get('pages_stored', 0)} pages stored")
			return result
			
		except Exception as e:
			logger.error(f"Job {job_id} failed: {e}", exc_info=True)
			await job.updateData({
				**job_data,
				'status': 'failed',
				'error': str(e),
			})
			raise
	
	# BullMQ Worker initialization - use connection string
	_knowledge_worker = Worker(
		"knowledge-retrieval",
		process_job,
		connection="redis://localhost:6379",
		opts={
			'concurrency': 1,  # Process one job at a time (browser sessions are resource-intensive)
		},
	)
	
	logger.info("Knowledge retrieval worker started")
	return _knowledge_worker


async def stop_knowledge_worker():
	"""Stop the knowledge retrieval worker."""
	global _knowledge_worker
	if _knowledge_worker:
		await _knowledge_worker.close()
		_knowledge_worker = None
		logger.info("Knowledge retrieval worker stopped")


async def get_job_status(job_id: str) -> dict[str, Any] | None:
	"""
	Get status of a job from the queue.
	
	Args:
		job_id: Job ID
	
	Returns:
		Job status dictionary or None if not found
	"""
	queue = await get_knowledge_queue()
	if queue is None:
		return None
	
	try:
		# BullMQ uses getJob method (check if available)
		if hasattr(queue, 'getJob'):
			job = await queue.getJob(job_id)
		else:
			# Alternative: get job by ID from Redis directly
			job = None
		if job is None:
			return None
		
		job_data = job.data
		job_state = await job.getState()
		
		return {
			'job_id': job_id,
			'status': job_state,
			'data': job_data,
			'progress': job.progress if hasattr(job, 'progress') else None,
		}
	except Exception as e:
		logger.error(f"Failed to get job status: {e}")
		return None


async def close_connections():
	"""Close all queue and Redis connections."""
	global _knowledge_queue, _knowledge_worker, _redis_client
	
	if _knowledge_worker:
		await stop_knowledge_worker()
	
	if _knowledge_queue:
		await _knowledge_queue.close()
		_knowledge_queue = None
	
	if _redis_client:
		await _redis_client.close()
		_redis_client = None
	
	logger.info("All queue connections closed")

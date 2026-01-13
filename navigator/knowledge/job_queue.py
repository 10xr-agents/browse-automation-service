"""
RQ (Redis Queue) Job Queue Integration for Knowledge Retrieval

Provides durable job queue for long-running knowledge retrieval tasks using RQ.
RQ workers run as separate processes (not inline with the API server).
"""

import logging
import os
from typing import Any

try:
	import rq
	from rq import Queue, Retry
	from rq.job import Job as RQJob
	from redis import Redis

	RQ_AVAILABLE = True
except ImportError:
	RQ_AVAILABLE = False
	logging.warning('RQ not installed. Install with: pip install rq redis')

logger = logging.getLogger(__name__)

# Global queue instance
_knowledge_queue: Queue | None = None
_redis_client: Redis | None = None


def get_redis_url() -> str:
	"""
	Get Redis URL from environment variable.
	
	Returns:
		Redis URL string (raises ValueError if not set)
	
	Raises:
		ValueError: If REDIS_URL is not set
	"""
	redis_url = os.getenv("REDIS_URL")
	if not redis_url:
		raise ValueError(
			"Redis connection URL not found. "
			"Please set REDIS_URL in your .env.local file."
		)
	return redis_url


def get_redis_client() -> Redis | None:
	"""
	Get or create Redis client for RQ.
	
	Note: RQ requires decode_responses=False because it stores binary data (pickled objects)
	in Redis. RQ handles encoding/decoding internally.
	"""
	global _redis_client
	if _redis_client is None:
		try:
			redis_url = get_redis_url()
			# RQ does NOT support decode_responses=True - it needs binary mode for pickled data
			_redis_client = Redis.from_url(redis_url, decode_responses=False)
			_redis_client.ping()
			logger.info(f"Redis client connected to {redis_url}")
			return _redis_client
		except Exception as e:
			logger.warning(f"Redis not available: {e}")
			return None
	return _redis_client


def get_knowledge_queue() -> Queue | None:
	"""
	Get or create RQ queue for knowledge retrieval jobs.
	
	Returns:
		Queue instance or None if RQ not available
	"""
	global _knowledge_queue
	
	if not RQ_AVAILABLE:
		return None
	
	if _knowledge_queue is None:
		redis_client = get_redis_client()
		if redis_client is None:
			return None
		
		_knowledge_queue = Queue("knowledge-retrieval", connection=redis_client)
		logger.info("RQ knowledge retrieval queue created")
	
	return _knowledge_queue


def add_exploration_job(
	start_url: str,
	max_pages: int | None = None,
	max_depth: int = 3,
	strategy: str = "BFS",
	job_id: str | None = None,
	include_paths: list[str] | None = None,
	exclude_paths: list[str] | None = None,
	authentication: dict[str, Any] | None = None,
) -> str:
	"""
	Add a knowledge retrieval job to the RQ queue.
	
	Args:
		start_url: Starting URL for exploration
		max_pages: Maximum number of pages to explore
		max_depth: Maximum exploration depth
		strategy: Exploration strategy (BFS or DFS)
		job_id: Optional job ID (auto-generated if None)
		include_paths: Path patterns to include
		exclude_paths: Path patterns to exclude
		authentication: Optional authentication dict (never logged or persisted)
	
	Returns:
		RQ Job ID (string)
	"""
	from uuid_extensions import uuid7str
	
	if not job_id:
		job_id = uuid7str()
	
	queue = get_knowledge_queue()
	if queue is None:
		raise RuntimeError("RQ queue not available. Install rq and redis.")
	
	job_data = {
		'start_url': start_url,
		'max_pages': max_pages,
		'max_depth': max_depth,
		'strategy': strategy,
		'job_id': job_id,
		'include_paths': include_paths,
		'exclude_paths': exclude_paths,
		'authentication': authentication,  # Authentication passed to worker (never logged)
	}
	
	# Enqueue job with RQ
	# RQ uses job_id parameter to set custom job ID
	# Use string path format that RQ can parse correctly
	# Format: 'module.path.function_name' (using dot, not colon)
	try:
		# Use string path with dot format (not colon) - RQ will import it correctly
		# The function is defined in this file below, so the path is correct
		rq_job = queue.enqueue(
			'navigator.knowledge.job_queue.process_knowledge_job',  # String path with dot format
			job_data,
			job_id=job_id,  # Use our custom job ID
			retry=Retry(max=3, interval=60),  # Retry up to 3 times with 60s delay
			job_timeout='1h',  # Long-running jobs can take up to 1 hour
		)
		
		logger.info(f"📋 Added job to RQ queue: {job_id}")
		logger.info(f"   Queue: knowledge-retrieval")
		logger.info(f"   RQ Job ID: {rq_job.id}")
		logger.info(f"   Job will be processed by RQ worker process")
		logger.info(f"   ⚠️  Make sure RQ worker is running: rq worker knowledge-retrieval")
		logger.info(f"   Or use: uv run python navigator/knowledge/worker.py")
		
		return rq_job.id
	except Exception as e:
		logger.error(f"Failed to enqueue job: {e}", exc_info=True)
		raise


def process_knowledge_job(job_data: dict[str, Any]) -> dict[str, Any]:
	"""
	Process a knowledge retrieval job.
	
	This function is called by RQ worker processes (separate from API server).
	
	Args:
		job_data: Job data dictionary
	
	Returns:
		Result dictionary
	"""
	import asyncio
	from dotenv import load_dotenv
	import os
	
	# Load environment variables in worker process
	# This ensures MongoDB and Redis configs are available
	load_dotenv(dotenv_path='.env.local', override=False)
	load_dotenv(override=True)
	
	from navigator.knowledge.job_registry import get_job_registry
	from browser_use import BrowserSession
	
	job_id = job_data.get('job_id')
	start_url = job_data.get('start_url')
	max_pages = job_data.get('max_pages')
	max_depth = job_data.get('max_depth', 3)
	strategy_str = job_data.get('strategy', 'BFS')
	include_paths = job_data.get('include_paths')
	exclude_paths = job_data.get('exclude_paths')
	authentication_dict = job_data.get('authentication')  # Authentication dict (never logged)
	
	logger.info("=" * 80)
	logger.info(f"🎯 [RQ Worker] Job received from queue!")
	logger.info(f"   Job ID: {job_id}")
	logger.info(f"   Start URL: {start_url}")
	logger.info(f"   Strategy: {strategy_str}, Max Depth: {max_depth}, Max Pages: {max_pages or 'unlimited'}")
	if include_paths:
		logger.info(f"   Include paths: {include_paths}")
	if exclude_paths:
		logger.info(f"   Exclude paths: {exclude_paths}")
	logger.info("=" * 80)
	
	# Update job status to running
	async def update_and_process():
		job_registry = await get_job_registry()
		await job_registry.update_job(job_id, {'status': 'running'})
		
		# Create browser session for this job
		# Use headless mode for worker processes
		browser_session = BrowserSession(headless=True)
		await browser_session.start()
		
		try:
			# Import pipeline factory
			from navigator.knowledge.pipeline import KnowledgePipeline
			
			# Map strategy string to enum
			from navigator.knowledge.exploration_engine import ExplorationStrategy
			strategy = ExplorationStrategy.BFS if strategy_str.upper() == 'BFS' else ExplorationStrategy.DFS
			
			# Create pipeline with browser session
			pipeline = KnowledgePipeline(
				browser_session=browser_session,
				max_depth=max_depth,
				strategy=strategy,
				include_paths=include_paths,
				exclude_paths=exclude_paths,
			)
			
			# Perform login if authentication provided
			credentials = None
			auth_service = None
			if authentication_dict:
				from navigator.knowledge.auth_service import AuthenticationService, Credentials
				auth_service = AuthenticationService(browser_session)
				credentials = Credentials(
					username=authentication_dict['username'],
					password=authentication_dict['password'],
					login_url=None,  # Auto-detect login URL from start_url
				)
				
				# Navigate to start URL first to detect login page
				from navigator.action.command import NavigateActionCommand
				from navigator.action.dispatcher import ActionDispatcher
				action_dispatcher = ActionDispatcher(browser_session)
				navigate_action = NavigateActionCommand(params={'url': start_url})
				await action_dispatcher.execute_action(navigate_action)
				await asyncio.sleep(2)  # Wait for page load
				
				# Attempt login
				logger.info(f"🔐 [Job {job_id}] Attempting login with provided authentication")
				login_result = await auth_service.perform_login(credentials)
				
				if login_result['success']:
					logger.info(f"✅ [Job {job_id}] Login successful: {login_result.get('logged_in_url')}")
				else:
					logger.warning(f"⚠️  [Job {job_id}] Login failed: {login_result.get('error')}")
					# Continue with unauthenticated exploration (or fail based on configuration)
					# For now, we'll continue and let the user decide based on results
			
			# Run exploration
			logger.info(f"📊 Starting exploration pipeline for job {job_id}")
			result = await pipeline.explore_and_store(
				start_url=start_url,
				max_pages=max_pages,
				job_id=job_id,
			)
			
			# Add login status to results if authentication was provided
			if authentication_dict and auth_service:
				result['authentication_attempted'] = True
				result['authentication_success'] = auth_service.authenticated
			
			# Update job with results
			await job_registry.update_job(job_id, {
				'results': result,
				'status': 'completed' if result.get('error') is None else 'failed',
			})
			
			pages_stored = result.get('pages_stored', 0)
			pages_processed = result.get('pages_processed', 0)
			pages_failed = result.get('pages_failed', 0)
			external_links = result.get('external_links_detected', 0)
			
			logger.info("=" * 80)
			logger.info(f"✅ Job {job_id} completed successfully")
			logger.info(f"   Pages stored: {pages_stored}")
			logger.info(f"   Pages processed: {pages_processed}")
			logger.info(f"   Pages failed: {pages_failed}")
			logger.info(f"   External links detected: {external_links}")
			logger.info("=" * 80)
			
			return result
		finally:
			# Always close browser session
			try:
				await browser_session.close()
			except Exception as e:
				logger.warning(f"Error closing browser session: {e}")
	
	try:
		# Run async function in sync context (RQ workers run sync code)
		loop = asyncio.new_event_loop()
		asyncio.set_event_loop(loop)
		try:
			result = loop.run_until_complete(update_and_process())
			return result
		finally:
			loop.close()
	except Exception as e:
		logger.error("=" * 80)
		logger.error(f"❌ Job {job_id} failed with error: {e}")
		logger.error(f"   Error type: {type(e).__name__}")
		logger.error("=" * 80, exc_info=True)
		
		# Update job status to failed
		try:
			error_loop = asyncio.new_event_loop()
			asyncio.set_event_loop(error_loop)
			try:
				job_registry = error_loop.run_until_complete(get_job_registry())
				error_loop.run_until_complete(job_registry.update_job(job_id, {
					'status': 'failed',
					'error': str(e),
				}))
			finally:
				error_loop.close()
		except Exception as update_error:
			logger.error(f"Failed to update job status: {update_error}")
		
		raise  # Re-raise to mark job as failed in RQ


def get_job_status(job_id: str) -> dict[str, Any] | None:
	"""
	Get status of a job from RQ.
	
	Args:
		job_id: Job ID
	
	Returns:
		Job status dictionary or None if not found
	"""
	if not RQ_AVAILABLE:
		return None
	
	try:
		redis_client = get_redis_client()
		if redis_client is None:
			return None
		
		# Get job from RQ
		try:
			rq_job = RQJob.fetch(job_id, connection=redis_client)
		except Exception:
			# Job not found in RQ
			return None
		
		# Map RQ job status to our status format
		status_map = {
			'queued': 'queued',
			'started': 'running',
			'finished': 'completed',
			'failed': 'failed',
			'deferred': 'pending',
			'scheduled': 'pending',
		}
		
		rq_status = rq_job.get_status()
		status = status_map.get(rq_status, rq_status)
		
		return {
			'job_id': job_id,
			'status': status,
			'rq_status': rq_status,
			'result': rq_job.result if rq_status == 'finished' else None,
			'exc_info': str(rq_job.exc_info) if rq_status == 'failed' and rq_job.exc_info else None,
		}
	except Exception as e:
		logger.error(f"Failed to get job status: {e}")
		return None


def close_connections():
	"""Close all queue and Redis connections."""
	global _knowledge_queue, _redis_client
	
	# RQ queues don't need explicit closing, but we can clear the reference
	_knowledge_queue = None
	
	if _redis_client:
		try:
			_redis_client.close()
		except Exception:
			pass
		_redis_client = None
	
	logger.info("All queue connections closed")

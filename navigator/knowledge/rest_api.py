"""
REST API endpoints for Knowledge Retrieval & Storage Flow

Provides HTTP endpoints for:
- Starting knowledge retrieval jobs
- Pausing/resuming jobs
- Getting live progress
- Getting partial/final results
- Cancelling jobs
- Inspecting crawl graph state
"""

import logging
from typing import Any

from uuid_extensions import uuid7str

try:
	from fastapi import APIRouter, HTTPException
	from fastapi.responses import JSONResponse
	from pydantic import BaseModel, Field

	FASTAPI_AVAILABLE = True
except ImportError:
	FASTAPI_AVAILABLE = False
	logging.warning('FastAPI not installed. Install with: pip install fastapi')

from navigator.knowledge.pipeline import KnowledgePipeline

logger = logging.getLogger(__name__)

# Import job registry
from navigator.knowledge.job_registry import get_job_registry

# RQ integration
try:
	from navigator.knowledge.job_queue import add_exploration_job
	from navigator.knowledge.job_queue import get_job_status as get_queue_job_status
	RQ_AVAILABLE = True
except ImportError:
	RQ_AVAILABLE = False
	logger.debug('RQ not available, using in-memory job registry')


# Pydantic models for request/response
class AuthenticationModel(BaseModel):
	"""Authentication model for website login (credentials are never logged or persisted)."""
	username: str = Field(..., description="Username or email for login")
	password: str = Field(..., description="Password for login")


class StartExplorationRequest(BaseModel):
	"""Request model for starting exploration."""
	start_url: str = Field(..., description="Starting URL for exploration")
	max_pages: int | None = Field(None, description="Maximum number of pages to explore")
	max_depth: int = Field(3, description="Maximum exploration depth")
	strategy: str = Field("BFS", description="Exploration strategy: BFS or DFS")
	job_id: str | None = Field(None, description="Optional job ID (auto-generated if not provided)")
	include_paths: list[str] | None = Field(None, description="Path patterns to include (e.g., ['/docs/*', '/api/v1/*'])")
	exclude_paths: list[str] | None = Field(None, description="Path patterns to exclude (e.g., ['/admin/*', '/api/*'])")
	authentication: AuthenticationModel | None = Field(None, description="Optional authentication for protected websites (never logged or persisted)")


class JobStatusResponse(BaseModel):
	"""Response model for job status."""
	job_id: str
	status: str  # 'running', 'paused', 'completed', 'failed', 'cancelled'
	paused: bool
	current_page: str | None = None
	pages_completed: int = 0
	pages_queued: int = 0
	pages_failed: int = 0
	links_discovered: int = 0
	external_links_detected: int = 0
	error: str | None = None
	# Enhanced metrics
	estimated_time_remaining: float | None = None  # seconds
	processing_rate: float | None = None  # pages per minute
	recent_pages: list[dict[str, Any]] | None = None  # Recent completed pages with titles


class JobControlRequest(BaseModel):
	"""Request model for job control (pause/resume/cancel)."""
	job_id: str = Field(..., description="Job ID to control")
	wait_for_current_page: bool = Field(False, description="For cancel: wait for current page to complete before cancelling")


def create_knowledge_router(
	pipeline_factory: Any | None = None,  # callable type
) -> APIRouter | None:
	"""
	Create FastAPI router for knowledge retrieval endpoints.
	
	Args:
		pipeline_factory: Factory function to create KnowledgePipeline instances
	
	Returns:
		APIRouter instance or None if FastAPI not available
	"""
	if not FASTAPI_AVAILABLE:
		return None
	
	router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
	
	# Store pipeline factory and active pipelines
	_pipeline_factory = pipeline_factory
	_active_pipelines: dict[str, Any] = {}  # job_id -> pipeline (in-memory only, can't serialize to MongoDB)
	
	@router.post("/explore/start", response_model=dict)
	async def start_exploration(request: StartExplorationRequest):
		"""
		Start a knowledge retrieval job.
		
		Returns job ID and initial status.
		"""
		try:
			# Get MongoDB job registry
			job_registry = await get_job_registry()
			
			# Generate job ID if not provided
			job_id = request.job_id or uuid7str()
			
			logger.info("=" * 80)
			logger.info("=" * 80)
			logger.info(f"📥 [REST API] Received exploration start request")
			logger.info(f"   Job ID: {job_id}")
			logger.info(f"   Start URL: {request.start_url}")
			logger.info(f"   Max pages: {request.max_pages}, Max depth: {request.max_depth}")
			logger.info(f"   Strategy: {request.strategy}")
			if request.include_paths:
				logger.info(f"   Include paths: {request.include_paths}")
			if request.exclude_paths:
				logger.info(f"   Exclude paths: {request.exclude_paths}")
			if request.authentication:
				logger.info(f"   Authentication: Enabled (username: {request.authentication.username})")
				# DO NOT log password - credentials are never logged
			logger.info("=" * 80)
			
			# Create pipeline (requires browser session)
			if _pipeline_factory is None:
				raise HTTPException(
					status_code=500,
					detail="Pipeline factory not configured. Browser session required."
				)
			
			# Try to use RQ if available, otherwise use in-memory
			if RQ_AVAILABLE:
				try:
					logger.info(f"✅ RQ is available, using queue-based execution")
					# Convert authentication model to dict (credentials never logged or persisted)
					authentication_dict = None
					if request.authentication:
						authentication_dict = {
							'username': request.authentication.username,
							'password': request.authentication.password,
						}
					
					# Add job to RQ queue (sync function, no await needed)
					queue_job_id = add_exploration_job(
						start_url=request.start_url,
						max_pages=request.max_pages,
						max_depth=request.max_depth,
						strategy=request.strategy,
						job_id=job_id,
						include_paths=request.include_paths,
						exclude_paths=request.exclude_paths,
						authentication=authentication_dict,
					)
					logger.info(f"✅ Job queued successfully: {job_id} (queue job ID: {queue_job_id})")
					
					# Store in registry for status tracking
					await job_registry.register_job(job_id, {
						'job_id': job_id,
						'start_url': request.start_url,
						'status': 'queued',
						'queue_job_id': queue_job_id,
						# Note: pipeline is None (created by worker) - not stored in MongoDB
					})
					
					return JSONResponse({
						'job_id': job_id,
						'status': 'queued',
						'message': 'Job queued via RQ. Use /api/knowledge/explore/status/{job_id} to check progress. Start RQ worker with: rq worker knowledge-retrieval',
					})
				except Exception as e:
					logger.warning(f"⚠️  RQ queue failed, falling back to in-memory: {e}")
					logger.warning(f"   Error details: {type(e).__name__}: {str(e)}")
			
			# Fallback to in-memory execution
			# Create pipeline instance (async)
			import asyncio
			create_pipeline_func = _pipeline_factory()
			
			# Handle async factory (returns coroutine function)
			if asyncio.iscoroutinefunction(create_pipeline_func):
				pipeline = await create_pipeline_func()
			elif asyncio.iscoroutine(create_pipeline_func):
				pipeline = await create_pipeline_func
			else:
				# Sync factory that returns async function
				async_create = create_pipeline_func
				if asyncio.iscoroutinefunction(async_create):
					pipeline = await async_create()
				else:
					pipeline = async_create
			
			# Configure pipeline with path restrictions
			if request.include_paths or request.exclude_paths:
				pipeline.include_paths = request.include_paths or []
				pipeline.exclude_paths = request.exclude_paths or []
			
			# Store job in registry (MongoDB)
			await job_registry.register_job(job_id, {
				'job_id': job_id,
				'start_url': request.start_url,
				'status': 'queued',
				'max_pages': request.max_pages,
				'max_depth': request.max_depth,
				'strategy': request.strategy,
				'results': {},
			})
			# Store pipeline reference in memory (can't serialize to MongoDB)
			_active_pipelines[job_id] = pipeline
			
			# Start exploration in background
			import asyncio
			async def run_exploration():
				try:
					await job_registry.update_job(job_id, {'status': 'running'})
					result = await pipeline.explore_and_store(
						start_url=request.start_url,
						max_pages=request.max_pages,
						job_id=job_id,
					)
					await job_registry.update_job(job_id, {
						'results': result,
						'status': 'completed' if result.get('error') is None else 'failed',
					})
				except Exception as e:
					logger.error(f"Exploration job {job_id} failed: {e}", exc_info=True)
					await job_registry.update_job(job_id, {
						'status': 'failed',
						'error': str(e),
					})
			
			# Run in background (FastAPI runs in async context)
			asyncio.create_task(run_exploration())
			
			return JSONResponse({
				'job_id': job_id,
				'status': 'queued',
				'message': 'Job started. Use /api/knowledge/explore/status/{job_id} to check progress.',
			})
		except Exception as e:
			logger.error(f"Failed to start exploration: {e}", exc_info=True)
			raise HTTPException(status_code=500, detail=str(e))
	
	@router.get("/explore/status/{job_id}", response_model=JobStatusResponse)
	async def get_job_status(job_id: str):
		"""
		Get live progress for a knowledge retrieval job.
		
		Supports polling for real-time updates.
		"""
		try:
			job_registry = await get_job_registry()
			job = await job_registry.get_job(job_id)
			if not job:
				raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
			
			# Try to get status from RQ queue first
			if RQ_AVAILABLE and job.get('queue_job_id'):
				try:
					queue_status = get_queue_job_status(job_id)  # RQ get_job_status is sync
					if queue_status:
						# Map RQ status to our format
						return JSONResponse({
							'job_id': job_id,
							'status': queue_status.get('status', 'unknown'),
							'paused': False,  # RQ doesn't have pause/resume
						})
				except Exception as e:
					logger.debug(f"Failed to get queue status: {e}")
			
			# Get status from pipeline if available (pipeline stored in memory, not MongoDB)
			pipeline: KnowledgePipeline | None = _active_pipelines.get(job_id)
			if pipeline:
				status = pipeline.get_job_status()
				# Get results if available
				results = job.get('results', {})
				
				# Calculate enhanced metrics
				pages_completed = results.get('pages_stored', 0)
				pages_queued = max(0, results.get('pages_processed', 0) - pages_completed)
				processing_times = pipeline.page_processing_times
				
				estimated_time = pipeline._calculate_estimated_time_remaining(
					pages_completed=pages_completed,
					pages_queued=pages_queued,
					processing_times=processing_times,
				)
				processing_rate = pipeline._calculate_processing_rate(processing_times)
				
				return JSONResponse({
					'job_id': job_id,
					'status': status.get('status', job.get('status', 'unknown')),
					'paused': status.get('paused', False),
					'current_page': results.get('current_page'),
					'pages_completed': pages_completed,
					'pages_queued': pages_queued,
					'pages_failed': results.get('pages_failed', 0),
					'links_discovered': results.get('links_discovered', 0),
					'external_links_detected': results.get('external_links_detected', 0),
					'error': results.get('error'),
					'estimated_time_remaining': estimated_time,
					'processing_rate': processing_rate,
					'recent_pages': pipeline.recent_completed_pages.copy() if pipeline.recent_completed_pages else None,
				})
			else:
				return JSONResponse({
					'job_id': job_id,
					'status': job.get('status', 'unknown'),
					'paused': False,
				})
		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to get job status: {e}", exc_info=True)
			raise HTTPException(status_code=500, detail=str(e))
	
	@router.post("/explore/pause")
	async def pause_job(request: JobControlRequest):
		"""
		Pause a running knowledge retrieval job.
		
		Job can be resumed later.
		"""
		try:
			job_registry = await get_job_registry()
			job = await job_registry.get_job(request.job_id)
			if not job:
				raise HTTPException(status_code=404, detail=f"Job {request.job_id} not found")
			
			pipeline: KnowledgePipeline | None = _active_pipelines.get(request.job_id)
			if not pipeline:
				raise HTTPException(status_code=400, detail="Job not started yet")
			
			success = pipeline.pause_job()
			if success:
				await job_registry.update_job(request.job_id, {'status': 'paused'})
				return JSONResponse({'job_id': request.job_id, 'status': 'paused'})
			else:
				raise HTTPException(status_code=400, detail="Job cannot be paused (not running)")
		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to pause job: {e}", exc_info=True)
			raise HTTPException(status_code=500, detail=str(e))
	
	@router.post("/explore/resume")
	async def resume_job(request: JobControlRequest):
		"""
		Resume a paused knowledge retrieval job.
		"""
		try:
			job_registry = await get_job_registry()
			job = await job_registry.get_job(request.job_id)
			if not job:
				raise HTTPException(status_code=404, detail=f"Job {request.job_id} not found")
			
			pipeline: KnowledgePipeline | None = _active_pipelines.get(request.job_id)
			if not pipeline:
				raise HTTPException(status_code=400, detail="Job not started yet")
			
			success = pipeline.resume_job()
			if success:
				await job_registry.update_job(request.job_id, {'status': 'running'})
				return JSONResponse({'job_id': request.job_id, 'status': 'resumed'})
			else:
				raise HTTPException(status_code=400, detail="Job cannot be resumed (not paused)")
		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to resume job: {e}", exc_info=True)
			raise HTTPException(status_code=500, detail=str(e))
	
	@router.post("/explore/cancel")
	async def cancel_job(request: JobControlRequest):
		"""
		Cancel a knowledge retrieval job.
		
		Job cannot be resumed after cancellation.
		If wait_for_current_page is True, waits for current page to complete before cancelling.
		Also cancels RQ jobs that are running or stuck.
		"""
		try:
			job_registry = await get_job_registry()
			job = await job_registry.get_job(request.job_id)
			if not job:
				raise HTTPException(status_code=404, detail=f"Job {request.job_id} not found")
			
			# Try to cancel RQ job if it's running
			if RQ_AVAILABLE:
				try:
					from navigator.knowledge.job_queue import get_redis_client
					from rq.job import Job as RQJob
					
					redis_client = get_redis_client()
					if redis_client:
						try:
							rq_job = RQJob.fetch(request.job_id, connection=redis_client)
							rq_status = rq_job.get_status()
							
							# Cancel RQ job if it's queued, started, or deferred
							if rq_status in ('queued', 'started', 'deferred'):
								logger.info(f"🛑 Cancelling RQ job {request.job_id} (status: {rq_status})")
								rq_job.cancel()  # Cancel the RQ job
								# Also try to stop it if it's running
								if rq_status == 'started':
									try:
										rq_job.stop()  # Stop running job
									except Exception as stop_error:
										logger.warning(f"Could not stop running RQ job: {stop_error}")
						except Exception as rq_error:
							# Job might not exist in RQ (already finished or never queued)
							logger.debug(f"RQ job {request.job_id} not found or already finished: {rq_error}")
				except Exception as e:
					logger.warning(f"Failed to cancel RQ job: {e}")
			
			# Cancel in-memory pipeline if it exists
			pipeline: KnowledgePipeline | None = _active_pipelines.get(request.job_id)
			if pipeline:
				success = pipeline.cancel_job(wait_for_current_page=request.wait_for_current_page)
				if success:
					if request.wait_for_current_page:
						await job_registry.update_job(request.job_id, {'status': 'cancelling'})
						return JSONResponse({
							'job_id': request.job_id,
							'status': 'cancelling',
							'message': 'Job will be cancelled after current page completes',
						})
					else:
						await job_registry.update_job(request.job_id, {'status': 'cancelled'})
						return JSONResponse({
							'job_id': request.job_id,
							'status': 'cancelled',
							'message': 'Job cancelled immediately',
						})
			
			# Update job status in registry
			await job_registry.update_job(request.job_id, {'status': 'cancelled'})
			return JSONResponse({
				'job_id': request.job_id,
				'status': 'cancelled',
				'message': 'Job cancelled',
			})
		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to cancel job: {e}", exc_info=True)
			raise HTTPException(status_code=500, detail=str(e))
	
	@router.get("/explore/results/{job_id}")
	async def get_job_results(job_id: str, partial: bool = False):
		"""
		Get results for a knowledge retrieval job.
		
		Args:
			job_id: Job ID
			partial: If True, return partial results even if job is still running
		
		Returns:
			Job results with pages, links, errors, etc.
		"""
		try:
			job_registry = await get_job_registry()
			job = await job_registry.get_job(job_id)
			if not job:
				raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
			
			status = job.get('status', 'unknown')
			if status not in ('completed', 'failed', 'cancelled', 'cancelling') and not partial:
				raise HTTPException(
					status_code=400,
					detail=f"Job {job_id} is still {status}. Use partial=true to get partial results."
				)
			
			results = job.get('results', {})
			
			# Enhance results with metadata if available
			enhanced_results = results.copy()
			if 'website_metadata' in results:
				enhanced_results['metadata'] = results['website_metadata']
			
			# Include error categorization in errors list
			if 'errors' in results:
				enhanced_results['errors'] = results['errors']  # Already includes error_type from pipeline
			
			return JSONResponse(enhanced_results)
		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to get job results: {e}", exc_info=True)
			raise HTTPException(status_code=500, detail=str(e))
	
	@router.get("/explore/jobs")
	async def list_jobs():
		"""
		List all knowledge retrieval jobs.
		
		Returns summary of all jobs.
		"""
		try:
			job_registry = await get_job_registry()
			all_jobs = await job_registry.list_jobs()
			jobs = []
			for job_data in all_jobs:
				jobs.append({
					'job_id': job_data.get('job_id'),
					'status': job_data.get('status', 'unknown'),
					'start_url': job_data.get('start_url', ''),
				})
			return JSONResponse({'jobs': jobs, 'count': len(jobs)})
		except Exception as e:
			logger.error(f"Failed to list jobs: {e}", exc_info=True)
			raise HTTPException(status_code=500, detail=str(e))
	
	return router

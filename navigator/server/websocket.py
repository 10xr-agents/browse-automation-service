"""
WebSocket Server for Browser Automation Service

Provides WebSocket endpoints for voice agent to connect and receive browser events.
"""

import logging

try:
	from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
	from fastapi.responses import JSONResponse

	FASTAPI_AVAILABLE = True
except ImportError:
	FASTAPI_AVAILABLE = False
	logging.warning('FastAPI not installed. Install with: pip install fastapi websockets')

from navigator.session.manager import BrowserSessionManager
from navigator.streaming.broadcaster import EventBroadcaster

logger = logging.getLogger(__name__)

# Import knowledge retrieval REST API
try:
	from navigator.knowledge.rest_api import create_knowledge_router
	KNOWLEDGE_API_AVAILABLE = True
except ImportError:
	KNOWLEDGE_API_AVAILABLE = False
	logger.warning('Knowledge REST API not available. Install required dependencies.')

# Global event broadcaster instance
event_broadcaster = EventBroadcaster()

# Global browser session manager instance
session_manager = BrowserSessionManager(event_broadcaster)

# FastAPI app instance (created on demand)
_app: FastAPI | None = None


def get_app() -> FastAPI:
	"""Get or create FastAPI app instance."""
	global _app
	if _app is None:
		if not FASTAPI_AVAILABLE:
			raise ImportError('FastAPI not installed. Install with: pip install fastapi websockets')
		_app = FastAPI(title='Browser Automation Service WebSocket API')
		_setup_routes(_app)
	return _app


def _setup_routes(app: FastAPI) -> None:
	"""Setup WebSocket routes."""
	
	# Setup knowledge retrieval REST API
	_setup_knowledge_api(app)

	@app.websocket('/mcp/events/{room_name}')
	async def mcp_events_websocket(websocket: WebSocket, room_name: str):
		"""WebSocket endpoint for real-time event streaming.

		Args:
			websocket: WebSocket connection
			room_name: LiveKit room name
		"""
		logger.info(f'[WebSocket] New connection attempt for room: {room_name}')
		logger.debug(f'[WebSocket] Client: {websocket.client if hasattr(websocket, "client") else "unknown"}')
		
		await event_broadcaster.register_websocket(websocket, room_name)
		logger.debug(f'[WebSocket] ✅ Connection registered for room: {room_name}')

		try:
			# Listen for incoming messages (voice agent can send commands if needed)
			while True:
				logger.debug(f'[WebSocket] Waiting for message from room: {room_name}')
				data = await websocket.receive_json()
				# Handle incoming commands if needed
				# Most commands come via MCP tools, but WebSocket can handle real-time commands too
				logger.debug(f'[WebSocket] Received message from voice agent in room {room_name}: {data}')
		except WebSocketDisconnect:
			logger.info(f'[WebSocket] Client disconnected from room: {room_name}')
		except Exception as e:
			logger.error(f'[WebSocket] ❌ Error in WebSocket connection for room {room_name}: {e}', exc_info=True)
		finally:
			logger.debug(f'[WebSocket] Cleaning up connection for room: {room_name}')
			await event_broadcaster.unregister_websocket(websocket, room_name)

	@app.get('/health')
	async def health_check():
		"""Health check endpoint."""
		# Check JobManager status if available
		job_manager_status = None
		try:
			if hasattr(app.state, 'job_manager'):
				job_manager = app.state.job_manager
				job_manager_status = job_manager.get_status()
		except Exception as e:
			logger.debug(f"Error getting JobManager status: {e}")
		
		# Check queue availability
		try:
			from navigator.knowledge.job_queue import get_knowledge_queue
			queue = get_knowledge_queue()
			queue_available = queue is not None
		except Exception:
			queue_available = False
		
		response = {
			'status': 'ok',
			'service': 'browser-automation-websocket',
			'queue_available': queue_available,
		}
		
		if job_manager_status:
			response['job_manager'] = job_manager_status
		else:
			response['note'] = 'JobManager not available - workers must be started manually'
		
		return JSONResponse(response)
	
	@app.get('/api/knowledge/worker/status')
	async def get_worker_status():
		"""Get worker status and queue information."""
		try:
			from navigator.knowledge.job_queue import get_knowledge_queue
			from navigator.knowledge.job_registry import get_job_registry
			
			# Get JobManager status if available
			job_manager_status = None
			if hasattr(app.state, 'job_manager'):
				job_manager = app.state.job_manager
				job_manager_status = job_manager.get_status()
			
			# Check queue availability
			queue = get_knowledge_queue()  # Sync function
			queue_available = queue is not None
			
			# Count jobs by status
			job_registry = await get_job_registry()
			all_jobs = await job_registry.list_jobs()
			
			status_counts = {}
			for job in all_jobs:
				status = job.get('status', 'unknown')
				status_counts[status] = status_counts.get(status, 0) + 1
			
			response = {
				'worker_type': 'rq_auto_scaling' if job_manager_status and job_manager_status.get('enabled') else 'rq_manual',
				'queue_available': queue_available,
				'queue_name': 'knowledge-retrieval',
				'job_counts': status_counts,
				'total_jobs': len(all_jobs),
			}
			
			if job_manager_status:
				response['job_manager'] = job_manager_status
			else:
				response['note'] = 'JobManager not available - workers must be started manually'
			
			return JSONResponse(response)
		except Exception as e:
			logger.error(f"Error getting worker status: {e}", exc_info=True)
			return JSONResponse({
				'worker_type': 'unknown',
				'error': str(e),
			}, status_code=500)

	@app.get('/rooms/{room_name}/connections')
	async def get_connections(room_name: str):
		"""Get number of WebSocket connections for a room."""
		count = event_broadcaster.get_connection_count(room_name)
		return JSONResponse({'room_name': room_name, 'connection_count': count})
	
	@app.websocket('/api/knowledge/explore/ws/{job_id}')
	async def knowledge_exploration_websocket(websocket: WebSocket, job_id: str):
		"""WebSocket endpoint for real-time knowledge retrieval progress updates.
		
		Args:
			websocket: WebSocket connection
			job_id: Knowledge retrieval job ID
		"""
		logger.info(f'[WebSocket] New knowledge exploration connection for job: {job_id}')
		
		await websocket.accept()
		
		try:
			# Import here to avoid circular dependencies
			from navigator.knowledge.job_registry import get_job_registry
			from navigator.knowledge.progress_observer import WebSocketProgressObserver, CompositeProgressObserver, LoggingProgressObserver
			
			# Check if job exists
			job_registry = await get_job_registry()
			job = await job_registry.get_job(job_id)
			if not job:
				await websocket.send_json({
					'type': 'error',
					'error': f'Job {job_id} not found',
				})
				await websocket.close()
				return
			
			# Create WebSocket progress observer for this connection
			class JobWebSocketObserver:
				"""WebSocket observer for a specific job."""
				def __init__(self, websocket: WebSocket):
					self.websocket = websocket
				
				async def on_progress(self, progress):
					"""Send progress update via WebSocket."""
					try:
						await self.websocket.send_json({
							'type': 'progress',
							'data': progress.to_dict() if hasattr(progress, 'to_dict') else progress,
						})
					except Exception as e:
						logger.error(f"Error sending progress via WebSocket: {e}")
				
				async def on_page_completed(self, url: str, result: dict[str, Any]):
					"""Send page completion via WebSocket."""
					try:
						await self.websocket.send_json({
							'type': 'page_completed',
							'data': {'url': url, 'result': result},
						})
					except Exception as e:
						logger.error(f"Error sending page completion via WebSocket: {e}")
				
				async def on_external_link_detected(self, from_url: str, to_url: str):
					"""Send external link detection via WebSocket."""
					try:
						await self.websocket.send_json({
							'type': 'external_link_detected',
							'data': {'from_url': from_url, 'to_url': to_url},
						})
					except Exception as e:
						logger.error(f"Error sending external link detection via WebSocket: {e}")
				
				async def on_error(self, url: str, error: str):
					"""Send error via WebSocket."""
					try:
						await self.websocket.send_json({
							'type': 'error',
							'data': {'url': url, 'error': error},
						})
					except Exception as e:
						logger.error(f"Error sending error via WebSocket: {e}")
			
			ws_observer = JobWebSocketObserver(websocket)
			
			# Add observer to pipeline if it exists
			pipeline = job.get('pipeline')
			if pipeline and hasattr(pipeline, 'progress_observer'):
				# Wrap existing observer with composite that includes WebSocket
				existing_observer = pipeline.progress_observer
				if isinstance(existing_observer, CompositeProgressObserver):
					existing_observer.observers.append(ws_observer)
				else:
					# Create composite with existing + WebSocket
					pipeline.progress_observer = CompositeProgressObserver([
						existing_observer,
						ws_observer,
					])
			
			# Send initial status
			await websocket.send_json({
				'type': 'connected',
				'job_id': job_id,
				'status': job.get('status', 'unknown'),
			})
			
			# Keep connection alive and listen for messages
			while True:
				try:
					data = await websocket.receive_json()
					logger.debug(f'[WebSocket] Received message for job {job_id}: {data}')
					# Handle incoming messages if needed (e.g., pause/resume commands)
				except WebSocketDisconnect:
					logger.info(f'[WebSocket] Client disconnected for job: {job_id}')
					break
				except Exception as e:
					logger.error(f'[WebSocket] Error in WebSocket connection for job {job_id}: {e}', exc_info=True)
					break
		except Exception as e:
			logger.error(f'[WebSocket] Error setting up knowledge exploration WebSocket: {e}', exc_info=True)
			try:
				await websocket.close()
			except Exception:
				pass

	@app.post('/mcp/tools/call')
	async def call_mcp_tool(request: Request):
		"""HTTP endpoint for MCP tool calls from Voice Agent Service.
		
		Expected request format:
		{
			"tool": "tool_name",
			"arguments": {...}
		}
		"""
		try:
			request_data = await request.json()
		except Exception as e:
			logger.error(f'[HTTP] Failed to parse request JSON: {e}')
			return JSONResponse(
				{'error': 'Invalid JSON in request body'},
				status_code=400
			)
		
		logger.info(f'[HTTP] MCP tool call received: {request_data.get("tool")}')
		logger.debug(f'[HTTP] Tool call arguments: {request_data.get("arguments")}')
		
		try:
			tool_name = request_data.get('tool')
			arguments = request_data.get('arguments', {})
			
			if not tool_name:
				return JSONResponse(
					{'error': 'tool name is required'},
					status_code=400
				)
			
			# Import here to avoid circular dependencies
			from navigator.server.mcp import BrowserAutomationMCPServer
			
			# Create MCP server instance (reuse session manager)
			mcp_server = BrowserAutomationMCPServer(session_manager=session_manager)
			
			# Route to appropriate handler
			if tool_name == 'start_browser_session':
				result = await mcp_server._start_browser_session(arguments)
			elif tool_name == 'pause_browser_session':
				result = await mcp_server._pause_browser_session(arguments)
			elif tool_name == 'resume_browser_session':
				result = await mcp_server._resume_browser_session(arguments)
			elif tool_name == 'close_browser_session':
				result = await mcp_server._close_browser_session(arguments)
			elif tool_name == 'execute_action':
				result = await mcp_server._execute_action(arguments)
			elif tool_name == 'get_browser_context':
				result = await mcp_server._get_browser_context(arguments)
			elif tool_name == 'get_screen_content':
				result = await mcp_server._get_screen_content(arguments)
			elif tool_name == 'find_form_fields':
				result = await mcp_server._find_form_fields(arguments)
			elif tool_name == 'recover_browser_session':
				result = await mcp_server._recover_browser_session(arguments)
			elif tool_name == 'start_knowledge_exploration':
				result = await mcp_server._start_knowledge_exploration(arguments)
			elif tool_name == 'get_exploration_status':
				result = await mcp_server._get_exploration_status(arguments)
			elif tool_name == 'pause_exploration':
				result = await mcp_server._pause_exploration(arguments)
			elif tool_name == 'resume_exploration':
				result = await mcp_server._resume_exploration(arguments)
			elif tool_name == 'cancel_exploration':
				result = await mcp_server._cancel_exploration(arguments)
			elif tool_name == 'get_knowledge_results':
				result = await mcp_server._get_knowledge_results(arguments)
			elif tool_name == 'query_knowledge':
				result = await mcp_server._query_knowledge(arguments)
			else:
				logger.warning(f'[HTTP] Unknown tool: {tool_name}')
				return JSONResponse(
					{'error': f'Unknown tool: {tool_name}'},
					status_code=404
				)
			
			logger.info(f'[HTTP] ✅ Tool {tool_name} completed successfully')
			return JSONResponse(result)
			
		except Exception as e:
			logger.error(f'[HTTP] ❌ Tool call failed: {e}', exc_info=True)
			return JSONResponse(
				{'error': str(e)},
				status_code=500
			)
	
	@app.get('/mcp/tools')
	async def list_mcp_tools():
		"""List all available MCP tools."""
		logger.debug('[HTTP] Listing MCP tools')
		
		tools = [
			{
				'name': 'start_browser_session',
				'description': 'Start a browser session for a LiveKit room with video streaming'
			},
			{
				'name': 'pause_browser_session',
				'description': 'Pause video streaming for a room'
			},
			{
				'name': 'resume_browser_session',
				'description': 'Resume video streaming for a room'
			},
			{
				'name': 'close_browser_session',
				'description': 'Close a browser session and stop streaming'
			},
			{
				'name': 'execute_action',
				'description': 'Execute a browser action (navigate, click, type, scroll, wait, etc.)'
			},
			{
				'name': 'get_browser_context',
				'description': 'Get current browser context (URL, title, ready state, scroll position, cursor position)'
			},
			{
				'name': 'get_screen_content',
				'description': 'Get detailed screen content for agent communication'
			},
			{
				'name': 'find_form_fields',
				'description': 'Intelligently find form field indices by analyzing element attributes (type, name, id, placeholder). Returns indices for username/email field, password field, and submit button. Much faster than brute-forcing through indices.'
			},
			{
				'name': 'recover_browser_session',
				'description': 'Attempt to recover a failed browser session'
			},
			{
				'name': 'start_knowledge_exploration',
				'description': 'Start a knowledge retrieval job to explore and extract knowledge from a website'
			},
			{
				'name': 'get_exploration_status',
				'description': 'Get live status and progress for a knowledge retrieval job'
			},
			{
				'name': 'pause_exploration',
				'description': 'Pause a running knowledge retrieval job'
			},
			{
				'name': 'resume_exploration',
				'description': 'Resume a paused knowledge retrieval job'
			},
			{
				'name': 'cancel_exploration',
				'description': 'Cancel a knowledge retrieval job'
			},
			{
				'name': 'get_knowledge_results',
				'description': 'Get results from a knowledge retrieval job (partial or final)'
			},
			{
				'name': 'query_knowledge',
				'description': 'Query stored knowledge (pages, semantic search, links, sitemaps)'
			}
		]
		
		return JSONResponse({'tools': tools})


def _setup_knowledge_api(app: FastAPI) -> None:
	"""Setup knowledge retrieval REST API routes."""
	if not KNOWLEDGE_API_AVAILABLE:
		logger.warning('Knowledge REST API not available, skipping setup')
		return
	
	def create_pipeline_factory():
		"""Factory function to create KnowledgePipeline instances.
		
		Creates a pipeline with a browser session from the session manager.
		For knowledge retrieval, we use a dedicated browser session.
		"""
		from browser_use import BrowserSession
		from browser_use.browser.profile import BrowserProfile
		from navigator.knowledge.pipeline import KnowledgePipeline
		from navigator.knowledge.progress_observer import (
			CompositeProgressObserver,
			LoggingProgressObserver,
		)
		
		# Try to get Redis observer if available
		observers = [LoggingProgressObserver()]
		
		try:
			import os
			import redis.asyncio as redis
			redis_url = os.getenv("REDIS_URL")
			if not redis_url:
				raise ValueError("REDIS_URL not set in environment variables. Please set it in .env.local")
			redis_client = redis.from_url(redis_url, decode_responses=False)
			from navigator.knowledge.progress_observer import RedisProgressObserver
			redis_observer = RedisProgressObserver(redis_client=redis_client)
			observers.append(redis_observer)
			logger.info('Redis progress observer enabled')
		except Exception as e:
			logger.debug(f'Redis not available for progress observer: {e}')
		
		# Create composite observer
		progress_observer = CompositeProgressObserver(observers)
		
		async def create_pipeline():
			"""Create a new pipeline instance with a fresh browser session."""
			# Create browser session for knowledge retrieval
			profile = BrowserProfile(headless=True, user_data_dir=None, keep_alive=True)
			browser_session = BrowserSession(browser_profile=profile)
			
			# Start browser session (async context)
			await browser_session.start()
			await browser_session.attach_all_watchdogs()
			
			return KnowledgePipeline(
				browser_session=browser_session,
				progress_observer=progress_observer,
			)
		
		return create_pipeline
	
	# Create and include knowledge router
	# Pipeline factory returns async function, which is fine for REST API (endpoints are async)
	router = create_knowledge_router(pipeline_factory=create_pipeline_factory)
	if router:
		app.include_router(router)
		logger.info('Knowledge retrieval REST API routes registered')
		
		# Initialize and start JobManager for auto-scaling RQ workers
		@app.on_event("startup")
		async def start_job_manager():
			"""Start JobManager for auto-scaling RQ workers."""
			try:
				from navigator.knowledge.worker_manager import get_job_manager, JobTypeConfig
				import os
				
				redis_url = os.getenv("REDIS_URL")
				if not redis_url:
					logger.warning("⚠️  [Startup] REDIS_URL not set - JobManager disabled")
					logger.warning("   Please set REDIS_URL in your .env.local file")
					# Still start stuck job monitor
					_start_stuck_job_monitor()
					return
				
				# Get or create JobManager with default configuration
				job_manager = get_job_manager(
					redis_url=redis_url,
					job_types=[
						JobTypeConfig(
							queue_name="knowledge-retrieval",
							min_workers=1,
							max_workers=5,
							scale_up_threshold=5,
							scale_down_threshold=0,
						)
					],
				)
				
				# Start JobManager
				await job_manager.start()
				
				# Store reference for shutdown
				app.state.job_manager = job_manager
				
			except Exception as e:
				logger.error(f"❌ [Startup] Failed to start JobManager: {e}", exc_info=True)
				logger.warning("⚠️  [Startup] RQ workers will NOT be managed automatically")
				logger.warning("   You must start workers manually: rq worker knowledge-retrieval")
			
			# Start background task to check for stuck jobs (timeout mechanism)
			_start_stuck_job_monitor()
		
		def _start_stuck_job_monitor():
			"""Start background task to monitor stuck jobs."""
			import asyncio
			from navigator.knowledge.job_registry import get_job_registry
			from navigator.knowledge.job_queue import get_redis_client, RQ_AVAILABLE
			from datetime import datetime, timezone
			
			async def monitor_stuck_jobs():
				"""Check for jobs stuck in queued or running status for too long."""
				# Wait a bit before starting monitoring
				await asyncio.sleep(10)  # Give jobs time to start
				
				# Timeout for queued jobs: 2 minutes (120 seconds)
				# RQ workers should pick up jobs within seconds, so 2 minutes is reasonable
				QUEUED_JOB_TIMEOUT_SECONDS = 120
				
				# Timeout for running/exploring jobs: 30 minutes (1800 seconds)
				# Jobs can take a long time, but if they're not updating progress, they're likely stuck
				RUNNING_JOB_TIMEOUT_SECONDS = 1800  # 30 minutes
				
				logger.info("🔍 Stuck job monitor started (checks every 30s)")
				logger.info(f"   Queued job timeout: {QUEUED_JOB_TIMEOUT_SECONDS}s")
				logger.info(f"   Running job timeout: {RUNNING_JOB_TIMEOUT_SECONDS}s")
				
				while True:
					try:
						await asyncio.sleep(30)  # Check every 30 seconds
						
						job_registry = await get_job_registry()
						all_jobs = await job_registry.list_jobs()
						
						now = datetime.now(timezone.utc)
						stuck_count = 0
						cancelled_count = 0
						
						for job in all_jobs:
							status = job.get('status', 'unknown')
							job_id = job.get('job_id')
							created_at = job.get('created_at')
							updated_at = job.get('updated_at')
							
							# Use updated_at for running jobs, created_at for queued jobs
							if status in ('running', 'exploring'):
								check_time = updated_at if updated_at else created_at
							else:
								check_time = created_at if created_at else updated_at
							
							if not check_time:
								continue
							
							# Handle both timezone-aware and naive datetimes
							if isinstance(check_time, str):
								from dateutil.parser import parse as parse_date
								check_time = parse_date(check_time)
							if isinstance(check_time, datetime):
								if check_time.tzinfo is None:
									# Naive datetime - assume UTC
									check_time = check_time.replace(tzinfo=timezone.utc)
								
								time_elapsed = (now - check_time).total_seconds()
								
								# Check for jobs stuck in queued/pending status
								if status in ('queued', 'pending'):
									if time_elapsed > QUEUED_JOB_TIMEOUT_SECONDS:
										logger.warning(f"⏰ Job {job_id} stuck in '{status}' status for {time_elapsed:.0f} seconds - marking as failed")
										await job_registry.update_job(
											job_id,
											{
												'status': 'failed',
												'error': f'Job timeout: Stuck in {status} status for {time_elapsed:.0f} seconds. Worker may not be processing jobs.',
											}
										)
										stuck_count += 1
								
								# Check for jobs stuck in running/exploring status (not updating)
								elif status in ('running', 'exploring'):
									if time_elapsed > RUNNING_JOB_TIMEOUT_SECONDS:
										logger.warning(f"⏰ Job {job_id} stuck in '{status}' status for {time_elapsed:.0f} seconds - cancelling")
										
										# Try to cancel RQ job if available
										if RQ_AVAILABLE:
											try:
												from rq.job import Job as RQJob
												redis_client = get_redis_client()
												if redis_client:
													try:
														rq_job = RQJob.fetch(job_id, connection=redis_client)
														rq_status = rq_job.get_status()
														if rq_status in ('queued', 'started', 'deferred'):
															logger.info(f"🛑 Cancelling RQ job {job_id} (RQ status: {rq_status})")
															rq_job.cancel()
															if rq_status == 'started':
																try:
																	rq_job.stop()  # Try to stop running job
																except Exception:
																	pass
													except Exception as rq_error:
														logger.debug(f"Could not cancel RQ job {job_id}: {rq_error}")
											except Exception as e:
												logger.warning(f"Error cancelling RQ job: {e}")
										
										# Update job status to cancelled
										await job_registry.update_job(
											job_id,
											{
												'status': 'cancelled',
												'error': f'Job timeout: Stuck in {status} status for {time_elapsed:.0f} seconds without progress. Job cancelled automatically.',
											}
										)
										cancelled_count += 1
						
						if stuck_count > 0:
							logger.warning(f"⏰ Marked {stuck_count} stuck job(s) as failed due to timeout")
						if cancelled_count > 0:
							logger.warning(f"🛑 Cancelled {cancelled_count} stuck running job(s) due to timeout")
					except Exception as e:
						logger.error(f"Error in stuck job monitor: {e}", exc_info=True)
						await asyncio.sleep(60)  # Wait longer on error
			
			# Start monitoring in background
			asyncio.create_task(monitor_stuck_jobs())
		
		@app.on_event("shutdown")
		async def cleanup_on_shutdown():
			"""Cleanup JobManager and RQ connections on app shutdown."""
			logger.info("=" * 80)
			logger.info("🛑 [Shutdown] Cleaning up...")
			logger.info("=" * 80)
			
			# Stop JobManager first (stops workers gracefully)
			try:
				if hasattr(app.state, 'job_manager'):
					job_manager = app.state.job_manager
					await job_manager.stop(timeout=30)
			except Exception as e:
				logger.error(f"❌ [Shutdown] Error stopping JobManager: {e}", exc_info=True)
			
			# Close RQ connections
			try:
				from navigator.knowledge.job_queue import close_connections
				close_connections()  # Sync function
				logger.info("✅ [Shutdown] RQ connections closed successfully")
			except Exception as e:
				logger.warning(f"⚠️  [Shutdown] Error closing connections: {e}")
			
			logger.info("=" * 80)
	else:
		logger.warning('Failed to create knowledge router')


def get_event_broadcaster() -> EventBroadcaster:
	"""Get the global event broadcaster instance."""
	return event_broadcaster

def get_session_manager() -> BrowserSessionManager:
	"""Get the global session manager instance."""
	return session_manager

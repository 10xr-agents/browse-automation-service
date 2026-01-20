"""
WebSocket Server for Browser Automation Service

Provides WebSocket endpoints for voice agent to connect and receive browser events.
"""

import logging
from typing import Any

try:
	from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, status
	from fastapi.exceptions import RequestValidationError
	from fastapi.middleware.cors import CORSMiddleware
	from fastapi.responses import JSONResponse

	FASTAPI_AVAILABLE = True
except ImportError:
	FASTAPI_AVAILABLE = False
	logging.warning('FastAPI not installed. Install with: pip install fastapi websockets')

from navigator.session.manager import BrowserSessionManager
from navigator.streaming.broadcaster import EventBroadcaster

logger = logging.getLogger(__name__)

# Temporal-based knowledge API is setup in _setup_knowledge_api()

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


def create_app_with_lifespan(lifespan) -> FastAPI:
	"""
	Create FastAPI app with custom lifespan context manager.
	
	This is used by start_server.py to inject Temporal worker startup/shutdown logic.
	
	Args:
		lifespan: AsyncContextManager for app lifespan (startup/shutdown)
	
	Returns:
		FastAPI app instance
	"""
	global _app
	if not FASTAPI_AVAILABLE:
		raise ImportError('FastAPI not installed. Install with: pip install fastapi websockets')

	_app = FastAPI(
		title='Browser Automation Service API',
		description=(
			'**Knowledge Extraction & Browser Automation API**\n\n'
			'Extract knowledge from websites, documentation, and videos, '
			'then query the resulting knowledge graph for navigation paths, screens, tasks, and actions.\n\n'
			'## Features\n\n'
			'- 🌐 **Multi-Source Ingestion**: Extract from websites, docs, videos\n'
			'- 📊 **Knowledge Graph**: Query navigation paths and relationships\n'
			'- 🔄 **Workflow Tracking**: Real-time progress monitoring\n'
			'- 🤖 **Browser Automation**: WebSocket-based event streaming\n'
			'- ⚡ **Temporal Workflows**: Durable, fault-tolerant execution\n\n'
			'## Getting Started\n\n'
			'1. Start knowledge extraction: `POST /api/knowledge/ingest/start`\n'
			'2. Track progress: `GET /api/knowledge/workflows/status/{job_id}`\n'
			'3. Query knowledge: `POST /api/knowledge/graph/query`\n\n'
			'For complete documentation, see `/docs` (Swagger UI) or `/redoc` (ReDoc).'
		),
		version='1.0.1',
		contact={
			'name': 'Browser Automation Service Team',
			'email': 'support@yourservice.com',
		},
		license_info={
			'name': 'MIT',
			'url': 'https://opensource.org/licenses/MIT',
		},
		tags_metadata=[
			{
				'name': 'Knowledge Extraction',
				'description': (
					'Knowledge extraction and retrieval endpoints. '
					'Start ingestion workflows, track progress, query the knowledge graph, '
					'and retrieve detailed definitions of screens, tasks, actions, and transitions.'
				),
			},
			{
				'name': 'Health',
				'description': 'Service health and status monitoring endpoints.',
			},
		],
		lifespan=lifespan,
		docs_url='/docs',  # Swagger UI endpoint
		redoc_url='/redoc',  # ReDoc endpoint
		openapi_url='/openapi.json',  # OpenAPI schema endpoint
		swagger_ui_parameters={
			'defaultModelsExpandDepth': -1,  # Don't expand models by default
			'docExpansion': 'none',  # Don't expand operations by default
			'filter': True,  # Enable search filter
			'showCommonExtensions': True,  # Show common extensions
			'tryItOutEnabled': True,  # Enable "Try it out" by default
		},
	)

	# Add CORS middleware to handle OPTIONS preflight requests
	_app.add_middleware(
		CORSMiddleware,
		allow_origins=["*"],  # Allow all origins (can be restricted in production)
		allow_credentials=True,
		allow_methods=["*"],  # Allow all HTTP methods
		allow_headers=["*"],  # Allow all headers
	)

	# Add exception handler for validation errors to log them
	@_app.exception_handler(RequestValidationError)
	async def validation_exception_handler(request: Request, exc: RequestValidationError):
		"""Log validation errors for debugging."""
		errors = exc.errors()
		error_details = []
		for error in errors:
			field_path = '.'.join(str(loc) for loc in error['loc'])
			error_details.append(f"{field_path}: {error['msg']} (type: {error['type']})")

		# Try to get request body (may be consumed already)
		body_str = "N/A"
		try:
			body_bytes = await request.body()
			if body_bytes:
				import json
				body_str = json.loads(body_bytes.decode('utf-8'))
		except Exception:
			pass

		logger.warning(
			f"❌ Validation error on {request.method} {request.url.path}: "
			f"{'; '.join(error_details)}"
		)
		logger.warning(f"   Request body: {body_str}")

		# Check if it's the old format being sent
		if isinstance(body_str, dict):
			if 'source_type' in body_str or 'source_url' in body_str:
				logger.warning(
					"   ⚠️  Client is using OLD API format. New format requires:\n"
					"      - website_url (required): Target website for Phase 2 DOM analysis\n"
					"      - s3_references + file_metadata_list OR documentation_urls (at least one required)\n"
					"      - credentials (optional): For authenticated login"
				)

		return JSONResponse(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			content={
				"detail": errors,
				"message": f"Validation failed: {'; '.join(error_details)}"
			}
		)

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

	@app.get(
		'/health',
		tags=['Health'],
		summary='Health Check',
		description='Check if the service is running and healthy.',
		response_description='Service health status',
	)
	async def health_check():
		"""Health check endpoint."""
		response = {
			'status': 'ok',
			'service': 'browser-automation-websocket',
		}

		return JSONResponse(response)

	@app.get('/api/knowledge/worker/status')
	async def get_worker_status():
		"""Get worker status and job information."""
		try:
			from navigator.knowledge.job_registry import get_job_registry

			# Count jobs by status
			job_registry = await get_job_registry()
			all_jobs = await job_registry.list_jobs()

			status_counts = {}
			for job in all_jobs:
				status = job.get('status', 'unknown')
				status_counts[status] = status_counts.get(status, 0) + 1

			response = {
				'worker_type': 'in_memory',
				'job_counts': status_counts,
				'total_jobs': len(all_jobs),
			}

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
			from navigator.knowledge.progress_observer import (
				CompositeProgressObserver,
			)

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
	"""Setup knowledge extraction REST API routes."""
	try:
		from navigator.knowledge.rest_api import create_knowledge_api_router

		router = create_knowledge_api_router()
		if router:
			app.include_router(router)
			logger.info('✅ Knowledge extraction API registered (Phase 6)')
		else:
			logger.error('❌ Failed to create knowledge API router')
	except ImportError as e:
		logger.error(f'❌ Knowledge API not available: {e}')
		logger.error('   Please install required dependencies: uv sync')
	except Exception as e:
		logger.error(f'❌ Failed to setup knowledge API: {e}', exc_info=True)


def get_event_broadcaster() -> EventBroadcaster:
	"""Get the global event broadcaster instance."""
	return event_broadcaster

def get_session_manager() -> BrowserSessionManager:
	"""Get the global session manager instance."""
	return session_manager

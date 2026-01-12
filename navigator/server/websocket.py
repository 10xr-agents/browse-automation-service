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
		return JSONResponse({'status': 'ok', 'service': 'browser-automation-websocket'})

	@app.get('/rooms/{room_name}/connections')
	async def get_connections(room_name: str):
		"""Get number of WebSocket connections for a room."""
		count = event_broadcaster.get_connection_count(room_name)
		return JSONResponse({'room_name': room_name, 'connection_count': count})

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
			elif tool_name == 'recover_browser_session':
				result = await mcp_server._recover_browser_session(arguments)
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
				'name': 'recover_browser_session',
				'description': 'Attempt to recover a failed browser session'
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
			import redis.asyncio as redis
			redis_client = redis.from_url("redis://localhost:6379", decode_responses=False)
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
	else:
		logger.warning('Failed to create knowledge router')


def get_event_broadcaster() -> EventBroadcaster:
	"""Get the global event broadcaster instance."""
	return event_broadcaster

def get_session_manager() -> BrowserSessionManager:
	"""Get the global session manager instance."""
	return session_manager

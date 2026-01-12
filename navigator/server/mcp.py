"""
MCP Server for Browser Automation Service MVP

This server exposes Browser Automation Service capabilities as MCP tools,
allowing Voice Agent Service to connect as an MCP client and execute actions.

Usage:
    python -m mvp.mcp_server

Or as an MCP server in Claude Desktop or other MCP clients:
    {
        "mcpServers": {
            "browser-automation": {
                "command": "python",
                "args": ["-m", "mvp.mcp_server"],
                "env": {}
            }
        }
    }
"""

import asyncio
import json
import logging
import os
import sys
from typing import Any

from dotenv import load_dotenv

try:
	import mcp.server.stdio
	import mcp.types as types
	from mcp.server import Server
	from mcp.server.models import InitializationOptions

	MCP_AVAILABLE = True
except ImportError:
	MCP_AVAILABLE = False
	logging.error('MCP SDK not installed. Install with: pip install mcp')
	sys.exit(1)

# Load environment variables
load_dotenv()

from browser_use import BrowserSession
from browser_use.browser.profile import BrowserProfile
from navigator.action.command import (
	ActionCommand,
	ActionType,
	ClickActionCommand,
	NavigateActionCommand,
	ScrollActionCommand,
	TypeActionCommand,
	WaitActionCommand,
)
from navigator.action.dispatcher import ActionDispatcher
from navigator.server.websocket import get_event_broadcaster
from navigator.session.manager import BrowserSessionManager

# Import knowledge retrieval components (will import inside functions when needed)
KNOWLEDGE_AVAILABLE = True  # Assume available, will handle ImportError in functions

# Configure logging for MCP mode
logging.basicConfig(
	stream=sys.stderr,
	level=logging.WARNING,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
	force=True,
)
logger = logging.getLogger(__name__)


class BrowserAutomationMCPServer:
	"""MCP Server exposing Browser Automation Service capabilities."""

	def __init__(self, session_manager: BrowserSessionManager | None = None):
		self.server = Server('browser-automation-service')
		self.browser_session: BrowserSession | None = None
		self.action_dispatcher: ActionDispatcher | None = None
		# Initialize session manager with event broadcaster
		if session_manager is None:
			event_broadcaster = get_event_broadcaster()
			self.session_manager = BrowserSessionManager(event_broadcaster=event_broadcaster)
		else:
			self.session_manager = session_manager
		self._setup_handlers()

	def _setup_handlers(self):
		"""Setup MCP server handlers."""

		@self.server.list_tools()
		async def handle_list_tools() -> list[types.Tool]:
			"""List all available browser automation tools."""
			return [
				# LiveKit-aware session management tools
				types.Tool(
					name='start_browser_session',
					description='Start a browser session for a LiveKit room with video streaming. LiveKit credentials can be provided via arguments or environment variables (LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)',
					inputSchema={
						'type': 'object',
						'properties': {
							'room_name': {'type': 'string', 'description': 'LiveKit room name (required)'},
							'livekit_url': {'type': 'string', 'description': 'LiveKit server URL (optional if LIVEKIT_URL env var is set)'},
							'livekit_api_key': {'type': 'string', 'description': 'LiveKit API key (optional if LIVEKIT_API_KEY env var is set)'},
							'livekit_api_secret': {'type': 'string', 'description': 'LiveKit API secret (optional if LIVEKIT_API_SECRET env var is set)'},
							'livekit_token': {'type': 'string', 'description': 'Pre-generated LiveKit access token (optional if api_key/secret provided)'},
							'participant_identity': {'type': 'string', 'description': 'Participant identity for token generation (default: "browser-agent")'},
							'participant_name': {'type': 'string', 'description': 'Participant name for token generation (default: "Browser Automation Agent")'},
							'initial_url': {'type': 'string', 'description': 'Optional initial URL to navigate to'},
							'viewport_width': {'type': 'integer', 'description': 'Browser viewport width', 'default': 1920},
							'viewport_height': {'type': 'integer', 'description': 'Browser viewport height', 'default': 1080},
							'fps': {'type': 'integer', 'description': 'Video frames per second', 'default': 10},
						},
						'required': ['room_name'],
					},
				),
				types.Tool(
					name='pause_browser_session',
					description='Pause video publishing for a browser session (keep browser alive)',
					inputSchema={
						'type': 'object',
						'properties': {
							'room_name': {'type': 'string', 'description': 'LiveKit room name'},
						},
						'required': ['room_name'],
					},
				),
				types.Tool(
					name='resume_browser_session',
					description='Resume video publishing for a browser session',
					inputSchema={
						'type': 'object',
						'properties': {
							'room_name': {'type': 'string', 'description': 'LiveKit room name'},
						},
						'required': ['room_name'],
					},
				),
				types.Tool(
					name='close_browser_session',
					description='Close a browser session and stop video streaming',
					inputSchema={
						'type': 'object',
						'properties': {
							'room_name': {'type': 'string', 'description': 'LiveKit room name'},
						},
						'required': ['room_name'],
					},
				),
				# Action execution tools (LiveKit-aware)
				types.Tool(
					name='execute_action',
					description='Execute a browser action (navigate, click, type, scroll, wait)',
					inputSchema={
						'type': 'object',
						'properties': {
							'room_name': {'type': 'string', 'description': 'LiveKit room name'},
							'action_type': {
								'type': 'string',
								'enum': ['navigate', 'click', 'type', 'scroll', 'wait', 'go_back', 'refresh'],
								'description': 'Type of action to execute',
							},
							'params': {
								'type': 'object',
								'description': 'Action-specific parameters (JSON object)',
							},
						},
						'required': ['room_name', 'action_type', 'params'],
					},
				),
				types.Tool(
					name='get_browser_context',
					description='Get current browser state (URL, title, ready state, scroll position, cursor position)',
					inputSchema={
						'type': 'object',
						'properties': {
							'room_name': {'type': 'string', 'description': 'LiveKit room name'},
						},
						'required': ['room_name'],
					},
				),
				types.Tool(
					name='get_screen_content',
					description='Get screen content with DOM summary, scroll position, viewport, and cursor position for agent communication',
					inputSchema={
						'type': 'object',
						'properties': {
							'room_name': {'type': 'string', 'description': 'LiveKit room name'},
						},
						'required': ['room_name'],
					},
				),
				types.Tool(
					name='recover_browser_session',
					description='Attempt to recover a failed browser session (reconnect LiveKit, restore state)',
					inputSchema={
						'type': 'object',
						'properties': {
							'room_name': {'type': 'string', 'description': 'LiveKit room name'},
						},
						'required': ['room_name'],
					},
				),
				# Knowledge Retrieval Tools
				types.Tool(
					name='start_knowledge_exploration',
					description='Start a knowledge retrieval job to explore and extract knowledge from a website',
					inputSchema={
						'type': 'object',
						'properties': {
							'start_url': {'type': 'string', 'description': 'Starting URL for exploration'},
							'max_pages': {'type': 'integer', 'description': 'Maximum number of pages to explore (optional)'},
							'max_depth': {'type': 'integer', 'description': 'Maximum exploration depth (default: 3)'},
							'strategy': {'type': 'string', 'enum': ['BFS', 'DFS'], 'description': 'Exploration strategy: BFS (breadth-first) or DFS (depth-first)'},
							'job_id': {'type': 'string', 'description': 'Optional job ID (auto-generated if not provided)'},
						},
						'required': ['start_url'],
					},
				),
				types.Tool(
					name='get_exploration_status',
					description='Get live status and progress for a knowledge retrieval job',
					inputSchema={
						'type': 'object',
						'properties': {
							'job_id': {'type': 'string', 'description': 'Job ID from start_knowledge_exploration'},
						},
						'required': ['job_id'],
					},
				),
				types.Tool(
					name='pause_exploration',
					description='Pause a running knowledge retrieval job',
					inputSchema={
						'type': 'object',
						'properties': {
							'job_id': {'type': 'string', 'description': 'Job ID to pause'},
						},
						'required': ['job_id'],
					},
				),
				types.Tool(
					name='resume_exploration',
					description='Resume a paused knowledge retrieval job',
					inputSchema={
						'type': 'object',
						'properties': {
							'job_id': {'type': 'string', 'description': 'Job ID to resume'},
						},
						'required': ['job_id'],
					},
				),
				types.Tool(
					name='cancel_exploration',
					description='Cancel a knowledge retrieval job',
					inputSchema={
						'type': 'object',
						'properties': {
							'job_id': {'type': 'string', 'description': 'Job ID to cancel'},
						},
						'required': ['job_id'],
					},
				),
				types.Tool(
					name='get_knowledge_results',
					description='Get results from a knowledge retrieval job (partial or final)',
					inputSchema={
						'type': 'object',
						'properties': {
							'job_id': {'type': 'string', 'description': 'Job ID'},
							'partial': {'type': 'boolean', 'description': 'If true, return partial results even if job is still running'},
						},
						'required': ['job_id'],
					},
				),
				types.Tool(
					name='query_knowledge',
					description='Query stored knowledge (pages, semantic search, links, sitemaps)',
					inputSchema={
						'type': 'object',
						'properties': {
							'query_type': {'type': 'string', 'enum': ['page', 'search', 'links', 'sitemap_semantic', 'sitemap_functional'], 'description': 'Type of query'},
							'params': {'type': 'object', 'description': 'Query parameters (varies by query_type)'},
						},
						'required': ['query_type'],
					},
				),
			]

		@self.server.call_tool()
		async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
			"""Handle tool execution."""
			logger.debug(f'[MCP] Tool called: {name}')
			logger.debug(f'[MCP] Tool arguments: {arguments}')
			
			try:
				args = arguments or {}
				if name == 'start_browser_session':
					result = await self._start_browser_session(args)
				elif name == 'pause_browser_session':
					result = await self._pause_browser_session(args)
				elif name == 'resume_browser_session':
					result = await self._resume_browser_session(args)
				elif name == 'close_browser_session':
					result = await self._close_browser_session(args)
				elif name == 'execute_action':
					result = await self._execute_action(args)
				elif name == 'get_browser_context':
					result = await self._get_browser_context(args)
				elif name == 'get_screen_content':
					result = await self._get_screen_content(args)
				elif name == 'recover_browser_session':
					result = await self._recover_browser_session(args)
				elif name == 'start_knowledge_exploration':
					result = await self._start_knowledge_exploration(args)
				elif name == 'get_exploration_status':
					result = await self._get_exploration_status(args)
				elif name == 'pause_exploration':
					result = await self._pause_exploration(args)
				elif name == 'resume_exploration':
					result = await self._resume_exploration(args)
				elif name == 'cancel_exploration':
					result = await self._cancel_exploration(args)
				elif name == 'get_knowledge_results':
					result = await self._get_knowledge_results(args)
				elif name == 'query_knowledge':
					result = await self._query_knowledge(args)
				else:
					logger.warning(f'[MCP] Unknown tool: {name}')
					return [types.TextContent(type='text', text=f'Error: Unknown tool: {name}')]
				
				logger.debug(f'[MCP] Tool {name} completed successfully')
				return [types.TextContent(type='text', text=json.dumps(result, indent=2))]
			except Exception as e:
				logger.error(f'[MCP] ❌ Tool execution failed: {name} - {e}', exc_info=True)
				return [types.TextContent(type='text', text=f'Error: {str(e)}')]

	async def _ensure_browser_session(self):
		"""Ensure browser session is initialized."""
		if self.browser_session is None or self.browser_session._cdp_client_root is None:
			profile = BrowserProfile(headless=True, user_data_dir=None, keep_alive=True)
			self.browser_session = BrowserSession(browser_profile=profile)
			await self.browser_session.start()
			await self.browser_session.attach_all_watchdogs()
			self.action_dispatcher = ActionDispatcher(browser_session=self.browser_session)
			logger.info('Browser session initialized')

	async def _execute_action(self, arguments: dict[str, Any]) -> dict[str, Any]:
		"""Execute an action command."""
		await self._ensure_browser_session()

		action_type_str = arguments.get('action_type')
		params = arguments.get('params', {})

		if not action_type_str:
			raise ValueError('action_type is required')

		# Map string action type to ActionType enum
		action_type_map = {
			'navigate': ActionType.NAVIGATE,
			'click': ActionType.CLICK,
			'type': ActionType.TYPE,
			'scroll': ActionType.SCROLL,
			'wait': ActionType.WAIT,
			'go_back': ActionType.GO_BACK,
			'refresh': ActionType.REFRESH,
		}

		action_type = action_type_map.get(action_type_str)
		if not action_type:
			raise ValueError(f'Unknown action_type: {action_type_str}')

		# Create appropriate action command
		if action_type == ActionType.NAVIGATE:
			action = NavigateActionCommand(params=params)
		elif action_type == ActionType.CLICK:
			action = ClickActionCommand(params=params)
		elif action_type == ActionType.TYPE:
			action = TypeActionCommand(params=params)
		elif action_type == ActionType.SCROLL:
			action = ScrollActionCommand(params=params)
		elif action_type == ActionType.WAIT:
			action = WaitActionCommand(params=params)
		else:
			# For go_back and refresh, use base ActionCommand
			action = ActionCommand(action_type=action_type, params=params)

		# Execute action
		result = await self.action_dispatcher.execute_action(action)

		# Return result as dict
		return {
			'success': result.success,
			'error': result.error,
			'data': result.data,
		}

	async def _start_browser_session(self, arguments: dict[str, Any]) -> dict[str, Any]:
		"""Start a browser session for a LiveKit room."""
		logger.info('[MCP] Starting browser session...')
		
		room_name = arguments.get('room_name')
		# Get LiveKit config from arguments or environment variables
		livekit_url = arguments.get('livekit_url') or os.getenv('LIVEKIT_URL')
		livekit_api_key = arguments.get('livekit_api_key') or os.getenv('LIVEKIT_API_KEY')
		livekit_api_secret = arguments.get('livekit_api_secret') or os.getenv('LIVEKIT_API_SECRET')
		livekit_token = arguments.get('livekit_token') or os.getenv('LIVEKIT_TOKEN')
		participant_identity = arguments.get('participant_identity')
		participant_name = arguments.get('participant_name')
		initial_url = arguments.get('initial_url')
		viewport_width = arguments.get('viewport_width', 1920)
		viewport_height = arguments.get('viewport_height', 1080)
		fps = arguments.get('fps', 10)

		logger.debug(f'[MCP] Room name: {room_name}')
		logger.debug(f'[MCP] LiveKit URL: {livekit_url}')
		logger.debug(f'[MCP] Has API key: {bool(livekit_api_key)}, Has API secret: {bool(livekit_api_secret)}')
		logger.debug(f'[MCP] Has token: {bool(livekit_token)}')
		logger.debug(f'[MCP] Viewport: {viewport_width}x{viewport_height}, FPS: {fps}')

		if not room_name:
			raise ValueError('room_name is required')
		if not livekit_url:
			raise ValueError('livekit_url is required (provide via argument or LIVEKIT_URL env var)')
		
		# Validate that we have either token or api_key/secret
		if not livekit_token and not (livekit_api_key and livekit_api_secret):
			raise ValueError(
				'Either livekit_token or both livekit_api_key and livekit_api_secret are required '
				'(provide via arguments or LIVEKIT_TOKEN / LIVEKIT_API_KEY + LIVEKIT_API_SECRET env vars)'
			)

		return await self.session_manager.start_session(
			room_name=room_name,
			livekit_url=livekit_url,
			livekit_api_key=livekit_api_key,
			livekit_api_secret=livekit_api_secret,
			livekit_token=livekit_token,
			participant_identity=participant_identity,
			participant_name=participant_name,
			initial_url=initial_url,
			viewport_width=viewport_width,
			viewport_height=viewport_height,
			fps=fps,
		)

	async def _pause_browser_session(self, arguments: dict[str, Any]) -> dict[str, Any]:
		"""Pause video publishing for a browser session."""
		room_name = arguments.get('room_name')
		if not room_name:
			raise ValueError('room_name is required')
		return await self.session_manager.pause_session(room_name)

	async def _resume_browser_session(self, arguments: dict[str, Any]) -> dict[str, Any]:
		"""Resume video publishing for a browser session."""
		room_name = arguments.get('room_name')
		if not room_name:
			raise ValueError('room_name is required')
		return await self.session_manager.resume_session(room_name)

	async def _close_browser_session(self, arguments: dict[str, Any]) -> dict[str, Any]:
		"""Close a browser session."""
		room_name = arguments.get('room_name')
		if not room_name:
			raise ValueError('room_name is required')
		return await self.session_manager.close_session(room_name)

	async def _execute_action(self, arguments: dict[str, Any]) -> dict[str, Any]:
		"""Execute an action command."""
		room_name = arguments.get('room_name')
		action_type_str = arguments.get('action_type')
		params = arguments.get('params', {})

		if not room_name:
			raise ValueError('room_name is required')
		if not action_type_str:
			raise ValueError('action_type is required')

		return await self.session_manager.execute_action(room_name, action_type_str, params)

	async def _get_browser_context(self, arguments: dict[str, Any]) -> dict[str, Any]:
		"""Get current browser context."""
		room_name = arguments.get('room_name')
		if not room_name:
			raise ValueError('room_name is required')

		return await self.session_manager.get_browser_context(room_name)

	async def _get_screen_content(self, arguments: dict[str, Any]) -> dict[str, Any]:
		"""Get screen content with DOM summary for agent communication."""
		room_name = arguments.get('room_name')
		if not room_name:
			raise ValueError('room_name is required')

		screen_content = await self.session_manager.get_screen_content(room_name)
		
		# screen_content is already a dict from browser_session_manager.get_screen_content()
		# (it calls model_dump() internally), so just return it directly
		if isinstance(screen_content, dict):
			return screen_content
		else:
			# Fallback: if it's a Pydantic model, convert to dict
			return screen_content.model_dump()

	async def _recover_browser_session(self, arguments: dict[str, Any]) -> dict[str, Any]:
		"""Recover a failed browser session."""
		room_name = arguments.get('room_name')
		if not room_name:
			raise ValueError('room_name is required')

		return await self.session_manager.recover_session(room_name)
	
	# Knowledge Retrieval Tool Handlers
	async def _start_knowledge_exploration(self, arguments: dict[str, Any]) -> dict[str, Any]:
		"""Start a knowledge retrieval job."""
		if not KNOWLEDGE_AVAILABLE:
			raise ValueError('Knowledge retrieval components not available')
		
		start_url = arguments.get('start_url')
		max_pages = arguments.get('max_pages')
		max_depth = arguments.get('max_depth', 3)
		strategy_str = arguments.get('strategy', 'BFS')
		job_id = arguments.get('job_id')
		
		if not start_url:
			raise ValueError('start_url is required')
		
		# Import here to avoid circular dependencies
		from browser_use import BrowserSession
		from browser_use.browser.profile import BrowserProfile
		from navigator.knowledge.pipeline import ExplorationStrategy, KnowledgePipeline
		from navigator.knowledge.progress_observer import (
			CompositeProgressObserver,
			LoggingProgressObserver,
		)
		
		# Map strategy string to enum
		strategy = ExplorationStrategy.BFS if strategy_str.upper() == 'BFS' else ExplorationStrategy.DFS
		
		observers = [LoggingProgressObserver()]
		
		try:
			import redis.asyncio as redis
			redis_client = redis.from_url("redis://localhost:6379", decode_responses=False)
			from navigator.knowledge.progress_observer import RedisProgressObserver
			redis_observer = RedisProgressObserver(redis_client=redis_client)
			observers.append(redis_observer)
			logger.info('Redis progress observer enabled for knowledge exploration')
		except Exception as e:
			logger.debug(f'Redis not available for progress observer: {e}')
		
		progress_observer = CompositeProgressObserver(observers)
		
		# Create browser session
		profile = BrowserProfile(headless=True, user_data_dir=None, keep_alive=True)
		browser_session = BrowserSession(browser_profile=profile)
		await browser_session.start()
		await browser_session.attach_all_watchdogs()
		
		# Create pipeline
		pipeline = KnowledgePipeline(
			browser_session=browser_session,
			progress_observer=progress_observer,
			max_depth=max_depth,
			strategy=strategy,
		)
		
		# Generate job ID if not provided
		from uuid_extensions import uuid7str
		if not job_id:
			job_id = uuid7str()
		
		# Store in registry (import here to avoid circular deps)
		from navigator.knowledge.rest_api import _active_pipelines, _job_registry
		_job_registry[job_id] = {
			'job_id': job_id,
			'start_url': start_url,
			'status': 'queued',
			'pipeline': pipeline,
			'max_pages': max_pages,
			'results': {},
		}
		_active_pipelines[job_id] = pipeline
		
		# Start exploration in background
		async def run_exploration():
			try:
				_job_registry[job_id]['status'] = 'running'
				result = await pipeline.explore_and_store(
					start_url=start_url,
					max_pages=max_pages,
					job_id=job_id,
				)
				_job_registry[job_id]['results'] = result
				_job_registry[job_id]['status'] = 'completed' if result.get('error') is None else 'failed'
			except Exception as e:
				logger.error(f"Exploration job {job_id} failed: {e}", exc_info=True)
				_job_registry[job_id]['status'] = 'failed'
				_job_registry[job_id]['error'] = str(e)
		
		import asyncio
		asyncio.create_task(run_exploration())
		
		return {
			'job_id': job_id,
			'status': 'started',
			'message': 'Knowledge exploration job started',
		}
	
	async def _get_exploration_status(self, arguments: dict[str, Any]) -> dict[str, Any]:
		"""Get exploration job status."""
		if not KNOWLEDGE_AVAILABLE:
			raise ValueError('Knowledge retrieval components not available')
		
		from navigator.knowledge.rest_api import _job_registry
		job_id = arguments.get('job_id')
		if not job_id:
			raise ValueError('job_id is required')
		
		job = _job_registry.get(job_id)
		if not job:
			return {'error': f'Job {job_id} not found'}
		
		pipeline = job.get('pipeline')
		results = job.get('results', {})
		
		if pipeline:
			status = pipeline.get_job_status()
			return {
				'job_id': job_id,
				'status': status.get('status', job.get('status', 'unknown')),
				'paused': status.get('paused', False),
				'pages_completed': results.get('pages_stored', 0),
				'pages_failed': results.get('pages_failed', 0),
				'external_links_detected': results.get('external_links_detected', 0),
			}
		else:
			return {
				'job_id': job_id,
				'status': job.get('status', 'unknown'),
			}
	
	async def _pause_exploration(self, arguments: dict[str, Any]) -> dict[str, Any]:
		"""Pause exploration job."""
		if not KNOWLEDGE_AVAILABLE:
			raise ValueError('Knowledge retrieval components not available')
		
		from navigator.knowledge.rest_api import _job_registry
		job_id = arguments.get('job_id')
		if not job_id:
			raise ValueError('job_id is required')
		
		job = _job_registry.get(job_id)
		if not job:
			return {'error': f'Job {job_id} not found'}
		
		pipeline = job.get('pipeline')
		if not pipeline:
			return {'error': 'Job not started yet'}
		
		success = pipeline.pause_job()
		if success:
			job['status'] = 'paused'
			return {'job_id': job_id, 'status': 'paused'}
		else:
			return {'error': 'Job cannot be paused (not running)'}
	
	async def _resume_exploration(self, arguments: dict[str, Any]) -> dict[str, Any]:
		"""Resume exploration job."""
		if not KNOWLEDGE_AVAILABLE:
			raise ValueError('Knowledge retrieval components not available')
		
		from navigator.knowledge.rest_api import _job_registry
		job_id = arguments.get('job_id')
		if not job_id:
			raise ValueError('job_id is required')
		
		job = _job_registry.get(job_id)
		if not job:
			return {'error': f'Job {job_id} not found'}
		
		pipeline = job.get('pipeline')
		if not pipeline:
			return {'error': 'Job not started yet'}
		
		success = pipeline.resume_job()
		if success:
			job['status'] = 'running'
			return {'job_id': job_id, 'status': 'resumed'}
		else:
			return {'error': 'Job cannot be resumed (not paused)'}
	
	async def _cancel_exploration(self, arguments: dict[str, Any]) -> dict[str, Any]:
		"""Cancel exploration job."""
		if not KNOWLEDGE_AVAILABLE:
			raise ValueError('Knowledge retrieval components not available')
		
		from navigator.knowledge.rest_api import _job_registry
		job_id = arguments.get('job_id')
		if not job_id:
			raise ValueError('job_id is required')
		
		job = _job_registry.get(job_id)
		if not job:
			return {'error': f'Job {job_id} not found'}
		
		pipeline = job.get('pipeline')
		if pipeline:
			success = pipeline.cancel_job()
			if success:
				job['status'] = 'cancelled'
				return {'job_id': job_id, 'status': 'cancelled'}
		
		job['status'] = 'cancelled'
		return {'job_id': job_id, 'status': 'cancelled'}
	
	async def _get_knowledge_results(self, arguments: dict[str, Any]) -> dict[str, Any]:
		"""Get knowledge retrieval results."""
		if not KNOWLEDGE_AVAILABLE:
			raise ValueError('Knowledge retrieval components not available')
		
		from navigator.knowledge.rest_api import _job_registry
		job_id = arguments.get('job_id')
		partial = arguments.get('partial', False)
		
		if not job_id:
			raise ValueError('job_id is required')
		
		job = _job_registry.get(job_id)
		if not job:
			return {'error': f'Job {job_id} not found'}
		
		status = job.get('status', 'unknown')
		if status not in ('completed', 'failed', 'cancelled') and not partial:
			return {'error': f'Job {job_id} is still {status}. Use partial=true to get partial results.'}
		
		results = job.get('results', {})
		return results
	
	async def _query_knowledge(self, arguments: dict[str, Any]) -> dict[str, Any]:
		"""Query stored knowledge."""
		if not KNOWLEDGE_AVAILABLE:
			raise ValueError('Knowledge retrieval components not available')
		
		from navigator.knowledge.api import KnowledgeAPI
		from navigator.knowledge.rest_api import _job_registry
		from navigator.knowledge.storage import KnowledgeStorage
		from navigator.knowledge.vector_store import VectorStore
		
		query_type = arguments.get('query_type')
		params = arguments.get('params', {})
		
		if not query_type:
			raise ValueError('query_type is required')
		
		# Create KnowledgeAPI instance
		storage = KnowledgeStorage(use_arangodb=False)
		vector_store = VectorStore(use_vector_db=False)
		
		# Get pipeline from first available job (or create new one)
		pipeline = None
		for job in _job_registry.values():
			p = job.get('pipeline')
			if p:
				pipeline = p
				break
		
		knowledge_api = KnowledgeAPI(
			storage=storage,
			vector_store=vector_store,
			pipeline=pipeline,
		)
		
		result = await knowledge_api.query(query_type, params)
		return result

	async def run(self):
		"""Run the MCP server."""
		async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
			await self.server.run(
				read_stream,
				write_stream,
				InitializationOptions(
					server_name='browser-automation-service',
					server_version='1.0.0',
					capabilities=self.server.get_capabilities(
						experimental_capabilities={},
					),
				),
			)


async def main():
	"""Main entry point for MCP server."""
	server = BrowserAutomationMCPServer()
	await server.run()


if __name__ == '__main__':
	asyncio.run(main())

"""
MCP Server: Browser Session Management Tools

Tools for managing browser sessions, executing actions, and retrieving browser context.
"""

import logging
from typing import Any

try:
	import mcp.types as types
	MCP_AVAILABLE = True
except ImportError:
	MCP_AVAILABLE = False
	logging.warning('MCP SDK not installed. Install with: pip install mcp')

from navigator.session.manager import BrowserSessionManager

logger = logging.getLogger(__name__)


def get_browser_tools() -> list:
	"""
	Get list of browser session management MCP tools.
	
	Returns:
		List of MCP Tool definitions
	"""
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
					'participant_identity': {'type': 'string', 'description': 'Participant identity (optional)'},
					'participant_name': {'type': 'string', 'description': 'Participant name (optional)'},
					'initial_url': {'type': 'string', 'description': 'Initial URL to navigate to (optional)'},
					'viewport_width': {'type': 'integer', 'description': 'Viewport width in pixels (optional, default: 1920)'},
					'viewport_height': {'type': 'integer', 'description': 'Viewport height in pixels (optional, default: 1080)'},
					'fps': {'type': 'integer', 'description': 'Video frame rate (optional, default: 30)'},
				},
				'required': ['room_name'],
			},
		),
		types.Tool(
			name='pause_browser_session',
			description='Pause video publishing for a browser session',
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
			description='Close a browser session and stop streaming',
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
			description='Execute a browser action. Available actions: navigate, click, type, scroll, wait, go_back, go_forward, refresh, send_keys, right_click, double_click, hover, drag_drop, type_slowly, select_all, copy, paste, cut, clear, upload_file, select_dropdown, fill_form, select_multiple, submit_form, reset_form, play_video, pause_video, seek_video, adjust_volume, toggle_fullscreen, toggle_mute, take_screenshot, keyboard_shortcut, multi_select, highlight_element, zoom_in, zoom_out, zoom_reset, download_file, presentation_mode, show_pointer, animate_scroll, highlight_region, draw_on_page, focus_element',
			inputSchema={
				'type': 'object',
				'properties': {
					'room_name': {'type': 'string', 'description': 'LiveKit room name'},
					'action_type': {
						'type': 'string',
						'enum': [
							# Core navigation actions
							'navigate', 'click', 'type', 'scroll', 'wait', 'go_back', 'go_forward', 'refresh', 'send_keys',
							# Interaction actions
							'right_click', 'double_click', 'hover', 'drag_drop',
							# Text input actions
							'type_slowly', 'select_all', 'copy', 'paste', 'cut', 'clear',
							# Form actions
							'upload_file', 'select_dropdown', 'fill_form', 'select_multiple', 'submit_form', 'reset_form',
							# Media actions
							'play_video', 'pause_video', 'seek_video', 'adjust_volume', 'toggle_fullscreen', 'toggle_mute',
							# Advanced actions
							'take_screenshot', 'keyboard_shortcut', 'multi_select', 'highlight_element', 'zoom_in', 'zoom_out', 'zoom_reset', 'download_file',
							# Presentation actions
							'presentation_mode', 'show_pointer', 'animate_scroll', 'highlight_region', 'draw_on_page', 'focus_element',
						],
						'description': 'Type of action to execute',
					},
					'params': {
						'type': 'object',
						'description': 'Action-specific parameters',
					},
				},
				'required': ['room_name', 'action_type'],
			},
		),
		types.Tool(
			name='get_browser_context',
			description='Get current browser context (URL, title, ready state, scroll position, cursor position)',
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
			description='Get detailed screen content for agent communication (DOM summary, interactive elements, accessibility tree)',
			inputSchema={
				'type': 'object',
				'properties': {
					'room_name': {'type': 'string', 'description': 'LiveKit room name'},
				},
				'required': ['room_name'],
			},
		),
		types.Tool(
			name='find_form_fields',
			description='Intelligently find form field indices by analyzing element attributes (type, name, id, placeholder). Returns indices for username/email field, password field, and submit button. This is much faster than brute-forcing through indices.',
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
	]


def register_browser_tool_handlers(
	server,
	session_manager: BrowserSessionManager
) -> dict[str, callable]:
	"""
	Register browser tool handlers and return handler mapping.
	
	Args:
		server: MCP Server instance
		session_manager: Browser session manager
	
	Returns:
		Dict mapping tool names to handler functions
	"""
	handlers = {}
	
	async def _ensure_browser_session(room_name: str):
		"""Ensure browser session exists for room."""
		session = await session_manager.get_session(room_name)
		if not session:
			raise ValueError(f'Browser session not found for room: {room_name}')
		return session
	
	async def _start_browser_session(arguments: dict[str, Any]) -> dict[str, Any]:
		"""Start a browser session for a LiveKit room."""
		import os
		room_name = arguments.get('room_name')
		livekit_url = arguments.get('livekit_url') or os.getenv('LIVEKIT_URL')
		livekit_api_key = arguments.get('livekit_api_key') or os.getenv('LIVEKIT_API_KEY')
		livekit_api_secret = arguments.get('livekit_api_secret') or os.getenv('LIVEKIT_API_SECRET')
		livekit_token = arguments.get('livekit_token') or os.getenv('LIVEKIT_TOKEN')
		participant_identity = arguments.get('participant_identity')
		participant_name = arguments.get('participant_name')
		initial_url = arguments.get('initial_url')
		viewport_width = arguments.get('viewport_width', 1920)
		viewport_height = arguments.get('viewport_height', 1080)
		fps = arguments.get('fps', 30)

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

		return await session_manager.start_session(
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
	
	async def _pause_browser_session(arguments: dict[str, Any]) -> dict[str, Any]:
		"""Pause video publishing for a browser session."""
		room_name = arguments.get('room_name')
		if not room_name:
			raise ValueError('room_name is required')
		return await session_manager.pause_session(room_name)
	
	async def _resume_browser_session(arguments: dict[str, Any]) -> dict[str, Any]:
		"""Resume video publishing for a browser session."""
		room_name = arguments.get('room_name')
		if not room_name:
			raise ValueError('room_name is required')
		return await session_manager.resume_session(room_name)
	
	async def _close_browser_session(arguments: dict[str, Any]) -> dict[str, Any]:
		"""Close a browser session."""
		room_name = arguments.get('room_name')
		if not room_name:
			raise ValueError('room_name is required')
		return await session_manager.close_session(room_name)
	
	async def _execute_action(arguments: dict[str, Any]) -> dict[str, Any]:
		"""Execute an action command."""
		room_name = arguments.get('room_name')
		action_type_str = arguments.get('action_type')
		params = arguments.get('params', {})

		if not room_name:
			raise ValueError('room_name is required')
		if not action_type_str:
			raise ValueError('action_type is required')

		return await session_manager.execute_action(room_name, action_type_str, params)
	
	async def _get_browser_context(arguments: dict[str, Any]) -> dict[str, Any]:
		"""Get current browser context."""
		room_name = arguments.get('room_name')
		if not room_name:
			raise ValueError('room_name is required')

		return await session_manager.get_browser_context(room_name)
	
	async def _get_screen_content(arguments: dict[str, Any]) -> dict[str, Any]:
		"""Get screen content with DOM summary for agent communication."""
		room_name = arguments.get('room_name')
		if not room_name:
			raise ValueError('room_name is required')

		try:
			screen_content = await session_manager.get_screen_content(room_name)

			# screen_content is already a dict from browser_session_manager.get_screen_content()
			# (it calls model_dump() internally), so wrap it in success/error/data structure
			if isinstance(screen_content, dict):
				content_data = screen_content
			else:
				# Fallback: if it's a Pydantic model, convert to dict
				content_data = screen_content.model_dump()

			# Return wrapped response matching specification format
			return {
				'success': True,
				'error': None,
				'data': content_data,
			}
		except Exception as e:
			# Return error in specification format
			return {
				'success': False,
				'error': str(e),
				'data': None,
			}
	
	async def _find_form_fields(arguments: dict[str, Any]) -> dict[str, Any]:
		"""Find form field indices by analyzing element attributes."""
		room_name = arguments.get('room_name')
		if not room_name:
			raise ValueError('room_name is required')

		return await session_manager.find_form_fields(room_name)
	
	async def _recover_browser_session(arguments: dict[str, Any]) -> dict[str, Any]:
		"""Attempt to recover a failed browser session."""
		room_name = arguments.get('room_name')
		if not room_name:
			raise ValueError('room_name is required')

		return await session_manager.recover_session(room_name)
	
	# Map tool names to handlers
	handlers['start_browser_session'] = _start_browser_session
	handlers['pause_browser_session'] = _pause_browser_session
	handlers['resume_browser_session'] = _resume_browser_session
	handlers['close_browser_session'] = _close_browser_session
	handlers['execute_action'] = _execute_action
	handlers['get_browser_context'] = _get_browser_context
	handlers['get_screen_content'] = _get_screen_content
	handlers['find_form_fields'] = _find_form_fields
	handlers['recover_browser_session'] = _recover_browser_session
	
	return handlers

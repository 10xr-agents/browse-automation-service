"""
Browser Session Manager for LiveKit Integration

Manages browser sessions per LiveKit room, including:
- Browser session lifecycle
- LiveKit streaming integration
- Session state tracking
- Sequenced communication components (optional)
"""

import asyncio
import logging
from typing import Any

from browser_use import BrowserSession
from browser_use.browser.profile import BrowserProfile
from navigator.action.dispatcher import ActionDispatcher
from navigator.streaming.broadcaster import EventBroadcaster
from navigator.streaming.livekit import LiveKitStreamingService

logger = logging.getLogger(__name__)


class BrowserSessionInfo:
	"""Information about a browser session."""

	def __init__(
		self,
		room_name: str,
		browser_session: BrowserSession,
		action_dispatcher: ActionDispatcher,
		livekit_service: LiveKitStreamingService | None = None,
	):
		self.room_name = room_name
		self.browser_session = browser_session
		self.action_dispatcher = action_dispatcher
		self.livekit_service = livekit_service
		self.is_active = False
		self.is_paused = False


class BrowserSessionManager:
	"""Manages browser sessions for LiveKit rooms."""

	def __init__(self, event_broadcaster: EventBroadcaster | None = None):
		"""Initialize browser session manager.

		Args:
			event_broadcaster: Optional event broadcaster for sending events to voice agent
		"""
		self.sessions: dict[str, BrowserSessionInfo] = {}
		self.event_broadcaster = event_broadcaster

		# Sequenced communication components (optional, initialized lazily)
		self._state_diff_engine: Any | None = None
		self._state_publisher: Any | None = None
		self._sequence_tracker: Any | None = None
		self._dedup_cache: Any | None = None
		self._redis_streams_client: Any | None = None
		self._command_consumer: Any | None = None  # CommandConsumer instance (singleton per manager)

	async def start_session(
		self,
		room_name: str,
		livekit_url: str,
		livekit_api_key: str | None = None,
		livekit_api_secret: str | None = None,
		livekit_token: str | None = None,
		participant_identity: str | None = None,
		participant_name: str | None = None,
		initial_url: str | None = None,
		viewport_width: int = 1920,
		viewport_height: int = 1080,
		fps: int = 10,
	) -> dict[str, Any]:
		"""Start a new browser session for a LiveKit room.

		Args:
			room_name: Name of the LiveKit room
			livekit_url: LiveKit server URL
			livekit_api_key: LiveKit API key (for token generation)
			livekit_api_secret: LiveKit API secret (for token generation)
			livekit_token: Pre-generated LiveKit access token (optional if api_key/secret provided)
			participant_identity: Participant identity for token generation
			participant_name: Participant name for token generation
			initial_url: Optional initial URL to navigate to
			viewport_width: Browser viewport width
			viewport_height: Browser viewport height
			fps: Video frames per second

		Returns:
			Session info dict
		"""
		if room_name in self.sessions:
			logger.warning(f'[SessionManager] Session already exists for room: {room_name}')
			return {'status': 'already_exists', 'room_name': room_name}

		logger.info(f'[SessionManager] Starting browser session for room: {room_name}')
		logger.debug(f'[SessionManager] Viewport: {viewport_width}x{viewport_height}, FPS: {fps}')
		logger.debug(f'[SessionManager] LiveKit URL: {livekit_url}, Initial URL: {initial_url}')

		# Create browser session
		logger.debug('[SessionManager] Creating BrowserProfile...')
		profile = BrowserProfile(
			headless=True,
			user_data_dir=None,
			keep_alive=True,
			viewport={'width': viewport_width, 'height': viewport_height},
		)
		logger.debug('[SessionManager] Creating BrowserSession...')
		browser_session = BrowserSession(browser_profile=profile)
		logger.debug('[SessionManager] Starting browser session...')
		await browser_session.start()
		logger.debug('[SessionManager] Attaching watchdogs...')
		await browser_session.attach_all_watchdogs()
		logger.debug('[SessionManager] ✅ Browser session started')

		# Create action dispatcher
		logger.debug('[SessionManager] Creating ActionDispatcher...')
		action_dispatcher = ActionDispatcher(browser_session=browser_session)
		logger.debug('[SessionManager] ✅ ActionDispatcher created')

		# Create LiveKit streaming service
		logger.debug('[SessionManager] Creating LiveKitStreamingService...')
		livekit_service = LiveKitStreamingService(
			livekit_url=livekit_url,
			room_name=room_name,
			livekit_api_key=livekit_api_key,
			livekit_api_secret=livekit_api_secret,
			livekit_token=livekit_token,
			participant_identity=participant_identity,
			participant_name=participant_name,
			width=viewport_width,
			height=viewport_height,
			fps=fps,
		)
		logger.debug('[SessionManager] ✅ LiveKitStreamingService created')

		# Connect to LiveKit and start publishing (optional - handle failures gracefully)
		logger.debug('[SessionManager] Connecting to LiveKit...')
		try:
			await livekit_service.connect()
			logger.debug('[SessionManager] Starting video publishing...')
			await livekit_service.start_publishing(browser_session)
			logger.info('[SessionManager] ✅ LiveKit streaming started')
		except Exception as e:
			logger.warning(f'[SessionManager] ⚠️  LiveKit connection failed (continuing without streaming): {e}')
			logger.info('[SessionManager] Browser session will continue without LiveKit streaming')
			# Continue without LiveKit - browser automation still works

		# Set up automatic event broadcasting from browser session
		self._setup_browser_event_listeners(browser_session, action_dispatcher, room_name)

		# Navigate to initial URL if provided
		if initial_url:
			from navigator.action.command import NavigateActionCommand

			action = NavigateActionCommand(params={'url': initial_url})
			await action_dispatcher.execute_action(action)

		# Store session
		session_info = BrowserSessionInfo(
			room_name=room_name,
			browser_session=browser_session,
			action_dispatcher=action_dispatcher,
			livekit_service=livekit_service,
		)
		session_info.is_active = True
		self.sessions[room_name] = session_info

		# Start CommandConsumer for sequenced communication (if available)
		await self._start_command_consumer(room_name)

		logger.info(f'[SessionManager] ✅ Browser session started for room: {room_name}')
		return {'status': 'started', 'room_name': room_name}

	def _setup_browser_event_listeners(self, browser_session: BrowserSession, action_dispatcher: 'ActionDispatcher', room_name: str) -> None:
		"""Set up automatic event listeners for browser session events.

		Args:
			browser_session: Browser session to listen to
			action_dispatcher: Action dispatcher for getting browser context
			room_name: LiveKit room name for event broadcasting
		"""
		from browser_use.browser.events import BrowserErrorEvent, NavigationCompleteEvent

		# Capture action_dispatcher in closure
		_dispatcher = action_dispatcher
		_room = room_name

		async def on_navigation_complete(event: NavigationCompleteEvent) -> None:
			"""Handle navigation complete events."""
			logger.debug(f'[SessionManager] Navigation complete event: {event.url}')

			# Broadcast page navigation event
			if self.event_broadcaster:
				await self.event_broadcaster.broadcast_page_navigation(_room, event.url)

			# Wait a bit for page to fully settle, then broadcast page_load_complete
			# Check ready state after navigation
			await asyncio.sleep(0.5)  # Small delay to let page settle

			try:
				context = await _dispatcher.get_browser_context()
				if context.ready_state == 'complete':
					logger.debug(f'[SessionManager] Page load complete: {event.url}')
					if self.event_broadcaster:
						await self.event_broadcaster.broadcast_page_load_complete(_room, event.url)
			except Exception as e:
				logger.warning(f'[SessionManager] Could not get ready state after navigation: {e}')
				# Still broadcast page_load_complete even if we can't check ready state
				if self.event_broadcaster:
					await self.event_broadcaster.broadcast_page_load_complete(_room, event.url)

		async def on_browser_error(event: BrowserErrorEvent) -> None:
			"""Handle browser error events."""
			logger.error(f'[SessionManager] Browser error event: {event.message}')

			# Broadcast browser error event
			if self.event_broadcaster:
				await self.event_broadcaster.broadcast_browser_error(_room, event.message)

			# Mark session as inactive
			session = self.sessions.get(_room)
			if session:
				session.is_active = False

		# Register event listeners using EventBus.on() (bubus API)
		browser_session.event_bus.on(NavigationCompleteEvent, on_navigation_complete)
		browser_session.event_bus.on(BrowserErrorEvent, on_browser_error)
		logger.debug(f'[SessionManager] Registered event listeners for room: {room_name}')

	async def pause_session(self, room_name: str) -> dict[str, Any]:
		"""Pause video publishing for a session (keep browser alive).

		Args:
			room_name: Name of the LiveKit room

		Returns:
			Status dict
		"""
		session = self.sessions.get(room_name)
		if not session:
			return {'status': 'error', 'error': 'Session not found'}

		if session.is_paused:
			return {'status': 'already_paused', 'room_name': room_name}

		logger.info(f'Pausing browser session for room: {room_name}')
		await session.livekit_service.stop_publishing()
		session.is_paused = True

		return {'status': 'paused', 'room_name': room_name}

	async def resume_session(self, room_name: str) -> dict[str, Any]:
		"""Resume video publishing for a session.

		Args:
			room_name: Name of the LiveKit room

		Returns:
			Status dict
		"""
		session = self.sessions.get(room_name)
		if not session:
			return {'status': 'error', 'error': 'Session not found'}

		if not session.is_paused:
			return {'status': 'not_paused', 'room_name': room_name}

		logger.info(f'Resuming browser session for room: {room_name}')
		await session.livekit_service.start_publishing(session.browser_session)
		session.is_paused = False

		return {'status': 'resumed', 'room_name': room_name}

	async def close_session(self, room_name: str) -> dict[str, Any]:
		"""Close a browser session.

		Args:
			room_name: Name of the LiveKit room

		Returns:
			Status dict
		"""
		session = self.sessions.get(room_name)
		if not session:
			return {'status': 'error', 'error': 'Session not found'}

		logger.info(f'Closing browser session for room: {room_name}')

		try:
			# Stop CommandConsumer for this session (if running)
			await self._stop_command_consumer(room_name)

			# Stop video publishing
			if session.livekit_service:
				try:
					await session.livekit_service.stop_publishing()
					await session.livekit_service.disconnect()
				except Exception as e:
					logger.warning(f'Error stopping LiveKit service: {e}')

			# Close browser
			try:
				await session.browser_session.kill()
			except Exception as e:
				logger.warning(f'Error killing browser session: {e}')

		except Exception as e:
			logger.error(f'Error closing session: {e}', exc_info=True)
		finally:
			# Remove session
			if room_name in self.sessions:
				del self.sessions[room_name]

		return {'status': 'closed', 'room_name': room_name}

	def _init_sequenced_components(self) -> None:
		"""Initialize sequenced communication components (lazy initialization)."""
		if self._state_diff_engine is not None:
			return  # Already initialized

		try:
			from navigator.state.dedup_cache import DedupCache
			from navigator.state.diff_engine import StateDiffEngine
			from navigator.state.sequence_tracker import SequenceTracker

			# Initialize components
			self._state_diff_engine = StateDiffEngine()
			self._sequence_tracker = SequenceTracker()
			self._dedup_cache = DedupCache(ttl_seconds=300)  # 5 minutes TTL

			# Initialize Redis client for streams (async, so we'll initialize it when needed)
			# For now, set to None - will be initialized async when needed
			self._redis_streams_client = None
			self._state_publisher = None

			logger.debug("Sequenced communication components initialized")
		except ImportError as e:
			logger.debug(f"Sequenced communication components not available: {e}")

	async def _get_redis_streams_client(self) -> Any | None:
		"""Get Redis async client for streams (lazy initialization)."""
		if self._redis_streams_client is None:
			try:
				from navigator.streaming.redis_client import get_redis_streams_client
				self._redis_streams_client = await get_redis_streams_client()
				if self._redis_streams_client:
					# Initialize state publisher with Redis client
					from navigator.streaming.state_publisher import StatePublisher
					self._state_publisher = StatePublisher(self._redis_streams_client)
			except Exception as e:
				logger.debug(f"Redis streams client not available: {e}")
		return self._redis_streams_client

	def get_state_diff_engine(self) -> Any | None:
		"""Get StateDiffEngine instance (lazy initialization)."""
		self._init_sequenced_components()
		return self._state_diff_engine

	def get_sequence_tracker(self) -> Any | None:
		"""Get SequenceTracker instance (lazy initialization)."""
		self._init_sequenced_components()
		return self._sequence_tracker

	def get_dedup_cache(self) -> Any | None:
		"""Get DedupCache instance (lazy initialization)."""
		self._init_sequenced_components()
		return self._dedup_cache

	async def get_state_publisher(self) -> Any | None:
		"""Get StatePublisher instance (lazy initialization, requires Redis)."""
		self._init_sequenced_components()
		if self._state_publisher is None:
			await self._get_redis_streams_client()  # This will initialize state_publisher
		return self._state_publisher

	async def _get_command_consumer(self) -> Any | None:
		"""Get or create CommandConsumer instance (lazy initialization, singleton per manager)."""
		if self._command_consumer is None:
			try:
				from navigator.streaming.command_consumer_factory import create_command_consumer

				# Create CommandConsumer using factory (handles all component initialization)
				self._command_consumer = await create_command_consumer(
					session_manager=self,
					consumer_group="browser_agent_cluster",
				)

				if self._command_consumer:
					logger.info("CommandConsumer created and ready")
				else:
					logger.debug("CommandConsumer not available (Redis/components not configured)")
			except Exception as e:
				logger.debug(f"CommandConsumer not available: {e}")

		return self._command_consumer

	async def _start_command_consumer(self, session_id: str) -> None:
		"""Start CommandConsumer for a session (if available)."""
		try:
			command_consumer = await self._get_command_consumer()
			if command_consumer:
				await command_consumer.start_consuming(session_id)
				logger.info(f"CommandConsumer started for session: {session_id}")
			else:
				logger.debug(f"CommandConsumer not available, skipping start for session: {session_id}")
		except Exception as e:
			logger.warning(f"Failed to start CommandConsumer for session {session_id}: {e}")
			# Don't fail session start if CommandConsumer fails

	async def _stop_command_consumer(self, session_id: str) -> None:
		"""Stop CommandConsumer for a session (if running)."""
		try:
			if self._command_consumer:
				await self._command_consumer.stop_consuming(session_id)
				logger.info(f"CommandConsumer stopped for session: {session_id}")
		except Exception as e:
			logger.warning(f"Failed to stop CommandConsumer for session {session_id}: {e}")
			# Don't fail session close if CommandConsumer fails

	async def handle_browser_error(self, room_name: str, error: str) -> None:
		"""Handle browser error and broadcast to voice agent.

		Args:
			room_name: LiveKit room name
			error: Error message
		"""
		logger.error(f'Browser error in room {room_name}: {error}')

		# Broadcast error event
		if self.event_broadcaster:
			await self.event_broadcaster.broadcast_browser_error(room_name, error)

		# Mark session as inactive
		session = self.sessions.get(room_name)
		if session:
			session.is_active = False

	async def recover_session(self, room_name: str) -> dict[str, Any]:
		"""Attempt to recover a failed browser session.

		Args:
			room_name: LiveKit room name

		Returns:
			Recovery status dict
		"""
		session = self.sessions.get(room_name)
		if not session:
			return {'status': 'error', 'error': 'Session not found'}

		logger.info(f'Attempting to recover browser session for room: {room_name}')

		try:
			# Check if browser is still alive
			if session.browser_session._cdp_client_root is None:
				# Browser is dead, need to restart
				logger.warning('Browser session is dead, cannot recover without restart')
				return {'status': 'error', 'error': 'Browser session is dead, requires restart'}

			# Try to reconnect LiveKit if disconnected
			if session.livekit_service and not session.livekit_service.is_active:
				try:
					await session.livekit_service.connect()
					if not session.is_paused:
						await session.livekit_service.start_publishing(session.browser_session)
					logger.info('LiveKit service reconnected')
				except Exception as e:
					logger.error(f'Failed to reconnect LiveKit: {e}')
					return {'status': 'error', 'error': f'Failed to reconnect LiveKit: {e}'}

			# Mark session as active again
			session.is_active = True

			return {'status': 'recovered', 'room_name': room_name}

		except Exception as e:
			logger.error(f'Recovery failed: {e}', exc_info=True)
			return {'status': 'error', 'error': str(e)}

	def get_session(self, room_name: str) -> BrowserSessionInfo | None:
		"""Get session info for a room.

		Args:
			room_name: Name of the LiveKit room

		Returns:
			BrowserSessionInfo or None
		"""
		return self.sessions.get(room_name)

	async def execute_action(self, room_name: str, action_type: str, params: dict[str, Any]) -> dict[str, Any]:
		"""Execute an action on a browser session.

		Args:
			room_name: Name of the LiveKit room
			action_type: Type of action to execute
			params: Action parameters

		Returns:
			Action result dict
		"""
		session = self.sessions.get(room_name)
		if not session:
			return {'success': False, 'error': 'Session not found'}

		if not session.is_active:
			return {'success': False, 'error': 'Session not active'}

		from navigator.action.command import (
			ActionCommand,
			ActionType,
			ClickActionCommand,
			NavigateActionCommand,
			ScrollActionCommand,
			TypeActionCommand,
			WaitActionCommand,
		)

		# Map string action type to ActionType enum (for core actions) or string (for extended actions)
		action_type_map: dict[str, ActionType | str] = {
			# Core navigation actions
			'navigate': ActionType.NAVIGATE,
			'click': ActionType.CLICK,
			'type': ActionType.TYPE,
			'scroll': ActionType.SCROLL,
			'wait': ActionType.WAIT,
			'go_back': ActionType.GO_BACK,
			'go_forward': ActionType.GO_FORWARD,
			'refresh': ActionType.REFRESH,
			'send_keys': ActionType.SEND_KEYS,
			# Extended actions (use string values directly, ActionDispatcher handles them)
			'right_click': 'right_click',
			'double_click': 'double_click',
			'hover': 'hover',
			'drag_drop': 'drag_drop',
			'type_slowly': 'type_slowly',
			'select_all': 'select_all',
			'copy': 'copy',
			'paste': 'paste',
			'cut': 'cut',
			'clear': 'clear',
			'upload_file': ActionType.UPLOAD_FILE,
			'select_dropdown': 'select_dropdown',
			'fill_form': 'fill_form',
			'select_multiple': 'select_multiple',
			'submit_form': 'submit_form',
			'reset_form': 'reset_form',
			'play_video': 'play_video',
			'pause_video': 'pause_video',
			'seek_video': 'seek_video',
			'adjust_volume': 'adjust_volume',
			'toggle_fullscreen': 'toggle_fullscreen',
			'toggle_mute': 'toggle_mute',
			'take_screenshot': 'take_screenshot',
			'keyboard_shortcut': 'keyboard_shortcut',
			'multi_select': 'multi_select',
			'highlight_element': 'highlight_element',
			'zoom_in': 'zoom_in',
			'zoom_out': 'zoom_out',
			'zoom_reset': 'zoom_reset',
			'download_file': 'download_file',
			'presentation_mode': 'presentation_mode',
			'show_pointer': 'show_pointer',
			'animate_scroll': 'animate_scroll',
			'highlight_region': 'highlight_region',
			'draw_on_page': 'draw_on_page',
			'focus_element': 'focus_element',
		}

		action_type_value = action_type_map.get(action_type)
		if not action_type_value:
			return {'success': False, 'error': f'Unknown action_type: {action_type}'}

		# Create action command
		# For core actions with specific command classes, use them; otherwise use generic ActionCommand
		if isinstance(action_type_value, ActionType):
			if action_type_value == ActionType.NAVIGATE:
				action = NavigateActionCommand(params=params)
			elif action_type_value == ActionType.CLICK:
				action = ClickActionCommand(params=params)
			elif action_type_value == ActionType.TYPE:
				action = TypeActionCommand(params=params)
			elif action_type_value == ActionType.SCROLL:
				action = ScrollActionCommand(params=params)
			elif action_type_value == ActionType.WAIT:
				action = WaitActionCommand(params=params)
			else:
				# Other enum values (go_back, go_forward, refresh, send_keys, upload_file)
				action = ActionCommand(action_type=action_type_value, params=params)
		else:
			# For extended actions (string values), use ActionCommand with string action_type
			# ActionDispatcher handles these via string comparison
			action = ActionCommand(action_type=action_type_value, params=params)

		# Execute action
		try:
			result = await session.action_dispatcher.execute_action(action)

			# Broadcast events
			if self.event_broadcaster:
				if result.success:
					await self.event_broadcaster.broadcast_action_completed(
						room_name, {'action_type': action_type, 'params': params}
					)
					# Check if navigation occurred
					if action_type == 'navigate' and 'url' in params:
						await self.event_broadcaster.broadcast_page_navigation(room_name, params['url'])
				else:
					await self.event_broadcaster.broadcast_action_error(
						room_name, result.error or 'Unknown error', {'action_type': action_type, 'params': params}
					)

			return {
				'success': result.success,
				'error': result.error,
				'data': result.data,
			}
		except Exception as e:
			# Broadcast error event
			error_msg = str(e)
			if self.event_broadcaster:
				await self.event_broadcaster.broadcast_action_error(
					room_name, error_msg, {'action_type': action_type, 'params': params}
				)

			logger.error(f'Action execution failed: {e}', exc_info=True)
			return {
				'success': False,
				'error': error_msg,
				'data': {},
			}

	async def get_browser_context(self, room_name: str) -> dict[str, Any]:
		"""Get browser context for a session.

		Args:
			room_name: Name of the LiveKit room

		Returns:
			Browser context dict with URL, title, ready state, scroll position, viewport, and cursor position
		"""
		session = self.sessions.get(room_name)
		if not session:
			return {'error': 'Session not found'}

		context = await session.action_dispatcher.get_browser_context()

		# Convert BrowserContext Pydantic model to dict
		if hasattr(context, 'model_dump'):
			return context.model_dump()
		else:
			# Fallback: manual conversion
			return {
				'url': context.url,
				'title': context.title,
				'ready_state': context.ready_state,
				'scroll_x': context.scroll_x,
				'scroll_y': context.scroll_y,
				'viewport_width': context.viewport_width,
				'viewport_height': context.viewport_height,
				'cursor_x': context.cursor_x,
				'cursor_y': context.cursor_y,
			}

	async def get_screen_content(self, room_name: str) -> dict[str, Any]:
		"""Get screen content with DOM summary for agent communication.

		Args:
			room_name: Name of the LiveKit room

		Returns:
			Screen content dict with DOM summary, scroll position, viewport, and cursor position
		"""
		session = self.sessions.get(room_name)
		if not session:
			return {'error': 'Session not found'}

		screen_content = await session.action_dispatcher.get_screen_content()

		# Broadcast screen content update event
		if self.event_broadcaster:
			await self.event_broadcaster.broadcast_screen_content(room_name, screen_content.model_dump())

		return screen_content.model_dump()

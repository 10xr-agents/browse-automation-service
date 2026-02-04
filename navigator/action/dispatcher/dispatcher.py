"""
Main ActionDispatcher class.

Routes action commands to appropriate handlers and manages browser context.
"""

import asyncio
import logging

from browser_use import BrowserSession
from browser_use.browser.views import BrowserError
from browser_use.dom.service import DomService
from navigator.action.command import (
	ActionCommand,
	ActionResult,
	BrowserContext,
	ScreenContent,
)
from navigator.action.dispatcher.handlers import (
	input as input_handlers,
)
from navigator.action.dispatcher.handlers import (
	interaction as interaction_handlers,
)
from navigator.action.dispatcher.handlers import (
	navigation as navigation_handlers,
)
from navigator.action.dispatcher.handlers import (
	scrolling as scrolling_handlers,
)
from navigator.action.dispatcher.handlers import (
	utility as utility_handlers,
)
from navigator.action.dispatcher.utils import get_element_by_index

logger = logging.getLogger(__name__)


class ActionDispatcher:
	"""Dispatches ActionCommand primitives to browser events."""

	def __init__(self, browser_session: BrowserSession):
		"""Initialize the action dispatcher.

		Args:
			browser_session: The browser session to execute actions on
		"""
		self.browser_session = browser_session
		self.dom_service: DomService | None = None
		self._last_cursor_x: int | None = None
		self._last_cursor_y: int | None = None

	async def execute_action(self, action: ActionCommand) -> ActionResult:
		"""Execute an action command and return the result.

		Args:
			action: The action command to execute

		Returns:
			ActionResult with success/error indication
		"""
		# Get string value for comparison (ActionType uses use_enum_values=True, so it's already a string)
		action_type_str = action.action_type.value if hasattr(action.action_type, 'value') else str(action.action_type)
		logger.debug(f'[ActionDispatcher] Executing action: {action_type_str}')
		logger.debug(f'[ActionDispatcher] Action params: {action.params}')

		try:
			# Route to appropriate handler based on action type (compare with string value)
			if action_type_str == 'click':
				result, new_x, new_y = await interaction_handlers.execute_click(
					self.browser_session, action, self._last_cursor_x, self._last_cursor_y
				)
				self._last_cursor_x = new_x
				self._last_cursor_y = new_y
				return result
			elif action_type_str == 'type':
				return await input_handlers.execute_type(self.browser_session, action)
			elif action_type_str == 'navigate':
				return await navigation_handlers.execute_navigate(self.browser_session, action)
			elif action_type_str == 'scroll':
				return await scrolling_handlers.execute_scroll(self.browser_session, action)
			elif action_type_str == 'wait':
				return await utility_handlers.execute_wait(self.browser_session, action)
			elif action_type_str == 'go_back':
				return await navigation_handlers.execute_go_back(self.browser_session, action)
			elif action_type_str == 'go_forward':
				return await navigation_handlers.execute_go_forward(self.browser_session, action)
			elif action_type_str == 'refresh':
				return await navigation_handlers.execute_refresh(self.browser_session, action)
			elif action_type_str == 'send_keys':
				return await input_handlers.execute_send_keys(self.browser_session, action)
			# Step 1.7: Interaction Actions
			elif action_type_str == 'right_click':
				return await interaction_handlers.execute_right_click(self.browser_session, action)
			elif action_type_str == 'double_click':
				return await interaction_handlers.execute_double_click(self.browser_session, action)
			elif action_type_str == 'hover':
				return await interaction_handlers.execute_hover(self.browser_session, action)
			elif action_type_str == 'drag_drop':
				return await interaction_handlers.execute_drag_drop(self.browser_session, action)
			# Step 1.8: Text Input Actions (many use send_keys)
			elif action_type_str in ('select_all', 'copy', 'paste', 'cut', 'clear'):
				return await input_handlers.execute_text_input_action(self.browser_session, action_type_str, action)
			elif action_type_str == 'type_slowly':
				return await input_handlers.execute_type_slowly(self.browser_session, action)
			# Step 1.9: Form Actions
			elif action_type_str == 'upload_file':
				return await self._execute_upload_file(action)
			elif action_type_str == 'select_dropdown':
				return await self._execute_select_dropdown(action)
			elif action_type_str in ('fill_form', 'select_multiple', 'submit_form', 'reset_form'):
				return await self._execute_form_action(action_type_str, action)
			# Step 1.10: Media Actions (require JavaScript)
			elif action_type_str in ('play_video', 'pause_video', 'seek_video', 'adjust_volume', 'toggle_fullscreen', 'toggle_mute'):
				return await self._execute_media_action(action_type_str, action)
			# Step 1.11: Advanced Actions
			elif action_type_str == 'take_screenshot':
				return await utility_handlers.execute_take_screenshot(self.browser_session, action)
			elif action_type_str == 'keyboard_shortcut':
				return await self._execute_keyboard_shortcut(action)
			elif action_type_str in ('multi_select', 'highlight_element', 'zoom_in', 'zoom_out', 'zoom_reset', 'download_file'):
				return await self._execute_advanced_action(action_type_str, action)
			# Step 1.12: Presentation-Specific Actions (require JavaScript)
			elif action_type_str in ('presentation_mode', 'show_pointer', 'animate_scroll', 'highlight_region', 'draw_on_page', 'focus_element'):
				return await self._execute_presentation_action(action_type_str, action)
			else:
				result = ActionResult(
					success=False,
					error=f'Unsupported action type: {action_type_str}',
				)

			logger.debug(f'[ActionDispatcher] Action result: success={result.success}, error={result.error}')
			return result

		except BrowserError as e:
			# Browser errors are expected and should be returned as ActionResult
			return ActionResult(
				success=False,
				error=e.message or str(e),
				data={'browser_error': True},
			)
		except Exception as e:
			logger.error(f'Action execution failed: {type(e).__name__}: {e}', exc_info=True)
			return ActionResult(
				success=False,
				error=f'Action execution failed: {str(e)}',
			)

	# Form Actions (Step 1.9)
	async def _execute_upload_file(self, action: ActionCommand) -> ActionResult:
		"""Execute upload_file action."""
		from browser_use.browser.events import UploadFileEvent
		from browser_use.browser.views import BrowserError

		params = action.params

		if 'index' not in params or 'file_path' not in params:
			return ActionResult(
				success=False,
				error='Upload_file action requires "index" and "file_path" parameters',
			)

		index = params['index']
		file_path = params['file_path']
		element = await get_element_by_index(self.browser_session, index)

		if element is None:
			return ActionResult(
				success=False,
				error=f'Element with index {index} not found',
			)

		try:
			event = self.browser_session.event_bus.dispatch(
				UploadFileEvent(node=element, file_path=file_path)
			)
			await event
			await event.event_result(raise_if_any=False, raise_if_none=False)

			return ActionResult(success=True, data={'file_path': file_path})
		except BrowserError as e:
			return ActionResult(success=False, error=e.message or str(e), data={'browser_error': True})
		except Exception as e:
			logger.error(f'Upload file execution failed: {e}', exc_info=True)
			return ActionResult(success=False, error=f'Upload file execution failed: {str(e)}')

	async def _execute_select_dropdown(self, action: ActionCommand) -> ActionResult:
		"""Execute select_dropdown action."""
		from browser_use.browser.events import SelectDropdownOptionEvent
		from browser_use.browser.views import BrowserError

		params = action.params

		if 'index' not in params or 'text' not in params:
			return ActionResult(
				success=False,
				error='Select_dropdown action requires "index" and "text" parameters',
			)

		index = params['index']
		text = params['text']
		element = await get_element_by_index(self.browser_session, index)

		if element is None:
			return ActionResult(
				success=False,
				error=f'Element with index {index} not found',
			)

		try:
			event = self.browser_session.event_bus.dispatch(
				SelectDropdownOptionEvent(node=element, text=text)
			)
			await event
			await event.event_result(raise_if_any=False, raise_if_none=False)

			return ActionResult(success=True, data={'text': text})
		except BrowserError as e:
			return ActionResult(success=False, error=e.message or str(e), data={'browser_error': True})
		except Exception as e:
			logger.error(f'Select dropdown execution failed: {e}', exc_info=True)
			return ActionResult(success=False, error=f'Select dropdown execution failed: {str(e)}')

	async def _execute_form_action(self, action_type: str, action: ActionCommand) -> ActionResult:
		"""Execute form actions (fill_form, select_multiple, submit_form, reset_form)."""
		from browser_use.browser.events import SendKeysEvent, TypeTextEvent
		from navigator.action.dispatcher.utils import execute_javascript, get_element_by_index, wait_for_transition

		params = action.params

		if action_type == 'fill_form':
			# Fill form with multiple fields
			if 'fields' not in params:
				return ActionResult(success=False, error='Fill_form action requires "fields" parameter')

			fields = params['fields']
			results = []

			for field in fields:
				field_index = field.get('index')
				field_value = field.get('value')

				if field_index is None or field_value is None:
					continue

				element = await get_element_by_index(self.browser_session, field_index)
				if element is None:
					continue

				event = self.browser_session.event_bus.dispatch(
					TypeTextEvent(node=element, text=str(field_value), clear=True)
				)
				await event
				await event.event_result(raise_if_any=False, raise_if_none=False)
				results.append({'index': field_index, 'value': field_value})

			return ActionResult(success=True, data={'fields': results})

		elif action_type == 'submit_form':
			# Submit form (press Enter or find submit button)
			if 'index' in params:
				index = params['index']
				# Get initial URL before submission
				try:
					initial_url = await self.browser_session.get_current_page_url()
				except Exception:
					initial_url = None
				
				# Use send_keys with Enter
				event = self.browser_session.event_bus.dispatch(SendKeysEvent(keys='Enter'))
				await event
				await event.event_result(raise_if_any=False, raise_if_none=False)
				
				# Wait for form submission to complete (navigation, DOM updates, network requests)
				try:
					from navigator.action.dispatcher.utils import wait_for_transition
					transition_result = await wait_for_transition(
						browser_session=self.browser_session,
						initial_url=initial_url,
						max_wait_time=8.0,  # Form submissions can take time
						check_interval=0.3,
						wait_for_dom_stability=True,
						wait_for_network_idle=True,
					)
					if transition_result['url_changed']:
						logger.debug(f"✅ Form submission caused navigation: {initial_url} → {transition_result['final_url']}")
					else:
						logger.debug(f"✅ Form submission complete (no URL change, likely SPA update)")
					
					# Record delay for intelligence tracking
					from navigator.knowledge.delay_tracking import get_delay_tracker
					delay_tracker = get_delay_tracker()
					action_id = params.get('action_id') or f"submit_form_{index}"
					final_url = transition_result.get('final_url', initial_url)
					
					delay_tracker.record_delay(
						entity_id=action_id,
						entity_type='action',
						delay_ms=transition_result.get('wait_time_ms', transition_result['wait_time'] * 1000),
						url_changed=transition_result.get('url_changed', False),
						dom_stable=transition_result.get('dom_stable', False),
						network_idle=transition_result.get('network_idle', False),
						context={
							'action_type': 'submit_form',
							'form_index': index,
							'initial_url': initial_url,
							'final_url': final_url,
						},
					)
					
					# Also track as transition if URL changed
					if transition_result.get('url_changed', False) and initial_url and initial_url != final_url:
						delay_tracker.record_transition_delay(
							from_url=initial_url,
							to_url=final_url,
							delay_ms=transition_result.get('wait_time_ms', transition_result['wait_time'] * 1000),
							url_changed=True,
							dom_stable=transition_result.get('dom_stable', False),
							network_idle=transition_result.get('network_idle', False),
							context={
								'action_type': 'submit_form',
								'action_id': action_id,
								'form_index': index,
							},
						)
				except Exception as e:
					# Don't fail form submission if transition waiting fails
					logger.debug(f"Error waiting for form submission transition: {e}")
					await asyncio.sleep(1.0)  # Fallback
				
				return ActionResult(success=True, data={})
			else:
				return ActionResult(success=False, error='Submit_form action requires "index" parameter')

		elif action_type == 'reset_form':
			# Reset form using JavaScript
			if 'index' not in params:
				return ActionResult(success=False, error='Reset_form action requires "index" parameter')

			index = params['index']
			js_code = f'''
			(function(){{
				try {{
					const allElements = Array.from(document.querySelectorAll('*'));
					const element = allElements[{index}];
					if (element && element.form) {{
						element.form.reset();
						return {{success: true}};
					}}
					return {{error: 'Element or form not found'}};
				}} catch(e) {{
					return {{error: e.message}};
				}}
			}})()
			'''

			result = await execute_javascript(self.browser_session, js_code)
			if 'error' in result:
				return ActionResult(success=False, error=result['error'])
			return ActionResult(success=True, data=result.get('result', {}))

		elif action_type == 'select_multiple':
			# Select multiple options (for multi-select dropdowns)
			if 'index' not in params or 'values' not in params:
				return ActionResult(success=False, error='Select_multiple action requires "index" and "values" parameters')

			index = params['index']
			values = params['values']
			element = await get_element_by_index(self.browser_session, index)

			if element is None:
				return ActionResult(success=False, error=f'Element with index {index} not found')

			# Use JavaScript for multi-select
			values_str = ','.join([f'"{v}"' for v in values])
			js_code = f'''
			(function(){{
				try {{
					const allElements = Array.from(document.querySelectorAll('*'));
					const element = allElements[{index}];
					if (element && element.tagName === 'SELECT') {{
						const values = [{values_str}];
						Array.from(element.options).forEach(option => {{
							option.selected = values.includes(option.value) || values.includes(option.text);
						}});
						element.dispatchEvent(new Event('change', {{bubbles: true}}));
						return {{success: true}};
					}}
					return {{error: 'Element is not a select element'}};
				}} catch(e) {{
					return {{error: e.message}};
				}}
			}})()
			'''

			result = await execute_javascript(self.browser_session, js_code)
			if 'error' in result:
				return ActionResult(success=False, error=result['error'])
			return ActionResult(success=True, data=result.get('result', {}))

		return ActionResult(success=False, error=f'Unknown form action: {action_type}')

	# Media Actions (Step 1.10)
	async def _execute_media_action(self, action_type: str, action: ActionCommand) -> ActionResult:
		"""Execute media actions (play_video, pause_video, seek_video, adjust_volume, toggle_fullscreen, toggle_mute)."""
		from navigator.action.dispatcher.utils import execute_javascript

		params = action.params
		index = params.get('index', 0)

		if action_type == 'play_video':
			js_action = 'element.play();'
		elif action_type == 'pause_video':
			js_action = 'element.pause();'
		elif action_type == 'seek_video':
			timestamp = params.get('timestamp', 0)
			js_action = f'element.currentTime = {timestamp};'
		elif action_type == 'adjust_volume':
			volume = params.get('volume', 0.5)
			js_action = f'element.volume = {volume};'
		elif action_type == 'toggle_fullscreen':
			js_action = 'element.requestFullscreen();'
		elif action_type == 'toggle_mute':
			js_action = 'element.muted = !element.muted;'
		else:
			return ActionResult(success=False, error=f'Unknown media action: {action_type}')

		js_code = f'''
		(function(){{
			try {{
				const allElements = Array.from(document.querySelectorAll('video, audio'));
				const element = allElements[{index}];
				if (element) {{
					{js_action}
					return {{success: true}};
				}}
				return {{error: 'Media element not found'}};
			}} catch(e) {{
				return {{error: e.message}};
			}}
		}})()
		'''

		result = await execute_javascript(self.browser_session, js_code)
		if 'error' in result:
			return ActionResult(success=False, error=result['error'])
		return ActionResult(success=True, data=result.get('result', {}))

	# Advanced Actions (Step 1.11)
	async def _execute_keyboard_shortcut(self, action: ActionCommand) -> ActionResult:
		"""Execute keyboard_shortcut action."""
		from browser_use.browser.events import SendKeysEvent
		from browser_use.browser.views import BrowserError

		params = action.params

		if 'keys' not in params:
			return ActionResult(success=False, error='Keyboard_shortcut action requires "keys" parameter')

		keys = params['keys']
		if isinstance(keys, list):
			keys = '+'.join(keys)

		try:
			event = self.browser_session.event_bus.dispatch(SendKeysEvent(keys=keys))
			await event
			await event.event_result(raise_if_any=False, raise_if_none=False)
			return ActionResult(success=True, data={'keys': keys})
		except BrowserError as e:
			return ActionResult(success=False, error=e.message or str(e), data={'browser_error': True})
		except Exception as e:
			logger.error(f'Keyboard shortcut execution failed: {e}', exc_info=True)
			return ActionResult(success=False, error=f'Keyboard shortcut execution failed: {str(e)}')

	async def _execute_advanced_action(self, action_type: str, action: ActionCommand) -> ActionResult:
		"""Execute advanced actions (multi_select, highlight_element, zoom_in, zoom_out, zoom_reset, download_file)."""
		from navigator.action.dispatcher.utils import execute_javascript

		params = action.params

		if action_type == 'zoom_in':
			js_code = '(function(){document.body.style.zoom = (parseFloat(document.body.style.zoom) || 1) + 0.1; return {success: true};})()'
		elif action_type == 'zoom_out':
			js_code = '(function(){document.body.style.zoom = Math.max(0.5, (parseFloat(document.body.style.zoom) || 1) - 0.1); return {success: true};})()'
		elif action_type == 'zoom_reset':
			js_code = '(function(){document.body.style.zoom = 1; return {success: true};})()'
		elif action_type == 'highlight_element':
			index = params.get('index', 0)
			js_code = f'''
			(function(){{
				try {{
					const allElements = Array.from(document.querySelectorAll('*'));
					const element = allElements[{index}];
					if (element) {{
						const originalOutline = element.style.outline;
						element.style.outline = '3px solid red';
						setTimeout(() => {{ element.style.outline = originalOutline; }}, 1000);
						return {{success: true}};
					}}
					return {{error: 'Element not found'}};
				}} catch(e) {{
					return {{error: e.message}};
				}}
			}})()
			'''
		elif action_type == 'download_file':
			# Download file - browser-use handles this automatically via DownloadsWatchdog
			return ActionResult(success=True, data={'note': 'Downloads are handled automatically by browser-use'})
		else:
			return ActionResult(success=False, error=f'Unknown advanced action: {action_type}')

		result = await execute_javascript(self.browser_session, js_code)
		if 'error' in result:
			return ActionResult(success=False, error=result['error'])
		return ActionResult(success=True, data=result.get('result', {}))

	# Presentation Actions (Step 1.12)
	async def _execute_presentation_action(self, action_type: str, action: ActionCommand) -> ActionResult:
		"""Execute presentation-specific actions."""
		from navigator.action.dispatcher.utils import execute_javascript

		params = action.params

		if action_type == 'presentation_mode':
			enabled = params.get('enabled', True)
			js_code = f'''
			(function(){{
				try {{
					if ({str(enabled).lower()}) {{
						document.documentElement.requestFullscreen();
						document.body.style.overflow = 'hidden';
						return {{success: true, mode: 'enabled'}};
					}} else {{
						document.exitFullscreen();
						document.body.style.overflow = '';
						return {{success: true, mode: 'disabled'}};
					}}
				}} catch(e) {{
					return {{error: e.message}};
				}}
			}})()
			'''
		elif action_type == 'animate_scroll':
			direction = params.get('direction', 'down')
			duration = params.get('duration', 1.0)
			amount = params.get('amount', 500)
			scroll_amount = amount if direction == 'down' else -amount
			js_code = f'''
			(function(){{
				try {{
					const start = window.pageYOffset;
					const end = start + {scroll_amount};
					const duration = {duration} * 1000;
					const startTime = performance.now();
					
					function scroll() {{
						const elapsed = performance.now() - startTime;
						const progress = Math.min(elapsed / duration, 1);
						const ease = progress * (2 - progress);
						window.scrollTo(0, start + (end - start) * ease);
						if (progress < 1) requestAnimationFrame(scroll);
					}}
					scroll();
					return {{success: true}};
				}} catch(e) {{
					return {{error: e.message}};
				}}
			}})()
			'''
		elif action_type == 'highlight_region':
			x = params.get('x', 0)
			y = params.get('y', 0)
			width = params.get('width', 100)
			height = params.get('height', 100)
			js_code = f'''
			(function(){{
				try {{
					const highlight = document.createElement('div');
					highlight.style.cssText = 'position:fixed;left:{x}px;top:{y}px;width:{width}px;height:{height}px;background:rgba(255,0,0,0.3);z-index:9999;pointer-events:none;';
					document.body.appendChild(highlight);
					setTimeout(() => highlight.remove(), 1000);
					return {{success: true}};
				}} catch(e) {{
					return {{error: e.message}};
				}}
			}})()
			'''
		elif action_type == 'focus_element':
			index = params.get('index', 0)
			js_code = f'''
			(function(){{
				try {{
					const allElements = Array.from(document.querySelectorAll('*'));
					const element = allElements[{index}];
					if (element) {{
						element.focus();
						element.scrollIntoView({{behavior: 'smooth', block: 'center'}});
						return {{success: true}};
					}}
					return {{error: 'Element not found'}};
				}} catch(e) {{
					return {{error: e.message}};
				}}
			}})()
			'''
		elif action_type in ('show_pointer', 'draw_on_page'):
			# Placeholder implementations
			return ActionResult(success=True, data={'note': f'{action_type} requires custom implementation'})
		else:
			return ActionResult(success=False, error=f'Unknown presentation action: {action_type}')

		result = await execute_javascript(self.browser_session, js_code)
		if 'error' in result:
			return ActionResult(success=False, error=result['error'])
		return ActionResult(success=True, data=result.get('result', {}))

	async def get_browser_context(self) -> BrowserContext:
		"""Get current browser context.

		Returns:
			BrowserContext with current browser state including scroll position and viewport
		"""
		url = await self.browser_session.get_current_page_url()
		title = await self.browser_session.get_current_page_title()

		# Try to determine ready state and get viewport/scroll info
		ready_state = 'unknown'
		scroll_x = 0
		scroll_y = 0
		viewport_width = 1920
		viewport_height = 1080

		try:
			cdp_session = await self.browser_session.get_or_create_cdp_session()
			# Check if we can get frame tree (indicates page is loaded)
			frame_tree = await cdp_session.cdp_client.send.Page.getFrameTree(session_id=cdp_session.session_id)
			if frame_tree:
				ready_state = 'complete'

			# Get layout metrics for scroll position and viewport
			metrics = await cdp_session.cdp_client.send.Page.getLayoutMetrics(session_id=cdp_session.session_id)
			css_visual_viewport = metrics.get('cssVisualViewport', {})
			css_layout_viewport = metrics.get('cssLayoutViewport', {})

			# Get viewport dimensions
			viewport_width = int(css_layout_viewport.get('clientWidth') or css_visual_viewport.get('clientWidth', 1920))
			viewport_height = int(css_layout_viewport.get('clientHeight') or css_visual_viewport.get('clientHeight', 1080))

			# Get scroll position
			scroll_x = int(css_visual_viewport.get('pageX', 0))
			scroll_y = int(css_visual_viewport.get('pageY', 0))
		except Exception:
			ready_state = 'loading'

		return BrowserContext(
			url=url or 'about:blank',
			title=title or 'Unknown',
			ready_state=ready_state,
			scroll_x=scroll_x,
			scroll_y=scroll_y,
			viewport_width=viewport_width,
			viewport_height=viewport_height,
			cursor_x=self._last_cursor_x,
			cursor_y=self._last_cursor_y,
		)

	async def get_screen_content(self) -> ScreenContent:
		"""Get current screen content with DOM summary for agent communication.

		Returns:
			ScreenContent with DOM summary, scroll position, viewport, and cursor position
		"""
		# Get browser state summary which includes DOM state
		browser_state = await self.browser_session.get_browser_state_summary(include_screenshot=False)

		# Get DOM summary (LLM-readable representation)
		dom_summary = browser_state.dom_state.llm_representation() if browser_state.dom_state else 'Empty DOM tree'

		# Get scroll position and viewport from page_info or browser context
		scroll_x = 0
		scroll_y = 0
		viewport_width = 1920
		viewport_height = 1080

		if browser_state.page_info:
			scroll_x = browser_state.page_info.scroll_x
			scroll_y = browser_state.page_info.scroll_y
			viewport_width = browser_state.page_info.viewport_width
			viewport_height = browser_state.page_info.viewport_height
		else:
			# Fallback: get from browser context
			context = await self.get_browser_context()
			scroll_x = context.scroll_x
			scroll_y = context.scroll_y
			viewport_width = context.viewport_width
			viewport_height = context.viewport_height

		# Count visible interactive elements
		visible_elements_count = len(browser_state.dom_state.selector_map) if browser_state.dom_state else 0

		return ScreenContent(
			url=browser_state.url,
			title=browser_state.title,
			dom_summary=dom_summary,
			visible_elements_count=visible_elements_count,
			scroll_x=scroll_x,
			scroll_y=scroll_y,
			viewport_width=viewport_width,
			viewport_height=viewport_height,
			cursor_x=self._last_cursor_x,
			cursor_y=self._last_cursor_y,
		)

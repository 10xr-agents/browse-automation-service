"""
Action Dispatcher for MVP

This module provides the bridge between ActionCommand primitives and the
existing event-driven browser automation system.

It converts ActionCommand primitives to browser events and executes them.
"""

import asyncio
import logging
from typing import Any

from browser_use import BrowserSession
from browser_use.browser.events import (
	ClickCoordinateEvent,
	ClickElementEvent,
	GoBackEvent,
	GoForwardEvent,
	NavigateToUrlEvent,
	RefreshEvent,
	ScrollEvent,
	ScreenshotEvent,
	SelectDropdownOptionEvent,
	SendKeysEvent,
	TypeTextEvent,
	UploadFileEvent,
	WaitEvent,
)
from browser_use.browser.views import BrowserError
from browser_use.dom.service import DomService

from navigator.action.command import (
	ActionCommand,
	ActionResult,
	BrowserContext,
	ClickActionCommand,
	NavigateActionCommand,
	ScreenContent,
	ScrollActionCommand,
	TypeActionCommand,
	WaitActionCommand,
)

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
				result = await self._execute_click(action)
			elif action_type_str == 'type':
				result = await self._execute_type(action)
			elif action_type_str == 'navigate':
				result = await self._execute_navigate(action)
			elif action_type_str == 'scroll':
				result = await self._execute_scroll(action)
			elif action_type_str == 'wait':
				result = await self._execute_wait(action)
			elif action_type_str == 'go_back':
				result = await self._execute_go_back(action)
			elif action_type_str == 'go_forward':
				result = await self._execute_go_forward(action)
			elif action_type_str == 'refresh':
				result = await self._execute_refresh(action)
			elif action_type_str == 'send_keys':
				result = await self._execute_send_keys(action)
			# Step 1.7: Interaction Actions
			elif action_type_str == 'right_click':
				result = await self._execute_right_click(action)
			elif action_type_str == 'double_click':
				result = await self._execute_double_click(action)
			elif action_type_str == 'hover':
				result = await self._execute_hover(action)
			elif action_type_str == 'drag_drop':
				result = await self._execute_drag_drop(action)
			# Step 1.8: Text Input Actions (many use send_keys)
			elif action_type_str in ('select_all', 'copy', 'paste', 'cut', 'clear'):
				result = await self._execute_text_input_action(action_type_str, action)
			elif action_type_str == 'type_slowly':
				result = await self._execute_type_slowly(action)
			# Step 1.9: Form Actions
			elif action_type_str == 'upload_file':
				result = await self._execute_upload_file(action)
			elif action_type_str == 'select_dropdown':
				result = await self._execute_select_dropdown(action)
			elif action_type_str in ('fill_form', 'select_multiple', 'submit_form', 'reset_form'):
				result = await self._execute_form_action(action_type_str, action)
			# Step 1.10: Media Actions (require JavaScript)
			elif action_type_str in ('play_video', 'pause_video', 'seek_video', 'adjust_volume', 'toggle_fullscreen', 'toggle_mute'):
				result = await self._execute_media_action(action_type_str, action)
			# Step 1.11: Advanced Actions
			elif action_type_str == 'take_screenshot':
				result = await self._execute_take_screenshot(action)
			elif action_type_str == 'keyboard_shortcut':
				result = await self._execute_keyboard_shortcut(action)
			elif action_type_str in ('multi_select', 'highlight_element', 'zoom_in', 'zoom_out', 'zoom_reset', 'download_file'):
				result = await self._execute_advanced_action(action_type_str, action)
			# Step 1.12: Presentation-Specific Actions (require JavaScript)
			elif action_type_str in ('presentation_mode', 'show_pointer', 'animate_scroll', 'highlight_region', 'draw_on_page', 'focus_element'):
				result = await self._execute_presentation_action(action_type_str, action)
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

	async def _execute_click(self, action: ClickActionCommand) -> ActionResult:
		"""Execute a click action."""
		params = action.params

		# Check if we have coordinates or index
		if 'coordinate_x' in params and 'coordinate_y' in params:
			# Click at coordinates - track cursor position
			coordinate_x = params['coordinate_x']
			coordinate_y = params['coordinate_y']
			self._last_cursor_x = coordinate_x
			self._last_cursor_y = coordinate_y

			event = self.browser_session.event_bus.dispatch(
				ClickCoordinateEvent(
					coordinate_x=coordinate_x,
					coordinate_y=coordinate_y,
					button=params.get('button', 'left'),
					force=params.get('force', False),
				)
			)
			await event
			result = await event.event_result(raise_if_any=False, raise_if_none=False)

			if result and isinstance(result, dict) and 'validation_error' in result:
				return ActionResult(
					success=False,
					error=result['validation_error'],
				)

			return ActionResult(
				success=True,
				data=result if isinstance(result, dict) else {},
			)

		elif 'index' in params:
			# Click by element index - need to get element from DOM
			index = params['index']
			element = await self._get_element_by_index(index)

			if element is None:
				return ActionResult(
					success=False,
					error=f'Element with index {index} not found',
				)

			# Track cursor position - try to get element center coordinates
			try:
				if element.snapshot_node and element.snapshot_node.bounds:
					bounds = element.snapshot_node.bounds
					center_x = int(bounds.x + bounds.width / 2)
					center_y = int(bounds.y + bounds.height / 2)
					self._last_cursor_x = center_x
					self._last_cursor_y = center_y
			except Exception:
				# If we can't get coordinates, that's okay - cursor position will be None
				pass

			event = self.browser_session.event_bus.dispatch(
				ClickElementEvent(
					node=element,
					button=params.get('button', 'left'),
				)
			)
			await event
			result = await event.event_result(raise_if_any=False, raise_if_none=False)

			if result and isinstance(result, dict) and 'validation_error' in result:
				return ActionResult(
					success=False,
					error=result['validation_error'],
				)

			return ActionResult(
				success=True,
				data=result if isinstance(result, dict) else {},
			)
		else:
			return ActionResult(
				success=False,
				error='Click action requires either "index" or "coordinate_x"/"coordinate_y" parameters',
			)

	async def _execute_type(self, action: TypeActionCommand) -> ActionResult:
		"""Execute a type action."""
		params = action.params

		if 'text' not in params:
			return ActionResult(
				success=False,
				error='Type action requires "text" parameter',
			)

		text = params['text']
		# Validate that text is a non-empty string
		if text is None or not isinstance(text, str):
			return ActionResult(
				success=False,
				error='Type action requires "text" parameter to be a non-empty string',
			)

		clear = params.get('clear', False)

		# If index is provided, get element from DOM
		if 'index' in params:
			index = params['index']
			element = await self._get_element_by_index(index)

			if element is None:
				return ActionResult(
					success=False,
					error=f'Element with index {index} not found',
				)

			event = self.browser_session.event_bus.dispatch(
				TypeTextEvent(
					node=element,
					text=text,
					clear=clear,
				)
			)
			await event
			result = await event.event_result(raise_if_any=False, raise_if_none=False)

			return ActionResult(
				success=True,
				data=result if isinstance(result, dict) else {},
			)
		else:
			# Type to focused element (index 0)
			# Get the first input element or use current focus
			element = await self._get_element_by_index(0)
			if element is None:
				return ActionResult(
					success=False,
					error='No element found to type into. Provide an index parameter.',
				)

			event = self.browser_session.event_bus.dispatch(
				TypeTextEvent(
					node=element,
					text=text,
					clear=clear,
				)
			)
			await event
			result = await event.event_result(raise_if_any=False, raise_if_none=False)

			return ActionResult(
				success=True,
				data=result if isinstance(result, dict) else {},
			)

	async def _execute_navigate(self, action: NavigateActionCommand) -> ActionResult:
		"""Execute a navigate action."""
		params = action.params

		if 'url' not in params:
			return ActionResult(
				success=False,
				error='Navigate action requires "url" parameter',
			)

		url = params['url']
		new_tab = params.get('new_tab', False)

		try:
			event = self.browser_session.event_bus.dispatch(
				NavigateToUrlEvent(
					url=url,
					new_tab=new_tab,
				)
			)
			await event
			await event.event_result(raise_if_any=True, raise_if_none=False)

			# Wait a bit for page to load
			await asyncio.sleep(0.5)

			return ActionResult(
				success=True,
				data={'url': url},
			)
		except BrowserError as e:
			return ActionResult(
				success=False,
				error=e.message or str(e),
				data={'browser_error': True},
			)

	async def _execute_scroll(self, action: ScrollActionCommand) -> ActionResult:
		"""Execute a scroll action."""
		params = action.params

		direction = params.get('direction', 'down')
		amount = params.get('amount', 500)  # Default to 500 pixels

		# Validate direction
		if direction not in ['up', 'down', 'left', 'right']:
			return ActionResult(
				success=False,
				error=f'Invalid scroll direction: {direction}. Use "up", "down", "left", or "right"',
			)

		# ScrollEvent uses direction and amount (in pixels), node=None means scroll page
		event = self.browser_session.event_bus.dispatch(
			ScrollEvent(
				direction=direction,  # type: ignore
				amount=amount,
				node=None,  # None means scroll the page, not a specific element
			)
		)
		await event
		await event.event_result(raise_if_any=False, raise_if_none=False)

		return ActionResult(
			success=True,
			data={'direction': direction, 'amount': amount},
		)

	async def _execute_wait(self, action: WaitActionCommand) -> ActionResult:
		"""Execute a wait action."""
		params = action.params

		if 'seconds' not in params:
			return ActionResult(
				success=False,
				error='Wait action requires "seconds" parameter',
			)

		seconds = float(params['seconds'])

		event = self.browser_session.event_bus.dispatch(WaitEvent(seconds=seconds))
		await event
		await event.event_result(raise_if_any=False, raise_if_none=False)

		return ActionResult(
			success=True,
			data={'waited_seconds': seconds},
		)

	async def _execute_go_back(self, action: ActionCommand) -> ActionResult:
		"""Execute a go back action."""
		event = self.browser_session.event_bus.dispatch(GoBackEvent())
		await event
		await event.event_result(raise_if_any=False, raise_if_none=False)

		return ActionResult(
			success=True,
			data={},
		)

	async def _execute_go_forward(self, action: ActionCommand) -> ActionResult:
		"""Execute a go forward action."""
		event = self.browser_session.event_bus.dispatch(GoForwardEvent())
		await event
		await event.event_result(raise_if_any=False, raise_if_none=False)

		return ActionResult(
			success=True,
			data={},
		)

	async def _execute_refresh(self, action: ActionCommand) -> ActionResult:
		"""Execute a refresh action."""
		event = self.browser_session.event_bus.dispatch(RefreshEvent())
		await event
		await event.event_result(raise_if_any=False, raise_if_none=False)

		return ActionResult(
			success=True,
			data={},
		)

	async def _execute_send_keys(self, action: ActionCommand) -> ActionResult:
		"""Execute a send_keys action."""
		keys = action.params.get('keys')
		if not keys:
			return ActionResult(
				success=False,
				error='keys parameter is required for send_keys action',
			)

		logger.debug(f'[ActionDispatcher] Sending keys: {keys}')
		
		from browser_use.browser.events import SendKeysEvent
		
		event = self.browser_session.event_bus.dispatch(SendKeysEvent(keys=keys))
		await event
		await event.event_result(raise_if_any=False, raise_if_none=False)

		return ActionResult(
			success=True,
			data={'keys': keys},
		)

	async def _execute_javascript(self, code: str) -> dict[str, Any]:
		"""
		Helper method to execute JavaScript code in the browser.
		
		Args:
			code: JavaScript code to execute (should be wrapped in IIFE)
		
		Returns:
			Dict with result data or error
		"""
		cdp_session = await self.browser_session.get_or_create_cdp_session()
		
		try:
			# Wrap code in IIFE if not already wrapped
			if not (code.strip().startswith('(function') or code.strip().startswith('(async function')):
				code = f'(function(){{try{{return {code}}}catch(e){{return {{error:e.message}}}}}})()'
			
			result = await cdp_session.cdp_client.send.Runtime.evaluate(
				params={'expression': code, 'returnByValue': True, 'awaitPromise': True},
				session_id=cdp_session.session_id,
			)
			
			if result.get('exceptionDetails'):
				exception = result['exceptionDetails']
				error_text = exception.get('text', 'Unknown error')
				return {'error': f'JavaScript execution error: {error_text}'}
			
			result_data = result.get('result', {})
			if result_data.get('wasThrown'):
				return {'error': 'JavaScript execution failed (wasThrown=true)'}
			
			value = result_data.get('value')
			return {'result': value} if value is not None else {'result': None}
			
		except Exception as e:
			return {'error': f'Failed to execute JavaScript: {type(e).__name__}: {e}'}

	# Step 1.7: Interaction Actions

	async def _execute_right_click(self, action: ActionCommand) -> ActionResult:
		"""Execute a right-click action."""
		params = action.params
		
		if 'index' not in params:
			return ActionResult(
				success=False,
				error='Right-click action requires "index" parameter',
			)
		
		index = params['index']
		element = await self._get_element_by_index(index)
		
		if element is None:
			return ActionResult(
				success=False,
				error=f'Element with index {index} not found',
			)
		
		try:
			event = self.browser_session.event_bus.dispatch(
				ClickElementEvent(node=element, button='right')
			)
			await event
			await event.event_result(raise_if_any=False, raise_if_none=False)
			
			return ActionResult(success=True, data={})
		except BrowserError as e:
			return ActionResult(success=False, error=e.message or str(e), data={'browser_error': True})
		except Exception as e:
			logger.error(f'Right-click execution failed: {e}', exc_info=True)
			return ActionResult(success=False, error=f'Right-click execution failed: {str(e)}')

	async def _execute_double_click(self, action: ActionCommand) -> ActionResult:
		"""Execute a double-click action using JavaScript."""
		params = action.params
		
		if 'index' not in params:
			return ActionResult(
				success=False,
				error='Double-click action requires "index" parameter',
			)
		
		index = params['index']
		element = await self._get_element_by_index(index)
		
		if element is None:
			return ActionResult(
				success=False,
				error=f'Element with index {index} not found',
			)
		
		# Double-click using JavaScript
		js_code = f'''
		(function(){{
			try {{
				const allElements = Array.from(document.querySelectorAll('*'));
				const element = allElements[{index}];
				if (element) {{
					const event = new MouseEvent('dblclick', {{bubbles: true, cancelable: true}});
					element.dispatchEvent(event);
					return {{success: true}};
				}}
				return {{error: 'Element not found'}};
			}} catch(e) {{
				return {{error: e.message}};
			}}
		}})()
		'''
		
		result = await self._execute_javascript(js_code)
		if 'error' in result:
			return ActionResult(success=False, error=result['error'])
		
		return ActionResult(success=True, data=result.get('result', {}))

	async def _execute_hover(self, action: ActionCommand) -> ActionResult:
		"""Execute a hover action using JavaScript."""
		params = action.params
		
		if 'index' not in params:
			return ActionResult(
				success=False,
				error='Hover action requires "index" parameter',
			)
		
		index = params['index']
		
		# Hover using JavaScript (mouseenter/mouseover events)
		js_code = f'''
		(function(){{
			try {{
				const allElements = Array.from(document.querySelectorAll('*'));
				const element = allElements[{index}];
				if (element) {{
					const mouseEnterEvent = new MouseEvent('mouseenter', {{bubbles: true, cancelable: true}});
					const mouseOverEvent = new MouseEvent('mouseover', {{bubbles: true, cancelable: true}});
					element.dispatchEvent(mouseEnterEvent);
					element.dispatchEvent(mouseOverEvent);
					return {{success: true}};
				}}
				return {{error: 'Element not found'}};
			}} catch(e) {{
				return {{error: e.message}};
			}}
		}})()
		'''
		
		result = await self._execute_javascript(js_code)
		if 'error' in result:
			return ActionResult(success=False, error=result['error'])
		
		return ActionResult(success=True, data=result.get('result', {}))

	async def _execute_drag_drop(self, action: ActionCommand) -> ActionResult:
		"""Execute a drag-and-drop action using JavaScript."""
		params = action.params
		
		if 'source_index' not in params or 'target_index' not in params:
			return ActionResult(
				success=False,
				error='Drag-drop action requires "source_index" and "target_index" parameters',
			)
		
		source_index = params['source_index']
		target_index = params['target_index']
		
		# Drag-and-drop using JavaScript
		js_code = f'''
		(function(){{
			try {{
				const allElements = Array.from(document.querySelectorAll('*'));
				const sourceElement = allElements[{source_index}];
				const targetElement = allElements[{target_index}];
				if (!sourceElement || !targetElement) {{
					return {{error: 'Source or target element not found'}};
				}}
				
				// Create and dispatch drag events
				const dragStartEvent = new DragEvent('dragstart', {{bubbles: true, cancelable: true}});
				sourceElement.dispatchEvent(dragStartEvent);
				
				const dragOverEvent = new DragEvent('dragover', {{bubbles: true, cancelable: true}});
				targetElement.dispatchEvent(dragOverEvent);
				
				const dropEvent = new DragEvent('drop', {{bubbles: true, cancelable: true}});
				targetElement.dispatchEvent(dropEvent);
				
				const dragEndEvent = new DragEvent('dragend', {{bubbles: true, cancelable: true}});
				sourceElement.dispatchEvent(dragEndEvent);
				
				return {{success: true}};
			}} catch(e) {{
				return {{error: e.message}};
			}}
		}})()
		'''
		
		result = await self._execute_javascript(js_code)
		if 'error' in result:
			return ActionResult(success=False, error=result['error'])
		
		return ActionResult(success=True, data=result.get('result', {}))

	# Step 1.8: Text Input Actions

	async def _execute_text_input_action(self, action_type: str, action: ActionCommand) -> ActionResult:
		"""Execute text input actions (select_all, copy, paste, cut, clear)."""
		params = action.params
		
		# Map action types to keyboard shortcuts
		key_map = {
			'select_all': 'ctrl+a',
			'copy': 'ctrl+c',
			'paste': 'ctrl+v',
			'cut': 'ctrl+x',
		}
		
		if action_type == 'clear':
			# Clear uses type with empty text
			if 'index' not in params:
				return ActionResult(success=False, error='Clear action requires "index" parameter')
			index = params['index']
			element = await self._get_element_by_index(index)
			if element is None:
				return ActionResult(success=False, error=f'Element with index {index} not found')
			
			event = self.browser_session.event_bus.dispatch(
				TypeTextEvent(node=element, text='', clear=True)
			)
			await event
			await event.event_result(raise_if_any=False, raise_if_none=False)
			return ActionResult(success=True, data={})
		
		if action_type in key_map:
			keys = key_map[action_type]
			event = self.browser_session.event_bus.dispatch(SendKeysEvent(keys=keys))
			await event
			await event.event_result(raise_if_any=False, raise_if_none=False)
			return ActionResult(success=True, data={'keys': keys})
		
		return ActionResult(success=False, error=f'Unknown text input action: {action_type}')

	async def _execute_type_slowly(self, action: ActionCommand) -> ActionResult:
		"""Execute type_slowly action (types with delays between characters)."""
		params = action.params
		
		if 'text' not in params:
			return ActionResult(success=False, error='Type_slowly action requires "text" parameter')
		
		text = params['text']
		delay = params.get('delay', 0.1)
		index = params.get('index')
		
		if index is not None:
			element = await self._get_element_by_index(index)
			if element is None:
				return ActionResult(success=False, error=f'Element with index {index} not found')
			
			# Type character by character with delays
			for char in text:
				event = self.browser_session.event_bus.dispatch(
					TypeTextEvent(node=element, text=char, clear=False)
				)
				await event
				await event.event_result(raise_if_any=False, raise_if_none=False)
				await asyncio.sleep(delay)
			
			return ActionResult(success=True, data={'text': text, 'delay': delay})
		else:
			return ActionResult(success=False, error='Type_slowly action requires "index" parameter')

	# Step 1.9: Form Actions

	async def _execute_upload_file(self, action: ActionCommand) -> ActionResult:
		"""Execute upload_file action."""
		params = action.params
		
		if 'index' not in params or 'file_path' not in params:
			return ActionResult(
				success=False,
				error='Upload_file action requires "index" and "file_path" parameters',
			)
		
		index = params['index']
		file_path = params['file_path']
		element = await self._get_element_by_index(index)
		
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
		params = action.params
		
		if 'index' not in params or 'text' not in params:
			return ActionResult(
				success=False,
				error='Select_dropdown action requires "index" and "text" parameters',
			)
		
		index = params['index']
		text = params['text']
		element = await self._get_element_by_index(index)
		
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
				
				element = await self._get_element_by_index(field_index)
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
				# Use send_keys with Enter
				event = self.browser_session.event_bus.dispatch(SendKeysEvent(keys='Enter'))
				await event
				await event.event_result(raise_if_any=False, raise_if_none=False)
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
			
			result = await self._execute_javascript(js_code)
			if 'error' in result:
				return ActionResult(success=False, error=result['error'])
			return ActionResult(success=True, data=result.get('result', {}))
		
		elif action_type == 'select_multiple':
			# Select multiple options (for multi-select dropdowns)
			if 'index' not in params or 'values' not in params:
				return ActionResult(success=False, error='Select_multiple action requires "index" and "values" parameters')
			
			index = params['index']
			values = params['values']
			element = await self._get_element_by_index(index)
			
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
			
			result = await self._execute_javascript(js_code)
			if 'error' in result:
				return ActionResult(success=False, error=result['error'])
			return ActionResult(success=True, data=result.get('result', {}))
		
		return ActionResult(success=False, error=f'Unknown form action: {action_type}')

	# Step 1.10: Media Actions (require JavaScript)

	async def _execute_media_action(self, action_type: str, action: ActionCommand) -> ActionResult:
		"""Execute media actions (play_video, pause_video, seek_video, adjust_volume, toggle_fullscreen, toggle_mute)."""
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
		
		result = await self._execute_javascript(js_code)
		if 'error' in result:
			return ActionResult(success=False, error=result['error'])
		return ActionResult(success=True, data=result.get('result', {}))

	# Step 1.11: Advanced Actions

	async def _execute_take_screenshot(self, action: ActionCommand) -> ActionResult:
		"""Execute take_screenshot action."""
		params = action.params
		full_page = params.get('full_page', False)
		clip = params.get('clip')
		
		try:
			event = self.browser_session.event_bus.dispatch(
				ScreenshotEvent(full_page=full_page, clip=clip)
			)
			await event
			result = await event.event_result(raise_if_any=False, raise_if_none=False)
			
			if isinstance(result, str):
				return ActionResult(success=True, data={'screenshot': result})
			return ActionResult(success=True, data={})
		except BrowserError as e:
			return ActionResult(success=False, error=e.message or str(e), data={'browser_error': True})
		except Exception as e:
			logger.error(f'Screenshot execution failed: {e}', exc_info=True)
			return ActionResult(success=False, error=f'Screenshot execution failed: {str(e)}')

	async def _execute_keyboard_shortcut(self, action: ActionCommand) -> ActionResult:
		"""Execute keyboard_shortcut action."""
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
		
		result = await self._execute_javascript(js_code)
		if 'error' in result:
			return ActionResult(success=False, error=result['error'])
		return ActionResult(success=True, data=result.get('result', {}))

	# Step 1.12: Presentation-Specific Actions (require JavaScript)

	async def _execute_presentation_action(self, action_type: str, action: ActionCommand) -> ActionResult:
		"""Execute presentation-specific actions."""
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
		
		result = await self._execute_javascript(js_code)
		if 'error' in result:
			return ActionResult(success=False, error=result['error'])
		return ActionResult(success=True, data=result.get('result', {}))

	async def _get_element_by_index(self, index: int):
		"""Get a DOM element by index.

		Args:
			index: The element index

		Returns:
			EnhancedDOMTreeNode or None if not found
		"""
		# Request browser state to build DOM if not already built
		from browser_use.browser.events import BrowserStateRequestEvent

		event = self.browser_session.event_bus.dispatch(BrowserStateRequestEvent())
		await event
		await event.event_result(raise_if_any=False, raise_if_none=False)

		# Get element from cached selector map (async method)
		element = await self.browser_session.get_dom_element_by_index(index)
		return element

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

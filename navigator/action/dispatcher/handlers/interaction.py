"""
Interaction action handlers.

Handles click, right_click, double_click, hover, and drag_drop actions.
"""

import logging

from browser_use.browser.events import ClickCoordinateEvent, ClickElementEvent
from browser_use.browser.views import BrowserError
from navigator.action.command import ActionCommand, ActionResult, ClickActionCommand
from navigator.action.dispatcher.utils import execute_javascript, get_element_by_index, wait_for_transition

logger = logging.getLogger(__name__)


async def execute_click(browser_session, action: ClickActionCommand, last_cursor_x, last_cursor_y) -> tuple[ActionResult, int | None, int | None]:
	"""Execute a click action.
	
	Returns:
		Tuple of (ActionResult, new_cursor_x, new_cursor_y)
	"""
	params = action.params

	# Check if we have coordinates or index
	if 'coordinate_x' in params and 'coordinate_y' in params:
		# Click at coordinates - track cursor position
		coordinate_x = params['coordinate_x']
		coordinate_y = params['coordinate_y']
		new_cursor_x = coordinate_x
		new_cursor_y = coordinate_y

		event = browser_session.event_bus.dispatch(
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
			return (
				ActionResult(
					success=False,
					error=result['validation_error'],
				),
				new_cursor_x,
				new_cursor_y,
			)

		# Wait for transition after click (handles navigation, DOM updates, network requests)
		# Only wait if click was successful (no validation_error)
		has_error = result and isinstance(result, dict) and result.get('validation_error')
		if not has_error:
			try:
				initial_url = await browser_session.get_current_page_url()
				transition_result = await wait_for_transition(
					browser_session=browser_session,
					initial_url=initial_url,
					max_wait_time=5.0,  # Wait up to 5 seconds for transitions
					check_interval=0.3,
					wait_for_dom_stability=True,
					wait_for_network_idle=True,
				)
				if transition_result['url_changed']:
					logger.debug(f"✅ Click caused navigation: {initial_url} → {transition_result['final_url']}")
				
				# Record delay for intelligence tracking
				from navigator.knowledge.delay_tracking import get_delay_tracker
				delay_tracker = get_delay_tracker()
				# Generate action_id based on click type
				if 'coordinate_x' in params and 'coordinate_y' in params:
					action_id = params.get('action_id') or f"click_coordinate_{params['coordinate_x']}_{params['coordinate_y']}"
					context = {
						'action_type': 'click',
						'coordinate_x': params['coordinate_x'],
						'coordinate_y': params['coordinate_y'],
						'initial_url': initial_url,
						'final_url': transition_result.get('final_url'),
					}
				else:
					action_id = params.get('action_id') or f"click_index_{params.get('index')}"
					context = {
						'action_type': 'click',
						'element_index': params.get('index'),
						'initial_url': initial_url,
						'final_url': transition_result.get('final_url'),
					}
				
				delay_tracker.record_delay(
					entity_id=action_id,
					entity_type='action',
					delay_ms=transition_result.get('wait_time_ms', transition_result['wait_time'] * 1000),
					url_changed=transition_result.get('url_changed', False),
					dom_stable=transition_result.get('dom_stable', False),
					network_idle=transition_result.get('network_idle', False),
					context=context,
				)
				
				# Also track as transition if URL changed
				if transition_result.get('url_changed', False):
					final_url = transition_result.get('final_url', initial_url)
					if initial_url != final_url:
						delay_tracker.record_transition_delay(
							from_url=initial_url,
							to_url=final_url,
							delay_ms=transition_result.get('wait_time_ms', transition_result['wait_time'] * 1000),
							url_changed=True,
							dom_stable=transition_result.get('dom_stable', False),
							network_idle=transition_result.get('network_idle', False),
							context={
								'action_type': 'click',
								'action_id': action_id,
								**context,
							},
						)
			except Exception as e:
				# Don't fail the action if transition waiting fails
				logger.debug(f"Error waiting for transition after click: {e}")

		return (
			ActionResult(
				success=True,
				data=result if isinstance(result, dict) else {},
			),
			new_cursor_x,
			new_cursor_y,
		)

	elif 'index' in params:
		# Click by element index - need to get element from DOM
		index = params['index']
		element = await get_element_by_index(browser_session, index)

		if element is None:
			return (
				ActionResult(
					success=False,
					error=f'Element with index {index} not found',
				),
				last_cursor_x,
				last_cursor_y,
			)

		# Track cursor position - try to get element center coordinates
		new_cursor_x = last_cursor_x
		new_cursor_y = last_cursor_y
		try:
			if element.snapshot_node and element.snapshot_node.bounds:
				bounds = element.snapshot_node.bounds
				center_x = int(bounds.x + bounds.width / 2)
				center_y = int(bounds.y + bounds.height / 2)
				new_cursor_x = center_x
				new_cursor_y = center_y
		except Exception:
			# If we can't get coordinates, that's okay - cursor position will be None
			pass

		event = browser_session.event_bus.dispatch(
			ClickElementEvent(
				node=element,
				button=params.get('button', 'left'),
			)
		)
		await event
		result = await event.event_result(raise_if_any=False, raise_if_none=False)

		if result and isinstance(result, dict) and 'validation_error' in result:
			return (
				ActionResult(
					success=False,
					error=result['validation_error'],
				),
				new_cursor_x,
				new_cursor_y,
			)

		# Wait for transition after click (handles navigation, DOM updates, network requests)
		# Only wait if click was successful (no validation_error)
		has_error = result and isinstance(result, dict) and result.get('validation_error')
		if not has_error:
			try:
				initial_url = await browser_session.get_current_page_url()
				transition_result = await wait_for_transition(
					browser_session=browser_session,
					initial_url=initial_url,
					max_wait_time=5.0,  # Wait up to 5 seconds for transitions
					check_interval=0.3,
					wait_for_dom_stability=True,
					wait_for_network_idle=True,
				)
				if transition_result['url_changed']:
					logger.debug(f"✅ Click caused navigation: {initial_url} → {transition_result['final_url']}")
				
				# Record delay for intelligence tracking
				from navigator.knowledge.delay_tracking import get_delay_tracker
				delay_tracker = get_delay_tracker()
				# Generate action_id based on click type
				if 'coordinate_x' in params and 'coordinate_y' in params:
					action_id = params.get('action_id') or f"click_coordinate_{params['coordinate_x']}_{params['coordinate_y']}"
					context = {
						'action_type': 'click',
						'coordinate_x': params['coordinate_x'],
						'coordinate_y': params['coordinate_y'],
						'initial_url': initial_url,
						'final_url': transition_result.get('final_url'),
					}
				else:
					action_id = params.get('action_id') or f"click_index_{params.get('index')}"
					context = {
						'action_type': 'click',
						'element_index': params.get('index'),
						'initial_url': initial_url,
						'final_url': transition_result.get('final_url'),
					}
				
				delay_tracker.record_delay(
					entity_id=action_id,
					entity_type='action',
					delay_ms=transition_result.get('wait_time_ms', transition_result['wait_time'] * 1000),
					url_changed=transition_result.get('url_changed', False),
					dom_stable=transition_result.get('dom_stable', False),
					network_idle=transition_result.get('network_idle', False),
					context=context,
				)
				
				# Also track as transition if URL changed
				if transition_result.get('url_changed', False):
					final_url = transition_result.get('final_url', initial_url)
					if initial_url != final_url:
						delay_tracker.record_transition_delay(
							from_url=initial_url,
							to_url=final_url,
							delay_ms=transition_result.get('wait_time_ms', transition_result['wait_time'] * 1000),
							url_changed=True,
							dom_stable=transition_result.get('dom_stable', False),
							network_idle=transition_result.get('network_idle', False),
							context={
								'action_type': 'click',
								'action_id': action_id,
								**context,
							},
						)
			except Exception as e:
				# Don't fail the action if transition waiting fails
				logger.debug(f"Error waiting for transition after click: {e}")

		return (
			ActionResult(
				success=True,
				data=result if isinstance(result, dict) else {},
			),
			new_cursor_x,
			new_cursor_y,
		)
	else:
		return (
			ActionResult(
				success=False,
				error='Click action requires either "index" or "coordinate_x"/"coordinate_y" parameters',
			),
			last_cursor_x,
			last_cursor_y,
		)


async def execute_right_click(browser_session, action: ActionCommand) -> ActionResult:
	"""Execute a right-click action."""
	params = action.params

	if 'index' not in params:
		return ActionResult(
			success=False,
			error='Right-click action requires "index" parameter',
		)

	index = params['index']
	element = await get_element_by_index(browser_session, index)

	if element is None:
		return ActionResult(
			success=False,
			error=f'Element with index {index} not found',
		)

	try:
		event = browser_session.event_bus.dispatch(
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


async def execute_double_click(browser_session, action: ActionCommand) -> ActionResult:
	"""Execute a double-click action using JavaScript."""
	params = action.params

	if 'index' not in params:
		return ActionResult(
			success=False,
			error='Double-click action requires "index" parameter',
		)

	index = params['index']
	element = await get_element_by_index(browser_session, index)

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

	result = await execute_javascript(browser_session, js_code)
	if 'error' in result:
		return ActionResult(success=False, error=result['error'])

	return ActionResult(success=True, data=result.get('result', {}))


async def execute_hover(browser_session, action: ActionCommand) -> ActionResult:
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

	result = await execute_javascript(browser_session, js_code)
	if 'error' in result:
		return ActionResult(success=False, error=result['error'])

	return ActionResult(success=True, data=result.get('result', {}))


async def execute_drag_drop(browser_session, action: ActionCommand) -> ActionResult:
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

	result = await execute_javascript(browser_session, js_code)
	if 'error' in result:
		return ActionResult(success=False, error=result['error'])

	return ActionResult(success=True, data=result.get('result', {}))

"""
Input action handlers.

Handles type, send_keys, text input actions, and type_slowly actions.
"""

import asyncio
import logging

from browser_use.browser.events import SendKeysEvent, TypeTextEvent
from navigator.action.command import ActionCommand, ActionResult, TypeActionCommand
from navigator.action.dispatcher.utils import get_element_by_index

logger = logging.getLogger(__name__)


async def execute_type(browser_session, action: TypeActionCommand) -> ActionResult:
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
		element = await get_element_by_index(browser_session, index)

		if element is None:
			return ActionResult(
				success=False,
				error=f'Element with index {index} not found',
			)

		event = browser_session.event_bus.dispatch(
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
		element = await get_element_by_index(browser_session, 0)
		if element is None:
			return ActionResult(
				success=False,
				error='No element found to type into. Provide an index parameter.',
			)

		event = browser_session.event_bus.dispatch(
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


async def execute_send_keys(browser_session, action: ActionCommand) -> ActionResult:
	"""Execute a send_keys action."""
	keys = action.params.get('keys')
	if not keys:
		return ActionResult(
			success=False,
			error='keys parameter is required for send_keys action',
		)

	logger.debug(f'[ActionDispatcher] Sending keys: {keys}')

	event = browser_session.event_bus.dispatch(SendKeysEvent(keys=keys))
	await event
	await event.event_result(raise_if_any=False, raise_if_none=False)

	return ActionResult(
		success=True,
		data={'keys': keys},
	)


async def execute_text_input_action(browser_session, action_type: str, action: ActionCommand) -> ActionResult:
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
		element = await get_element_by_index(browser_session, index)
		if element is None:
			return ActionResult(success=False, error=f'Element with index {index} not found')

		event = browser_session.event_bus.dispatch(
			TypeTextEvent(node=element, text='', clear=True)
		)
		await event
		await event.event_result(raise_if_any=False, raise_if_none=False)
		return ActionResult(success=True, data={})

	if action_type in key_map:
		keys = key_map[action_type]
		event = browser_session.event_bus.dispatch(SendKeysEvent(keys=keys))
		await event
		await event.event_result(raise_if_any=False, raise_if_none=False)
		return ActionResult(success=True, data={'keys': keys})

	return ActionResult(success=False, error=f'Unknown text input action: {action_type}')


async def execute_type_slowly(browser_session, action: ActionCommand) -> ActionResult:
	"""Execute type_slowly action (types with delays between characters)."""
	params = action.params

	if 'text' not in params:
		return ActionResult(success=False, error='Type_slowly action requires "text" parameter')

	text = params['text']
	delay = params.get('delay', 0.1)
	index = params.get('index')

	if index is not None:
		element = await get_element_by_index(browser_session, index)
		if element is None:
			return ActionResult(success=False, error=f'Element with index {index} not found')

		# Type character by character with delays
		for char in text:
			event = browser_session.event_bus.dispatch(
				TypeTextEvent(node=element, text=char, clear=False)
			)
			await event
			await event.event_result(raise_if_any=False, raise_if_none=False)
			await asyncio.sleep(delay)

		return ActionResult(success=True, data={'text': text, 'delay': delay})
	else:
		return ActionResult(success=False, error='Type_slowly action requires "index" parameter')

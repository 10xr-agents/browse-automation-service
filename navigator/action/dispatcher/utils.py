"""
Shared utilities for action dispatcher.

Helper functions used across multiple action handlers.
"""

import logging
from typing import Any

from browser_use import BrowserSession

logger = logging.getLogger(__name__)


async def execute_javascript(browser_session: BrowserSession, code: str) -> dict[str, Any]:
	"""
	Helper function to execute JavaScript code in the browser.
	
	Args:
		browser_session: Browser session to execute JavaScript in
		code: JavaScript code to execute (should be wrapped in IIFE)
	
	Returns:
		Dict with result data or error
	"""
	cdp_session = await browser_session.get_or_create_cdp_session()

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


async def get_element_by_index(browser_session: BrowserSession, index: int):
	"""Get a DOM element by index.

	Args:
		browser_session: Browser session to get element from
		index: The element index

	Returns:
		EnhancedDOMTreeNode or None if not found
	"""
	# Request browser state to build DOM if not already built
	from browser_use.browser.events import BrowserStateRequestEvent

	event = browser_session.event_bus.dispatch(BrowserStateRequestEvent())
	await event
	await event.event_result(raise_if_any=False, raise_if_none=False)

	# Get element from cached selector map (async method)
	element = await browser_session.get_dom_element_by_index(index)
	return element

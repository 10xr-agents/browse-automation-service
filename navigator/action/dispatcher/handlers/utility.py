"""
Utility action handlers.

Handles wait and screenshot actions.
"""

import logging

from browser_use.browser.events import ScreenshotEvent, WaitEvent
from browser_use.browser.views import BrowserError
from navigator.action.command import ActionCommand, ActionResult, WaitActionCommand

logger = logging.getLogger(__name__)


async def execute_wait(browser_session, action: WaitActionCommand) -> ActionResult:
	"""Execute a wait action."""
	params = action.params

	if 'seconds' not in params:
		return ActionResult(
			success=False,
			error='Wait action requires "seconds" parameter',
		)

	seconds = float(params['seconds'])

	event = browser_session.event_bus.dispatch(WaitEvent(seconds=seconds))
	await event
	await event.event_result(raise_if_any=False, raise_if_none=False)

	return ActionResult(
		success=True,
		data={'waited_seconds': seconds},
	)


async def execute_take_screenshot(browser_session, action: ActionCommand) -> ActionResult:
	"""Execute take_screenshot action."""
	params = action.params
	full_page = params.get('full_page', False)
	clip = params.get('clip')

	try:
		event = browser_session.event_bus.dispatch(
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

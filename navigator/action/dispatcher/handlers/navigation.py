"""
Navigation action handlers.

Handles navigate, go_back, go_forward, and refresh actions.
"""

import asyncio
import logging

from browser_use.browser.events import (
	GoBackEvent,
	GoForwardEvent,
	NavigateToUrlEvent,
	RefreshEvent,
)
from browser_use.browser.views import BrowserError
from navigator.action.command import ActionCommand, ActionResult, NavigateActionCommand

logger = logging.getLogger(__name__)


async def execute_navigate(browser_session, action: NavigateActionCommand) -> ActionResult:
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
		event = browser_session.event_bus.dispatch(
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


async def execute_go_back(browser_session, action: ActionCommand) -> ActionResult:
	"""Execute a go back action."""
	event = browser_session.event_bus.dispatch(GoBackEvent())
	await event
	await event.event_result(raise_if_any=False, raise_if_none=False)

	return ActionResult(
		success=True,
		data={},
	)


async def execute_go_forward(browser_session, action: ActionCommand) -> ActionResult:
	"""Execute a go forward action."""
	event = browser_session.event_bus.dispatch(GoForwardEvent())
	await event
	await event.event_result(raise_if_any=False, raise_if_none=False)

	return ActionResult(
		success=True,
		data={},
	)


async def execute_refresh(browser_session, action: ActionCommand) -> ActionResult:
	"""Execute a refresh action."""
	event = browser_session.event_bus.dispatch(RefreshEvent())
	await event
	await event.event_result(raise_if_any=False, raise_if_none=False)

	return ActionResult(
		success=True,
		data={},
	)

"""
Scrolling action handlers.

Handles scroll actions.
"""

import logging

from browser_use.browser.events import ScrollEvent
from navigator.action.command import ActionResult, ScrollActionCommand

logger = logging.getLogger(__name__)


async def execute_scroll(browser_session, action: ScrollActionCommand) -> ActionResult:
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
	event = browser_session.event_bus.dispatch(
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

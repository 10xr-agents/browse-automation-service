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
from navigator.action.dispatcher.utils import wait_for_transition

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

		# Wait for navigation to complete using intelligent transition waiting
		try:
			initial_url = await browser_session.get_current_page_url()
			transition_result = await wait_for_transition(
				browser_session=browser_session,
				initial_url=initial_url,  # Wait for navigation from initial URL
				max_wait_time=8.0,  # Wait up to 8 seconds for slow pages
				check_interval=0.3,
				wait_for_dom_stability=True,
				wait_for_network_idle=True,
			)
			logger.debug(f"✅ Navigation complete: {transition_result['final_url']} (waited {transition_result['wait_time']:.2f}s)")
			
			# Record delay for intelligence tracking
			from navigator.knowledge.delay_tracking import get_delay_tracker
			delay_tracker = get_delay_tracker()
			final_url = transition_result.get('final_url', url)
			
			# Track as action
			action_id = params.get('action_id') or f"navigate_{url}"
			delay_tracker.record_delay(
				entity_id=action_id,
				entity_type='action',
				delay_ms=transition_result.get('wait_time_ms', transition_result['wait_time'] * 1000),
				url_changed=transition_result.get('url_changed', False),
				dom_stable=transition_result.get('dom_stable', False),
				network_idle=transition_result.get('network_idle', False),
				context={
					'action_type': 'navigate',
					'initial_url': initial_url,
					'target_url': url,
					'final_url': final_url,
				},
			)
			
			# Also track as transition if URL changed
			if transition_result.get('url_changed', False) and initial_url != final_url:
				delay_tracker.record_transition_delay(
					from_url=initial_url,
					to_url=final_url,
					delay_ms=transition_result.get('wait_time_ms', transition_result['wait_time'] * 1000),
					url_changed=True,
					dom_stable=transition_result.get('dom_stable', False),
					network_idle=transition_result.get('network_idle', False),
					context={
						'action_type': 'navigate',
						'action_id': action_id,
					},
				)
		except Exception as e:
			# Don't fail navigation if transition waiting fails - navigation event already succeeded
			logger.debug(f"Error waiting for navigation transition: {e}")
			# Fallback to simple sleep
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
	try:
		initial_url = await browser_session.get_current_page_url()
	except Exception:
		initial_url = None

	event = browser_session.event_bus.dispatch(GoBackEvent())
	await event
	await event.event_result(raise_if_any=False, raise_if_none=False)

	# Wait for navigation to complete
	try:
		from navigator.action.dispatcher.utils import wait_for_transition
		transition_result = await wait_for_transition(
			browser_session=browser_session,
			initial_url=initial_url,
			max_wait_time=5.0,
			check_interval=0.3,
			wait_for_dom_stability=True,
			wait_for_network_idle=True,
		)
		logger.debug(f"✅ Go back complete: {transition_result['final_url']} (waited {transition_result['wait_time']:.2f}s)")
		
		# Record delay for intelligence tracking
		from navigator.knowledge.delay_tracking import get_delay_tracker
		delay_tracker = get_delay_tracker()
		action_id = f"go_back_{initial_url}"
		delay_tracker.record_delay(
			entity_id=action_id,
			entity_type='action',
			delay_ms=transition_result.get('wait_time_ms', transition_result['wait_time'] * 1000),
			url_changed=transition_result.get('url_changed', False),
			dom_stable=transition_result.get('dom_stable', False),
			network_idle=transition_result.get('network_idle', False),
			context={
				'action_type': 'go_back',
				'initial_url': initial_url,
				'final_url': transition_result.get('final_url'),
			},
		)
	except Exception as e:
		logger.debug(f"Error waiting for go_back transition: {e}")
		await asyncio.sleep(0.5)  # Fallback

	return ActionResult(
		success=True,
		data={},
	)


async def execute_go_forward(browser_session, action: ActionCommand) -> ActionResult:
	"""Execute a go forward action."""
	try:
		initial_url = await browser_session.get_current_page_url()
	except Exception:
		initial_url = None

	event = browser_session.event_bus.dispatch(GoForwardEvent())
	await event
	await event.event_result(raise_if_any=False, raise_if_none=False)

	# Wait for navigation to complete
	try:
		from navigator.action.dispatcher.utils import wait_for_transition
		transition_result = await wait_for_transition(
			browser_session=browser_session,
			initial_url=initial_url,
			max_wait_time=5.0,
			check_interval=0.3,
			wait_for_dom_stability=True,
			wait_for_network_idle=True,
		)
		logger.debug(f"✅ Go forward complete: {transition_result['final_url']} (waited {transition_result['wait_time']:.2f}s)")
		
		# Record delay for intelligence tracking
		from navigator.knowledge.delay_tracking import get_delay_tracker
		delay_tracker = get_delay_tracker()
		action_id = f"go_forward_{initial_url}"
		delay_tracker.record_delay(
			entity_id=action_id,
			entity_type='action',
			delay_ms=transition_result.get('wait_time_ms', transition_result['wait_time'] * 1000),
			url_changed=transition_result.get('url_changed', False),
			dom_stable=transition_result.get('dom_stable', False),
			network_idle=transition_result.get('network_idle', False),
			context={
				'action_type': 'go_forward',
				'initial_url': initial_url,
				'final_url': transition_result.get('final_url'),
			},
		)
	except Exception as e:
		logger.debug(f"Error waiting for go_forward transition: {e}")
		await asyncio.sleep(0.5)  # Fallback

	return ActionResult(
		success=True,
		data={},
	)


async def execute_refresh(browser_session, action: ActionCommand) -> ActionResult:
	"""Execute a refresh action."""
	try:
		initial_url = await browser_session.get_current_page_url()
	except Exception:
		initial_url = None

	event = browser_session.event_bus.dispatch(RefreshEvent())
	await event
	await event.event_result(raise_if_any=False, raise_if_none=False)

	# Wait for page to reload
	try:
		from navigator.action.dispatcher.utils import wait_for_transition
		transition_result = await wait_for_transition(
			browser_session=browser_session,
			initial_url=initial_url,
			max_wait_time=8.0,  # Refresh might take longer
			check_interval=0.3,
			wait_for_dom_stability=True,
			wait_for_network_idle=True,
		)
		logger.debug(f"✅ Refresh complete: {transition_result['final_url']} (waited {transition_result['wait_time']:.2f}s)")
		
		# Record delay for intelligence tracking
		from navigator.knowledge.delay_tracking import get_delay_tracker
		delay_tracker = get_delay_tracker()
		action_id = f"refresh_{initial_url}"
		delay_tracker.record_delay(
			entity_id=action_id,
			entity_type='action',
			delay_ms=transition_result.get('wait_time_ms', transition_result['wait_time'] * 1000),
			url_changed=transition_result.get('url_changed', False),
			dom_stable=transition_result.get('dom_stable', False),
			network_idle=transition_result.get('network_idle', False),
			context={
				'action_type': 'refresh',
				'initial_url': initial_url,
				'final_url': transition_result.get('final_url'),
			},
		)
	except Exception as e:
		logger.debug(f"Error waiting for refresh transition: {e}")
		await asyncio.sleep(1.0)  # Fallback - refresh usually takes longer

	return ActionResult(
		success=True,
		data={},
	)

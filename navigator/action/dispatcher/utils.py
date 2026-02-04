"""
Utility functions for action dispatcher.
"""

import asyncio
import logging
import time
from typing import Any

from browser_use import BrowserSession

logger = logging.getLogger(__name__)


async def wait_for_transition(
	browser_session: BrowserSession,
	initial_url: str | None = None,
	max_wait_time: float = 5.0,
	check_interval: float = 0.3,
	wait_for_dom_stability: bool = True,
	wait_for_network_idle: bool = True,
) -> dict[str, Any]:
	"""
	Intelligently wait for UI transitions (navigation, DOM changes, network activity).
	
	This utility handles delays in:
	- Page navigation (URL changes)
	- DOM updates (elements appearing/disappearing)
	- Network requests (API calls, resource loading)
	- Button/action responses (form submissions, clicks)
	
	Args:
		browser_session: Browser session instance
		initial_url: Starting URL (if None, gets current URL)
		max_wait_time: Maximum time to wait in seconds
		check_interval: Time between checks in seconds
		wait_for_dom_stability: Whether to wait for DOM to stabilize
		wait_for_network_idle: Whether to wait for network to be idle
	
	Returns:
		Dictionary with:
		{
			'final_url': str,
			'url_changed': bool,
			'wait_time': float,
			'dom_stable': bool,
			'network_idle': bool,
		}
	"""
	start_time = time.time()
	
	if initial_url is None:
		initial_url = await browser_session.get_current_page_url()
	
	final_url = initial_url
	url_changed = False
	dom_stable = False
	network_idle = False
	
	# Track DOM state for stability detection
	last_dom_hash = None
	dom_stable_count = 0
	dom_stable_threshold = 2  # Need 2 consecutive stable checks
	
	# Track network state
	network_idle_count = 0
	network_idle_threshold = 2  # Need 2 consecutive idle checks
	
	max_checks = int(max_wait_time / check_interval)
	
	logger.debug(f"⏳ Waiting for transition (max {max_wait_time}s, checking every {check_interval}s)")
	
	for i in range(max_checks):
		elapsed_time = time.time() - start_time
		
		# Check URL change
		try:
			current_url = await browser_session.get_current_page_url()
			if current_url != initial_url:
				final_url = current_url
				url_changed = True
				logger.debug(f"📍 URL changed after {elapsed_time:.2f}s: {initial_url} → {current_url}")
				# Continue waiting for DOM/network to stabilize after URL change
		except Exception as e:
			logger.debug(f"Error getting current URL: {e}")
		
		# Check DOM stability (if enabled)
		if wait_for_dom_stability:
			try:
				browser_state = await browser_session.get_browser_state_summary(include_screenshot=False)
				if browser_state and browser_state.dom_state:
					# Create a simple hash of DOM structure (selector count + text content length)
					selector_count = len(browser_state.dom_state.selector_map) if browser_state.dom_state.selector_map else 0
					text_length = len(browser_state.dom_state.text_content) if browser_state.dom_state.text_content else 0
					current_dom_hash = f"{selector_count}:{text_length}"
					
					if current_dom_hash == last_dom_hash:
						dom_stable_count += 1
						if dom_stable_count >= dom_stable_threshold:
							dom_stable = True
							logger.debug(f"✅ DOM stable after {elapsed_time:.2f}s ({dom_stable_count} consecutive stable checks)")
					else:
						dom_stable_count = 0
						last_dom_hash = current_dom_hash
			except Exception as e:
				logger.debug(f"Error checking DOM stability: {e}")
		
		# Check network idle (if enabled)
		if wait_for_network_idle:
			try:
				# Heuristic: if URL changed and DOM is stable, assume network is idle
				if url_changed and dom_stable:
					network_idle_count += 1
					if network_idle_count >= network_idle_threshold:
						network_idle = True
						logger.debug(f"✅ Network appears idle after {elapsed_time:.2f}s")
			except Exception as e:
				logger.debug(f"Error checking network state: {e}")
		
		# Early exit conditions
		# If URL changed and we've waited a reasonable amount, we can proceed
		if url_changed:
			# If URL changed and we've waited at least 1 second, check if we should continue
			if elapsed_time >= 1.0:
				# If DOM is stable or we've waited long enough, proceed
				if dom_stable or elapsed_time >= 3.0:
					logger.debug(f"✅ Transition complete: URL changed, DOM stable or sufficient wait time")
					break
		
		# If no URL change but DOM is stable and we've waited a bit, might be a SPA update
		if not url_changed and dom_stable and elapsed_time >= 2.0:
			logger.debug(f"✅ DOM stable without URL change (likely SPA update) after {elapsed_time:.2f}s")
			break
		
		# Sleep before next check
		await asyncio.sleep(check_interval)
	
	# Final state check
	if not url_changed:
		try:
			final_url = await browser_session.get_current_page_url()
			if final_url != initial_url:
				url_changed = True
		except Exception:
			pass
	
	wait_time = time.time() - start_time
	
	result = {
		'final_url': final_url,
		'url_changed': url_changed,
		'wait_time': wait_time,
		'wait_time_ms': wait_time * 1000,  # Also provide in milliseconds
		'dom_stable': dom_stable,
		'network_idle': network_idle,
	}
	
	# Record delay for intelligence tracking (if entity context is available)
	# This will be called by action handlers with proper entity_id
	return result


async def get_element_by_index(browser_session: BrowserSession, index: int) -> Any:
	"""
	Get DOM element by index from browser session.
	
	Args:
		browser_session: Browser session instance
		index: Element index
	
	Returns:
		EnhancedDOMTreeNode or None if index not found
	"""
	return await browser_session.get_element_by_index(index)


async def execute_javascript(browser_session: BrowserSession, script: str) -> Any:
	"""
	Execute JavaScript code in browser context.
	
	Args:
		browser_session: Browser session instance
		script: JavaScript code to execute
	
	Returns:
		Result of JavaScript execution
	"""
	from browser_use.browser.events import EvaluateJavaScriptEvent
	
	event = browser_session.event_bus.dispatch(EvaluateJavaScriptEvent(script=script))
	await event
	result = await event.event_result(raise_if_any=False, raise_if_none=False)
	return result

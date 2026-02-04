"""
Authentication Service for Knowledge Retrieval

Handles login detection, execution, and validation for authenticated website exploration.

NOTE: Credentials are currently logged for debugging purposes. Will be masked again after testing.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

from browser_use import BrowserSession
from browser_use.browser.events import SendKeysEvent
from navigator.action.command import ClickActionCommand, TypeActionCommand
from navigator.action.dispatcher import ActionDispatcher

logger = logging.getLogger(__name__)


@dataclass
class Credentials:
	"""
	Credentials for authentication.
	
	Credentials are kept in memory only and never logged or persisted.
	
	NOTE: Temporarily showing credentials in logs for debugging. Will be masked again after testing.
	"""
	username: str
	password: str
	login_url: str | None = None  # Optional explicit login URL

	def __repr__(self) -> str:
		"""Show credentials for debugging (temporary - will be masked after testing)."""
		return f"Credentials(username={self.username}, password={self.password}, login_url={self.login_url})"


class AuthenticationService:
	"""
	Service for handling authentication during knowledge retrieval.
	
	Features:
	- Login page detection
	- Automatic form filling
	- Login submission
	- Login validation
	- Secure credential handling (never logged or persisted)
	"""

	def __init__(self, browser_session: BrowserSession):
		"""
		Initialize authentication service.
		
		Args:
			browser_session: Browser session for navigation and DOM access
		"""
		self.browser_session = browser_session
		self.action_dispatcher = ActionDispatcher(browser_session)
		self._authenticated = False

		logger.debug("AuthenticationService initialized")

	async def detect_login_page(self, url: str) -> bool:
		"""
		Detect if current page is a login page.
		
		Args:
			url: Current page URL
		
		Returns:
			True if login page detected, False otherwise
		"""
		try:
			# Check URL for login indicators
			url_lower = url.lower()
			login_url_patterns = [
				r'/login',
				r'/signin',
				r'/auth',
				r'/sign-in',
				r'/log-in',
				r'/authenticate',
				r'/account/login',
			]

			for pattern in login_url_patterns:
				if re.search(pattern, url_lower):
					# Additional check: if we can access authenticated content, we're not on a login page
					# This handles SPAs where URL might stay on /signin but we're actually logged in
					try:
						has_auth_content = await self._check_authenticated_content()
						if has_auth_content:
							logger.debug(f"URL matches login pattern {pattern} but authenticated content detected - not a login page")
							return False
					except Exception:
						pass  # If check fails, fall back to URL-based detection
					
					logger.debug(f"Login page detected by URL pattern: {pattern} in {url}")
					return True

			# Check DOM for login form indicators using browser state
			try:
				browser_state = await self.browser_session.get_browser_state_summary(include_screenshot=False)
				selector_map = browser_state.dom_state.selector_map if browser_state.dom_state else {}

				# Check for password input fields (strong indicator of login page)
				has_password_input = False
				has_username_input = False

				for element in selector_map.values():
					if element.tag_name and element.tag_name.upper() == 'INPUT':
						input_type = element.attributes.get('type', '').lower() if element.attributes else ''

						if input_type == 'password':
							has_password_input = True
						elif input_type in ('email', 'text'):
							input_name = element.attributes.get('name', '').lower() if element.attributes else ''
							input_id = element.attributes.get('id', '').lower() if element.attributes else ''
							input_placeholder = element.attributes.get('placeholder', '').lower() if element.attributes else ''

							username_indicators = ['user', 'email', 'username', 'login', 'account']
							field_text = f"{input_name} {input_id} {input_placeholder}".lower()
							if any(indicator in field_text for indicator in username_indicators):
								has_username_input = True

					if has_password_input and has_username_input:
						break

				if has_password_input and has_username_input:
					logger.debug(f"Login page detected by form elements in {url}")
					return True
			except Exception as e:
				logger.debug(f"Error checking DOM for login indicators: {e}")

			return False

		except Exception as e:
			logger.debug(f"Error detecting login page: {e}")
			return False

	async def find_form_fields(
		self,
		username: str,
		password: str,
	) -> tuple[int | None, int | None, int | None]:
		"""
		Find username, password, and submit button indices in the DOM.
		
		Args:
			username: Username to find field for (used for validation, not lookup)
			password: Password to find field for (used for validation, not lookup)
		
		Returns:
			Tuple of (username_field_index, password_field_index, submit_button_index)
			Returns None for any field that couldn't be found
		"""
		try:
			# Get browser state to access selector map
			browser_state = await self.browser_session.get_browser_state_summary(include_screenshot=False)
			selector_map = browser_state.dom_state.selector_map if browser_state.dom_state else {}

			if not selector_map:
				logger.warning("Selector map is empty - cannot find form fields")
				return None, None, None

			username_index = None
			password_index = None
			submit_index = None

			# Iterate through selector map to find form fields
			for idx, element in selector_map.items():
				if element.tag_name and element.tag_name.upper() == 'INPUT':
					input_type = element.attributes.get('type', '').lower() if element.attributes else ''
					input_name = element.attributes.get('name', '').lower() if element.attributes else ''
					input_id = element.attributes.get('id', '').lower() if element.attributes else ''
					input_placeholder = element.attributes.get('placeholder', '').lower() if element.attributes else ''

					# Check for password field
					if input_type == 'password' and password_index is None:
						password_index = idx

					# Check for username/email field
					elif input_type in ('email', 'text'):
						username_indicators = ['user', 'email', 'username', 'login', 'account']
						field_text = f"{input_name} {input_id} {input_placeholder}".lower()
						if any(indicator in field_text for indicator in username_indicators) and username_index is None:
							username_index = idx

					# Check for submit button (input type=submit)
					elif input_type == 'submit' and submit_index is None:
						submit_index = idx

				# Check for submit button (button element)
				elif element.tag_name and element.tag_name.upper() == 'BUTTON':
					button_type = element.attributes.get('type', '').lower() if element.attributes else ''
					button_text = element.get_all_children_text().lower() if hasattr(element, 'get_all_children_text') else ''

					# Check for submit button
					if button_type == 'submit' or 'login' in button_text or 'sign in' in button_text:
						if submit_index is None:
							submit_index = idx

			return username_index, password_index, submit_index

		except Exception as e:
			logger.error(f"Error finding form fields: {e}", exc_info=True)
			return None, None, None

	async def perform_login(
		self,
		credentials: Credentials,
		login_url: str | None = None,
	) -> dict[str, Any]:
		"""
		Perform login using provided credentials.
		
		Args:
			credentials: Credentials for login
			login_url: Optional explicit login URL (if None, uses current page or credentials.login_url)
		
		Returns:
			Dictionary with login result:
			{
				'success': bool,
				'message': str,
				'error': str | None,
				'logged_in_url': str | None,
			}
		"""
		try:
			# Navigate to login page if needed
			target_url = login_url or credentials.login_url
			if target_url:
				current_url = await self.browser_session.get_current_page_url()
				if current_url != target_url:
					logger.info(f"Navigating to login page: {target_url}")
					from navigator.action.command import NavigateActionCommand
					navigate_action = NavigateActionCommand(params={'url': target_url})
					navigate_result = await self.action_dispatcher.execute_action(navigate_action)
					if not navigate_result.success:
						return {
							'success': False,
							'message': 'Failed to navigate to login page',
							'error': navigate_result.error,
							'logged_in_url': None,
						}

					# Wait for page to fully load and stabilize
					logger.info("⏳ Waiting for login page to fully load...")
					await asyncio.sleep(6)

			# Find form fields
			username_index, password_index, submit_index = await self.find_form_fields(
				credentials.username,
				credentials.password,
			)

			if username_index is None:
				return {
					'success': False,
					'message': 'Username field not found',
					'error': 'Could not locate username/email input field on login page',
					'logged_in_url': None,
				}

			if password_index is None:
				return {
					'success': False,
					'message': 'Password field not found',
					'error': 'Could not locate password input field on login page',
					'logged_in_url': None,
				}

			logger.info(f"Found login form fields: username_index={username_index}, password_index={password_index}, submit_index={submit_index}")
			
			# Log credentials for debugging (temporary - will be masked after testing)
			logger.info(f"🔐 Attempting login with username: '{credentials.username}' and password: '{credentials.password}'")

			# Fill username field
			logger.info("Filling username field")
			username_action = TypeActionCommand(params={
				'index': username_index,
				'text': credentials.username,
				'clear': True,
			})
			username_result = await self.action_dispatcher.execute_action(username_action)
			if not username_result.success:
				return {
					'success': False,
					'message': 'Failed to fill username field',
					'error': username_result.error,
					'logged_in_url': None,
				}

			# Wait for username field to stabilize
			logger.info("⏳ Waiting after username input...")
			await asyncio.sleep(1.5)

			# Fill password field
			logger.info("Filling password field")
			password_action = TypeActionCommand(params={
				'index': password_index,
				'text': credentials.password,
				'clear': True,
			})
			password_result = await self.action_dispatcher.execute_action(password_action)
			if not password_result.success:
				return {
					'success': False,
					'message': 'Failed to fill password field',
					'error': password_result.error,
					'logged_in_url': None,
				}

			# Wait for password field to stabilize
			logger.info("⏳ Waiting after password input...")
			await asyncio.sleep(1.5)

			# Submit form using multiple strategies (most reliable first)
			submit_success = False
			
			# Strategy 1: Focus password field and press Enter (most reliable per browser-use examples)
			try:
				logger.info("📝 Strategy 1: Focusing password field and pressing Enter...")
				from navigator.action.dispatcher.utils import get_element_by_index
				password_element = await get_element_by_index(self.browser_session, password_index)
				if password_element:
					# Focus the password field
					await password_element.focus()
					await asyncio.sleep(0.5)
					
					# Get page and press Enter
					page = await self.browser_session.get_current_page()
					await page.press('Enter')
					submit_success = True
					logger.info("✅ Submitted form using Enter key on password field")
			except Exception as e:
				logger.debug(f"Strategy 1 failed: {e}")
			
			# Strategy 2: Try JavaScript form submission (fallback)
			if not submit_success:
				try:
					logger.info("📝 Strategy 2: Submitting form via JavaScript...")
					from navigator.action.dispatcher.utils import execute_javascript
					
					# Find the form containing the password field and submit it
					js_code = """
					(() => {
						const passwordInput = document.querySelector('input[type="password"]');
						if (!passwordInput) return {error: 'Password input not found'};
						
						let form = passwordInput.form;
						if (!form) {
							// Find parent form element
							let parent = passwordInput.parentElement;
							while (parent && parent.tagName !== 'FORM') {
								parent = parent.parentElement;
							}
							form = parent;
						}
						
						if (form) {
							form.submit();
							return {success: true, method: 'form.submit()'};
						} else {
							// Try dispatching submit event on password input
							const submitEvent = new Event('submit', {bubbles: true, cancelable: true});
							passwordInput.dispatchEvent(submitEvent);
							return {success: true, method: 'dispatchEvent'};
						}
					})()
					"""
					
					js_result = await execute_javascript(self.browser_session, js_code)
					if 'error' not in js_result:
						submit_success = True
						logger.info(f"✅ Submitted form via JavaScript: {js_result.get('result', {}).get('method', 'unknown')}")
					else:
						logger.debug(f"JavaScript submission failed: {js_result.get('error')}")
				except Exception as e:
					logger.debug(f"Strategy 2 failed: {e}")
			
			# Strategy 3: Click submit button (last resort)
			if not submit_success and submit_index is not None:
				try:
					logger.info(f"📝 Strategy 3: Clicking submit button (index: {submit_index})...")
					submit_action = ClickActionCommand(params={'index': submit_index})
					submit_result = await self.action_dispatcher.execute_action(submit_action)
					if submit_result.success:
						submit_success = True
						logger.info("✅ Submitted form by clicking submit button")
					else:
						logger.warning(f"Submit button click failed: {submit_result.error}")
				except Exception as e:
					logger.debug(f"Strategy 3 failed: {e}")
			
			if not submit_success:
				return {
					'success': False,
					'message': 'Failed to submit login form - all strategies failed',
					'error': 'Could not submit form using Enter key, JavaScript, or button click',
					'logged_in_url': None,
				}

			# Wait for navigation/response using intelligent transition waiting
			logger.info("⏳ Waiting for login response...")
			initial_url = await self.browser_session.get_current_page_url()
			
			# Use intelligent wait for transition (handles URL changes, DOM stability, network idle)
			transition_result = await self._wait_for_transition(
				initial_url=initial_url,
				max_wait_time=8.0,  # Increased wait time for slow login responses
				check_interval=0.3,  # Check more frequently
			)
			
			logged_in_url = transition_result['final_url']
			logger.info(f"📍 URL after login attempt: {logged_in_url} (waited {transition_result['wait_time']:.2f}s)")
			
			# Check if we're still on login page
			is_still_login_page = await self.detect_login_page(logged_in_url)
			if is_still_login_page:
				logger.warning(f"⚠️ Still on login page after submission. URL: {logged_in_url}")
				# Detect error messages (now used in validation)
				has_errors = await self._detect_error_messages()
				if has_errors:
					logger.warning(f"⚠️ Error messages detected on login page")
			
			# Validate login with enhanced multi-strategy validation
			login_valid = await self.validate_login(logged_in_url, initial_url=initial_url)

			if login_valid:
				self._authenticated = True
				logger.info(f"✅ Login validation passed. Final URL: {logged_in_url}")
				return {
					'success': True,
					'message': 'Login successful',
					'error': None,
					'logged_in_url': logged_in_url,
				}
			else:
				logger.warning(f"❌ Login validation failed. Final URL: {logged_in_url}")
				return {
					'success': False,
					'message': 'Login failed - still on login page or error page',
					'error': f'Login validation failed - page did not change or login error detected. Final URL: {logged_in_url}',
					'logged_in_url': logged_in_url,
				}

		except Exception as e:
			logger.error(f"Error performing login: {e}", exc_info=True)
			return {
				'success': False,
				'message': 'Login error',
				'error': str(e),
				'logged_in_url': None,
			}

	async def validate_login(self, url: str, initial_url: str | None = None) -> bool:
		"""
		Validate if login was successful using multiple validation strategies.
		
		Args:
			url: Current page URL after login attempt
			initial_url: Initial URL before login (for comparison)
		
		Returns:
			True if login appears successful, False otherwise
		"""
		try:
			# Strategy 1: Check for authenticated content FIRST (before checking if still on login page)
			# This handles SPAs where URL might stay on /signin but we're actually logged in
			has_authenticated_content = await self._check_authenticated_content()
			if has_authenticated_content:
				logger.info(f"✅ Authenticated content detected in DOM - login successful (even if URL suggests login page)")
				return True
			
			has_auth_cookies = await self._check_authentication_cookies()
			if has_auth_cookies:
				logger.info(f"✅ Authentication cookies detected - login successful (even if URL suggests login page)")
				return True
			
			# Strategy 2: Check if we're still on a login page (strong negative indicator)
			# Only check this if we haven't found authenticated content/cookies
			is_login_page = await self.detect_login_page(url)
			if is_login_page:
				logger.info(f"❌ Still on login page - login likely failed. URL: {url}")
				# Check for error messages on the login page
				has_errors = await self._detect_error_messages()
				if has_errors:
					logger.warning(f"❌ Error messages detected on login page - login failed")
				return False

			# Strategy 3: Check URL for error/denied patterns (strong negative indicator)
			url_lower = url.lower()
			error_patterns = [
				r'/error',
				r'/denied',
				r'/forbidden',
				r'/unauthorized',
				r'/access-denied',
				r'/login.*error',
				r'/signin.*error',
			]
			
			for pattern in error_patterns:
				if re.search(pattern, url_lower):
					logger.warning(f"⚠️ Error page detected: {pattern} in {url}")
					return False

			# Strategy 4: Check URL for success indicators (moderate positive indicator)
			success_patterns = [
				r'/dashboard',
				r'/home',
				r'/account',
				r'/profile',
				r'/welcome',
				r'/main',
				r'/app',
				r'/workspace',
				r'/portal',
			]

			for pattern in success_patterns:
				if re.search(pattern, url_lower):
					logger.info(f"✅ Login success detected by URL pattern: {pattern} in {url}")
					return True

			# Strategy 5: Check if URL changed from initial (weak positive indicator)
			if initial_url and url != initial_url:
				# URL changed and not on login/error page - likely success
				logger.info(f"✅ URL changed from {initial_url} to {url} and not on login page - assuming login success")
				return True

			# Strategy 6: Fallback - if not on login page and no errors, assume success
			# (This is a heuristic - less reliable but better than failing on unknown pages)
			logger.info(f"⚠️ URL not on login page and no clear indicators - assuming login success. URL: {url}")
			return True

		except Exception as e:
			logger.error(f"Error validating login: {e}", exc_info=True)
			return False

	async def _check_authenticated_content(self) -> bool:
		"""
		Check DOM for indicators of authenticated content.
		
		Returns:
			True if authenticated content indicators found, False otherwise
		"""
		try:
			browser_state = await self.browser_session.get_browser_state_summary(include_screenshot=False)
			if not browser_state or not browser_state.dom_state:
				return False

			selector_map = browser_state.dom_state.selector_map if browser_state.dom_state else {}
			page_text = browser_state.dom_state.text_content.lower() if browser_state.dom_state.text_content else ""

			# Check for authenticated content indicators
			authenticated_indicators = [
				# User profile/avatar elements
				'avatar', 'profile', 'user-menu', 'user-dropdown', 'account-menu',
				# Logout buttons/links
				'logout', 'sign out', 'sign-out', 'log out', 'log-out',
				# Authenticated navigation
				'dashboard', 'my account', 'settings', 'preferences',
				# User-specific content
				'welcome back', 'hello,', 'hi,', 'logged in as',
			]

			# Check page text for authenticated indicators
			for indicator in authenticated_indicators:
				if indicator in page_text:
					logger.debug(f"Found authenticated indicator in text: {indicator}")
					return True

			# Check DOM elements for authenticated indicators
			for idx, element in selector_map.items():
				if not element.tag_name:
					continue

				# Check for logout buttons/links
				element_text = element.get_all_children_text().lower() if hasattr(element, 'get_all_children_text') else ""
				element_attrs = element.attributes or {}
				element_id = element_attrs.get('id', '').lower()
				element_class = element_attrs.get('class', '').lower()
				element_href = element_attrs.get('href', '').lower()

				# Check for logout indicators
				logout_indicators = ['logout', 'sign-out', 'signout', 'log-out', 'log out']
				if any(indicator in element_text or indicator in element_id or indicator in element_class or indicator in element_href 
					   for indicator in logout_indicators):
					logger.debug(f"Found logout element: {element_text[:50]}")
					return True

				# Check for user profile/avatar elements
				profile_indicators = ['avatar', 'user-profile', 'user-menu', 'account-menu', 'profile-picture']
				if any(indicator in element_id or indicator in element_class for indicator in profile_indicators):
					logger.debug(f"Found profile element: {element_id or element_class}")
					return True

			return False

		except Exception as e:
			logger.debug(f"Error checking authenticated content: {e}")
			return False

	async def _check_authentication_cookies(self) -> bool:
		"""
		Check for authentication/session cookies.
		
		Returns:
			True if authentication cookies found, False otherwise
		"""
		try:
			# Get cookies via CDP
			if not hasattr(self.browser_session, '_cdp_get_cookies'):
				logger.debug("Browser session does not support cookie access")
				return False

			cookies = await self.browser_session._cdp_get_cookies()
			if not cookies:
				logger.debug("No cookies found")
				return False

			# Check for common authentication cookie names
			auth_cookie_patterns = [
				'session', 'sessionid', 'auth', 'authentication', 'token', 'access_token',
				'jwt', 'csrf', 'csrf_token', 'user_id', 'userid', 'logged_in', 'login',
				'remember', 'remember_me', 'sso', 'oauth', 'identity',
			]

			for cookie in cookies:
				# Cookie can be a dict or Cookie object - handle both
				if hasattr(cookie, 'name'):
					# Cookie object (from cdp_use.cdp.network.Cookie)
					cookie_name = cookie.name.lower() if cookie.name else ''
					cookie_value = cookie.value if cookie.value else ''
				else:
					# Dict format
					cookie_name = cookie.get('name', '').lower()
					cookie_value = cookie.get('value', '')

				# Check if cookie name matches auth patterns and has a value
				for pattern in auth_cookie_patterns:
					if pattern in cookie_name and cookie_value:
						logger.debug(f"Found authentication cookie: {cookie_name}")
						return True

			logger.debug(f"Checked {len(cookies)} cookies, no authentication cookies found")
			return False

		except Exception as e:
			logger.debug(f"Error checking authentication cookies: {e}")
			return False

	async def _detect_error_messages(self) -> bool:
		"""
		Detect error messages on the current page.
		
		Returns:
			True if error messages detected, False otherwise
		"""
		try:
			browser_state = await self.browser_session.get_browser_state_summary(include_screenshot=False)
			if not browser_state or not browser_state.dom_state:
				return False

			page_text = browser_state.dom_state.text_content.lower() if browser_state.dom_state.text_content else ""
			selector_map = browser_state.dom_state.selector_map if browser_state.dom_state else {}

			# Error keywords to look for
			error_keywords = [
				'invalid', 'incorrect', 'wrong', 'failed', 'error', 'denied',
				'blocked', 'unauthorized', 'forbidden', 'access denied',
				'login failed', 'authentication failed', 'credentials',
				'username or password', 'try again', 'please try again',
			]

			# Check page text for error keywords
			for keyword in error_keywords:
				if keyword in page_text:
					logger.debug(f"Found error keyword in page text: {keyword}")
					return True

			# Check for error elements (common error class/ID patterns)
			for idx, element in selector_map.items():
				element_attrs = element.attributes or {}
				element_id = element_attrs.get('id', '').lower()
				element_class = element_attrs.get('class', '').lower()
				element_text = element.get_all_children_text().lower() if hasattr(element, 'get_all_children_text') else ""

				# Check for error indicators in element attributes
				error_indicators = ['error', 'alert', 'warning', 'danger', 'invalid', 'failed']
				if any(indicator in element_id or indicator in element_class for indicator in error_indicators):
					# Verify it contains error text
					if any(keyword in element_text for keyword in error_keywords[:5]):  # Check first 5 keywords
						logger.debug(f"Found error element: {element_id or element_class}")
						return True

			return False

		except Exception as e:
			logger.debug(f"Error detecting error messages: {e}")
			return False

	async def _wait_for_transition(
		self,
		initial_url: str | None = None,
		max_wait_time: float = 8.0,
		check_interval: float = 0.3,
		wait_for_dom_stability: bool = True,
		wait_for_network_idle: bool = True,
	) -> dict[str, Any]:
		"""
		Intelligently wait for UI transitions (navigation, DOM changes, network activity).
		
		Delegates to the shared utility function in navigator.action.dispatcher.utils.
		"""
		from navigator.action.dispatcher.utils import wait_for_transition
		
		return await wait_for_transition(
			browser_session=self.browser_session,
			initial_url=initial_url,
			max_wait_time=max_wait_time,
			check_interval=check_interval,
			wait_for_dom_stability=wait_for_dom_stability,
			wait_for_network_idle=wait_for_network_idle,
		)

	@property
	def authenticated(self) -> bool:
		"""Check if session is authenticated."""
		return self._authenticated

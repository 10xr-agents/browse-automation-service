"""
Authentication Service for Knowledge Retrieval

Handles login detection, execution, and validation for authenticated website exploration.
Credentials are handled securely - never logged or persisted.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

from browser_use import BrowserSession
from browser_use.dom.views import EnhancedDOMTreeNode
from browser_use.browser.events import SendKeysEvent

from navigator.action.dispatcher import ActionDispatcher
from navigator.action.command import TypeActionCommand, ClickActionCommand, NavigateActionCommand

logger = logging.getLogger(__name__)


@dataclass
class Credentials:
	"""
	Credentials for authentication.
	
	Credentials are kept in memory only and never logged or persisted.
	"""
	username: str
	password: str
	login_url: str | None = None  # Optional explicit login URL
	
	def __repr__(self) -> str:
		"""Mask credentials in string representation."""
		return f"Credentials(username=***, password=***, login_url={self.login_url})"


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
					
					# Wait for page to load
					await asyncio.sleep(2)
			
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
			
			# Wait a bit
			await asyncio.sleep(0.5)
			
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
			
			# Wait a bit
			await asyncio.sleep(0.5)
			
			# Submit form
			if submit_index is not None:
				logger.info("Clicking submit button")
				submit_action = ClickActionCommand(params={'index': submit_index})
				submit_result = await self.action_dispatcher.execute_action(submit_action)
				if not submit_result.success:
					return {
						'success': False,
						'message': 'Failed to click submit button',
						'error': submit_result.error,
						'logged_in_url': None,
					}
			else:
				# Try Enter key (use SendKeysEvent directly since password field is already focused)
				logger.info("Submitting form with Enter key")
				event = self.browser_session.event_bus.dispatch(SendKeysEvent(keys="Enter"))
				await event
				await event.event_result(raise_if_any=False, raise_if_none=False)
			
			# Wait for navigation/response
			await asyncio.sleep(3)
			
			# Validate login
			logged_in_url = await self.browser_session.get_current_page_url()
			login_valid = await self.validate_login(logged_in_url)
			
			if login_valid:
				self._authenticated = True
				return {
					'success': True,
					'message': 'Login successful',
					'error': None,
					'logged_in_url': logged_in_url,
				}
			else:
				return {
					'success': False,
					'message': 'Login failed - still on login page or error page',
					'error': 'Login validation failed - page did not change or login error detected',
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
	
	async def validate_login(self, url: str) -> bool:
		"""
		Validate if login was successful.
		
		Args:
			url: Current page URL after login attempt
		
		Returns:
			True if login appears successful, False otherwise
		"""
		try:
			# Check if we're no longer on a login page
			is_login_page = await self.detect_login_page(url)
			if is_login_page:
				logger.debug("Still on login page - login likely failed")
				return False
			
			# Check URL for success indicators
			url_lower = url.lower()
			success_patterns = [
				r'/dashboard',
				r'/home',
				r'/account',
				r'/profile',
				r'/welcome',
			]
			
			for pattern in success_patterns:
				if re.search(pattern, url_lower):
					logger.debug(f"Login success detected by URL pattern: {pattern}")
					return True
			
			# If URL changed and we're not on a login page, assume success
			# (This is a heuristic - could be improved with more sophisticated detection)
			logger.debug("URL changed and not on login page - assuming login success")
			return True
		
		except Exception as e:
			logger.debug(f"Error validating login: {e}")
			return False
	
	@property
	def authenticated(self) -> bool:
		"""Check if session is authenticated."""
		return self._authenticated

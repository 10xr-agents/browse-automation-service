"""
Website documentation crawler using Browser-Use.

Cursor-style website indexing with respect for robots.txt, rate limiting,
and comprehensive page snapshot capture. Uses Browser-Use for better bot
detection bypass and cloud browser support.
"""

import asyncio
import logging
import re
import time
from collections import deque
from typing import Any
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import aiohttp
import tiktoken
from bs4 import BeautifulSoup
from robotexclusionrulesparser import RobotExclusionRulesParser

# Browser-Use imports removed from top - will import inline where needed
from navigator.schemas import (
	ContentChunk,
	IngestionResult,
	SourceMetadata,
	SourceType,
)

logger = logging.getLogger(__name__)


class WebsiteCrawler:
	"""
	Crawls website documentation using Browser-Use.
	
	Features:
	- Respects robots.txt
	- Rate limiting (configurable requests/second)
	- Navigation structure extraction
	- Page snapshots (DOM + screenshot)
	- Depth-limited crawling
	- Bot detection bypass (via Browser-Use)
	- Cloud browser support
	"""

	def __init__(
		self,
		max_depth: int = 5,
		max_pages: int = 100,
		rate_limit: float = 0.1,  # seconds between requests
		max_tokens_per_chunk: int = 2000,
		user_agent: str = "NavigatorBot/1.0 (+https://navigator.ai/bot)",
		use_cloud: bool = False,  # Use Browser-Use cloud browsers
		headless: bool = True,
		credentials: dict[str, str] | None = None,  # Optional: {'username': '...', 'password': '...', 'login_url': '...'}
	):
		"""
		Initialize website crawler.
		
		Args:
			max_depth: Maximum crawl depth from seed URL
			max_pages: Maximum number of pages to crawl
			rate_limit: Minimum seconds between requests
			max_tokens_per_chunk: Maximum tokens per content chunk
			user_agent: User agent string
			use_cloud: Use Browser-Use cloud browsers (better bot detection bypass)
			headless: Run browser in headless mode
			credentials: Optional credentials for login {'username': '...', 'password': '...', 'login_url': '...'}
		"""
		self.max_depth = max_depth
		self.max_pages = max_pages
		self.rate_limit = rate_limit
		self.max_tokens_per_chunk = max_tokens_per_chunk
		self.user_agent = user_agent
		self.use_cloud = use_cloud
		self.headless = headless
		self.credentials = credentials
		self.tokenizer = tiktoken.get_encoding("cl100k_base")

		# Crawl state
		self.visited_urls: set[str] = set()
		self.url_queue: deque[tuple[str, int]] = deque()  # (url, depth)
		self.robots_parser: RobotExclusionRulesParser | None = None
		self.last_request_time: float = 0.0
		self.navigation_structure: dict[str, Any] = {}

	async def crawl_website(self, seed_url: str) -> IngestionResult:
		"""
		Crawl a website starting from seed URL.
		
		Args:
			seed_url: Starting URL for crawl
		
		Returns:
			IngestionResult with all crawled pages
		"""
		# Create result
		result = IngestionResult(
			ingestion_id=str(uuid4()),
			source_type=SourceType.WEBSITE_DOCUMENTATION,
			metadata=SourceMetadata(
				source_type=SourceType.WEBSITE_DOCUMENTATION,
				url=seed_url,
				title=None,  # Will be set from first page
			)
		)

		try:
			# Parse seed URL
			parsed_seed = urlparse(seed_url)
			base_domain = f"{parsed_seed.scheme}://{parsed_seed.netloc}"

			# Load robots.txt
			await self._load_robots_txt(base_domain)

			# Initialize queue
			self.url_queue.append((seed_url, 0))

			# Create Browser-Use session
			logger.info(f"🌐 Initializing Browser-Use crawler (use_cloud={self.use_cloud})")
			from browser_use.browser.session import BrowserSession

			browser_session = BrowserSession(
				headless=self.headless,
				use_cloud=self.use_cloud,
			)

			# Start browser session
			await browser_session.start()

			# Create initial page (will reuse for navigation)
			page = await browser_session.new_page()

			# Check if login is needed and perform it
			if self.credentials:
				await self._handle_login(browser_session, page, seed_url, result)

			try:
				while self.url_queue and len(self.visited_urls) < self.max_pages:
					url, depth = self.url_queue.popleft()

					# Skip if already visited or depth exceeded
					if url in self.visited_urls or depth > self.max_depth:
						continue

					# Check robots.txt
					if not self._can_fetch(url):
						logger.info(f"Skipping {url} (blocked by robots.txt)")
						continue

					# Rate limiting
					await self._rate_limit()

					# Crawl page
					try:
						page_data = await self._crawl_page(browser_session, page, url, depth, base_domain)

						if page_data:
							self.visited_urls.add(url)

							# Phase 5.1: Create screen definition from browser state for authenticated portals
							if self.credentials and page_data.get('url_patterns'):
								# Extract screen directly from browser state
								screen = await self._create_screen_from_browser_state(
									browser_session,
									page_data,
									base_domain
								)
								if screen:
									# Store screen in page_data for later processing
									page_data['extracted_screen'] = screen.dict()
									logger.debug(f"✅ Extracted screen: {screen.screen_id} ({screen.name})")
							
							# Create chunk from page
							chunk = ContentChunk(
								chunk_id=f"{result.ingestion_id}_{len(result.content_chunks)}",
								content=page_data['content'],
								chunk_index=len(result.content_chunks),
								token_count=len(self.tokenizer.encode(page_data['content'])),
								chunk_type="webpage",
								section_title=page_data.get('title'),
								# Phase 5.1: Add screen metadata to chunk
								metadata={
									'url': page_data.get('url'),
									'url_patterns': page_data.get('url_patterns', []),
									'dom_indicators': page_data.get('dom_indicators', []),
									'ui_elements_count': len(page_data.get('ui_elements', [])),
									'spatial_info': page_data.get('spatial_info', {}),
									'extracted_screen': page_data.get('extracted_screen'),
								}
							)
							result.content_chunks.append(chunk)

							# Set title from first page
							if result.metadata.title is None:
								result.metadata.title = page_data.get('title', 'Unknown')

							# Extract navigation structure
							self._extract_navigation_structure(url, page_data)

							logger.info(f"✅ Crawled [{depth}]: {url}")

					except Exception as e:
						logger.error(f"Error crawling {url}: {e}")
						result.add_error(
							"CrawlError",
							f"Failed to crawl {url}: {str(e)}",
							{"url": url, "depth": depth}
						)

			finally:
				# Always stop browser
				await browser_session.stop()

			# Mark complete
			result.mark_complete()
			logger.info(f"✅ Crawled {len(self.visited_urls)} pages from {seed_url}")

		except Exception as e:
			logger.error(f"❌ Error crawling website: {e}", exc_info=True)
			result.add_error("WebsiteCrawlError", str(e), {"seed_url": seed_url})
			result.mark_complete()

		return result

	async def _load_robots_txt(self, base_url: str) -> None:
		"""Load and parse robots.txt."""
		robots_url = urljoin(base_url, "/robots.txt")

		try:
			async with aiohttp.ClientSession() as session:
				async with session.get(robots_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
					if response.status == 200:
						robots_content = await response.text()
						self.robots_parser = RobotExclusionRulesParser()
						self.robots_parser.parse(robots_content)
						logger.info(f"✅ Loaded robots.txt from {robots_url}")
					else:
						logger.info(f"No robots.txt found at {robots_url} (status: {response.status})")
		except Exception as e:
			logger.warning(f"Could not load robots.txt: {e}")

	def _can_fetch(self, url: str) -> bool:
		"""Check if URL can be fetched according to robots.txt."""
		if self.robots_parser is None:
			return True

		try:
			return self.robots_parser.is_allowed(self.user_agent, url)
		except Exception:
			# If parsing fails, allow by default
			return True

	async def _rate_limit(self) -> None:
		"""Enforce rate limiting between requests."""
		current_time = time.time()
		time_since_last = current_time - self.last_request_time

		if time_since_last < self.rate_limit:
			await asyncio.sleep(self.rate_limit - time_since_last)

		self.last_request_time = time.time()

	async def _crawl_page(
		self,
		browser_session: Any,
		page: Any,
		url: str,
		depth: int,
		base_domain: str,
	) -> dict[str, Any] | None:
		"""
		Phase 5.1: Crawl a single page using Browser-Use BrowserSession.
		
		Enhanced to extract actual web UI screens with:
		- Real URL patterns from actual URLs
		- Actual DOM indicators from browser state
		- Real UI elements from selector_map
		- Spatial information if available
		
		Args:
			browser_session: Browser-Use BrowserSession instance
			page: Browser-Use Page instance (reused for navigation)
			url: URL to crawl
			depth: Current depth
			base_domain: Base domain for link filtering
		
		Returns:
			Page data dictionary with extracted screen information or None if failed
		"""
		try:
			# Navigate to page using Browser-Use API
			logger.debug(f"Navigating to {url}")

			# Navigate to URL (reuse existing page)
			await page.goto(url)

			# Wait for page to load
			import asyncio
			await asyncio.sleep(2)  # Give page time to load

			# Phase 5.1: Get browser state for DOM extraction
			browser_state = await browser_session.get_browser_state_summary(include_screenshot=False)
			
			# Extract page data using Browser-Use API
			title = await page.get_title()
			current_url = await page.get_url()

			# Phase 5.1: Extract DOM state and selector map
			dom_state = browser_state.dom_state if browser_state else None
			selector_map = dom_state.selector_map if dom_state else {}
			text_content = dom_state.text_content if dom_state else ""

			# Phase 5.1: Extract real URL pattern from actual URL
			url_patterns = self._extract_url_pattern_from_url(current_url, base_domain)

			# Phase 5.1: Extract actual DOM indicators from browser state
			dom_indicators = self._extract_dom_indicators_from_state(dom_state, selector_map, title)

			# Phase 5.1: Extract real UI elements from selector_map
			ui_elements = self._extract_ui_elements_from_selector_map(selector_map)

			# Phase 5.1: Extract spatial information if available
			spatial_info = self._extract_spatial_information(selector_map, dom_state)

			# Get page content using JavaScript evaluation (must use arrow function format)
			content = await page.evaluate('() => document.documentElement.outerHTML')

			# Parse with BeautifulSoup for text extraction
			soup = BeautifulSoup(content, 'html.parser')

			# Remove scripts, styles, etc.
			for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe']):
				element.decompose()

			# Extract main content
			main_content = soup.find('main') or soup.find('article') or soup.find('body')

			if main_content:
				text_content_fallback = main_content.get_text(separator='\n', strip=True)
			else:
				text_content_fallback = soup.get_text(separator='\n', strip=True)

			# Use DOM text content if available, otherwise fallback to parsed text
			final_text_content = text_content if text_content else text_content_fallback

			# Phase 5.1: Create enhanced content with screen structure
			enhanced_content = f"# {title}\n\nURL: {current_url}\n\n"
			if url_patterns:
				enhanced_content += f"URL Patterns: {', '.join(url_patterns)}\n\n"
			if dom_indicators:
				enhanced_content += f"DOM Indicators: {', '.join(dom_indicators)}\n\n"
			if ui_elements:
				enhanced_content += f"UI Elements: {len(ui_elements)} elements found\n\n"
			enhanced_content += f"{final_text_content}"

			# Extract links for next depth level
			if depth < self.max_depth:
				# Get all links using JavaScript (must use arrow function format)
				links_json = await page.evaluate('() => JSON.stringify(Array.from(document.querySelectorAll("a[href]")).map(a => a.href))')
				import json
				links = json.loads(links_json) if links_json else []

				# Filter and queue links
				for link in links:
					# Normalize URL
					absolute_link = urljoin(url, link)
					parsed_link = urlparse(absolute_link)

					# Only follow links to same domain
					if parsed_link.netloc == urlparse(base_domain).netloc:
						# Remove fragments
						clean_link = f"{parsed_link.scheme}://{parsed_link.netloc}{parsed_link.path}"
						if parsed_link.query:
							clean_link += f"?{parsed_link.query}"

						if clean_link not in self.visited_urls:
							self.url_queue.append((clean_link, depth + 1))

			return {
				'url': current_url,
				'title': title,
				'content': enhanced_content,
				'depth': depth,
				# Phase 5.1: Add extracted screen data
				'url_patterns': url_patterns,
				'dom_indicators': dom_indicators,
				'ui_elements': ui_elements,
				'spatial_info': spatial_info,
				'selector_map': {str(k): str(v) for k, v in list(selector_map.items())[:10]},  # Sample for debugging
			}

		except Exception as e:
			logger.error(f"Error processing page {url}: {e}")
			return None
	
	def _extract_url_pattern_from_url(self, url: str, base_domain: str) -> list[str]:
		"""
		Phase 5.1: Extract real URL pattern from actual URL.
		
		Creates regex patterns that match the actual URL structure.
		"""
		patterns = []
		
		try:
			parsed = urlparse(url)
			
			# Pattern 1: Exact URL match
			exact_pattern = f"^{re.escape(url)}$"
			patterns.append(exact_pattern)
			
			# Pattern 2: Path-based pattern (allows query params and fragments)
			if parsed.path:
				# Escape path but allow query params and fragments
				path_pattern = re.escape(parsed.path)
				pattern = f"^{re.escape(parsed.scheme)}://{re.escape(parsed.netloc)}{path_pattern}(?:\\?.*)?(?:#.*)?$"
				patterns.append(pattern)
			
			# Pattern 3: Parameterized pattern (replace IDs with wildcards)
			if parsed.path:
				# Replace numeric IDs with \d+ pattern
				param_path = re.sub(r'/\d+', r'/\d+', parsed.path)
				param_path = re.sub(r'/[a-f0-9]{8,}', r'/[a-f0-9]+', param_path)  # UUIDs
				if param_path != parsed.path:
					escaped_path = re.escape(param_path).replace(r'\d\+', r'\d+').replace(r'\[a-f0-9\]\+', r'[a-f0-9]+')
					pattern = f"^{re.escape(parsed.scheme)}://{re.escape(parsed.netloc)}{escaped_path}(?:\\?.*)?(?:#.*)?$"
					patterns.append(pattern)
			
			logger.debug(f"Extracted {len(patterns)} URL patterns from {url}")
			
		except Exception as e:
			logger.warning(f"Failed to extract URL patterns from {url}: {e}")
		
		return patterns
	
	def _extract_dom_indicators_from_state(
		self,
		dom_state: Any,
		selector_map: dict[int, Any],
		title: str
	) -> list[str]:
		"""
		Phase 5.1: Extract actual DOM indicators from browser state.
		
		Extracts indicators from:
		- Page title
		- DOM element IDs, classes, attributes
		- Text content patterns
		"""
		indicators = []
		
		# Add title as indicator
		if title:
			indicators.append(f"title:{title}")
		
		# Extract indicators from selector_map
		for idx, element in list(selector_map.items())[:20]:  # Limit to first 20 elements
			if not element:
				continue
			
			# Extract from attributes
			if hasattr(element, 'attributes') and element.attributes:
				attrs = element.attributes
				
				# ID indicator
				if attrs.get('id'):
					indicators.append(f"id:{attrs['id']}")
				
				# Class indicators (first few classes)
				if attrs.get('class'):
					classes = attrs['class'].split()[:3]  # First 3 classes
					for cls in classes:
						if len(cls) > 2:  # Skip very short classes
							indicators.append(f"class:{cls}")
				
				# Role indicator
				if attrs.get('role'):
					indicators.append(f"role:{attrs['role']}")
				
				# Data attributes
				for key, value in attrs.items():
					if key.startswith('data-') and value:
						indicators.append(f"{key}:{value}")
			
			# Extract from tag name
			if hasattr(element, 'tag_name') and element.tag_name:
				tag = element.tag_name.upper()
				if tag in ['BUTTON', 'INPUT', 'FORM', 'NAV', 'HEADER', 'FOOTER']:
					indicators.append(f"tag:{tag}")
		
		# Deduplicate
		indicators = list(set(indicators))
		
		logger.debug(f"Extracted {len(indicators)} DOM indicators")
		
		return indicators
	
	def _extract_ui_elements_from_selector_map(
		self,
		selector_map: dict[int, Any]
	) -> list[dict[str, Any]]:
		"""
		Phase 5.1: Extract real UI elements from selector_map.
		
		Converts Browser-Use EnhancedDOMTreeNode objects to UIElement-like structures.
		"""
		ui_elements = []
		
		for idx, element in selector_map.items():
			if not element:
				continue
			
			# Only extract interactive elements
			if not hasattr(element, 'tag_name') or not element.tag_name:
				continue
			
			tag = element.tag_name.upper()
			
			# Filter for interactive elements
			interactive_tags = ['BUTTON', 'INPUT', 'SELECT', 'TEXTAREA', 'A', 'FORM', 'LINK']
			if tag not in interactive_tags:
				continue
			
			# Extract element data
			element_data = {
				'element_id': f"element_{idx}",
				'type': tag.lower(),
				'index': idx,
			}
			
			# Extract attributes
			if hasattr(element, 'attributes') and element.attributes:
				attrs = element.attributes
				
				# Build selector
				selector_parts = []
				if attrs.get('id'):
					selector_parts.append(f"#{attrs['id']}")
					element_data['selector'] = {'css': f"#{attrs['id']}"}
				elif attrs.get('class'):
					classes = attrs['class'].split()
					if classes:
						selector_parts.append(f".{classes[0]}")
						element_data['selector'] = {'css': f".{classes[0]}"}
				
				if not element_data.get('selector'):
					element_data['selector'] = {'css': f"{tag.lower()}[data-index='{idx}']"}
				
				# Extract text content
				if hasattr(element, 'get_all_children_text'):
					try:
						text = element.get_all_children_text(max_depth=2)
						if text:
							element_data['text'] = text[:100]  # Limit length
					except Exception:
						pass
				
				# Extract other attributes
				if attrs.get('placeholder'):
					element_data['placeholder'] = attrs['placeholder']
				if attrs.get('href'):
					element_data['href'] = attrs['href']
				if attrs.get('type'):
					element_data['input_type'] = attrs['type']
				if attrs.get('name'):
					element_data['name'] = attrs['name']
			
			ui_elements.append(element_data)
		
		logger.debug(f"Extracted {len(ui_elements)} UI elements from selector_map")
		
		return ui_elements
	
	def _extract_spatial_information(
		self,
		selector_map: dict[int, Any],
		dom_state: Any
	) -> dict[str, Any]:
		"""
		Phase 5.1: Extract spatial information if available.
		
		Extracts position, layout context, and visual hierarchy from DOM elements.
		"""
		spatial_info = {
			'elements_with_position': 0,
			'elements_with_layout': 0,
		}
		
		# Check if elements have position information
		for idx, element in list(selector_map.items())[:20]:
			if not element:
				continue
			
			# Check for position data in element
			if hasattr(element, 'bounding_box') and element.bounding_box:
				spatial_info['elements_with_position'] += 1
			
			# Infer layout context from element position and parent
			if hasattr(element, 'parent') and element.parent:
				spatial_info['elements_with_layout'] += 1
		
		return spatial_info

	async def _handle_login(
		self,
		browser_session: Any,
		page: Any,
		seed_url: str,
		result: IngestionResult,
	) -> None:
		"""
		Handle login if credentials are provided.
		
		Args:
			browser_session: Browser session instance
			page: Page instance
			seed_url: Starting URL
			result: Ingestion result to add errors if login fails
		"""
		try:
			from navigator.knowledge.auth_service import AuthenticationService, Credentials

			# Navigate to seed URL first to check if login is needed
			logger.info(f"🔐 Checking if login is required for {seed_url}")
			await page.goto(seed_url)
			await asyncio.sleep(2)  # Wait for page to load

			# Check current URL
			current_url = await page.get_url()

			# Initialize auth service
			auth_service = AuthenticationService(browser_session)

			# Check if we're on a login page
			is_login_page = await auth_service.detect_login_page(current_url)

			if is_login_page or self.credentials.get('login_url'):
				logger.info("🔐 Login page detected or login URL provided - performing login")

				# Create credentials object
				creds = Credentials(
					username=self.credentials.get('username', ''),
					password=self.credentials.get('password', ''),
					login_url=self.credentials.get('login_url'),
				)

				# Perform login
				login_result = await auth_service.perform_login(creds)

				if login_result['success']:
					logger.info(f"✅ Login successful: {login_result.get('message', 'Logged in')}")
					# Update seed URL if login redirected us
					if login_result.get('logged_in_url'):
						logger.info(f"📍 Redirected to: {login_result['logged_in_url']}")
				else:
					error_msg = f"Login failed: {login_result.get('error', login_result.get('message', 'Unknown error'))}"
					logger.error(f"❌ {error_msg}")
					result.add_error(
						"LoginError",
						error_msg,
						{"login_url": current_url}
					)
			else:
				logger.info("ℹ️ No login required - proceeding with crawl")

		except Exception as e:
			logger.error(f"❌ Error during login: {e}", exc_info=True)
			result.add_error(
				"LoginError",
				f"Failed to perform login: {str(e)}",
				{"seed_url": seed_url}
			)

	def _extract_navigation_structure(self, url: str, page_data: dict[str, Any]) -> None:
		"""Extract navigation structure from page."""
		# Store basic navigation info
		self.navigation_structure[url] = {
			'title': page_data.get('title'),
			'depth': page_data.get('depth', 0),
		}
	
	async def _create_screen_from_browser_state(
		self,
		browser_session: Any,
		page_data: dict[str, Any],
		base_domain: str
	) -> Any | None:
		"""
		Phase 5.1: Create ScreenDefinition directly from browser state.
		
		Extracts actual web UI screen with:
		- Real URL patterns from actual URL
		- Actual DOM indicators from browser state
		- Real UI elements from selector_map
		- Spatial information if available
		
		Args:
			browser_session: Browser-Use BrowserSession instance
			page_data: Page data dictionary with extracted information
			base_domain: Base domain for website_id
		
		Returns:
			ScreenDefinition object or None if failed
		"""
		try:
			from navigator.knowledge.extract.screens import (
				ElementSelector,
				Indicator,
				ScreenDefinition,
				ScreenRegion,
				SelectorStrategy,
				StateSignature,
				UIElement,
			)
			
			url = page_data.get('url', '')
			title = page_data.get('title', 'Unknown Page')
			
			# Improve screen name extraction from DOM
			# Try multiple sources in order of preference:
			# 1. H1 heading (most specific)
			# 2. Page title (good fallback)
			# 3. URL path segment (last resort)
			# 4. Navigation breadcrumb (if available)
			screen_name = await self._extract_best_screen_name(
				browser_session,
				page_data,
				title,
				url
			)
			
			# Generate screen ID
			from hashlib import md5
			screen_name_normalized = re.sub(r'[^\w\s-]', '', screen_name.lower())
			screen_name_normalized = re.sub(r'[-\s]+', '_', screen_name_normalized)
			screen_name_normalized = screen_name_normalized[:30]
			hash_suffix = md5(screen_name.encode()).hexdigest()[:8]
			screen_id = f"{screen_name_normalized}_{hash_suffix}"
			
			# Extract website_id from base_domain
			parsed_domain = urlparse(base_domain)
			website_id = parsed_domain.netloc.replace('.', '_')
			
			# Phase 5.1: Create URL patterns from actual URL
			url_patterns = page_data.get('url_patterns', [])
			
			# Phase 5.1: Create state signature from DOM indicators
			dom_indicators = page_data.get('dom_indicators', [])
			required_indicators = []
			
			# Add URL match indicator
			if url_patterns:
				for pattern in url_patterns[:3]:  # Limit to first 3 patterns
					required_indicators.append(Indicator(
						type='url_matches',
						pattern=pattern,
						reason='URL pattern for screen recognition'
					))
			
			# Add DOM indicators
			for indicator_str in dom_indicators[:10]:  # Limit to first 10
				if ':' in indicator_str:
					ind_type, ind_value = indicator_str.split(':', 1)
					if ind_type in ['id', 'class', 'role']:
						required_indicators.append(Indicator(
							type=f'dom_{ind_type}',
							value=ind_value,
							selector=f"[{ind_type}='{ind_value}']",
							reason=f'DOM {ind_type} indicator for screen recognition'
						))
			
			# Add title as indicator
			if title:
				required_indicators.append(Indicator(
					type='dom_contains',
					value=title[:50],  # Limit length
					selector='h1, h2, .page-title, title',
					reason='Page title for screen recognition'
				))
			
			state_signature = StateSignature(
				required_indicators=required_indicators,
				optional_indicators=[],
				exclusion_indicators=[],
				negative_indicators=[],
			)
			
			# Phase 5.1: Create UI elements from selector_map data
			ui_elements_data = page_data.get('ui_elements', [])
			ui_elements = []
			
			for elem_data in ui_elements_data:
				try:
					# Build selector
					selector_dict = elem_data.get('selector', {})
					if isinstance(selector_dict, dict):
						css_selector = selector_dict.get('css', f"[data-index='{elem_data.get('index', 0)}']")
					else:
						css_selector = str(selector_dict)
					
					selector = ElementSelector(
						strategies=[SelectorStrategy(
							type='css',
							css=css_selector,
						)]
					)
					
					# Extract element properties
					element_type = elem_data.get('type', 'unknown')
					element_id = elem_data.get('element_id', f"element_{elem_data.get('index', 0)}")
					
					# Create UIElement
					ui_element = UIElement(
						element_id=element_id,
						type=element_type,
						selector=selector,
						affordances=[],  # Will be populated by affordance extraction
						metadata={
							'index': elem_data.get('index'),
							'text': elem_data.get('text', '')[:100],
							'placeholder': elem_data.get('placeholder'),
							'href': elem_data.get('href'),
							'input_type': elem_data.get('input_type'),
							'name': elem_data.get('name'),
						}
					)
					
					ui_elements.append(ui_element)
				except Exception as e:
					logger.debug(f"Failed to create UIElement from data: {e}")
					continue
			
			# Phase 5.1: Extract spatial information and create regions
			spatial_info = page_data.get('spatial_info', {})
			regions = []
			
			# Create basic regions if we have UI elements
			if ui_elements:
				# Simple region detection based on element types
				header_elements = [e for e in ui_elements if e.type in ['nav', 'header']]
				main_elements = [e for e in ui_elements if e.type in ['form', 'button', 'input']]
				
				if header_elements:
					regions.append(ScreenRegion(
						region_id=f"{website_id}_header_{hash_suffix}",
						region_type='header',
						bounds={'x': 0, 'y': 0, 'width': 1920, 'height': 80},
						ui_element_ids=[e.element_id for e in header_elements[:10]],
						metadata={'extraction_method': 'browser_state'}
					))
				
				if main_elements:
					regions.append(ScreenRegion(
						region_id=f"{website_id}_main_{hash_suffix}",
						region_type='main',
						bounds={'x': 0, 'y': 80, 'width': 1920, 'height': 1000},
						ui_element_ids=[e.element_id for e in main_elements[:20]],
						metadata={'extraction_method': 'browser_state'}
					))
			
			# Priority 7: Enrich UI elements with spatial info if available
			# Extract spatial info from page_data if available
			spatial_info = page_data.get('spatial_info', {})
			ui_elements_with_spatial = page_data.get('ui_elements_with_spatial', [])
			
			# Priority 7: Match UI elements with spatial data by element_id or index
			for ui_elem in ui_elements:
				# Add basic layout context based on element type (fallback)
				if ui_elem.type in ['nav', 'header']:
					ui_elem.layout_context = 'header'
				elif ui_elem.type in ['form', 'button', 'input']:
					ui_elem.layout_context = 'main'
				
				# Priority 7: Try to find spatial data for this element
				for spatial_elem in ui_elements_with_spatial:
					if isinstance(spatial_elem, dict):
						# Match by element_id or index
						if (spatial_elem.get('element_id') == ui_elem.element_id or
						    spatial_elem.get('index') == ui_elem.metadata.get('index')):
							# Priority 7: Extract position data
							if spatial_elem.get('position'):
								position = spatial_elem['position']
								if isinstance(position, dict):
									# Ensure bounding_box exists
									if 'bounding_box' not in position and all(k in position for k in ['x', 'y', 'width', 'height']):
										position['bounding_box'] = {
											'x': position.get('x', 0),
											'y': position.get('y', 0),
											'width': position.get('width', 0),
											'height': position.get('height', 0),
										}
									ui_elem.position = position
							
							# Priority 7: Extract layout_context if available
							if spatial_elem.get('layout_context'):
								ui_elem.layout_context = spatial_elem['layout_context']
							
							# Priority 7: Extract importance_score if available
							if spatial_elem.get('importance_score') is not None:
								try:
									score = float(spatial_elem['importance_score'])
									ui_elem.importance_score = max(0.0, min(1.0, score))
								except (ValueError, TypeError):
									pass
							
							# Priority 7: Extract visual_properties if available
							if spatial_elem.get('visual_properties'):
								ui_elem.visual_properties = spatial_elem['visual_properties']
							
							break
			
			# Create ScreenDefinition
			screen = ScreenDefinition(
				screen_id=screen_id,
				name=screen_name,  # Use improved screen name
				website_id=website_id,
				url_patterns=url_patterns,
				state_signature=state_signature,
				ui_elements=ui_elements,
				content_type="web_ui",
				is_actionable=True,
				metadata={
					'extraction_method': 'browser_state',
					'extracted_from': 'authenticated_portal',
					'url': url,
					'regions': [r.dict() for r in regions] if regions else None,
					'layout_structure': {
						'type': 'standard',
						'regions_count': len(regions),
					} if regions else None,
				}
			)
			
			logger.info(f"✅ Created screen from browser state: {screen_id} ({screen_name})")
			return screen
			
		except Exception as e:
			logger.error(f"Failed to create screen from browser state: {e}", exc_info=True)
			return None
	
	async def _extract_best_screen_name(
		self,
		browser_session: Any,
		page_data: dict[str, Any],
		title: str,
		url: str
	) -> str:
		"""
		Extract the best screen name from DOM using multiple strategies.
		
		Priority order:
		1. H1 heading (most specific page identifier)
		2. H2 heading (if H1 not available)
		3. Page title (good fallback)
		4. URL path segment (e.g., /dashboard -> "Dashboard")
		5. Navigation breadcrumb (if available)
		
		Args:
			browser_session: Browser session for DOM access
			page_data: Page data dictionary
			title: Page title
			url: Current URL
		
		Returns:
			Best screen name found
		"""
		# Strategy 1: Try to get H1 heading from DOM
		try:
			# Access page from browser_session if available
			if hasattr(browser_session, 'page') and browser_session.page:
				page = browser_session.page
				# Try to get H1 using JavaScript
				h1_text = await page.evaluate('() => { const h1 = document.querySelector("h1"); return h1 ? h1.textContent.trim() : null; }')
				if h1_text and len(h1_text) > 0 and len(h1_text) <= 100:
					# Clean H1 text
					h1_clean = re.sub(r'\s+', ' ', h1_text).strip()
					if 2 <= len(h1_clean) <= 80:
						logger.debug(f"Extracted screen name from H1: {h1_clean}")
						return h1_clean
		except Exception as e:
			logger.debug(f"Could not extract H1: {e}")
		
		# Strategy 2: Try H2 heading
		try:
			if hasattr(browser_session, 'page') and browser_session.page:
				page = browser_session.page
				h2_text = await page.evaluate('() => { const h2 = document.querySelector("h2"); return h2 ? h2.textContent.trim() : null; }')
				if h2_text and len(h2_text) > 0 and len(h2_text) <= 100:
					h2_clean = re.sub(r'\s+', ' ', h2_text).strip()
					if 2 <= len(h2_clean) <= 80:
						logger.debug(f"Extracted screen name from H2: {h2_clean}")
						return h2_clean
		except Exception as e:
			logger.debug(f"Could not extract H2: {e}")
		
		# Strategy 3: Use page title (clean it up)
		if title and title != 'Unknown Page':
			# Clean title: remove site name, limit length
			title_clean = title
			# Remove common suffixes like " - SiteName"
			title_clean = re.sub(r'\s*-\s*[^-]+$', '', title_clean).strip()
			# Limit length
			if len(title_clean) > 80:
				title_clean = title_clean[:77] + '...'
			if 2 <= len(title_clean) <= 80:
				return title_clean
		
		# Strategy 4: Extract from URL path
		try:
			from urllib.parse import urlparse
			parsed = urlparse(url)
			if parsed.path and parsed.path != '/':
				# Get last path segment
				path_segments = [s for s in parsed.path.split('/') if s]
				if path_segments:
					last_segment = path_segments[-1]
					# Convert to readable name
					# e.g., "dashboard" -> "Dashboard", "user-profile" -> "User Profile"
					name = last_segment.replace('-', ' ').replace('_', ' ')
					name = ' '.join(word.capitalize() for word in name.split())
					if 2 <= len(name) <= 80:
						logger.debug(f"Extracted screen name from URL path: {name}")
						return name
		except Exception as e:
			logger.debug(f"Could not extract from URL: {e}")
		
		# Strategy 5: Try navigation breadcrumb
		try:
			if hasattr(browser_session, 'page') and browser_session.page:
				page = browser_session.page
				breadcrumb_text = await page.evaluate('''
					() => {
						const breadcrumb = document.querySelector('nav[aria-label="breadcrumb"], .breadcrumb, [role="navigation"]');
						if (breadcrumb) {
							const items = Array.from(breadcrumb.querySelectorAll('a, span'));
							const lastItem = items[items.length - 1];
							return lastItem ? lastItem.textContent.trim() : null;
						}
						return null;
					}
				''')
				if breadcrumb_text and len(breadcrumb_text) > 0 and len(breadcrumb_text) <= 80:
					logger.debug(f"Extracted screen name from breadcrumb: {breadcrumb_text}")
					return breadcrumb_text
		except Exception as e:
			logger.debug(f"Could not extract from breadcrumb: {e}")
		
		# Fallback: Use title or "Unknown Page"
		return title if title else "Unknown Page"

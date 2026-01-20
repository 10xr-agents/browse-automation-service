"""
Website documentation crawler using Browser-Use.

Cursor-style website indexing with respect for robots.txt, rate limiting,
and comprehensive page snapshot capture. Uses Browser-Use for better bot
detection bypass and cloud browser support.
"""

import asyncio
import logging
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

							# Create chunk from page
							chunk = ContentChunk(
								chunk_id=f"{result.ingestion_id}_{len(result.content_chunks)}",
								content=page_data['content'],
								chunk_index=len(result.content_chunks),
								token_count=len(self.tokenizer.encode(page_data['content'])),
								chunk_type="webpage",
								section_title=page_data.get('title'),
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
		Crawl a single page using Browser-Use BrowserSession.
		
		Args:
			browser_session: Browser-Use BrowserSession instance
			page: Browser-Use Page instance (reused for navigation)
			url: URL to crawl
			depth: Current depth
			base_domain: Base domain for link filtering
		
		Returns:
			Page data dictionary or None if failed
		"""
		try:
			# Navigate to page using Browser-Use API
			logger.debug(f"Navigating to {url}")

			# Navigate to URL (reuse existing page)
			await page.goto(url)

			# Wait for page to load
			import asyncio
			await asyncio.sleep(2)  # Give page time to load

			# Extract page data using Browser-Use API
			title = await page.get_title()

			# Get page content using JavaScript evaluation (must use arrow function format)
			content = await page.evaluate('() => document.documentElement.outerHTML')

			# Parse with BeautifulSoup
			soup = BeautifulSoup(content, 'html.parser')

			# Remove scripts, styles, etc.
			for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe']):
				element.decompose()

			# Extract main content
			main_content = soup.find('main') or soup.find('article') or soup.find('body')

			if main_content:
				text_content = main_content.get_text(separator='\n', strip=True)
			else:
				text_content = soup.get_text(separator='\n', strip=True)

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
				'url': url,
				'title': title,
				'content': f"# {title}\n\nURL: {url}\n\n{text_content}",
				'depth': depth,
			}

		except Exception as e:
			logger.error(f"Error processing page {url}: {e}")
			return None

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

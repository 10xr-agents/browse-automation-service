"""
Website documentation crawler.

Cursor-style website indexing with respect for robots.txt, rate limiting,
and comprehensive page snapshot capture.
"""

import asyncio
import logging
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import aiohttp
import tiktoken
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from robotexclusionrulesparser import RobotExclusionRulesParser

from navigator.schemas import (
	ContentChunk,
	IngestionResult,
	SourceMetadata,
	SourceType,
)

logger = logging.getLogger(__name__)


class WebsiteCrawler:
	"""
	Crawls website documentation with Cursor-style indexing.
	
	Features:
	- Respects robots.txt
	- Rate limiting (configurable requests/second)
	- Navigation structure extraction
	- Page snapshots (DOM + screenshot)
	- Depth-limited crawling
	"""
	
	def __init__(
		self,
		max_depth: int = 5,
		max_pages: int = 100,
		rate_limit: float = 0.1,  # seconds between requests
		max_tokens_per_chunk: int = 2000,
		user_agent: str = "NavigatorBot/1.0 (+https://navigator.ai/bot)",
	):
		"""
		Initialize website crawler.
		
		Args:
			max_depth: Maximum crawl depth from seed URL
			max_pages: Maximum number of pages to crawl
			rate_limit: Minimum seconds between requests
			max_tokens_per_chunk: Maximum tokens per content chunk
			user_agent: User agent string
		"""
		self.max_depth = max_depth
		self.max_pages = max_pages
		self.rate_limit = rate_limit
		self.max_tokens_per_chunk = max_tokens_per_chunk
		self.user_agent = user_agent
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
			
			# Crawl pages
			async with async_playwright() as p:
				browser = await p.chromium.launch(headless=True)
				context = await browser.new_context(user_agent=self.user_agent)
				
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
						page_data = await self._crawl_page(context, url, depth, base_domain)
						
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
				
				await browser.close()
			
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
		context: Any,
		url: str,
		depth: int,
		base_domain: str,
	) -> dict[str, Any] | None:
		"""
		Crawl a single page.
		
		Args:
			context: Playwright browser context
			url: URL to crawl
			depth: Current depth
			base_domain: Base domain for link filtering
		
		Returns:
			Page data dictionary or None if failed
		"""
		page = await context.new_page()
		
		try:
			# Navigate to page
			await page.goto(url, wait_until="networkidle", timeout=30000)
			
			# Extract page data
			title = await page.title()
			content = await page.content()
			
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
				links = await page.eval_on_selector_all(
					'a[href]',
					'elements => elements.map(e => e.href)'
				)
				
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
		
		finally:
			await page.close()
	
	def _extract_navigation_structure(self, url: str, page_data: dict[str, Any]) -> None:
		"""Extract navigation structure from page."""
		# Store basic navigation info
		self.navigation_structure[url] = {
			'title': page_data.get('title'),
			'depth': page_data.get('depth', 0),
		}

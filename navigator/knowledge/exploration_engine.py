"""
Exploration Engine for Knowledge Retrieval

Implements website exploration with link discovery, tracking, depth management,
BFS/DFS strategies, and form handling.
"""

import asyncio
import logging
import re
from collections import deque
from enum import Enum
from typing import Any
from urllib.parse import urljoin, urlparse

from browser_use import BrowserSession
from browser_use.dom.serializer.html_serializer import HTMLSerializer

logger = logging.getLogger(__name__)


class ExplorationStrategy(str, Enum):
	"""Exploration strategy enumeration."""
	BFS = "BFS"  # Breadth-first search
	DFS = "DFS"  # Depth-first search


class ExplorationEngine:
	"""
	Exploration engine for website crawling and link discovery.
	
	Supports:
	- Link discovery on pages
	- Visited URL tracking
	- Depth management
	- BFS and DFS exploration strategies
	- Form detection (for future form handling)
	"""
	
	def __init__(
		self,
		browser_session: BrowserSession,
		max_depth: int = 3,
		strategy: ExplorationStrategy = ExplorationStrategy.BFS,
		base_url: str | None = None,
	):
		"""
		Initialize the exploration engine.
		
		Args:
			browser_session: Browser session for navigation and DOM access
			max_depth: Maximum exploration depth (default: 3)
			strategy: Exploration strategy - BFS or DFS (default: BFS)
			base_url: Base URL for resolving relative links (optional)
		"""
		self.browser_session = browser_session
		self.max_depth = max_depth
		self.strategy = strategy
		self.base_url = base_url
		
		# Visited URLs tracking
		self.visited_urls: set[str] = set()
		
		# Depth tracking per URL
		self.url_depths: dict[str, int] = {}
		
		# Exploration progress
		self.explored_pages: list[dict[str, Any]] = []
		
		logger.debug(
			f"ExplorationEngine initialized (max_depth: {max_depth}, strategy: {strategy.value})"
		)
	
	async def discover_links(self, url: str) -> list[dict[str, Any]]:
		"""
		Discover links on a single page.
		
		Args:
			url: URL of the page to discover links from
		
		Returns:
			List of discovered links, each with 'href', 'text', and optional attributes
		"""
		logger.debug(f"Discovering links from {url}")
		
		try:
			# Navigate to URL
			from browser_use.browser.events import NavigateToUrlEvent
			event = self.browser_session.event_bus.dispatch(NavigateToUrlEvent(url=url))
			await event
			await asyncio.sleep(0.5)  # Wait for page load
			
			# Get DOM service and extract HTML
			# Use the helper function from markdown_extractor for browser_session approach
			from browser_use.dom.markdown_extractor import _get_enhanced_dom_tree_from_browser_session
			enhanced_dom_tree = await _get_enhanced_dom_tree_from_browser_session(self.browser_session)
			
			# Serialize to HTML
			html_serializer = HTMLSerializer(extract_links=True)
			page_html = html_serializer.serialize(enhanced_dom_tree)
			
			# Parse HTML and extract links
			links = self._extract_links_from_html(page_html, url)
			
			logger.debug(f"Discovered {len(links)} links from {url}")
			return links
		
		except Exception as e:
			logger.error(f"Error discovering links from {url}: {e}", exc_info=True)
			return []
	
	def _extract_links_from_html(self, html: str, base_url: str) -> list[dict[str, Any]]:
		"""
		Extract links from HTML string.
		
		Args:
			html: HTML content
			base_url: Base URL for resolving relative links
		
		Returns:
			List of link dictionaries with 'href', 'text', and attributes
		"""
		links = []
		# Pattern to match <a> tags with href attribute
		link_pattern = re.compile(
			r'<a\s+[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>',
			re.IGNORECASE | re.DOTALL
		)
		
		for match in link_pattern.finditer(html):
			href = match.group(1)
			text = match.group(2)
			
			# Extract text content (remove HTML tags)
			text_content = re.sub(r'<[^>]+>', '', text).strip()
			
			# Resolve relative URLs
			resolved_url = self._resolve_url(href, base_url)
			
			# Skip invalid URLs (javascript:, mailto:, etc.)
			if not self._is_valid_url(resolved_url):
				continue
			
			# Extract attributes from the full tag
			full_tag = match.group(0)
			attributes = self._extract_attributes(full_tag)
			
			# Check if link is external
			is_external = self._is_external_link(resolved_url)
			
			links.append({
				"href": resolved_url,
				"text": text_content,
				"attributes": attributes,
				"internal": not is_external,
				"external": is_external,
			})
		
		return links
	
	def _extract_attributes(self, tag: str) -> dict[str, str]:
		"""Extract attributes from an HTML tag."""
		attributes = {}
		# Pattern to match attribute="value" or attribute='value'
		attr_pattern = re.compile(r'(\w+)\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)
		
		for match in attr_pattern.finditer(tag):
			key = match.group(1).lower()
			value = match.group(2)
			attributes[key] = value
		
		return attributes
	
	def _resolve_url(self, href: str, base_url: str) -> str:
		"""Resolve relative URL against base URL."""
		if not href:
			return ""
		
		# Use urljoin to resolve relative URLs
		resolved = urljoin(base_url, href)
		
		# Remove fragment (#)
		parsed = urlparse(resolved)
		resolved_no_fragment = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
		if parsed.query:
			resolved_no_fragment += f"?{parsed.query}"
		
		return resolved_no_fragment
	
	def _is_valid_url(self, url: str) -> bool:
		"""Check if URL is valid for exploration."""
		if not url:
			return False
		
		parsed = urlparse(url)
		
		# Skip non-http(s) URLs
		if parsed.scheme not in ('http', 'https'):
			return False
		
		# Skip data URLs, javascript:, mailto:, etc.
		if parsed.scheme in ('data', 'javascript', 'mailto', 'tel', 'ftp'):
			return False
		
		return True
	
	def _is_external_link(self, url: str) -> bool:
		"""
		Check if URL is external to the base domain.
		
		CRITICAL: External links should be detected but NOT followed.
		We only need to identify them, not explore beyond them.
		
		Args:
			url: URL to check
		
		Returns:
			True if URL is external to base domain, False if internal
		"""
		if not self.base_url:
			# If no base URL set, cannot determine if external
			return False
		
		try:
			url_parsed = urlparse(url)
			base_parsed = urlparse(self.base_url)
			
			# Compare netloc (domain) - normalize to lowercase
			url_domain = url_parsed.netloc.lower()
			base_domain = base_parsed.netloc.lower()
			
			# Remove port numbers for comparison
			url_domain = url_domain.split(':')[0]
			base_domain = base_domain.split(':')[0]
			
			# Check if domains match
			if url_domain == base_domain:
				return False  # Internal link
			
			# Check if URL is subdomain of base (e.g., www.example.com vs example.com)
			# This is still considered internal
			if url_domain.endswith('.' + base_domain) or base_domain.endswith('.' + url_domain):
				return False  # Subdomain, treat as internal
			
			# Different domain = external link
			return True
		except Exception as e:
			logger.warning(f"Error checking if URL is external: {url}: {e}")
			# On error, assume internal to be safe
			return False
	
	def track_visited(self, url: str) -> None:
		"""
		Track a URL as visited.
		
		Args:
			url: URL to mark as visited
		"""
		self.visited_urls.add(url)
		logger.debug(f"Tracked visited URL: {url[:80]}...")
	
	def is_visited(self, url: str) -> bool:
		"""
		Check if a URL has been visited.
		
		Args:
			url: URL to check
		
		Returns:
			True if URL has been visited, False otherwise
		"""
		return url in self.visited_urls
	
	def filter_unvisited(self, links: list[dict[str, Any]]) -> list[dict[str, Any]]:
		"""
		Filter out visited links.
		
		Args:
			links: List of link dictionaries
		
		Returns:
			Filtered list of unvisited links
		"""
		return [link for link in links if not self.is_visited(link["href"])]
	
	def filter_by_depth(self, links: list[dict[str, Any]], current_depth: int) -> list[dict[str, Any]]:
		"""
		Filter links by depth limit.
		
		Args:
			links: List of link dictionaries
			current_depth: Current exploration depth
		
		Returns:
			Filtered list of links within depth limit
		"""
		if current_depth >= self.max_depth:
			return []
		
		return links
	
	async def discover_forms(self, url: str) -> list[dict[str, Any]]:
		"""
		Discover forms on a single page.
		
		Args:
			url: URL of the page to discover forms from
		
		Returns:
			List of discovered forms with attributes and field information
		"""
		logger.debug(f"Discovering forms from {url}")
		
		try:
			# Navigate to URL if not already there
			current_url = await self.browser_session.get_current_page_url()
			if current_url != url:
				from browser_use.browser.events import NavigateToUrlEvent
				event = self.browser_session.event_bus.dispatch(NavigateToUrlEvent(url=url))
				await event
				await asyncio.sleep(0.5)  # Wait for page load
			
			# Get DOM and extract HTML
			from browser_use.dom.markdown_extractor import _get_enhanced_dom_tree_from_browser_session
			enhanced_dom_tree = await _get_enhanced_dom_tree_from_browser_session(self.browser_session)
			
			# Serialize to HTML
			html_serializer = HTMLSerializer(extract_links=True)
			page_html = html_serializer.serialize(enhanced_dom_tree)
			
			# Parse HTML and extract forms
			forms = self._extract_forms_from_html(page_html, url)
			
			logger.debug(f"Discovered {len(forms)} forms from {url}")
			return forms
		
		except Exception as e:
			logger.error(f"Error discovering forms from {url}: {e}", exc_info=True)
			return []
	
	def _extract_forms_from_html(self, html: str, base_url: str) -> list[dict[str, Any]]:
		"""
		Extract forms from HTML string.
		
		Args:
			html: HTML content
			base_url: Base URL for resolving relative form actions
		
		Returns:
			List of form dictionaries with 'action', 'method', 'fields', and attributes
		"""
		forms = []
		# Pattern to match <form> tags
		form_pattern = re.compile(
			r'<form\s+[^>]*>(.*?)</form>',
			re.IGNORECASE | re.DOTALL
		)
		
		for match in form_pattern.finditer(html):
			form_tag = match.group(0)
			form_content = match.group(1)
			
			# Extract form attributes
			attributes = self._extract_attributes(form_tag)
			
			# Extract action URL
			action = attributes.get('action', '')
			method = attributes.get('method', 'GET').upper()
			
			# Resolve relative action URLs
			if action:
				action_url = self._resolve_url(action, base_url)
			else:
				action_url = base_url
			
			# Extract form fields (input, select, textarea)
			fields = self._extract_form_fields(form_content)
			
			# Only include safe forms (GET method or read-only)
			# For POST forms, we'll skip them for now (Step 2.6 requirement)
			if method == 'GET' or self._is_read_only_form(fields):
				forms.append({
					"action": action_url,
					"method": method,
					"fields": fields,
					"attributes": attributes,
					"field_count": len(fields),
				})
		
		return forms
	
	def _extract_form_fields(self, form_content: str) -> list[dict[str, Any]]:
		"""
		Extract form fields from form content.
		
		Args:
			form_content: HTML content inside <form> tag
		
		Returns:
			List of field dictionaries with type, name, and attributes
		"""
		fields = []
		
		# Pattern to match input, select, textarea tags
		field_patterns = [
			(r'<input\s+[^>]*>', 'input'),
			(r'<select\s+[^>]*>.*?</select>', 'select'),
			(r'<textarea\s+[^>]*>.*?</textarea>', 'textarea'),
		]
		
		for pattern, field_type in field_patterns:
			field_tag_pattern = re.compile(pattern, re.IGNORECASE | re.DOTALL)
			for match in field_tag_pattern.finditer(form_content):
				field_tag = match.group(0)
				attributes = self._extract_attributes(field_tag)
				
				field_info = {
					"type": field_type,
					"attributes": attributes,
				}
				
				# Extract common field properties
				if 'type' in attributes:
					field_info['input_type'] = attributes['type']
				if 'name' in attributes:
					field_info['name'] = attributes['name']
				if 'id' in attributes:
					field_info['id'] = attributes['id']
				
				fields.append(field_info)
		
		return fields
	
	def _is_read_only_form(self, fields: list[dict[str, Any]]) -> bool:
		"""
		Check if form is read-only (no user input fields).
		
		Args:
			fields: List of form field dictionaries
		
		Returns:
			True if form appears to be read-only, False otherwise
		"""
		# Check if all fields are hidden, readonly, or disabled
		for field in fields:
			attrs = field.get('attributes', {})
			
			# Skip hidden, readonly, disabled fields
			if attrs.get('type') == 'hidden':
				continue
			if attrs.get('readonly') or attrs.get('disabled'):
				continue
			
			# If we find any editable field, form is not read-only
			return False
		
		# All fields are read-only
		return True
	
	async def explore(
		self,
		start_url: str,
		max_pages: int | None = None,
	) -> list[dict[str, Any]]:
		"""
		Explore a website starting from a URL.
		
		Args:
			start_url: Starting URL for exploration
			max_pages: Maximum number of pages to explore (None for unlimited)
		
		Returns:
			List of explored pages with URL, depth, and links
		"""
		logger.info(f"Starting exploration from {start_url} (strategy: {self.strategy.value}, max_depth: {self.max_depth})")
		
		# Initialize base URL
		if self.base_url is None:
			self.base_url = start_url
		
		# Reset exploration state
		self.explored_pages = []
		self.visited_urls.clear()
		self.url_depths.clear()
		
		# Track pages to explore based on strategy
		if self.strategy == ExplorationStrategy.BFS:
			# Use queue for BFS (level-by-level)
			to_explore_bfs: deque[tuple[str, int]] = deque([(start_url, 0)])
			to_explore_dfs: list[tuple[str, int]] = []  # Not used for BFS
		else:
			# Use stack for DFS (deep paths first)
			to_explore_bfs: deque[tuple[str, int]] = deque()  # Not used for DFS
			to_explore_dfs: list[tuple[str, int]] = [(start_url, 0)]
		
		# Exploration loop
		has_more = True
		while has_more:
			# Get next URL based on strategy
			if self.strategy == ExplorationStrategy.BFS:
				if not to_explore_bfs:
					break
				current_url, current_depth = to_explore_bfs.popleft()
			else:
				if not to_explore_dfs:
					break
				current_url, current_depth = to_explore_dfs.pop()
			
			# Check if already visited
			if self.is_visited(current_url):
				continue
			
			# Check depth limit
			if current_depth > self.max_depth:
				continue
			
			# Check max pages limit
			if max_pages is not None and len(self.explored_pages) >= max_pages:
				break
			
			# Explore page
			try:
				links = await self.discover_links(current_url)
				
				# Mark as visited
				self.track_visited(current_url)
				self.url_depths[current_url] = current_depth
				
				# Store explored page
				page_info = {
					"url": current_url,
					"depth": current_depth,
					"links": links,
					"link_count": len(links),
				}
				self.explored_pages.append(page_info)
				
				# Filter and add new URLs to explore
				# CRITICAL: Only follow internal links - external links are detected but NOT explored
				internal_links = [link for link in links if link.get("internal", True)]
				unvisited_links = self.filter_unvisited(internal_links)
				filtered_links = self.filter_by_depth(unvisited_links, current_depth)
				
				# Track external links for reporting (but don't explore them)
				external_links = [link for link in links if link.get("external", False)]
				if external_links:
					logger.debug(f"Found {len(external_links)} external links on {current_url[:80]}... (not following)")
				
				# Add to queue/stack (only internal links)
				next_depth = current_depth + 1
				for link in filtered_links:
					link_url = link["href"]
					if not self.is_visited(link_url):
						if self.strategy == ExplorationStrategy.BFS:
							to_explore_bfs.append((link_url, next_depth))
						else:
							to_explore_dfs.append((link_url, next_depth))
				
				logger.debug(f"Explored {current_url[:80]}... (depth: {current_depth}, links: {len(links)})")
			
			except Exception as e:
				logger.error(f"Error exploring {current_url}: {e}", exc_info=True)
				# Mark as visited even on error to avoid retrying
				self.track_visited(current_url)
		
		logger.info(f"Exploration complete: {len(self.explored_pages)} pages explored")
		return self.explored_pages

"""
Knowledge Pipeline for Knowledge Retrieval

Integrates exploration, analysis, and storage into a complete pipeline.
"""

import logging
import re
import time
from typing import Any
from urllib.parse import urlparse

from uuid_extensions import uuid7str

from browser_use import BrowserSession
from navigator.knowledge.exploration_engine import ExplorationEngine, ExplorationStrategy
from navigator.knowledge.progress_observer import (
	ExplorationProgress,
	LoggingProgressObserver,
	ProgressObserver,
)
from navigator.knowledge.semantic_analyzer import SemanticAnalyzer
from navigator.knowledge.storage import KnowledgeStorage
from navigator.knowledge.vector_store import VectorStore

logger = logging.getLogger(__name__)


class KnowledgePipeline:
	"""
	Knowledge pipeline that integrates exploration, analysis, and storage.
	
	Supports:
	- Complete pipeline: Explore → Analyze → Store
	- Integration with ExplorationEngine, SemanticAnalyzer, KnowledgeStorage, VectorStore
	- Batch processing of pages
	- Error handling and recovery
	"""
	
	def __init__(
		self,
		browser_session: BrowserSession,
		storage: KnowledgeStorage | None = None,
		vector_store: VectorStore | None = None,
		max_depth: int = 3,
		strategy: ExplorationStrategy = ExplorationStrategy.BFS,
		progress_observer: ProgressObserver | None = None,
		include_paths: list[str] | None = None,
		exclude_paths: list[str] | None = None,
	):
		"""
		Initialize the knowledge pipeline.
		
		Args:
			browser_session: Browser session for navigation
			storage: Knowledge storage instance (optional, creates default if None)
			vector_store: Vector store instance (optional, creates default if None)
			max_depth: Maximum exploration depth
			strategy: Exploration strategy (BFS or DFS)
			progress_observer: Progress observer for real-time updates (optional)
			include_paths: List of path patterns to include (e.g., ['/docs/*', '/api/v1/*'])
			exclude_paths: List of path patterns to exclude (e.g., ['/admin/*', '/api/*'])
		"""
		self.browser_session = browser_session
		self.storage = storage or KnowledgeStorage(use_arangodb=False)
		self.vector_store = vector_store or VectorStore(use_vector_db=False)
		
		# Initialize base_url from start_url when explore_and_store is called
		# For now, set it to None - it will be set when exploration starts
		self.exploration_engine = ExplorationEngine(
			browser_session=browser_session,
			max_depth=max_depth,
			strategy=strategy,
			base_url=None,  # Will be set from start_url in explore_and_store
		)
		self.semantic_analyzer = SemanticAnalyzer(browser_session=browser_session)
		
		# Progress observer for real-time updates
		# Default to logging observer if none provided
		if progress_observer is None:
			self.progress_observer = LoggingProgressObserver()
		else:
			self.progress_observer = progress_observer
		
		# Path restrictions
		self.include_paths = include_paths or []
		self.exclude_paths = exclude_paths or []
		
		# Job state tracking
		self.current_job_id: str | None = None
		self.job_status: str = "idle"  # 'idle', 'running', 'paused', 'completed', 'failed', 'cancelled'
		self.job_paused: bool = False
		
		# Enhanced progress tracking
		self.job_start_time: float | None = None
		self.page_processing_times: list[float] = []  # Track processing times for rate calculation
		self.recent_completed_pages: list[dict[str, Any]] = []  # Recent pages with titles
		self.max_recent_pages: int = 10  # Keep last 10 completed pages
		
		logger.debug("KnowledgePipeline initialized")
	
	async def process_url(self, url: str) -> dict[str, Any]:
		"""
		Process a single URL: extract content, analyze, and store.
		
		Args:
			url: URL to process
		
		Returns:
			Dictionary with processing results
		"""
		try:
			# Extract content
			content = await self.semantic_analyzer.extract_content(url)
			
			# Extract entities
			entities = self.semantic_analyzer.identify_entities(content.get('text', ''))
			
			# Extract topics
			topics = self.semantic_analyzer.extract_topics(content)
			
			# Generate embedding
			embedding = self.semantic_analyzer.generate_embedding(content.get('text', ''))
			
			# Store page
			page_data = {
				**content,
				'entities': entities,
				'topics': topics,
			}
			await self.storage.store_page(url, page_data)
			
			# Store embedding
			await self.vector_store.store_embedding(
				id=url,
				embedding=embedding,
				metadata={'url': url, 'title': content.get('title', '')},
			)
			
			logger.debug(f"Processed URL: {url}")
			
			return {
				'url': url,
				'success': True,
				'content': content,
				'entities': entities,
				'topics': topics,
			}
		except Exception as e:
			logger.error(f"Failed to process URL {url}: {e}")
			# Categorize error
			error_type = self._categorize_error(str(e), url)
			return {
				'url': url,
				'success': False,
				'error': str(e),
				'error_type': error_type,
			}
	
	def _categorize_error(self, error_msg: str, url: str) -> str:
		"""
		Categorize error type for better error handling.
		
		Args:
			error_msg: Error message
			url: URL that failed
		
		Returns:
			Error category: 'network', 'timeout', 'http_4xx', 'http_5xx', 'parsing', 'other'
		"""
		error_lower = error_msg.lower()
		
		# Network errors
		if any(keyword in error_lower for keyword in ['connection', 'network', 'dns', 'resolve', 'refused']):
			return 'network'
		
		# Timeout errors
		if any(keyword in error_lower for keyword in ['timeout', 'timed out', 'exceeded']):
			return 'timeout'
		
		# HTTP 4xx errors
		if any(keyword in error_lower for keyword in ['404', '403', '401', '400', 'not found', 'forbidden', 'unauthorized']):
			return 'http_4xx'
		
		# HTTP 5xx errors
		if any(keyword in error_lower for keyword in ['500', '502', '503', '504', 'server error', 'bad gateway', 'service unavailable']):
			return 'http_5xx'
		
		# Parsing errors
		if any(keyword in error_lower for keyword in ['parse', 'parsing', 'invalid', 'malformed', 'syntax']):
			return 'parsing'
		
		# Default to 'other'
		return 'other'
	
	async def explore_and_store(
		self,
		start_url: str,
		max_pages: int | None = None,
		job_id: str | None = None,
	) -> dict[str, Any]:
		"""
		Explore website and store all discovered pages.
		
		Args:
			start_url: Starting URL for exploration
			max_pages: Maximum number of pages to process (None for no limit)
			job_id: Optional job ID for tracking (auto-generated if None)
		
		Returns:
			Dictionary with exploration and storage results
		"""
		# Generate job ID if not provided
		if job_id is None:
			job_id = uuid7str()
		
		self.current_job_id = job_id
		self.job_status = "running"
		self.job_paused = False
		
		# Reset enhanced tracking
		self.job_start_time = time.time()
		self.page_processing_times = []
		self.recent_completed_pages = []
		
		results = {
			'job_id': job_id,
			'start_url': start_url,
			'pages_processed': 0,
			'pages_stored': 0,
			'pages_failed': 0,
			'external_links_detected': 0,
			'errors': [],
			'results': [],
			'website_metadata': {},  # Will be populated from start page
		}
		
		try:
			# Extract website metadata from start page
			try:
				start_content = await self.semantic_analyzer.extract_content(start_url)
				results['website_metadata'] = {
					'title': start_content.get('title', ''),
					'description': start_content.get('description', ''),
					'url': start_url,
				}
			except Exception as e:
				logger.warning(f"Failed to extract website metadata: {e}")
				results['website_metadata'] = {'url': start_url}
			
			# Emit initial progress
			await self.progress_observer.on_progress(ExplorationProgress(
				job_id=job_id,
				status="running",
				current_page=start_url,
				pages_completed=0,
				pages_queued=1,
				pages_failed=0,
			))
			
			# Set base URL for external link detection
			# CRITICAL: This ensures external links are detected and NOT followed
			self.exploration_engine.base_url = start_url
			
			# Discover links from start URL
			links = await self.exploration_engine.discover_links(start_url)
			
			# Collect URLs to process (start with start_url, then discovered links)
			urls_to_process = [start_url]
			processed_urls = set()
			
			# Add discovered links (only internal links for exploration)
			external_count = 0
			for link in links:
				link_url = link.get('href', '') or link.get('url', '')
				is_internal = link.get('internal', True)  # Default to True if not specified
				
				# Store all links (internal and external) for graph representation
				try:
					await self.storage.store_link(start_url, link_url, {
						'anchor_text': link.get('text', ''),
						'link_type': 'internal' if is_internal else 'external',
					})
				except Exception as e:
					logger.error(f"Failed to store link {start_url} -> {link_url}: {e}")
				
				# Only add internal links to exploration queue
				# CRITICAL: External links are detected and stored, but NOT explored
				if is_internal and link_url and link_url not in processed_urls:
					# Apply path filtering
					if self._should_explore_url(link_url):
						urls_to_process.append(link_url)
					else:
						logger.debug(f"Skipping URL due to path restrictions: {link_url}")
				elif not is_internal:
					external_count += 1
					results['external_links_detected'] += 1
					await self.progress_observer.on_external_link_detected(start_url, link_url)
					logger.debug(f"Skipping external link: {link_url} (detected but not exploring)")
			
			# Limit to max_pages if specified
			if max_pages:
				urls_to_process = urls_to_process[:max_pages]
	
	def _should_explore_url(self, url: str) -> bool:
		"""
		Check if URL should be explored based on include/exclude path patterns.
		
		Args:
			url: URL to check
		
		Returns:
			True if URL should be explored, False otherwise
		"""
		parsed = urlparse(url)
		path = parsed.path
		
		# If include_paths specified, URL must match at least one pattern
		if self.include_paths:
			matches_include = False
			for pattern in self.include_paths:
				if self._match_path_pattern(path, pattern):
					matches_include = True
					break
			if not matches_include:
				return False
		
		# If exclude_paths specified, URL must not match any pattern
		if self.exclude_paths:
			for pattern in self.exclude_paths:
				if self._match_path_pattern(path, pattern):
					return False
		
		return True
	
	def _match_path_pattern(self, path: str, pattern: str) -> bool:
		"""
		Match path against pattern (supports * wildcard).
		
		Args:
			path: URL path to match
			pattern: Pattern with * wildcard support (e.g., '/docs/*', '/api/v1/*')
		
		Returns:
			True if path matches pattern
		"""
		# Convert pattern to regex
		pattern_regex = pattern.replace('*', '.*')
		return bool(re.match(pattern_regex, path))
			
			# Process each URL
			for url in urls_to_process:
				# Check for pause
				if self.job_paused:
					self.job_status = "paused"
					await self.progress_observer.on_progress(ExplorationProgress(
						job_id=job_id,
						status="paused",
						current_page=url,
						pages_completed=results['pages_stored'],
						pages_queued=len(urls_to_process) - results['pages_processed'],
						pages_failed=results['pages_failed'],
						links_discovered=len(links),
						external_links_detected=results['external_links_detected'],
					))
					# Wait until resumed
					while self.job_paused:
						import asyncio
						await asyncio.sleep(0.5)
					self.job_status = "running"
				
				if url in processed_urls:
					continue
				processed_urls.add(url)
				
				# Check for cancellation
				if self.job_status == "cancelled":
					logger.info(f"Job {job_id} cancelled, stopping exploration")
					break
				elif self.job_status == "cancelling":
					# Process current page, then cancel
					logger.info(f"Job {job_id} cancelling after current page")
				
				# Track processing time
				page_start_time = time.time()
				
				# Calculate enhanced metrics
				estimated_time = self._calculate_estimated_time_remaining(
					pages_completed=results['pages_stored'],
					pages_queued=len(urls_to_process) - results['pages_processed'],
					processing_times=self.page_processing_times,
				)
				processing_rate = self._calculate_processing_rate(self.page_processing_times)
				
				# Emit progress before processing
				await self.progress_observer.on_progress(ExplorationProgress(
					job_id=job_id,
					status="running",
					current_page=url,
					pages_completed=results['pages_stored'],
					pages_queued=len(urls_to_process) - results['pages_processed'],
					pages_failed=results['pages_failed'],
					links_discovered=len(links),
					external_links_detected=results['external_links_detected'],
					estimated_time_remaining=estimated_time,
					processing_rate=processing_rate,
					recent_pages=self.recent_completed_pages.copy(),
				))
				
				# Process page
				process_result = await self.process_url(url)
				process_result['job_id'] = job_id
				results['results'].append(process_result)
				results['pages_processed'] += 1
				
				# Track processing time
				page_processing_time = time.time() - page_start_time
				self.page_processing_times.append(page_processing_time)
				# Keep only last 20 processing times for rate calculation
				if len(self.page_processing_times) > 20:
					self.page_processing_times = self.page_processing_times[-20:]
				
				if process_result.get('success'):
					results['pages_stored'] += 1
					
					# Track recent completed pages with titles
					page_title = process_result.get('content', {}).get('title', url)
					self.recent_completed_pages.append({
						'url': url,
						'title': page_title,
						'completed_at': time.time(),
					})
					# Keep only last N pages
					if len(self.recent_completed_pages) > self.max_recent_pages:
						self.recent_completed_pages = self.recent_completed_pages[-self.max_recent_pages:]
					
					await self.progress_observer.on_page_completed(url, process_result)
					
					# Discover and store links from this page
					try:
						page_links = await self.exploration_engine.discover_links(url)
						for link in page_links:
							link_url = link.get('href', '') or link.get('url', '')
							is_internal = link.get('internal', True)
							
							if link_url:
								# Store all links (internal and external) for graph representation
								try:
									await self.storage.store_link(url, link_url, {
										'anchor_text': link.get('text', ''),
										'link_type': 'internal' if is_internal else 'external',
									})
								except Exception as e:
									logger.error(f"Failed to store link {url} -> {link_url}: {e}")
								
								# CRITICAL: External links are detected and stored, but NOT added to exploration queue
								if not is_internal:
									results['external_links_detected'] += 1
									await self.progress_observer.on_external_link_detected(url, link_url)
									logger.debug(f"External link detected: {url} -> {link_url} (stored but not exploring)")
								elif link_url not in processed_urls and link_url not in urls_to_process:
									# Apply path filtering before adding to queue
									if self._should_explore_url(link_url):
										urls_to_process.append(link_url)
									else:
										logger.debug(f"Skipping URL due to path restrictions: {link_url}")
					except Exception as e:
						logger.error(f"Failed to discover links from {url}: {e}")
						await self.progress_observer.on_error(url, str(e))
				else:
					results['pages_failed'] += 1
					results['errors'].append(process_result)
					error_msg = process_result.get('error', 'Unknown error')
					await self.progress_observer.on_error(url, error_msg)
				
				# Check if cancelling after current page
				if self.job_status == "cancelling":
					self.job_status = "cancelled"
					logger.info(f"Job {job_id} cancelled after processing current page")
					break
			
			# Mark as completed (unless cancelled)
			if self.job_status != "cancelled":
				self.job_status = "completed"
			await self.progress_observer.on_progress(ExplorationProgress(
				job_id=job_id,
				status="completed",
				current_page=None,
				pages_completed=results['pages_stored'],
				pages_queued=0,
				pages_failed=results['pages_failed'],
				links_discovered=len(links),
				external_links_detected=results['external_links_detected'],
			))
			
			logger.info(f"Exploration complete: {results['pages_stored']}/{results['pages_processed']} pages stored")
		except Exception as e:
			logger.error(f"Failed to explore and store: {e}")
			self.job_status = "failed"
			results['error'] = str(e)
			await self.progress_observer.on_progress(ExplorationProgress(
				job_id=job_id,
				status="failed",
				current_page=None,
				pages_completed=results.get('pages_stored', 0),
				pages_queued=0,
				pages_failed=results.get('pages_failed', 0),
				error=str(e),
			))
		finally:
			self.current_job_id = None
		
		return results
	
	def pause_job(self) -> bool:
		"""
		Pause the current exploration job.
		
		Returns:
			True if job was paused, False if no job running
		"""
		if self.job_status == "running":
			self.job_paused = True
			return True
		return False
	
	def resume_job(self) -> bool:
		"""
		Resume the paused exploration job.
		
		Returns:
			True if job was resumed, False if no job paused
		"""
		if self.job_status == "paused" and self.job_paused:
			self.job_paused = False
			return True
		return False
	
	def cancel_job(self, wait_for_current_page: bool = False) -> bool:
		"""
		Cancel the current exploration job.
		
		Args:
			wait_for_current_page: If True, wait for current page to complete before cancelling
		
		Returns:
			True if job was cancelled, False if no job running
		"""
		if self.job_status in ("running", "paused"):
			if wait_for_current_page:
				# Set flag to cancel after current page completes
				self.job_status = "cancelling"
			else:
				# Cancel immediately
				self.job_status = "cancelled"
				self.job_paused = False
			return True
		return False
	
	def get_job_status(self) -> dict[str, Any]:
		"""
		Get current job status.
		
		Returns:
			Dictionary with job status information
		"""
		return {
			'job_id': self.current_job_id,
			'status': self.job_status,
			'paused': self.job_paused,
		}
	
	def _calculate_estimated_time_remaining(
		self,
		pages_completed: int,
		pages_queued: int,
		processing_times: list[float],
	) -> float | None:
		"""
		Calculate estimated time remaining based on average processing time.
		
		Args:
			pages_completed: Number of pages completed
			pages_queued: Number of pages remaining
			processing_times: List of page processing times in seconds
		
		Returns:
			Estimated time remaining in seconds, or None if cannot calculate
		"""
		if not processing_times or pages_queued == 0:
			return None
		
		# Calculate average processing time
		avg_time = sum(processing_times) / len(processing_times)
		
		# Estimate remaining time
		estimated = avg_time * pages_queued
		return estimated
	
	def _calculate_processing_rate(self, processing_times: list[float]) -> float | None:
		"""
		Calculate processing rate (pages per minute).
		
		Args:
			processing_times: List of page processing times in seconds
		
		Returns:
			Processing rate in pages per minute, or None if cannot calculate
		"""
		if not processing_times:
			return None
		
		# Calculate average processing time per page
		avg_time = sum(processing_times) / len(processing_times)
		
		if avg_time == 0:
			return None
		
		# Convert to pages per minute
		pages_per_minute = 60.0 / avg_time
		return pages_per_minute
	
	async def search_similar(self, query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
		"""
		Search for similar pages using semantic search.
		
		Args:
			query_text: Query text
			top_k: Number of results to return
		
		Returns:
			List of similar pages with scores
		"""
		try:
			# Generate query embedding
			query_embedding = self.semantic_analyzer.generate_embedding(query_text)
			
			# Search for similar embeddings
			similar_results = await self.vector_store.search_similar(query_embedding, top_k=top_k)
			
			# Enrich results with page data
			enriched_results = []
			for result in similar_results:
				url = result.get('id') or result.get('metadata', {}).get('url', '')
				if url:
					page_data = await self.storage.get_page(url)
					if page_data:
						enriched_results.append({
							'url': url,
							'score': result.get('score', 0.0),
							'page_data': page_data,
						})
			
			return enriched_results
		except Exception as e:
			logger.error(f"Failed to search similar: {e}")
			return []

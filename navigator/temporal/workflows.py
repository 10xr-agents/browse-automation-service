"""
Temporal workflows for knowledge extraction.

Workflows orchestrate activities and maintain state across long-running processes.
They are durable, versioned, and can be paused/resumed/cancelled.
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activities
with workflow.unsafe.imports_passed_through():
	from navigator.temporal.activities import (
		LinkDiscoveryInput,
		LinkDiscoveryResult,
		PageProcessingInput,
		PageProcessingResult,
		discover_links_activity,
		process_page_activity,
		store_link_activity,
	)

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeExtractionInput:
	"""Input for knowledge extraction workflow."""
	
	# Required parameters
	job_id: str
	start_url: str
	
	# Optional parameters
	max_pages: int | None = None
	max_depth: int = 3
	strategy: str = "BFS"  # "BFS" or "DFS"
	include_paths: list[str] = field(default_factory=list)
	exclude_paths: list[str] = field(default_factory=list)


@dataclass
class KnowledgeExtractionProgress:
	"""Progress state for knowledge extraction workflow."""
	
	pages_processed: int = 0
	pages_completed: int = 0
	pages_failed: int = 0
	links_discovered: int = 0
	external_links_detected: int = 0
	current_page: str | None = None
	errors: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class KnowledgeExtractionResult:
	"""Result of knowledge extraction workflow."""
	
	job_id: str
	status: str  # 'completed', 'failed', 'cancelled'
	pages_processed: int
	pages_completed: int
	pages_failed: int
	links_discovered: int
	external_links_detected: int
	errors: list[dict[str, Any]]
	processing_time: float
	error: str | None = None


@workflow.defn(name="knowledge-extraction-workflow")
class KnowledgeExtractionWorkflow:
	"""
	Durable workflow for knowledge extraction.
	
	Features:
	- BFS/DFS exploration strategies
	- Pause/resume support via signals
	- Cancellation support
	- Progress tracking via queries
	- Error handling and retry logic
	- Path filtering (include/exclude patterns)
	"""
	
	def __init__(self):
		# Workflow state
		self._paused = False
		self._cancelled = False
		
		# Progress tracking
		self._progress = KnowledgeExtractionProgress()
		
		# Visited URLs (for deduplication)
		self._visited_urls: set[str] = set()
		
		# Exploration queue (URL, depth)
		self._queue: deque[tuple[str, int]] = deque()
		
		# Start time (for duration tracking)
		self._start_time: float = 0.0
	
	@workflow.run
	async def run(self, input: KnowledgeExtractionInput) -> KnowledgeExtractionResult:
		"""
		Main workflow entry point.
		
		Args:
			input: Workflow input parameters
		
		Returns:
			Workflow result with statistics
		"""
		workflow.logger.info(f"🚀 Starting knowledge extraction workflow: {input.job_id}")
		workflow.logger.info(f"   Start URL: {input.start_url}")
		workflow.logger.info(f"   Max pages: {input.max_pages}, Max depth: {input.max_depth}")
		workflow.logger.info(f"   Strategy: {input.strategy}")
		
		self._start_time = workflow.now().timestamp()
		
		# Initialize queue with start URL
		self._queue.append((input.start_url, 0))
		self._visited_urls.add(input.start_url)
		
		# Activity retry policy
		retry_policy = RetryPolicy(
			initial_interval=timedelta(seconds=1),
			maximum_interval=timedelta(seconds=30),
			backoff_coefficient=2.0,
			maximum_attempts=3,
		)
		
		try:
			# Main exploration loop
			while self._queue and not self._cancelled:
				# Check if paused
				if self._paused:
					workflow.logger.info("⏸️  Workflow paused, waiting for resume...")
					await workflow.wait_condition(lambda: not self._paused or self._cancelled)
					if self._cancelled:
						break
					workflow.logger.info("▶️  Workflow resumed")
				
				# Check max pages limit
				if input.max_pages and self._progress.pages_processed >= input.max_pages:
					workflow.logger.info(f"🛑 Max pages limit reached: {input.max_pages}")
					break
				
				# Get next URL based on strategy
				if input.strategy == "BFS":
					url, depth = self._queue.popleft()  # FIFO for BFS
				else:  # DFS
					url, depth = self._queue.pop()  # LIFO for DFS
				
				# Check depth limit
				if depth > input.max_depth:
					workflow.logger.info(f"⏭️  Skipping {url} (depth {depth} > max {input.max_depth})")
					continue
				
				# Check path filters
				if not self._should_process_url(url, input.include_paths, input.exclude_paths):
					workflow.logger.info(f"⏭️  Skipping {url} (filtered by path patterns)")
					continue
				
				self._progress.current_page = url
				self._progress.pages_processed += 1
				
				workflow.logger.info(
					f"📄 Processing page {self._progress.pages_processed}: {url} (depth: {depth})"
				)
				
				# Step 1: Process page content (Activity)
				page_result = await workflow.execute_activity(
					process_page_activity,
					PageProcessingInput(url=url, job_id=input.job_id, depth=depth),
					start_to_close_timeout=timedelta(minutes=5),
					retry_policy=retry_policy,
				)
				
				if page_result.success:
					self._progress.pages_completed += 1
					workflow.logger.info(f"✅ Page processed successfully: {url}")
				else:
					self._progress.pages_failed += 1
					self._progress.errors.append({
						'url': url,
						'error': page_result.error,
						'error_type': page_result.error_type,
						'depth': depth,
					})
					workflow.logger.error(f"❌ Page processing failed: {url} - {page_result.error}")
				
				# Step 2: Discover links (Activity)
				link_result = await workflow.execute_activity(
					discover_links_activity,
					LinkDiscoveryInput(
						url=url,
						job_id=input.job_id,
						depth=depth,
						base_url=input.start_url,
					),
					start_to_close_timeout=timedelta(minutes=3),
					retry_policy=retry_policy,
				)
				
				if link_result.success:
					# Process discovered links
					new_links_count = 0
					
					# Add internal links to queue
					for link_url in link_result.internal_links:
						if link_url not in self._visited_urls:
							self._visited_urls.add(link_url)
							self._queue.append((link_url, depth + 1))
							new_links_count += 1
							
							# Store link relationship (Activity)
							await workflow.execute_activity(
								store_link_activity,
								args=[url, link_url, "internal", {"depth": depth + 1}],
								start_to_close_timeout=timedelta(seconds=30),
								retry_policy=retry_policy,
							)
					
					# Track external links (don't add to queue)
					for ext_link in link_result.external_links:
						self._progress.external_links_detected += 1
						
						# Store external link (Activity)
						await workflow.execute_activity(
							store_link_activity,
							args=[url, ext_link, "external", {"detected": True}],
							start_to_close_timeout=timedelta(seconds=30),
							retry_policy=retry_policy,
						)
					
					self._progress.links_discovered += new_links_count
					
					workflow.logger.info(
						f"🔗 Discovered {len(link_result.links)} links "
						f"({new_links_count} new internal, {len(link_result.external_links)} external)"
					)
				else:
					workflow.logger.error(f"❌ Link discovery failed: {url} - {link_result.error}")
				
				# Log progress
				workflow.logger.info(
					f"📊 Progress: {self._progress.pages_completed} completed, "
					f"{self._progress.pages_failed} failed, "
					f"{len(self._queue)} queued, "
					f"{self._progress.external_links_detected} external links"
				)
			
			# Determine final status
			if self._cancelled:
				status = "cancelled"
				workflow.logger.info("🚫 Workflow cancelled")
			elif self._progress.pages_failed > 0 and self._progress.pages_completed == 0:
				status = "failed"
				workflow.logger.error("❌ Workflow failed: all pages failed")
			else:
				status = "completed"
				workflow.logger.info("✅ Workflow completed successfully")
			
			processing_time = workflow.now().timestamp() - self._start_time
			
			return KnowledgeExtractionResult(
				job_id=input.job_id,
				status=status,
				pages_processed=self._progress.pages_processed,
				pages_completed=self._progress.pages_completed,
				pages_failed=self._progress.pages_failed,
				links_discovered=self._progress.links_discovered,
				external_links_detected=self._progress.external_links_detected,
				errors=self._progress.errors,
				processing_time=processing_time,
			)
		
		except Exception as e:
			workflow.logger.error(f"❌ Workflow failed with error: {e}", exc_info=True)
			
			processing_time = workflow.now().timestamp() - self._start_time
			
			return KnowledgeExtractionResult(
				job_id=input.job_id,
				status="failed",
				pages_processed=self._progress.pages_processed,
				pages_completed=self._progress.pages_completed,
				pages_failed=self._progress.pages_failed,
				links_discovered=self._progress.links_discovered,
				external_links_detected=self._progress.external_links_detected,
				errors=self._progress.errors,
				processing_time=processing_time,
				error=str(e),
			)
	
	@workflow.signal
	def pause(self):
		"""Signal: Pause the workflow."""
		workflow.logger.info("📥 Received pause signal")
		self._paused = True
	
	@workflow.signal
	def resume(self):
		"""Signal: Resume the workflow."""
		workflow.logger.info("📥 Received resume signal")
		self._paused = False
	
	@workflow.signal
	def cancel(self):
		"""Signal: Cancel the workflow."""
		workflow.logger.info("📥 Received cancel signal")
		self._cancelled = True
	
	@workflow.query
	def get_progress(self) -> dict[str, Any]:
		"""Query: Get current progress."""
		return {
			'pages_processed': self._progress.pages_processed,
			'pages_completed': self._progress.pages_completed,
			'pages_failed': self._progress.pages_failed,
			'pages_queued': len(self._queue),
			'links_discovered': self._progress.links_discovered,
			'external_links_detected': self._progress.external_links_detected,
			'current_page': self._progress.current_page,
			'paused': self._paused,
			'cancelled': self._cancelled,
		}
	
	@workflow.query
	def is_paused(self) -> bool:
		"""Query: Check if workflow is paused."""
		return self._paused
	
	@workflow.query
	def is_cancelled(self) -> bool:
		"""Query: Check if workflow is cancelled."""
		return self._cancelled
	
	def _should_process_url(
		self,
		url: str,
		include_paths: list[str],
		exclude_paths: list[str],
	) -> bool:
		"""
		Check if URL should be processed based on path filters.
		
		Args:
			url: URL to check
			include_paths: Path patterns to include
			exclude_paths: Path patterns to exclude
		
		Returns:
			True if URL should be processed, False otherwise
		"""
		from urllib.parse import urlparse
		import re
		
		parsed = urlparse(url)
		path = parsed.path
		
		# Check exclude patterns first
		for pattern in exclude_paths:
			if self._match_pattern(path, pattern):
				return False
		
		# If include patterns specified, check them
		if include_paths:
			for pattern in include_paths:
				if self._match_pattern(path, pattern):
					return True
			return False
		
		# No include patterns, allow by default (unless excluded)
		return True
	
	def _match_pattern(self, path: str, pattern: str) -> bool:
		"""
		Match path against pattern (supports wildcards).
		
		Args:
			path: URL path
			pattern: Pattern with wildcards (e.g., '/docs/*', '/api/v1/*')
		
		Returns:
			True if path matches pattern
		"""
		import re
		
		# Convert pattern to regex
		regex_pattern = pattern.replace('*', '.*').replace('?', '.')
		regex_pattern = f'^{regex_pattern}$'
		
		return bool(re.match(regex_pattern, path))

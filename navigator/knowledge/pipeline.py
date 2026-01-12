"""
Knowledge Pipeline for Knowledge Retrieval

Integrates exploration, analysis, and storage into a complete pipeline.
"""

import logging
from typing import Any

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
		
		# Job state tracking
		self.current_job_id: str | None = None
		self.job_status: str = "idle"  # 'idle', 'running', 'paused', 'completed', 'failed', 'cancelled'
		self.job_paused: bool = False
		
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
			return {
				'url': url,
				'success': False,
				'error': str(e),
			}
	
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
		
		results = {
			'job_id': job_id,
			'start_url': start_url,
			'pages_processed': 0,
			'pages_stored': 0,
			'pages_failed': 0,
			'external_links_detected': 0,
			'errors': [],
			'results': [],
		}
		
		try:
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
					urls_to_process.append(link_url)
				elif not is_internal:
					external_count += 1
					results['external_links_detected'] += 1
					await self.progress_observer.on_external_link_detected(start_url, link_url)
					logger.debug(f"Skipping external link: {link_url} (detected but not exploring)")
			
			# Limit to max_pages if specified
			if max_pages:
				urls_to_process = urls_to_process[:max_pages]
			
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
				))
				
				# Process page
				process_result = await self.process_url(url)
				process_result['job_id'] = job_id
				results['results'].append(process_result)
				results['pages_processed'] += 1
				
				if process_result.get('success'):
					results['pages_stored'] += 1
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
									# Add new internal link to queue
									urls_to_process.append(link_url)
					except Exception as e:
						logger.error(f"Failed to discover links from {url}: {e}")
						await self.progress_observer.on_error(url, str(e))
				else:
					results['pages_failed'] += 1
					results['errors'].append(process_result)
					error_msg = process_result.get('error', 'Unknown error')
					await self.progress_observer.on_error(url, error_msg)
			
			# Mark as completed
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
	
	def cancel_job(self) -> bool:
		"""
		Cancel the current exploration job.
		
		Returns:
			True if job was cancelled, False if no job running
		"""
		if self.job_status in ("running", "paused"):
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

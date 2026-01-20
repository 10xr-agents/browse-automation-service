"""
Knowledge Pipeline for Knowledge Retrieval

Integrates exploration, analysis, and storage into a complete pipeline.
"""

import logging
import time
from typing import Any

from uuid_extensions import uuid7str

from browser_use import BrowserSession
from navigator.knowledge.exploration_engine import ExplorationEngine, ExplorationStrategy
from navigator.knowledge.pipeline_exploration import process_exploration_loop
from navigator.knowledge.pipeline_helpers import categorize_error
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
		self.storage = storage or KnowledgeStorage(use_mongodb=True)
		self.vector_store = vector_store or VectorStore(use_mongodb=True)

		# Initialize base_url from start_url when explore_and_store is called
		self.exploration_engine = ExplorationEngine(
			browser_session=browser_session,
			max_depth=max_depth,
			strategy=strategy,
			base_url=None,  # Will be set from start_url in explore_and_store
		)
		self.semantic_analyzer = SemanticAnalyzer(browser_session=browser_session)

		# Progress observer for real-time updates
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
		self.page_processing_times: list[float] = []
		self.recent_completed_pages: list[dict[str, Any]] = []
		self.max_recent_pages: int = 10

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
			logger.debug(f"      📥 Extracting content from: {url}")
			# Extract content
			content = await self.semantic_analyzer.extract_content(url)
			logger.debug(f"      📊 Content extracted: {len(content.get('paragraphs', []))} paragraphs, {len(content.get('headings', []))} headings")

			# Extract entities
			logger.debug("      🏷️  Identifying entities...")
			entities = self.semantic_analyzer.identify_entities(content.get('text', ''))
			logger.debug(f"      ✅ Found {len(entities)} entities")

			# Extract topics
			logger.debug("      📑 Extracting topics...")
			topics = self.semantic_analyzer.extract_topics(content)
			logger.debug(f"      ✅ Found {len(topics)} topics")

			# Generate embedding
			logger.debug("      🔢 Generating embedding...")
			embedding = self.semantic_analyzer.generate_embedding(content.get('text', ''))
			logger.debug(f"      ✅ Embedding generated (size: {len(embedding)})")

			# Store page
			logger.debug(f"      💾 Storing page: {url}")
			page_data = {
				**content,
				'entities': entities,
				'topics': topics,
			}
			await self.storage.store_page(url, page_data)
			logger.debug("      ✅ Page stored successfully")

			# Store embedding
			logger.debug("      💾 Storing embedding...")
			await self.vector_store.store_embedding(
				id=url,
				embedding=embedding,
				metadata={'url': url, 'title': content.get('title', '')},
			)
			logger.debug("      ✅ Embedding stored")

			return {
				'url': url,
				'success': True,
				'content': content,
				'entities': entities,
				'topics': topics,
			}
		except Exception as e:
			# Categorize error
			error_type = categorize_error(str(e), url)
			logger.debug(f"      ❌ Processing failed ({error_type}): {str(e)}")
			return {
				'url': url,
				'success': False,
				'error': str(e),
				'error_type': error_type,
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

		# Reset enhanced tracking
		self.job_start_time = time.time()
		self.page_processing_times = []
		self.recent_completed_pages = []

		logger.info(f"🔍 [Job {job_id}] Starting exploration from: {start_url}")
		logger.info(f"   Max pages: {max_pages or 'unlimited'}, Max depth: {self.exploration_engine.max_depth}")
		logger.info(f"   Strategy: {self.exploration_engine.strategy.value}")
		if self.include_paths:
			logger.info(f"   Include paths: {self.include_paths}")
		if self.exclude_paths:
			logger.info(f"   Exclude paths: {self.exclude_paths}")

		results = {
			'job_id': job_id,
			'start_url': start_url,
			'pages_processed': 0,
			'pages_stored': 0,
			'pages_failed': 0,
			'external_links_detected': 0,
			'errors': [],
			'results': [],
			'website_metadata': {},
		}

		try:
			# Process exploration loop (delegated to helper module)
			await process_exploration_loop(self, start_url, max_pages, job_id, results)

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
				links_discovered=0,
				external_links_detected=results['external_links_detected'],
			))

			total_time = time.time() - self.job_start_time if self.job_start_time else 0
			logger.info("=" * 80)
			logger.info(f"🏁 [Job {job_id}] Exploration complete")
			logger.info(f"   Pages stored: {results['pages_stored']}/{results['pages_processed']}")
			logger.info(f"   Pages failed: {results['pages_failed']}")
			logger.info(f"   External links detected: {results['external_links_detected']}")
			logger.info(f"   Total time: {total_time:.2f}s")
			if self.page_processing_times:
				avg_time = sum(self.page_processing_times) / len(self.page_processing_times)
				logger.info(f"   Avg page time: {avg_time:.2f}s")
			logger.info("=" * 80)
		except Exception as e:
			logger.error("=" * 80)
			logger.error(f"❌ [Job {job_id}] Exploration failed: {e}")
			logger.error(f"   Error type: {type(e).__name__}")
			logger.error("=" * 80, exc_info=True)
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
		"""Pause the current exploration job."""
		if self.job_status == "running":
			self.job_paused = True
			return True
		return False

	def resume_job(self) -> bool:
		"""Resume the paused exploration job."""
		if self.job_status == "paused" and self.job_paused:
			self.job_paused = False
			return True
		return False

	def cancel_job(self, wait_for_current_page: bool = False) -> bool:
		"""Cancel the current exploration job."""
		if self.job_status in ("running", "paused"):
			if wait_for_current_page:
				self.job_status = "cancelling"
			else:
				self.job_status = "cancelled"
				self.job_paused = False
			return True
		return False

	def get_job_status(self) -> dict[str, Any]:
		"""Get current job status."""
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
	
	async def fill_action_gaps(
		self,
		knowledge_id: str,
		website_id: str
	) -> dict[str, Any]:
		"""
		Identify and fill gaps in action sequences using LLM extrapolation (Phase 5).
		
		This method:
		1. Analyzes all known actions and transitions
		2. Identifies gaps (actions that should be connected but aren't)
		3. Uses Gemini LLM to infer missing actions
		4. Validates and stores inferred actions
		
		Args:
			knowledge_id: Knowledge ID to analyze
			website_id: Website ID for context
		
		Returns:
			ExtrapolationResult dictionary
		"""
		try:
			from navigator.knowledge.extrapolation import (
				ActionExtrapolationService,
				ActionGap,
				ExtrapolationRequest,
			)
			from navigator.knowledge.persist.documents.actions import (
				query_actions_by_knowledge_id,
			)
			from navigator.knowledge.persist.documents import (
				query_transitions_by_knowledge_id,
			)
			
			# Get all actions and transitions for this knowledge
			actions = await query_actions_by_knowledge_id(knowledge_id, limit=1000)
			transitions = await query_transitions_by_knowledge_id(knowledge_id, limit=1000)
			
			# Identify gaps
			gaps = self._identify_action_gaps(actions, transitions)
			
			if not gaps:
				logger.info("No action gaps found")
				return {
					"gaps_filled": 0,
					"inferred_actions": [],
					"inferred_transitions": [],
					"confidence_scores": {},
					"errors": []
				}
			
			logger.info(f"Found {len(gaps)} action gaps, extrapolating with LLM...")
			
			# Create extrapolation service
			extrapolation_service = ActionExtrapolationService()
			
			# Extrapolate
			request = ExtrapolationRequest(
				gaps=gaps,
				knowledge_id=knowledge_id,
				website_id=website_id,
				include_screens=True,
				max_intermediate_steps=5
			)
			
			result = await extrapolation_service.extrapolate_actions(request)
			
			# Store inferred actions (with lower confidence flag)
			from navigator.knowledge.persist.documents.actions import save_action
			from navigator.knowledge.extract.actions import ActionDefinition
			
			stored_count = 0
			for inferred_action in result.inferred_actions:
				if inferred_action.confidence > 0.6:  # Only store high-confidence inferences
					try:
						# Create ActionDefinition from inferred action
						action_def = ActionDefinition(
							action_id=f"inferred_{inferred_action.action_type}_{hash(inferred_action.target) % 10000}",
							name=inferred_action.description,
							website_id=website_id,
							action_type=inferred_action.action_type,
							target_selector=inferred_action.target,
							parameters={},
							metadata={
								'inferred': True,
								'confidence': inferred_action.confidence,
								'reasoning': inferred_action.reasoning
							}
						)
						
						await save_action(action_def, knowledge_id=knowledge_id)
						stored_count += 1
					except Exception as e:
						logger.warning(f"Failed to store inferred action: {e}")
			
			logger.info(
				f"✅ Filled {result.gaps_filled} action gaps with {len(result.inferred_actions)} inferred actions "
				f"({stored_count} stored)"
			)
			
			return result.dict()
		
		except Exception as e:
			logger.error(f"Failed to fill action gaps: {e}", exc_info=True)
			return {
				"gaps_filled": 0,
				"inferred_actions": [],
				"inferred_transitions": [],
				"confidence_scores": {},
				"errors": [str(e)]
			}
	
	def _identify_action_gaps(
		self,
		actions: list[Any],  # list[ActionDefinition]
		transitions: list[Any]  # list[TransitionDefinition]
	) -> list[ActionGap]:
		"""
		Identify gaps in action sequences.
		
		Args:
			actions: List of known actions
			transitions: List of known transitions
		
		Returns:
			List of ActionGap objects representing missing connections
		"""
		from navigator.knowledge.extrapolation import ActionGap
		
		gaps = []
		
		# Build action graph
		action_to_screen: dict[str, str] = {}
		screen_to_actions: dict[str, list[str]] = {}
		
		for action in actions:
			for screen_id in (action.screen_ids or []):
				action_to_screen[action.action_id] = screen_id
				if screen_id not in screen_to_actions:
					screen_to_actions[screen_id] = []
				screen_to_actions[screen_id].append(action.action_id)
		
		# Find transitions that don't have clear action paths
		for transition in transitions:
			from_screen_id = getattr(transition, 'from_screen_id', None)
			to_screen_id = getattr(transition, 'to_screen_id', None)
			action_id = getattr(transition, 'action_id', None)
			
			# If transition has no action, it's a gap
			if not action_id:
				# Find actions on from_screen and to_screen
				from_actions = screen_to_actions.get(from_screen_id or '', [])
				to_actions = screen_to_actions.get(to_screen_id or '', [])
				
				if from_actions and to_actions:
					# Create gap between last action on from_screen and first action on to_screen
					gaps.append(ActionGap(
						from_action_id=from_actions[-1],
						to_action_id=to_actions[0],
						from_screen_id=from_screen_id,
						to_screen_id=to_screen_id
					))
		
		return gaps

"""
Temporal activities for knowledge extraction workflow.

Activities are individual units of work that can be retried independently.
Each activity should be idempotent and handle errors gracefully.
"""

import logging
from dataclasses import dataclass
from typing import Any

from temporalio import activity

from browser_use import BrowserSession
from navigator.knowledge.exploration_engine import ExplorationEngine, ExplorationStrategy
from navigator.knowledge.semantic_analyzer import SemanticAnalyzer
from navigator.knowledge.storage import KnowledgeStorage
from navigator.knowledge.vector_store import VectorStore

logger = logging.getLogger(__name__)


# Data models for activity inputs/outputs
@dataclass
class PageProcessingInput:
	"""Input for page processing activity."""
	url: str
	job_id: str
	depth: int


@dataclass
class PageProcessingResult:
	"""Result of page processing activity."""
	url: str
	success: bool
	title: str | None = None
	content_length: int = 0
	entities_count: int = 0
	topics_count: int = 0
	links_discovered: int = 0
	processing_time: float = 0.0
	error: str | None = None
	error_type: str | None = None


@dataclass
class LinkDiscoveryInput:
	"""Input for link discovery activity."""
	url: str
	job_id: str
	depth: int
	base_url: str


@dataclass
class LinkDiscoveryResult:
	"""Result of link discovery activity."""
	url: str
	links: list[dict[str, Any]]
	internal_links: list[str]
	external_links: list[str]
	success: bool
	error: str | None = None


# Global storage instances (initialized by worker)
_browser_session: BrowserSession | None = None
_storage: KnowledgeStorage | None = None
_vector_store: VectorStore | None = None
_semantic_analyzer: SemanticAnalyzer | None = None
_exploration_engine: ExplorationEngine | None = None


def init_activity_dependencies(
	browser_session: BrowserSession,
	storage: KnowledgeStorage,
	vector_store: VectorStore,
):
	"""
	Initialize global dependencies for activities.
	
	This should be called once when the worker starts.
	"""
	global _browser_session, _storage, _vector_store, _semantic_analyzer, _exploration_engine
	
	_browser_session = browser_session
	_storage = storage
	_vector_store = vector_store
	_semantic_analyzer = SemanticAnalyzer(browser_session=browser_session)
	_exploration_engine = ExplorationEngine(
		browser_session=browser_session,
		max_depth=10,  # Will be controlled by workflow
		strategy=ExplorationStrategy.BFS,
	)
	
	logger.info("✅ Activity dependencies initialized")


@activity.defn(name="discover_links")
async def discover_links_activity(input: LinkDiscoveryInput) -> LinkDiscoveryResult:
	"""
	Activity: Discover links on a page.
	
	Args:
		input: Link discovery input
	
	Returns:
		Link discovery result with internal and external links
	"""
	logger.info(f"🔍 [Activity] Discovering links from: {input.url}")
	
	try:
		if _exploration_engine is None:
			raise RuntimeError("Activity dependencies not initialized")
		
		# Set base URL for exploration engine
		_exploration_engine.base_url = input.base_url
		
		# Discover links
		links = await _exploration_engine.discover_links(input.url)
		
		# Separate internal and external links
		internal_links = []
		external_links = []
		
		for link in links:
			if link.get('is_external', False):
				external_links.append(link['href'])
			else:
				internal_links.append(link['href'])
		
		logger.info(
			f"✅ [Activity] Discovered {len(links)} links "
			f"({len(internal_links)} internal, {len(external_links)} external)"
		)
		
		return LinkDiscoveryResult(
			url=input.url,
			links=links,
			internal_links=internal_links,
			external_links=external_links,
			success=True,
		)
	
	except Exception as e:
		logger.error(f"❌ [Activity] Link discovery failed for {input.url}: {e}", exc_info=True)
		return LinkDiscoveryResult(
			url=input.url,
			links=[],
			internal_links=[],
			external_links=[],
			success=False,
			error=str(e),
		)


@activity.defn(name="process_page")
async def process_page_activity(input: PageProcessingInput) -> PageProcessingResult:
	"""
	Activity: Process a single page (extract content, analyze, store).
	
	Args:
		input: Page processing input
	
	Returns:
		Page processing result with metrics
	"""
	logger.info(f"📄 [Activity] Processing page: {input.url}")
	
	import time
	start_time = time.time()
	
	try:
		if _semantic_analyzer is None or _storage is None or _vector_store is None:
			raise RuntimeError("Activity dependencies not initialized")
		
		# Extract content
		content = await _semantic_analyzer.extract_content(input.url)
		
		# Extract entities
		entities = _semantic_analyzer.identify_entities(content.get('text', ''))
		
		# Extract topics
		topics = _semantic_analyzer.extract_topics(content)
		
		# Generate embedding
		embedding = _semantic_analyzer.generate_embedding(content.get('text', ''))
		
		# Store page
		page_data = {
			**content,
			'entities': entities,
			'topics': topics,
			'job_id': input.job_id,
			'depth': input.depth,
		}
		await _storage.store_page(input.url, page_data)
		
		# Store embedding
		await _vector_store.store_embedding(
			id=input.url,
			embedding=embedding,
			metadata={
				'url': input.url,
				'title': content.get('title', ''),
				'job_id': input.job_id,
			},
		)
		
		processing_time = time.time() - start_time
		
		logger.info(
			f"✅ [Activity] Page processed in {processing_time:.2f}s: {input.url} "
			f"({len(entities)} entities, {len(topics)} topics)"
		)
		
		return PageProcessingResult(
			url=input.url,
			success=True,
			title=content.get('title'),
			content_length=len(content.get('text', '')),
			entities_count=len(entities),
			topics_count=len(topics),
			processing_time=processing_time,
		)
	
	except Exception as e:
		processing_time = time.time() - start_time
		
		# Categorize error
		error_type = _categorize_error(str(e), input.url)
		
		logger.error(
			f"❌ [Activity] Page processing failed for {input.url} ({error_type}): {e}",
			exc_info=True
		)
		
		return PageProcessingResult(
			url=input.url,
			success=False,
			processing_time=processing_time,
			error=str(e),
			error_type=error_type,
		)


@activity.defn(name="store_link")
async def store_link_activity(
	from_url: str,
	to_url: str,
	link_type: str,
	metadata: dict[str, Any],
) -> bool:
	"""
	Activity: Store a link relationship.
	
	Args:
		from_url: Source URL
		to_url: Target URL
		link_type: Type of link (internal, external)
		metadata: Additional metadata
	
	Returns:
		Success status
	"""
	try:
		if _storage is None:
			raise RuntimeError("Activity dependencies not initialized")
		
		await _storage.store_link(
			from_url=from_url,
			to_url=to_url,
			link_type=link_type,
			metadata=metadata,
		)
		
		return True
	
	except Exception as e:
		logger.error(f"❌ [Activity] Link storage failed: {e}", exc_info=True)
		return False


def _categorize_error(error_msg: str, url: str) -> str:
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
	
	return 'other'

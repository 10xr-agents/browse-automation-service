"""
MCP Server: Knowledge Exploration Tools

Tools for starting, managing, and querying knowledge exploration jobs.
"""

import asyncio
import logging
from typing import Any

try:
	import mcp.types as types
	MCP_AVAILABLE = True
except ImportError:
	MCP_AVAILABLE = False
	logging.warning('MCP SDK not installed. Install with: pip install mcp')

from uuid_extensions import uuid7str

logger = logging.getLogger(__name__)

# Import knowledge retrieval components (will import inside functions when needed)
KNOWLEDGE_AVAILABLE = True  # Assume available, will handle ImportError in functions


def get_knowledge_tools() -> list:
	"""
	Get list of knowledge exploration MCP tools.
	
	Returns:
		List of MCP Tool definitions
	"""
	return [
		# Knowledge Retrieval Tools
		types.Tool(
			name='start_knowledge_exploration',
			description='Start a knowledge retrieval job to explore and extract knowledge from a website',
			inputSchema={
				'type': 'object',
				'properties': {
					'start_url': {'type': 'string', 'description': 'Starting URL for exploration'},
					'max_pages': {'type': 'integer', 'description': 'Maximum number of pages to explore (optional)'},
					'max_depth': {'type': 'integer', 'description': 'Maximum exploration depth (default: 3)'},
					'strategy': {'type': 'string', 'enum': ['BFS', 'DFS'], 'description': 'Exploration strategy: BFS (breadth-first) or DFS (depth-first)'},
					'job_id': {'type': 'string', 'description': 'Optional job ID (auto-generated if not provided)'},
				},
				'required': ['start_url'],
			},
		),
		types.Tool(
			name='get_exploration_status',
			description='Get live status and progress for a knowledge retrieval job',
			inputSchema={
				'type': 'object',
				'properties': {
					'job_id': {'type': 'string', 'description': 'Job ID from start_knowledge_exploration'},
				},
				'required': ['job_id'],
			},
		),
		types.Tool(
			name='pause_exploration',
			description='Pause a running knowledge retrieval job',
			inputSchema={
				'type': 'object',
				'properties': {
					'job_id': {'type': 'string', 'description': 'Job ID to pause'},
				},
				'required': ['job_id'],
			},
		),
		types.Tool(
			name='resume_exploration',
			description='Resume a paused knowledge retrieval job',
			inputSchema={
				'type': 'object',
				'properties': {
					'job_id': {'type': 'string', 'description': 'Job ID to resume'},
				},
				'required': ['job_id'],
			},
		),
		types.Tool(
			name='cancel_exploration',
			description='Cancel a knowledge retrieval job',
			inputSchema={
				'type': 'object',
				'properties': {
					'job_id': {'type': 'string', 'description': 'Job ID to cancel'},
				},
				'required': ['job_id'],
			},
		),
		types.Tool(
			name='get_knowledge_results',
			description='Get results from a knowledge retrieval job (partial or final)',
			inputSchema={
				'type': 'object',
				'properties': {
					'job_id': {'type': 'string', 'description': 'Job ID'},
					'partial': {'type': 'boolean', 'description': 'If true, return partial results even if job is still running'},
				},
				'required': ['job_id'],
			},
		),
		types.Tool(
			name='query_knowledge',
			description='Query stored knowledge (pages, semantic search, links, sitemaps)',
			inputSchema={
				'type': 'object',
				'properties': {
					'query_type': {
						'type': 'string',
						'enum': ['pages', 'semantic_search', 'links', 'sitemap'],
						'description': 'Type of query to execute',
					},
					'params': {
						'type': 'object',
						'description': 'Query-specific parameters',
					},
				},
				'required': ['query_type'],
			},
		),
	]


def register_knowledge_tool_handlers(server, mcp_server_instance) -> dict[str, Any]:
	"""
	Register knowledge tool handlers and return handler mapping.
	
	Args:
		server: MCP Server instance
		mcp_server_instance: BrowserAutomationMCPServer instance (for accessing pipelines)
	
	Returns:
		Dict mapping tool names to handler functions
	"""
	handlers = {}
	
	async def _start_knowledge_exploration(arguments: dict[str, Any]) -> dict[str, Any]:
		"""Start a knowledge exploration job."""
		if not KNOWLEDGE_AVAILABLE:
			raise ValueError('Knowledge retrieval components not available')

		from navigator.knowledge.pipeline import KnowledgePipeline
		from navigator.knowledge.exploration_engine import ExplorationStrategy

		start_url = arguments.get('start_url')
		max_pages = arguments.get('max_pages')
		max_depth = arguments.get('max_depth', 3)
		strategy_str = arguments.get('strategy', 'BFS')
		job_id = arguments.get('job_id')

		if not start_url:
			raise ValueError('start_url is required')

		# Convert strategy string to enum
		strategy = ExplorationStrategy.BFS if strategy_str.upper() == 'BFS' else ExplorationStrategy.DFS

		# Get browser session from session manager (create a temporary one if needed)
		# For knowledge exploration, we need a browser session
		from browser_use import BrowserSession
		browser_session = BrowserSession()
		await browser_session.start()

		# Create progress observer for real-time updates
		class ProgressObserver:
			def __init__(self):
				self.current_page = None
				self.pages_completed = 0
				self.pages_failed = 0

			def on_page_started(self, url: str):
				self.current_page = url
				logger.info(f"Exploring page: {url}")

			def on_page_completed(self, url: str, success: bool):
				if success:
					self.pages_completed += 1
				else:
					self.pages_failed += 1

		progress_observer = ProgressObserver()

		# Create knowledge pipeline
		pipeline = KnowledgePipeline(
			browser_session=browser_session,
			progress_observer=progress_observer,
			max_depth=max_depth,
			strategy=strategy,
		)

		# Generate job ID if not provided
		if not job_id:
			job_id = uuid7str()

		# Store in registry using MongoDB-based job registry
		from navigator.knowledge.job_registry import get_job_registry
		job_registry = await get_job_registry()
		await job_registry.create_job(
			job_id=job_id,
			start_url=start_url,
			max_pages=max_pages,
			max_depth=3,
			job_type='exploration',
			status='queued',
		)

		# Store pipeline in memory for this session (TODO: consider persistence)
		if not hasattr(mcp_server_instance, '_active_pipelines'):
			mcp_server_instance._active_pipelines = {}
		mcp_server_instance._active_pipelines[job_id] = pipeline

		# Start exploration in background
		async def run_exploration():
			try:
				job_registry = await get_job_registry()
				await job_registry.update_job_status(job_id, 'running')

				result = await pipeline.explore_and_store(
					start_url=start_url,
					max_pages=max_pages,
					job_id=job_id,
				)

				status = 'completed' if result.get('error') is None else 'failed'
				await job_registry.update_job_status(job_id, status)
				await job_registry.update_job(job_id, {'results': result})
			except Exception as e:
				logger.error(f"Exploration job {job_id} failed: {e}", exc_info=True)
				job_registry = await get_job_registry()
				await job_registry.update_job_status(job_id, 'failed')
				await job_registry.update_job(job_id, {'error': str(e)})

		asyncio.create_task(run_exploration())

		return {
			'job_id': job_id,
			'status': 'started',
			'message': 'Knowledge exploration job started',
		}
	
	async def _get_exploration_status(arguments: dict[str, Any]) -> dict[str, Any]:
		"""Get exploration job status."""
		if not KNOWLEDGE_AVAILABLE:
			raise ValueError('Knowledge retrieval components not available')

		from navigator.knowledge.job_registry import get_job_registry

		job_id = arguments.get('job_id')
		if not job_id:
			raise ValueError('job_id is required')

		job_registry = await get_job_registry()
		job = await job_registry.get_job(job_id)
		if not job:
			return {'error': f'Job {job_id} not found'}

		# Check in-memory pipeline if available
		pipeline = getattr(mcp_server_instance, '_active_pipelines', {}).get(job_id)
		results = job.get('results', {})

		if pipeline:
			status = pipeline.get_job_status()
			return {
				'job_id': job_id,
				'status': status.get('status', job.get('status', 'unknown')),
				'paused': status.get('paused', False),
				'pages_completed': results.get('pages_stored', 0),
				'pages_failed': results.get('pages_failed', 0),
				'external_links_detected': results.get('external_links_detected', 0),
			}
		else:
			return {
				'job_id': job_id,
				'status': job.get('status', 'unknown'),
			}
	
	async def _pause_exploration(arguments: dict[str, Any]) -> dict[str, Any]:
		"""Pause exploration job."""
		if not KNOWLEDGE_AVAILABLE:
			raise ValueError('Knowledge retrieval components not available')

		job_id = arguments.get('job_id')
		if not job_id:
			raise ValueError('job_id is required')

		pipeline = getattr(mcp_server_instance, '_active_pipelines', {}).get(job_id)
		if not pipeline:
			return {'error': f'Exploration job {job_id} not found'}

		pipeline.pause()
		from navigator.knowledge.job_registry import get_job_registry
		job_registry = await get_job_registry()
		await job_registry.update_job_status(job_id, 'paused')

		return {
			'job_id': job_id,
			'status': 'paused',
			'message': 'Exploration job paused',
		}
	
	async def _resume_exploration(arguments: dict[str, Any]) -> dict[str, Any]:
		"""Resume exploration job."""
		if not KNOWLEDGE_AVAILABLE:
			raise ValueError('Knowledge retrieval components not available')

		job_id = arguments.get('job_id')
		if not job_id:
			raise ValueError('job_id is required')

		pipeline = getattr(mcp_server_instance, '_active_pipelines', {}).get(job_id)
		if not pipeline:
			return {'error': f'Exploration job {job_id} not found'}

		pipeline.resume()
		from navigator.knowledge.job_registry import get_job_registry
		job_registry = await get_job_registry()
		await job_registry.update_job_status(job_id, 'running')

		return {
			'job_id': job_id,
			'status': 'running',
			'message': 'Exploration job resumed',
		}
	
	async def _cancel_exploration(arguments: dict[str, Any]) -> dict[str, Any]:
		"""Cancel exploration job."""
		if not KNOWLEDGE_AVAILABLE:
			raise ValueError('Knowledge retrieval components not available')

		job_id = arguments.get('job_id')
		if not job_id:
			raise ValueError('job_id is required')

		pipeline = getattr(mcp_server_instance, '_active_pipelines', {}).get(job_id)
		if pipeline:
			pipeline.cancel()
			del mcp_server_instance._active_pipelines[job_id]

		from navigator.knowledge.job_registry import get_job_registry
		job_registry = await get_job_registry()
		await job_registry.update_job_status(job_id, 'cancelled')

		return {
			'job_id': job_id,
			'status': 'cancelled',
			'message': 'Exploration job cancelled',
		}
	
	async def _get_knowledge_results(arguments: dict[str, Any]) -> dict[str, Any]:
		"""Get knowledge exploration results."""
		if not KNOWLEDGE_AVAILABLE:
			raise ValueError('Knowledge retrieval components not available')

		from navigator.knowledge.job_registry import get_job_registry

		job_id = arguments.get('job_id')
		partial = arguments.get('partial', False)

		if not job_id:
			raise ValueError('job_id is required')

		job_registry = await get_job_registry()
		job = await job_registry.get_job(job_id)
		if not job:
			return {'error': f'Job {job_id} not found'}

		# Check if job is still running
		if job.get('status') == 'running' and not partial:
			return {'error': 'Job is still running. Set partial=true to get partial results.'}

		results = job.get('results', {})
		return results
	
	async def _query_knowledge(arguments: dict[str, Any]) -> dict[str, Any]:
		"""Query stored knowledge."""
		if not KNOWLEDGE_AVAILABLE:
			raise ValueError('Knowledge retrieval components not available')

		from navigator.knowledge.api import KnowledgeAPI
		from navigator.knowledge.storage import KnowledgeStorage
		from navigator.knowledge.vector_store import VectorStore

		query_type = arguments.get('query_type')
		params = arguments.get('params', {})

		if not query_type:
			raise ValueError('query_type is required')

		# Create KnowledgeAPI instance
		storage = KnowledgeStorage(use_mongodb=True)
		vector_store = VectorStore(use_mongodb=True)

		# Get pipeline from in-memory storage if available
		pipeline = None
		active_pipelines = getattr(mcp_server_instance, '_active_pipelines', {})
		if active_pipelines:
			pipeline = next(iter(active_pipelines.values()))

		knowledge_api = KnowledgeAPI(
			storage=storage,
			vector_store=vector_store,
			pipeline=pipeline,
		)

		result = await knowledge_api.query(query_type, params)
		return result
	
	# Map tool names to handlers
	handlers['start_knowledge_exploration'] = _start_knowledge_exploration
	handlers['get_exploration_status'] = _get_exploration_status
	handlers['pause_exploration'] = _pause_exploration
	handlers['resume_exploration'] = _resume_exploration
	handlers['cancel_exploration'] = _cancel_exploration
	handlers['get_knowledge_results'] = _get_knowledge_results
	handlers['query_knowledge'] = _query_knowledge
	
	return handlers

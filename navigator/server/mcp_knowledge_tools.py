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
		# Phase 3: Agent Communication Tools
		types.Tool(
			name='query_knowledge_for_agent',
			description='Agent-friendly knowledge query that returns browser-use compatible actions. Supports: navigate_to_screen, execute_task, find_screen, get_actions, get_screen_context',
			inputSchema={
				'type': 'object',
				'properties': {
					'knowledge_id': {'type': 'string', 'description': 'Knowledge ID to query'},
					'instruction_type': {'type': 'string', 'enum': ['navigate_to_screen', 'execute_task', 'find_screen', 'get_actions', 'get_screen_context'], 'description': 'Type of instruction'},
					'target': {'type': 'string', 'description': 'Screen ID, task ID, URL, or description'},
					'context': {'type': 'object', 'description': 'Additional context (current_url, current_screen_id, dom_summary, etc.)'},
				},
				'required': ['knowledge_id', 'instruction_type', 'target'],
			},
		),
		# Phase 5: Action Extrapolation Tools
		types.Tool(
			name='fill_action_gaps',
			description='Use LLM to infer missing actions and transitions between known actions. Fills gaps in navigation paths.',
			inputSchema={
				'type': 'object',
				'properties': {
					'knowledge_id': {'type': 'string', 'description': 'Knowledge ID to analyze'},
					'website_id': {'type': 'string', 'description': 'Website ID for context'},
				},
				'required': ['knowledge_id', 'website_id'],
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
	
	# Phase 3: Agent Communication Handler
	async def _query_knowledge_for_agent(arguments: dict[str, Any]) -> dict[str, Any]:
		"""Agent-friendly knowledge query that returns browser-use compatible actions."""
		if not KNOWLEDGE_AVAILABLE:
			raise ValueError('Knowledge retrieval components not available')
		
		try:
			from navigator.knowledge.agent_communication import (
				AgentInstruction,
				AgentResponse,
				ScreenRecognitionService,
			)
			from navigator.knowledge.extract.actions import ActionDefinition
			from navigator.knowledge.extract.browser_use_mapping import ActionTranslator
			from navigator.knowledge.extract.tasks import TaskStep
			from navigator.knowledge.persist.documents.actions import get_action
			from navigator.knowledge.persist.documents.screens import get_screen
			from navigator.knowledge.persist.documents.tasks import get_task
			from navigator.knowledge.persist.navigation import (
				get_navigation_path,
				get_screen_context,
			)
			
			knowledge_id = arguments.get('knowledge_id')
			instruction_type = arguments.get('instruction_type')
			target = arguments.get('target')
			context = arguments.get('context', {})
			
			if not knowledge_id or not instruction_type or not target:
				raise ValueError('knowledge_id, instruction_type, and target are required')
			
			# Create instruction
			instruction = AgentInstruction(
				instruction_type=instruction_type,
				target=target,
				knowledge_id=knowledge_id,
				context=context
			)
			
			response = AgentResponse(success=False)
			
			if instruction.instruction_type == "navigate_to_screen":
				current_url = instruction.context.get("current_url")
				current_screen_id = instruction.context.get("current_screen_id")
				target_screen_id = instruction.target
				
				if not current_screen_id and current_url:
					recognition_service = ScreenRecognitionService()
					recognition_result = await recognition_service.recognize_screen(
						current_url,
						instruction.context.get("dom_summary", ""),
						knowledge_id
					)
					current_screen_id = recognition_result.get("screen_id")
				
				if not current_screen_id:
					response.error = "Could not determine current screen. Provide current_url or current_screen_id in context."
					return response.dict()
				
				path_result = await get_navigation_path(
					current_screen_id,
					target_screen_id,
					knowledge_id
				)
				
				if not path_result.get("path"):
					response.error = f"No path found from screen {current_screen_id} to {target_screen_id}"
					return response.dict()
				
				translator = ActionTranslator()
				actions = []
				
				for step in path_result.get("steps", []):
					if "action" in step:
						action_data = step["action"]
						action_def = ActionDefinition(
							action_id=action_data.get("action_id", ""),
							name=action_data.get("action_name", ""),
							website_id="",
							action_type=action_data.get("action_type", "click"),
							target_selector=action_data.get("target", ""),
							parameters=action_data.get("parameters", {})
						)
						browser_action = translator.translate_action(
							action_def,
							screen_id=step.get("to_screen_id")
						)
						actions.append(browser_action)
				
				target_screen = await get_screen(target_screen_id)
				verification = {}
				if target_screen:
					verification = {
						"url_patterns": target_screen.url_patterns,
						"required_indicators": [
							{
								"type": ind.type,
								"value": ind.value,
								"pattern": ind.pattern
							}
							for ind in target_screen.state_signature.required_indicators[:5]
						]
					}
				
				response = AgentResponse(
					success=True,
					actions=actions,
					expected_result={
						"screen_id": target_screen_id,
						"screen_name": target_screen.name if target_screen else None,
						"verification": verification
					}
				)
			
			elif instruction.instruction_type == "execute_task":
				task = await get_task(instruction.target)
				
				if not task:
					response.error = f"Task not found: {instruction.target}"
					return response.dict()
				
				translator = ActionTranslator()
				actions = []
				
				for step in task.steps:
					if isinstance(step, TaskStep) and step.action:
						browser_action = translator.translate_action(
							step.action,
							screen_id=step.screen_id
						)
						actions.append(browser_action)
				
				response = AgentResponse(
					success=True,
					actions=actions,
					expected_result={
						"task_id": task.task_id,
						"task_name": task.name,
						"success_criteria": getattr(task, 'success_criteria', None)
					}
				)
			
			elif instruction.instruction_type == "find_screen":
				current_url = instruction.context.get("current_url") or instruction.target
				
				recognition_service = ScreenRecognitionService()
				recognition_result = await recognition_service.recognize_screen(
					current_url,
					instruction.context.get("dom_summary", ""),
					knowledge_id
				)
				
				if recognition_result.get("screen_id"):
					response = AgentResponse(
						success=True,
						actions=[],
						expected_result=recognition_result
					)
				else:
					response.error = f"Screen not found for URL: {current_url}"
			
			elif instruction.instruction_type == "get_actions":
				current_screen_id = instruction.context.get("current_screen_id")
				if not current_screen_id:
					current_url = instruction.context.get("current_url")
					if current_url:
						recognition_service = ScreenRecognitionService()
						recognition_result = await recognition_service.recognize_screen(
							current_url,
							instruction.context.get("dom_summary", ""),
							knowledge_id
						)
						current_screen_id = recognition_result.get("screen_id")
				
				if not current_screen_id:
					response.error = "Could not determine current screen. Provide current_screen_id or current_url in context."
					return response.dict()
				
				recognition_service = ScreenRecognitionService()
				available_actions = await recognition_service._get_available_actions(
					current_screen_id,
					knowledge_id
				)
				
				response = AgentResponse(
					success=True,
					actions=[],
					expected_result={
						"screen_id": current_screen_id,
						"available_actions": available_actions
					}
				)
			
			elif instruction.instruction_type == "get_screen_context":
				screen_id = instruction.target
				context = await get_screen_context(screen_id, knowledge_id)
				
				response = AgentResponse(
					success=True,
					actions=[],
					expected_result=context
				)
			
			return response.dict()
		
		except Exception as e:
			logger.error(f"Failed to query knowledge for agent: {e}", exc_info=True)
			return {
				"success": False,
				"error": str(e),
				"actions": [],
				"expected_result": {}
			}
	
	# Phase 5: Action Extrapolation Handler
	async def _fill_action_gaps(arguments: dict[str, Any]) -> dict[str, Any]:
		"""Fill action gaps using LLM extrapolation."""
		if not KNOWLEDGE_AVAILABLE:
			raise ValueError('Knowledge retrieval components not available')
		
		try:
			from navigator.knowledge.pipeline import KnowledgePipeline
			from browser_use import BrowserSession
			
			knowledge_id = arguments.get('knowledge_id')
			website_id = arguments.get('website_id')
			
			if not knowledge_id or not website_id:
				raise ValueError('knowledge_id and website_id are required')
			
			# Create a temporary browser session for the pipeline
			browser_session = BrowserSession()
			await browser_session.start()
			
			try:
				# Create knowledge pipeline
				pipeline = KnowledgePipeline(browser_session=browser_session)
				
				# Fill action gaps
				result = await pipeline.fill_action_gaps(knowledge_id, website_id)
				
				return result
			
			finally:
				# Clean up browser session
				await browser_session.close()
		
		except Exception as e:
			logger.error(f"Failed to fill action gaps: {e}", exc_info=True)
			return {
				"gaps_filled": 0,
				"inferred_actions": [],
				"inferred_transitions": [],
				"confidence_scores": {},
				"errors": [str(e)]
			}
	
	# Map tool names to handlers
	handlers['start_knowledge_exploration'] = _start_knowledge_exploration
	handlers['get_exploration_status'] = _get_exploration_status
	handlers['pause_exploration'] = _pause_exploration
	handlers['resume_exploration'] = _resume_exploration
	handlers['cancel_exploration'] = _cancel_exploration
	handlers['get_knowledge_results'] = _get_knowledge_results
	handlers['query_knowledge'] = _query_knowledge
	# Phase 3 & 5: New handlers
	handlers['query_knowledge_for_agent'] = _query_knowledge_for_agent
	handlers['fill_action_gaps'] = _fill_action_gaps
	
	return handlers

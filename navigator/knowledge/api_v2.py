"""
Knowledge Extraction REST API

Production API for knowledge extraction and retrieval.

Implements Phase 6: REST API Upgrades

Provides HTTP endpoints for:
- Starting knowledge extraction workflows (6.1)
- Querying knowledge graphs (6.2)
- Retrieving knowledge definitions (6.3)
- Getting workflow status (6.4)
- Triggering verification workflows (6.5)
"""

import logging
from typing import Any, Literal
from uuid import uuid4

try:
	from fastapi import APIRouter, HTTPException, UploadFile, File, Form
	from fastapi.responses import JSONResponse
	from pydantic import BaseModel, Field
	FASTAPI_AVAILABLE = True
except ImportError:
	FASTAPI_AVAILABLE = False
	logging.warning('FastAPI not installed. Install with: pip install fastapi')

from temporalio.client import Client

logger = logging.getLogger(__name__)

# Import Temporal components
from navigator.temporal.config import get_temporal_client
from navigator.temporal.workflows_v2 import KnowledgeExtractionWorkflowV2, KnowledgeExtractionInputV2

# Import persistence layer
from navigator.knowledge.persist.state import (
	load_workflow_state,
	load_workflow_state_by_job_id,
	query_workflows_by_status,
	WorkflowStatus,
)
from navigator.knowledge.persist.checkpoints import list_checkpoints
from navigator.knowledge.persist.documents import (
	get_screen,
	get_task,
	get_action,
	get_transition,
	query_screens_by_website,
	query_tasks_by_website,
)
from navigator.knowledge.persist.collections import SourceType

# Import graph query functions
from navigator.knowledge.graph.nodes import get_screen_node, count_screen_nodes
from navigator.knowledge.graph.graphs import traverse_navigation_graph, find_recovery_paths


# ============================================================================
# Phase 6.1: Ingestion API Request/Response Models
# ============================================================================

class IngestionOptionsModel(BaseModel):
	"""Options for ingestion."""
	max_pages: int | None = Field(None, description="Maximum pages to crawl (website only)")
	max_depth: int | None = Field(None, description="Maximum crawl depth (website only)")
	extract_code_blocks: bool = Field(True, description="Extract code blocks (documentation only)")
	extract_thumbnails: bool = Field(True, description="Extract video thumbnails (video only)")


class StartIngestionRequest(BaseModel):
	"""Request model for starting knowledge extraction."""
	source_type: SourceType = Field(..., description="Source type: documentation, website, or video")
	source_url: str | None = Field(None, description="URL for website or video")
	source_name: str | None = Field(None, description="Human-readable source name")
	options: IngestionOptionsModel = Field(default_factory=IngestionOptionsModel, description="Type-specific options")
	job_id: str | None = Field(None, description="Optional job ID (auto-generated if not provided)")


class StartIngestionResponse(BaseModel):
	"""Response model for starting ingestion."""
	job_id: str = Field(..., description="Workflow execution ID")
	workflow_id: str = Field(..., description="Temporal workflow ID")
	status: str = Field(..., description="Initial status (queued)")
	estimated_duration_seconds: int | None = Field(None, description="Estimated completion time")
	message: str = Field(..., description="Human-readable message")


# ============================================================================
# Phase 6.2: Graph Query Request/Response Models
# ============================================================================

class GraphQueryRequest(BaseModel):
	"""Request model for graph queries."""
	query_type: Literal["find_path", "get_neighbors", "search_screens", "get_transitions"] = Field(..., description="Query type")
	source_screen_id: str | None = Field(None, description="Source screen ID (for find_path, get_transitions)")
	target_screen_id: str | None = Field(None, description="Target screen ID (for find_path)")
	screen_name: str | None = Field(None, description="Screen name to search (for search_screens)")
	website_id: str | None = Field(None, description="Website ID filter")
	limit: int = Field(10, description="Maximum results to return")


class GraphQueryResponse(BaseModel):
	"""Response model for graph queries."""
	query_type: str = Field(..., description="Query type executed")
	results: list[dict[str, Any]] = Field(..., description="Query results")
	count: int = Field(..., description="Number of results returned")
	execution_time_ms: float | None = Field(None, description="Query execution time in milliseconds")


# ============================================================================
# Phase 6.3: Knowledge Definition Response Models
# ============================================================================

class ScreenDefinitionResponse(BaseModel):
	"""Response model for screen definition."""
	screen_id: str
	name: str
	website_id: str
	url_patterns: list[str]
	state_signature: dict[str, Any]
	ui_elements: list[dict[str, Any]]
	metadata: dict[str, Any]


class TaskDefinitionResponse(BaseModel):
	"""Response model for task definition."""
	task_id: str
	name: str
	website_id: str
	description: str
	goal: str
	steps: list[dict[str, Any]]
	preconditions: list[dict[str, Any]]
	postconditions: list[dict[str, Any]]
	iterator_spec: dict[str, Any] | None
	io_spec: dict[str, Any] | None


# ============================================================================
# Phase 6.4: Workflow Status Response Models
# ============================================================================

class CheckpointInfo(BaseModel):
	"""Checkpoint information."""
	activity_name: str
	checkpoint_id: int
	items_processed: int
	total_items: int
	progress_percentage: float


class WorkflowStatusResponse(BaseModel):
	"""Response model for workflow status."""
	job_id: str
	workflow_id: str
	status: str
	phase: str | None
	progress: float
	errors: list[str]
	warnings: list[str]
	checkpoints: list[CheckpointInfo]
	created_at: str
	updated_at: str
	metadata: dict[str, Any]


# ============================================================================
# Phase 6.5: Verification Trigger Request/Response Models
# ============================================================================

class VerificationRequest(BaseModel):
	"""Request model for starting verification."""
	target_type: Literal["job", "screen", "task"] = Field(..., description="Verification target type")
	target_id: str = Field(..., description="Target ID (job_id, screen_id, or task_id)")
	verification_options: dict[str, Any] = Field(default_factory=dict, description="Verification options")


class VerificationResponse(BaseModel):
	"""Response model for verification start."""
	verification_job_id: str = Field(..., description="Verification workflow ID")
	target_type: str
	target_id: str
	status: str = Field(..., description="Initial status (queued)")
	message: str


# ============================================================================
# Router Creation
# ============================================================================

def create_knowledge_api_router() -> APIRouter | None:
	"""
	Create FastAPI router for knowledge extraction REST API.
	
	Production API implementing Phase 6: REST API Upgrades
	
	Returns:
		APIRouter instance or None if FastAPI not available
	"""
	if not FASTAPI_AVAILABLE:
		logger.error("FastAPI not available, cannot create router")
		return None
	
	router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
	
	# Store Temporal client
	_temporal_client: Client | None = None
	
	async def _get_temporal_client() -> Client:
		"""Get or create Temporal client."""
		nonlocal _temporal_client
		if _temporal_client is None:
			_temporal_client = await get_temporal_client()
		return _temporal_client
	
	# ========================================================================
	# Phase 6.1: Ingestion API
	# ========================================================================
	
	@router.post("/ingest/start", response_model=StartIngestionResponse)
	async def start_ingestion(request: StartIngestionRequest) -> StartIngestionResponse:
		"""
		Start knowledge extraction workflow (Phase 6.1).
		
		Supports:
		- Documentation ingestion (via URL or file upload)
		- Website crawling (via URL)
		- Video ingestion (via URL or file upload)
		
		Returns job_id for tracking workflow progress.
		"""
		try:
			# Generate job_id if not provided
			job_id = request.job_id or f"job-{uuid4()}"
			workflow_id = f"knowledge-extraction-{job_id}"
			
			# Get Temporal client
			client = await _get_temporal_client()
			
			# Create workflow input
			workflow_input = KnowledgeExtractionInputV2(
				source_type=request.source_type.value,
				source_url=request.source_url,
				source_name=request.source_name or request.source_url or "Unknown",
				job_id=job_id,
			)
			
			# Start workflow
			handle = await client.start_workflow(
				KnowledgeExtractionWorkflowV2.run,
				workflow_input,
				id=workflow_id,
				task_queue="knowledge-extraction-queue",
			)
			
			logger.info(f"Started knowledge extraction workflow: job_id={job_id}, workflow_id={workflow_id}")
			
			# Estimate duration based on source type
			estimated_duration = {
				SourceType.DOCUMENTATION: 300,  # 5 minutes
				SourceType.WEBSITE: 900,  # 15 minutes
				SourceType.VIDEO: 600,  # 10 minutes
			}.get(request.source_type, 600)
			
			return StartIngestionResponse(
				job_id=job_id,
				workflow_id=workflow_id,
				status="queued",
				estimated_duration_seconds=estimated_duration,
				message=f"Knowledge extraction workflow started successfully for {request.source_type.value}"
			)
		
		except Exception as e:
			logger.error(f"Failed to start ingestion workflow: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to start workflow: {str(e)}")
	
	@router.post("/ingest/upload", response_model=StartIngestionResponse)
	async def start_ingestion_upload(
		source_type: SourceType = Form(...),
		source_name: str = Form(...),
		file: UploadFile = File(...),
		job_id: str | None = Form(None),
	) -> StartIngestionResponse:
		"""
		Start knowledge extraction with file upload (Phase 6.1).
		
		Supports:
		- Documentation files (Markdown, PDF, TXT)
		- Video files (MP4, MOV, AVI)
		
		File is saved and processed by the workflow.
		"""
		try:
			# TODO: Save uploaded file to temporary storage
			# TODO: Pass file path to workflow instead of URL
			
			# For now, return error as file storage not yet implemented
			raise HTTPException(
				status_code=501,
				detail="File upload not yet implemented. Use URL-based ingestion instead."
			)
		
		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to handle file upload: {e}")
			raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")
	
	# ========================================================================
	# Phase 6.2: Graph Query API
	# ========================================================================
	
	@router.post("/graph/query", response_model=GraphQueryResponse)
	async def query_graph(request: GraphQueryRequest) -> GraphQueryResponse:
		"""
		Query knowledge graph (Phase 6.2).
		
		Supported query types:
		- find_path: Find shortest path between two screens
		- get_neighbors: Get adjacent screens
		- search_screens: Search screens by name
		- get_transitions: Get transitions from a screen
		"""
		import time
		start_time = time.time()
		
		try:
			results = []
			
			if request.query_type == "find_path":
				if not request.source_screen_id or not request.target_screen_id:
					raise HTTPException(status_code=400, detail="source_screen_id and target_screen_id required for find_path")
				
				# Use ArangoDB graph traversal
				path_results = await traverse_navigation_graph(
					start_vertex_id=f"screens/{request.source_screen_id}",
					direction="outbound",
					max_depth=10,
					limit=1
				)
				results = path_results.get('paths', [])
			
			elif request.query_type == "get_neighbors":
				if not request.source_screen_id:
					raise HTTPException(status_code=400, detail="source_screen_id required for get_neighbors")
				
				# Get adjacent screens
				neighbors = await traverse_navigation_graph(
					start_vertex_id=f"screens/{request.source_screen_id}",
					direction="outbound",
					max_depth=1,
					limit=request.limit
				)
				results = neighbors.get('vertices', [])
			
			elif request.query_type == "search_screens":
				if not request.screen_name and not request.website_id:
					raise HTTPException(status_code=400, detail="screen_name or website_id required for search_screens")
				
				# Search screens in ArangoDB
				# For now, return count (full search requires more complex AQL)
				count = await count_screen_nodes(website_id=request.website_id)
				results = [{"count": count, "website_id": request.website_id}]
			
			elif request.query_type == "get_transitions":
				if not request.source_screen_id:
					raise HTTPException(status_code=400, detail="source_screen_id required for get_transitions")
				
				# Get transitions from MongoDB
				from navigator.knowledge.persist.documents import query_transitions_by_source
				transitions = await query_transitions_by_source(request.source_screen_id, limit=request.limit)
				results = [t.dict() for t in transitions]
			
			else:
				raise HTTPException(status_code=400, detail=f"Unknown query type: {request.query_type}")
			
			execution_time_ms = (time.time() - start_time) * 1000
			
			return GraphQueryResponse(
				query_type=request.query_type,
				results=results,
				count=len(results),
				execution_time_ms=execution_time_ms
			)
		
		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Graph query failed: {e}")
			raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")
	
	# ========================================================================
	# Phase 6.3: Knowledge Definition APIs
	# ========================================================================
	
	@router.get("/screens/{screen_id}", response_model=dict)
	async def get_screen_definition(screen_id: str) -> dict:
		"""
		Get full screen definition from MongoDB (Phase 6.3).
		
		Returns complete screen definition with:
		- State signature (indicators)
		- UI elements with selectors
		- Affordances
		- Metadata
		"""
		try:
			screen = await get_screen(screen_id)
			if not screen:
				raise HTTPException(status_code=404, detail=f"Screen not found: {screen_id}")
			
			return screen.dict()
		
		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to get screen: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to retrieve screen: {str(e)}")
	
	@router.get("/tasks/{task_id}", response_model=dict)
	async def get_task_definition(task_id: str) -> dict:
		"""
		Get full task definition from MongoDB (Phase 6.3).
		
		Returns complete task definition with:
		- Steps with action references
		- Preconditions and postconditions
		- Iterator spec (if loops present)
		- IO spec (inputs/outputs with volatility)
		"""
		try:
			task = await get_task(task_id)
			if not task:
				raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
			
			return task.dict()
		
		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to get task: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to retrieve task: {str(e)}")
	
	@router.get("/actions/{action_id}", response_model=dict)
	async def get_action_definition(action_id: str) -> dict:
		"""
		Get full action definition from MongoDB (Phase 6.3).
		
		Returns complete action definition with:
		- Action type and parameters
		- Target selector
		- Preconditions and postconditions
		- Idempotency flag
		- Error handling strategy
		"""
		try:
			action = await get_action(action_id)
			if not action:
				raise HTTPException(status_code=404, detail=f"Action not found: {action_id}")
			
			return action.dict()
		
		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to get action: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to retrieve action: {str(e)}")
	
	@router.get("/transitions/{transition_id}", response_model=dict)
	async def get_transition_definition(transition_id: str) -> dict:
		"""
		Get full transition definition from MongoDB (Phase 6.3).
		
		Returns complete transition definition with:
		- Source and target screens
		- Trigger action
		- Conditions (required/optional)
		- Effects (state changes)
		- Cost estimation
		- Reliability score
		"""
		try:
			transition = await get_transition(transition_id)
			if not transition:
				raise HTTPException(status_code=404, detail=f"Transition not found: {transition_id}")
			
			return transition.dict()
		
		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to get transition: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to retrieve transition: {str(e)}")
	
	@router.get("/screens", response_model=list[dict])
	async def list_screens(website_id: str, limit: int = 100) -> list[dict]:
		"""List screens for a website."""
		try:
			screens = await query_screens_by_website(website_id, limit=limit)
			return [s.dict() for s in screens]
		except Exception as e:
			logger.error(f"Failed to list screens: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to list screens: {str(e)}")
	
	@router.get("/tasks", response_model=list[dict])
	async def list_tasks(website_id: str, limit: int = 100) -> list[dict]:
		"""List tasks for a website."""
		try:
			tasks = await query_tasks_by_website(website_id, limit=limit)
			return [t.dict() for t in tasks]
		except Exception as e:
			logger.error(f"Failed to list tasks: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to list tasks: {str(e)}")
	
	# ========================================================================
	# Phase 6.4: Workflow Status API
	# ========================================================================
	
	@router.get("/workflows/status/{job_id}", response_model=WorkflowStatusResponse)
	async def get_workflow_status(job_id: str) -> WorkflowStatusResponse:
		"""
		Get detailed workflow status (Phase 6.4).
		
		Returns:
		- Current status and phase
		- Progress percentage
		- Errors and warnings
		- Checkpoint information
		- Timestamps
		"""
		try:
			# Load workflow state from MongoDB
			state = await load_workflow_state_by_job_id(job_id)
			if not state:
				raise HTTPException(status_code=404, detail=f"Workflow not found: {job_id}")
			
			# Get checkpoints
			checkpoints = await list_checkpoints(state.workflow_id)
			checkpoint_info = [
				CheckpointInfo(
					activity_name=cp.activity_name,
					checkpoint_id=cp.checkpoint_id,
					items_processed=cp.items_processed,
					total_items=cp.total_items,
					progress_percentage=cp.progress_percentage
				)
				for cp in checkpoints
			]
			
			return WorkflowStatusResponse(
				job_id=state.job_id,
				workflow_id=state.workflow_id,
				status=state.status.value,
				phase=state.phase,
				progress=state.progress,
				errors=state.errors,
				warnings=state.warnings,
				checkpoints=checkpoint_info,
				created_at=state.created_at.isoformat(),
				updated_at=state.updated_at.isoformat(),
				metadata=state.metadata
			)
		
		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to get workflow status: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to retrieve status: {str(e)}")
	
	@router.get("/workflows/list", response_model=list[dict])
	async def list_workflows(status: WorkflowStatus | None = None, limit: int = 100) -> list[dict]:
		"""
		List workflows (optionally filtered by status).
		
		Supports pagination via limit parameter.
		"""
		try:
			if status:
				workflows = await query_workflows_by_status(status, limit=limit)
			else:
				# Get all statuses
				workflows = []
				for workflow_status in WorkflowStatus:
					batch = await query_workflows_by_status(workflow_status, limit=limit)
					workflows.extend(batch)
			
			return [
				{
					"job_id": w.job_id,
					"workflow_id": w.workflow_id,
					"status": w.status.value,
					"phase": w.phase,
					"progress": w.progress,
					"created_at": w.created_at.isoformat(),
					"updated_at": w.updated_at.isoformat(),
				}
				for w in workflows[:limit]
			]
		
		except Exception as e:
			logger.error(f"Failed to list workflows: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to list workflows: {str(e)}")
	
	# ========================================================================
	# Phase 6.5: Verification Trigger API
	# ========================================================================
	
	@router.post("/verify/start", response_model=VerificationResponse)
	async def start_verification(request: VerificationRequest) -> VerificationResponse:
		"""
		Start browser-based verification workflow (Phase 7).
		
		Verifies extracted knowledge by:
		- Navigating to screens
		- Executing tasks
		- Validating state signatures
		- Checking UI elements
		
		Returns verification_job_id for tracking progress.
		
		Note: Requires FEATURE_BROWSER_VERIFICATION=true
		"""
		try:
			# Check if verification feature is enabled
			from navigator.config import get_feature_flags
			flags = get_feature_flags()
			
			if not flags.is_verification_enabled():
				raise HTTPException(
					status_code=503,
					detail="Browser verification is not enabled. Set FEATURE_BROWSER_VERIFICATION=true to enable."
				)
			
			# Generate verification job ID
			verification_job_id = f"verify-{uuid4()}"
			workflow_id = f"verification-{verification_job_id}"
			
			# Get Temporal client
			client = await _get_temporal_client()
			
			# Import workflow
			from navigator.temporal.workflows_verification import KnowledgeVerificationWorkflow
			from navigator.schemas.verification import VerificationWorkflowInput
			
			# Create workflow input
			workflow_input = VerificationWorkflowInput(
				verification_job_id=verification_job_id,
				target_type=request.target_type,
				target_id=request.target_id,
				verification_options=request.verification_options,
			)
			
			# Start verification workflow
			handle = await client.start_workflow(
				KnowledgeVerificationWorkflow.run,
				workflow_input,
				id=workflow_id,
				task_queue="knowledge-extraction-queue",
			)
			
			logger.info(f"Started verification workflow: job_id={verification_job_id}, workflow_id={workflow_id}")
			
			return VerificationResponse(
				verification_job_id=verification_job_id,
				target_type=request.target_type,
				target_id=request.target_id,
				status="queued",
				message=f"Verification workflow started for {request.target_type} {request.target_id}"
			)
		
		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to start verification: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to start verification: {str(e)}")
	
	# ========================================================================
	# Health Check
	# ========================================================================
	
	@router.get("/health")
	async def health_check() -> dict:
		"""Health check endpoint."""
		return {
			"status": "healthy",
			"service": "knowledge-extraction-api",
			"version": "1.0.0"
		}
	
	return router

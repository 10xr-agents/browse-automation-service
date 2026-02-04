"""
Temporal workflow and activity schemas.

These schemas define type-safe input/output for all workflow and activity interactions.
Uses Python dataclasses for optimal Temporal serialization performance.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# Import from domain schemas for consistency
from navigator.schemas.domain import IngestionResult


class WorkflowPhase(str, Enum):
	"""Workflow execution phases."""
	INGESTION = "ingestion"
	EXTRACTION = "extraction"
	GRAPH_CONSTRUCTION = "graph_construction"
	VERIFICATION = "verification"
	ENRICHMENT = "enrichment"
	COMPLETED = "completed"


# ============================================================================
# Workflow Input/Output Schemas
# ============================================================================

@dataclass
class KnowledgeExtractionInputV2:
	"""
	Input for Knowledge Extraction Workflow V2 (two-phase process).
	
	Phase 1: Extract knowledge from files or documentation URLs
	- source_urls: Files (from S3) and/or documentation URLs for crawling
	
	Phase 2: DOM-level analysis on website with authentication
	- options.website_url: Website URL for authenticated DOM analysis
	- options.credentials: Authentication details for website login
	"""

	# Required
	job_id: str
	source_url: str  # Primary source URL (first file/URL from Phase 1)

	# Optional
	source_type: str | None = None  # Auto-detect if None (use string instead of enum for Temporal compatibility)
	source_name: str | None = None  # Human-readable source name
	max_depth: int = 5
	options: dict[str, Any] = field(default_factory=dict)  # Contains website_url and credentials for Phase 2

	# Phase 1: Multiple file/documentation URL support
	source_urls: list[str] | None = None  # Multiple source URLs/files for Phase 1 processing
	source_names: list[str] | None = None  # Optional names for each source (must match source_urls length)

	# Knowledge ID for persistence and querying
	knowledge_id: str | None = None  # Knowledge ID for persisting and querying extracted knowledge


@dataclass
class KnowledgeExtractionResultV2:
	"""Result of Knowledge Extraction Workflow V2."""

	job_id: str
	status: str  # completed, failed, cancelled

	# Statistics
	sources_ingested: int = 0
	screens_extracted: int = 0
	tasks_extracted: int = 0
	actions_extracted: int = 0
	transitions_extracted: int = 0
	business_functions_extracted: int = 0  # Video-specific
	workflows_extracted: int = 0  # Video-specific

	# Graph statistics
	graph_nodes: int = 0
	graph_edges: int = 0

	# Exploration statistics
	pages_explored: int = 0
	forms_identified: int = 0
	new_screens_from_exploration: int = 0
	new_actions_from_exploration: int = 0
	login_successful: bool = False

	# Verification statistics
	screens_verified: int = 0
	discrepancies_found: int = 0
	enrichments_applied: int = 0

	# Timing
	processing_time: float = 0.0

	# Errors
	errors: list[dict[str, Any]] = field(default_factory=list)
	error: str | None = None


@dataclass
class KnowledgeExtractionProgressV2:
	"""Progress state for workflow."""

	phase: WorkflowPhase = WorkflowPhase.INGESTION
	current_activity: str | None = None

	# Phase-specific progress
	items_processed: int = 0
	total_items: int = 0
	current_item_id: str | None = None

	# Overall statistics (accumulated)
	sources_ingested: int = 0
	screens_extracted: int = 0
	tasks_extracted: int = 0
	actions_extracted: int = 0
	business_functions_extracted: int = 0  # Video-specific
	workflows_extracted: int = 0  # Video-specific

	# Errors
	errors: list[dict[str, Any]] = field(default_factory=list)


# ============================================================================
# Activity Input/Output Schemas
# ============================================================================

# --- Ingestion Activity ---

@dataclass
class IngestSourceInput:
	"""Input for ingest_source_activity."""
	source_url: str
	source_type: str | None  # Use string instead of enum for Temporal compatibility
	job_id: str
	source_name: str | None = None  # Human-readable source name
	options: dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestSourceResult:
	"""
	Result of ingest_source_activity.
	
	This is a simplified dataclass wrapper around IngestionResult for Temporal compatibility.
	"""
	ingestion_id: str
	source_type: str  # Use string instead of enum for Temporal compatibility
	content_chunks: int
	total_tokens: int
	success: bool = True
	errors: list[str] = field(default_factory=list)

	@classmethod
	def from_ingestion_result(cls, result: IngestionResult) -> 'IngestSourceResult':
		"""Create from IngestionResult."""
		return cls(
			ingestion_id=result.ingestion_id,
			source_type=result.source_type.value if hasattr(result.source_type, 'value') else str(result.source_type),
			content_chunks=result.total_chunks,
			total_tokens=result.total_tokens,
			success=result.success,
			errors=[f"{e.error_type}: {e.error_message}" for e in result.errors]
		)


# --- Extraction Activities ---

@dataclass
class ExtractScreensInput:
	"""Input for extract_screens_activity."""
	ingestion_id: str  # Primary ingestion ID (for backward compatibility)
	job_id: str
	website_id: str | None = None  # Website identifier for grouping
	ingestion_ids: list[str] | None = None  # Optional: Multiple ingestion IDs (for batch file processing)
	knowledge_id: str | None = None  # Knowledge ID for persisting and querying extracted knowledge


@dataclass
class ExtractScreensResult:
	"""Result of extract_screens_activity."""
	screens_extracted: int
	screen_ids: list[str]
	errors: list[str] = field(default_factory=list)
	success: bool = True


@dataclass
class ExtractTasksInput:
	"""Input for extract_tasks_activity."""
	ingestion_id: str  # Primary ingestion ID (for backward compatibility)
	job_id: str
	website_id: str | None = None  # Website identifier for grouping
	ingestion_ids: list[str] | None = None  # Optional: Multiple ingestion IDs (for batch file processing)
	knowledge_id: str | None = None  # Knowledge ID for persisting and querying extracted knowledge


@dataclass
class ExtractTasksResult:
	"""Result of extract_tasks_activity."""
	tasks_extracted: int
	task_ids: list[str]
	errors: list[str] = field(default_factory=list)
	success: bool = True


@dataclass
class ExtractActionsInput:
	"""Input for extract_actions_activity."""
	ingestion_id: str  # Primary ingestion ID (for backward compatibility)
	job_id: str
	website_id: str | None = None  # Website identifier for grouping
	ingestion_ids: list[str] | None = None  # Optional: Multiple ingestion IDs (for batch file processing)
	knowledge_id: str | None = None  # Knowledge ID for persisting and querying extracted knowledge


@dataclass
class ExtractActionsResult:
	"""Result of extract_actions_activity."""
	actions_extracted: int
	action_ids: list[str]
	errors: list[str] = field(default_factory=list)
	success: bool = True


@dataclass
class ExtractTransitionsInput:
	"""Input for extract_transitions_activity."""
	ingestion_id: str  # Primary ingestion ID (for backward compatibility)
	job_id: str
	website_id: str | None = None  # Website identifier for grouping
	ingestion_ids: list[str] | None = None  # Optional: Multiple ingestion IDs (for batch file processing)
	knowledge_id: str | None = None  # Knowledge ID for persisting and querying extracted knowledge


@dataclass
class ExtractTransitionsResult:
	"""Result of extract_transitions_activity."""
	transitions_extracted: int
	transition_ids: list[str]
	errors: list[str] = field(default_factory=list)
	success: bool = True


# --- Business Function Extraction Activity (Video) ---

@dataclass
class ExtractBusinessFunctionsInput:
	"""Input for extract_business_functions_activity."""
	ingestion_id: str  # Primary ingestion ID
	job_id: str
	website_id: str | None = None
	ingestion_ids: list[str] | None = None  # Optional: Multiple ingestion IDs
	knowledge_id: str | None = None  # Knowledge ID for persisting and querying extracted knowledge


@dataclass
class ExtractBusinessFunctionsResult:
	"""Result of extract_business_functions_activity."""
	business_functions_extracted: int
	business_function_ids: list[str]
	errors: list[str] = field(default_factory=list)
	success: bool = True


# --- Workflow Extraction Activity (Video) ---

@dataclass
class ExtractWorkflowsInput:
	"""Input for extract_workflows_activity."""
	ingestion_id: str  # Primary ingestion ID
	job_id: str
	business_function: str | None = None  # Optional: Filter by business function
	website_id: str | None = None
	ingestion_ids: list[str] | None = None  # Optional: Multiple ingestion IDs
	knowledge_id: str | None = None  # Knowledge ID for persisting and querying extracted knowledge


@dataclass
class ExtractWorkflowsResult:
	"""Result of extract_workflows_activity."""
	workflows_extracted: int
	workflow_ids: list[str]
	errors: list[str] = field(default_factory=list)
	success: bool = True


# --- User Flow Extraction Activity (Phase 4) ---

@dataclass
class ExtractUserFlowsInput:
	"""Input for extract_user_flows_activity."""
	job_id: str
	knowledge_id: str  # Knowledge ID to query existing entities from
	website_id: str | None = None  # Website identifier for grouping


@dataclass
class ExtractUserFlowsResult:
	"""Result of extract_user_flows_activity."""
	user_flows_extracted: int
	user_flow_ids: list[str]
	errors: list[str] = field(default_factory=list)
	success: bool = True


# --- Post-Extraction Entity Linking Activity (Priority 2) ---

@dataclass
class LinkEntitiesInput:
	"""Input for link_entities_activity."""
	knowledge_id: str
	job_id: str | None = None


@dataclass
class LinkEntitiesResult:
	"""Result of link_entities_activity."""
	tasks_linked: int
	actions_linked: int
	business_functions_linked: int
	workflows_linked: int
	transitions_linked: int
	errors: list[str] = field(default_factory=list)
	success: bool = True


# --- Video Sub-Activities ---

@dataclass
class TranscribeVideoInput:
	"""Input for transcribe_video_activity (Deepgram transcription)."""
	video_path: str
	ingestion_id: str
	job_id: str


@dataclass
class TranscribeVideoResult:
	"""Result of transcribe_video_activity."""
	transcription_data: dict[str, Any]  # Deepgram transcription segments
	success: bool = True
	errors: list[str] = field(default_factory=list)


@dataclass
class FilterFramesInput:
	"""Input for filter_frames_activity (SSIM deduplication + frame extraction)."""
	video_path: str
	ingestion_id: str
	duration: float
	job_id: str
	scene_changes: list[float] = field(default_factory=list)  # Scene change timestamps


@dataclass
class FilterFramesResult:
	"""Result of filter_frames_activity."""
	filtered_frame_paths: list[tuple[float, str]]  # List of (timestamp, frame_path) tuples (unique frames only)
	all_frame_paths: list[tuple[float, str]]  # List of all (timestamp, frame_path) tuples (includes duplicates)
	duplicate_map: dict[float, float]  # Map duplicate timestamps to their previous unique timestamp
	metadata: dict[str, Any] | None = None  # Video metadata (extracted during filtering)
	success: bool = True
	errors: list[str] = field(default_factory=list)


@dataclass
class AnalyzeFramesBatchInput:
	"""Input for analyze_frames_batch_activity (parallel frame processing)."""
	frame_batch: list[tuple[float, str]]  # List of (timestamp, frame_path) tuples for this batch
	ingestion_id: str
	batch_index: int  # Batch index for logging
	job_id: str
	output_s3_prefix: str | None = None  # Optional S3 prefix for batch results (Claim Check pattern)


@dataclass
class AnalyzeFramesBatchResult:
	"""Result of analyze_frames_batch_activity (Claim Check pattern - returns S3 key, not data)."""
	s3_key: str  # S3 key where batch results JSON is stored (e.g., "s3://bucket/results/{ingestion_id}/batch_{index}.json")
	frame_count: int  # Number of frames analyzed in this batch
	success: bool = True
	errors: list[str] = field(default_factory=list)


@dataclass
class AssembleVideoIngestionInput:
	"""Input for assemble_video_ingestion_activity (Claim Check pattern - receives S3 keys, not data)."""
	ingestion_id: str
	video_path: str
	transcription_data: dict[str, Any] | None  # From transcribe_video_activity
	filtered_frame_paths: list[tuple[float, str]]  # From filter_frames_activity
	duplicate_map: dict[float, float]  # From filter_frames_activity
	analysis_result_s3_keys: list[str]  # List of S3 keys for batch result JSON files (Claim Check pattern - avoids history bloat)
	metadata: dict[str, Any] | None  # Video metadata
	job_id: str
	options: dict[str, Any] = field(default_factory=dict)


@dataclass
class AssembleVideoIngestionResult:
	"""Result of assemble_video_ingestion_activity."""
	ingestion_id: str
	content_chunks: int
	total_tokens: int
	success: bool = True
	errors: list[str] = field(default_factory=list)


# --- Graph Construction Activity ---

@dataclass
class BuildGraphInput:
	"""Input for build_graph_activity."""
	job_id: str
	screen_ids: list[str]
	task_ids: list[str]
	action_ids: list[str]
	transition_ids: list[str]


@dataclass
class BuildGraphResult:
	"""Result of build_graph_activity."""
	graph_nodes: int
	graph_edges: int
	screen_groups: int
	errors: list[str] = field(default_factory=list)
	success: bool = True


# --- Verification Activity ---

@dataclass
class VerifyExtractionInput:
	"""Input for verify_extraction_activity."""
	job_id: str
	screen_ids: list[str]
	task_ids: list[str]


@dataclass
class VerifyExtractionResult:
	"""Result of verify_extraction_activity."""
	screens_verified: int
	discrepancies_found: int
	discrepancy_ids: list[str]
	errors: list[str] = field(default_factory=list)
	success: bool = True


# --- Enrichment Activity ---

@dataclass
class EnrichKnowledgeInput:
	"""Input for enrich_knowledge_activity."""
	job_id: str
	discrepancy_ids: list[str]


@dataclass
class EnrichKnowledgeResult:
	"""Result of enrich_knowledge_activity."""
	enrichments_applied: int
	updated_screen_ids: list[str]
	updated_task_ids: list[str]
	errors: list[str] = field(default_factory=list)
	success: bool = True


# ============================================================================
# Activity: Delete Knowledge
# ============================================================================

@dataclass
class DeleteKnowledgeInput:
	"""Input for delete_knowledge_activity."""
	knowledge_id: str


@dataclass
class DeleteKnowledgeResult:
	"""Result of delete_knowledge_activity."""
	deletion_counts: dict[str, int]  # {'screens': 5, 'tasks': 3, ...}
	total_deleted: int
	success: bool = True
	errors: list[str] = field(default_factory=list)


# ============================================================================
# Activity: Primary URL Exploration
# ============================================================================

@dataclass
class ExplorePrimaryUrlInput:
	"""Input for explore_primary_url_activity."""
	job_id: str
	primary_url: str  # Primary URL to explore
	website_id: str
	credentials: dict[str, str] | None = None  # Optional: {'username': '...', 'password': '...', 'login_url': '...'}
	max_pages: int = 10  # Maximum pages to explore
	max_depth: int = 3  # Maximum exploration depth
	screen_ids: list[str] = field(default_factory=list)  # Existing screen IDs to enrich
	task_ids: list[str] = field(default_factory=list)  # Existing task IDs to enrich
	action_ids: list[str] = field(default_factory=list)  # Existing action IDs to enrich
	knowledge_id: str | None = None  # Knowledge ID for persisting and querying extracted knowledge


@dataclass
class ExplorePrimaryUrlResult:
	"""Result of explore_primary_url_activity."""
	pages_explored: int = 0
	forms_identified: int = 0
	forms_with_fields: int = 0  # Forms with extracted field details
	multi_step_forms: int = 0  # Multi-step forms detected
	links_clicked: int = 0  # Number of links clicked during exploration
	screens_enriched: int = 0
	tasks_enriched: int = 0
	actions_enriched: int = 0
	new_screens_found: int = 0
	new_actions_found: int = 0
	login_successful: bool = False
	success: bool = True
	errors: list[str] = field(default_factory=list)


# ============================================================================
# Idempotency Schema
# ============================================================================

@dataclass
class ActivityExecutionLog:
	"""Log entry for activity execution (for idempotency)."""

	idempotency_key: str  # {workflow_id}:{activity_name}:{content_hash}
	workflow_id: str
	activity_name: str

	# Input/Output
	input_hash: str
	output_data: dict[str, Any]

	# Execution metadata
	started_at: datetime
	completed_at: datetime
	success: bool
	error: str | None = None

	# Retry tracking
	attempt: int = 1

	# TTL (for cleanup)
	expires_at: datetime | None = None

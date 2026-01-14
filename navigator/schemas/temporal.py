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
from navigator.schemas.domain import SourceType, SourceMetadata, IngestionResult


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
	"""Input for Knowledge Extraction Workflow V2."""
	
	# Required
	job_id: str
	source_url: str
	
	# Optional
	source_type: SourceType | None = None  # Auto-detect if None
	max_depth: int = 5
	options: dict[str, Any] = field(default_factory=dict)


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
	
	# Graph statistics
	graph_nodes: int = 0
	graph_edges: int = 0
	
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
	source_type: SourceType | None
	job_id: str
	options: dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestSourceResult:
	"""
	Result of ingest_source_activity.
	
	This is a simplified dataclass wrapper around IngestionResult for Temporal compatibility.
	"""
	ingestion_id: str
	source_type: SourceType
	content_chunks: int
	total_tokens: int
	success: bool = True
	errors: list[str] = field(default_factory=list)
	
	@classmethod
	def from_ingestion_result(cls, result: IngestionResult) -> 'IngestSourceResult':
		"""Create from IngestionResult."""
		return cls(
			ingestion_id=result.ingestion_id,
			source_type=result.source_type,
			content_chunks=result.total_chunks,
			total_tokens=result.total_tokens,
			success=result.success,
			errors=[f"{e.error_type}: {e.error_message}" for e in result.errors]
		)


# --- Extraction Activities ---

@dataclass
class ExtractScreensInput:
	"""Input for extract_screens_activity."""
	ingestion_id: str
	job_id: str


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
	ingestion_id: str
	job_id: str


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
	ingestion_id: str
	job_id: str


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
	ingestion_id: str
	job_id: str


@dataclass
class ExtractTransitionsResult:
	"""Result of extract_transitions_activity."""
	transitions_extracted: int
	transition_ids: list[str]
	errors: list[str] = field(default_factory=list)
	success: bool = True


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

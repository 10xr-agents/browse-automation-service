"""
Unified schemas module for the Navigator application.

This module consolidates all schema definitions into a single namespace:
- Domain schemas: Business logic models (Pydantic)
- Temporal schemas: Workflow/Activity contracts (Dataclasses)

Usage:
    from navigator.schemas import SourceType, IngestionResult
    from navigator.schemas import IngestSourceInput, IngestSourceResult
"""

# Domain schemas (Pydantic models - rich validation)
from navigator.schemas.domain import (
	# Enums
	SourceType,
	DocumentFormat,
	VideoFormat,
	# Models
	SourceMetadata,
	ContentChunk,
	IngestionError,
	IngestionResult,
	# Utilities
	detect_source_type,
	detect_document_format,
	detect_video_format,
)

# Temporal schemas (Dataclasses - lightweight serialization)
from navigator.schemas.temporal import (
	# Workflow enums
	WorkflowPhase,
	# Workflow I/O
	KnowledgeExtractionInputV2,
	KnowledgeExtractionResultV2,
	KnowledgeExtractionProgressV2,
	# Activity I/O - Ingestion
	IngestSourceInput,
	IngestSourceResult,
	# Activity I/O - Extraction
	ExtractScreensInput,
	ExtractScreensResult,
	ExtractTasksInput,
	ExtractTasksResult,
	ExtractActionsInput,
	ExtractActionsResult,
	ExtractTransitionsInput,
	ExtractTransitionsResult,
	# Activity I/O - Graph
	BuildGraphInput,
	BuildGraphResult,
	# Activity I/O - Verification
	VerifyExtractionInput,
	VerifyExtractionResult,
	# Activity I/O - Enrichment
	EnrichKnowledgeInput,
	EnrichKnowledgeResult,
	# Idempotency
	ActivityExecutionLog,
)

__all__ = [
	# Domain - Enums
	'SourceType',
	'DocumentFormat',
	'VideoFormat',
	# Domain - Models
	'SourceMetadata',
	'ContentChunk',
	'IngestionError',
	'IngestionResult',
	# Domain - Utilities
	'detect_source_type',
	'detect_document_format',
	'detect_video_format',
	# Temporal - Workflow
	'WorkflowPhase',
	'KnowledgeExtractionInputV2',
	'KnowledgeExtractionResultV2',
	'KnowledgeExtractionProgressV2',
	# Temporal - Activities
	'IngestSourceInput',
	'IngestSourceResult',
	'ExtractScreensInput',
	'ExtractScreensResult',
	'ExtractTasksInput',
	'ExtractTasksResult',
	'ExtractActionsInput',
	'ExtractActionsResult',
	'ExtractTransitionsInput',
	'ExtractTransitionsResult',
	'BuildGraphInput',
	'BuildGraphResult',
	'VerifyExtractionInput',
	'VerifyExtractionResult',
	'EnrichKnowledgeInput',
	'EnrichKnowledgeResult',
	'ActivityExecutionLog',
]

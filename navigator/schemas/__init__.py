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
	ContentChunk,
	DataElement,
	DocumentFormat,
	FrameAnalysisResponse,
	IngestionError,
	IngestionResult,
	# Models
	SourceMetadata,
	# Enums
	SourceType,
	# Video frame analysis schemas (structured outputs)
	UIElement,
	VideoFormat,
	VisualIndicator,
	detect_document_format,
	# Utilities
	detect_source_type,
	detect_video_format,
)

# Temporal schemas (Dataclasses - lightweight serialization)
from navigator.schemas.temporal import (
	# Idempotency
	ActivityExecutionLog,
	AnalyzeFramesBatchInput,
	AnalyzeFramesBatchResult,
	AssembleVideoIngestionInput,
	AssembleVideoIngestionResult,
	# Activity I/O - Graph
	BuildGraphInput,
	BuildGraphResult,
	# Activity I/O - Delete Knowledge
	DeleteKnowledgeInput,
	DeleteKnowledgeResult,
	# Activity I/O - Enrichment
	EnrichKnowledgeInput,
	EnrichKnowledgeResult,
	# Activity I/O - Primary URL Exploration
	ExplorePrimaryUrlInput,
	ExplorePrimaryUrlResult,
	ExtractActionsInput,
	ExtractActionsResult,
	ExtractBusinessFunctionsInput,
	ExtractBusinessFunctionsResult,
	# Activity I/O - Extraction
	ExtractScreensInput,
	ExtractScreensResult,
	ExtractTasksInput,
	ExtractTasksResult,
	ExtractTransitionsInput,
	ExtractTransitionsResult,
	# Activity I/O - User Flow Extraction (Phase 4)
	ExtractUserFlowsInput,
	ExtractUserFlowsResult,
	ExtractWorkflowsInput,
	ExtractWorkflowsResult,
	# Activity I/O - Post-Extraction Entity Linking (Priority 2)
	LinkEntitiesInput,
	LinkEntitiesResult,
	FilterFramesInput,
	FilterFramesResult,
	# Activity I/O - Ingestion
	IngestSourceInput,
	IngestSourceResult,
	# Workflow I/O
	KnowledgeExtractionInputV2,
	KnowledgeExtractionProgressV2,
	KnowledgeExtractionResultV2,
	# Activity I/O - Video Sub-Activities
	TranscribeVideoInput,
	TranscribeVideoResult,
	# Activity I/O - Verification
	VerifyExtractionInput,
	VerifyExtractionResult,
	# Workflow enums
	WorkflowPhase,
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
	# Domain - Video Frame Analysis (Structured Outputs)
	'UIElement',
	'DataElement',
	'VisualIndicator',
	'FrameAnalysisResponse',
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
	'ExtractBusinessFunctionsInput',
	'ExtractBusinessFunctionsResult',
	'ExtractWorkflowsInput',
	'ExtractWorkflowsResult',
	'ExtractUserFlowsInput',
	'ExtractUserFlowsResult',
	'LinkEntitiesInput',
	'LinkEntitiesResult',
	'BuildGraphInput',
	'BuildGraphResult',
	'VerifyExtractionInput',
	'VerifyExtractionResult',
	'EnrichKnowledgeInput',
	'EnrichKnowledgeResult',
	'DeleteKnowledgeInput',
	'DeleteKnowledgeResult',
	'TranscribeVideoInput',
	'TranscribeVideoResult',
	'FilterFramesInput',
	'FilterFramesResult',
	'AnalyzeFramesBatchInput',
	'AnalyzeFramesBatchResult',
	'AssembleVideoIngestionInput',
	'AssembleVideoIngestionResult',
	'ExplorePrimaryUrlInput',
	'ExplorePrimaryUrlResult',
	'ActivityExecutionLog',
]

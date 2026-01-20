"""
REST API Request/Response Models

Shared Pydantic models for knowledge extraction REST API endpoints.
"""

import logging
from typing import Any, Literal

try:
	from fastapi import APIRouter, File, Form, HTTPException, UploadFile
	from pydantic import BaseModel, Field
	FASTAPI_AVAILABLE = True
except ImportError:
	FASTAPI_AVAILABLE = False
	logging.warning('FastAPI not installed. Install with: pip install fastapi')

from navigator.knowledge.persist.collections import SourceType
from navigator.schemas.s3 import FileMetadata, S3Reference

logger = logging.getLogger(__name__)


# ============================================================================
# Phase 6.1: Ingestion API Request/Response Models
# ============================================================================

class IngestionOptionsModel(BaseModel):
	"""Options for ingestion."""
	max_pages: int | None = Field(None, description="Maximum pages to crawl (website only)")
	max_depth: int | None = Field(None, description="Maximum crawl depth (website only)")
	extract_code_blocks: bool = Field(True, description="Extract code blocks (documentation only)")
	extract_thumbnails: bool = Field(True, description="Extract video thumbnails (video only)")
	credentials: dict[str, str] | None = Field(
		None,
		description="Optional credentials for website login: {'username': '...', 'password': '...', 'login_url': '...'}"
	)


class StartIngestionRequest(BaseModel):
	"""
	Request model for starting knowledge extraction.
	
	Two-phase knowledge extraction process:
	
	Phase 1: Extract knowledge from files or documentation URLs
	- Process uploaded files (video, audio, txt, md, docx, pdf, etc.) OR
	- Process publicly available documentation URLs for crawling
	
	Phase 2: DOM-level analysis on website with authentication
	- Use website_url + credentials to perform authenticated DOM analysis
	- Extract additional knowledge through browser-based interaction
	
	Required:
	- website_url: Target website/webportal for Phase 2 DOM analysis
	- At least one of: files (s3_references) OR documentation_urls
	
	Optional:
	- credentials: Authentication details for website login
	"""
	# Phase 2: Website for DOM analysis (required)
	website_url: str = Field(..., description="Website/webportal URL for authenticated DOM-level analysis (Phase 2)")
	website_name: str | None = Field(None, description="Human-readable website name")

	# Phase 1: Files or documentation URLs (at least one required)
	s3_references: list[S3Reference] | None = Field(None, description="Array of S3 file references (videos, audio, txt, md, docx, pdf, etc.) for Phase 1 processing")
	file_metadata_list: list[FileMetadata] | None = Field(None, description="Array of file metadata matching s3_references (required if s3_references provided)")
	documentation_urls: list[str] | None = Field(None, description="Array of publicly available documentation URLs for crawling in Phase 1")

	# Authentication for Phase 2
	credentials: dict[str, str] | None = Field(None, description="Credentials for website login: {'username': '...', 'password': '...', 'login_url': '...'}")

	# Options and metadata
	options: IngestionOptionsModel = Field(default_factory=IngestionOptionsModel, description="Extraction options (max_pages, max_depth, etc.)")
	job_id: str | None = Field(None, description="Optional job ID (auto-generated if not provided)")
	knowledge_id: str | None = Field(None, description="Knowledge ID for persisting and querying extracted knowledge (required for proper data storage)")


class StartIngestionResponse(BaseModel):
	"""Response model for starting ingestion."""
	job_id: str = Field(..., description="Job ID for tracking workflow progress")
	workflow_id: str = Field(..., description="Temporal workflow execution ID")
	status: str = Field(..., description="Initial workflow status (usually 'queued')")
	estimated_duration_seconds: int = Field(..., description="Estimated duration in seconds")
	message: str = Field(..., description="Human-readable status message")


# ============================================================================
# Phase 6.2: Graph Query API Request/Response Models
# ============================================================================

class GraphQueryRequest(BaseModel):
	"""Request model for graph queries."""
	query_type: Literal[
		"find_shortest_path",
		"get_adjacent_screens",
		"search_screens",
		"get_transitions",
	] = Field(..., description="Type of graph query to execute")
	
	# Parameters for find_shortest_path
	source_screen_id: str | None = Field(None, description="Source screen ID (for find_shortest_path, get_transitions)")
	target_screen_id: str | None = Field(None, description="Target screen ID (for find_shortest_path)")
	
	# Parameters for search_screens
	screen_name: str | None = Field(None, description="Screen name pattern (for search_screens)")
	website_id: str | None = Field(None, description="Website ID (for search_screens, get_adjacent_screens)")
	
	# Common parameters
	limit: int = Field(100, description="Maximum number of results to return")


class GraphQueryResponse(BaseModel):
	"""Response model for graph queries."""
	query_type: str = Field(..., description="Type of query executed")
	results: list[Any] = Field(..., description="Query results")
	count: int = Field(..., description="Number of results returned")
	execution_time_ms: float = Field(..., description="Query execution time in milliseconds")


# ============================================================================
# Phase 6.4: Workflow Status API Response Models
# ============================================================================

class WorkflowStatusResponse(BaseModel):
	"""Response model for workflow status."""
	job_id: str = Field(..., description="Job ID")
	workflow_id: str = Field(..., description="Temporal workflow execution ID")
	status: str = Field(..., description="Current workflow status")
	phase: str | None = Field(None, description="Current phase name")
	progress: float = Field(..., description="Progress percentage (0-100)")
	errors: list[str] = Field(default_factory=list, description="List of error messages")
	warnings: list[str] = Field(default_factory=list, description="List of warning messages")
	checkpoints: list[dict[str, Any]] = Field(default_factory=list, description="List of processing checkpoints")
	metadata: dict[str, Any] = Field(default_factory=dict, description="Additional workflow metadata")
	created_at: str = Field(..., description="Creation timestamp (ISO format)")
	updated_at: str = Field(..., description="Last update timestamp (ISO format)")


# ============================================================================
# Phase 6.5: Verification API Request/Response Models
# ============================================================================

class VerificationRequest(BaseModel):
	"""Request model for starting verification workflow."""
	target_type: Literal["screen", "task", "action"] = Field(..., description="Type of knowledge entity to verify")
	target_id: str = Field(..., description="ID of the entity to verify")
	verification_options: dict[str, Any] = Field(default_factory=dict, description="Verification options")


class VerificationResponse(BaseModel):
	"""Response model for verification workflow."""
	verification_job_id: str = Field(..., description="Verification job ID for tracking")
	target_type: str = Field(..., description="Type of entity being verified")
	target_id: str = Field(..., description="ID of entity being verified")
	status: str = Field(..., description="Initial verification status")
	message: str = Field(..., description="Status message")

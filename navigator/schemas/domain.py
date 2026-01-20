"""
Knowledge extraction and ingestion data schemas.

This module defines Pydantic models for all knowledge-related data structures including
source types, metadata, ingestion results, and extracted knowledge entities.
"""

import logging
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)


# =============================================================================
# Source Type Definitions
# =============================================================================

class SourceType(str, Enum):
	"""
	Types of content sources that can be ingested.
	
	- TECHNICAL_DOCUMENTATION: Structured documents (Markdown, HTML, PDF)
	- WEBSITE_DOCUMENTATION: Cursor-style website crawling with navigation
	- VIDEO_WALKTHROUGH: Demo and tutorial videos with visual content
	"""

	TECHNICAL_DOCUMENTATION = "technical_documentation"
	WEBSITE_DOCUMENTATION = "website_documentation"
	VIDEO_WALKTHROUGH = "video_walkthrough"


class DocumentFormat(str, Enum):
	"""Supported document formats for technical documentation."""

	MARKDOWN = "markdown"
	HTML = "html"
	PDF = "pdf"
	PLAIN_TEXT = "plain_text"
	DOCX = "docx"
	UNKNOWN = "unknown"


class VideoFormat(str, Enum):
	"""Supported video formats for video ingestion."""

	MP4 = "mp4"
	WEBM = "webm"
	AVI = "avi"
	MOV = "mov"
	MKV = "mkv"
	UNKNOWN = "unknown"


# =============================================================================
# Source Metadata
# =============================================================================

class SourceMetadata(BaseModel):
	"""
	Metadata about an ingested source.
	
	This model captures essential information about the source content including
	type, location, format, and temporal attributes.
	"""

	model_config = ConfigDict(
		extra='forbid',
		validate_assignment=True,
	)

	# Source identification
	source_type: SourceType = Field(description="Type of the source content")
	url: str | None = Field(default=None, description="Source URL or file path")
	title: str | None = Field(default=None, description="Title of the source content")

	# Format and structure
	format: DocumentFormat | VideoFormat | None = Field(
		default=None,
		description="Format of the source content"
	)
	size_bytes: int | None = Field(default=None, description="Size of the source in bytes", ge=0)

	# Temporal attributes
	last_modified: datetime | None = Field(
		default=None,
		description="Last modification timestamp of the source"
	)
	ingested_at: datetime = Field(
		default_factory=datetime.utcnow,
		description="Timestamp when source was ingested"
	)

	# Additional metadata
	author: str | None = Field(default=None, description="Author or creator of the content")
	tags: list[str] = Field(default_factory=list, description="Tags or keywords for categorization")
	language: str | None = Field(default=None, description="Primary language of the content")
	
	# Video-specific metadata
	thumbnails: list[str] = Field(
		default_factory=list,
		description="List of thumbnail file paths (for video sources)"
	)

	@field_validator('url')
	@classmethod
	def validate_url(cls, v: str | None) -> str | None:
		"""Validate URL format if provided."""
		if v is None:
			return v

		# Check if it's a file path (starts with /)
		if v.startswith('/'):
			return v

		# Validate as URL
		try:
			parsed = urlparse(v)
			if not parsed.scheme:
				logger.warning(f"URL missing scheme: {v}")
			if not parsed.netloc and not v.startswith('file://'):
				logger.warning(f"URL missing netloc: {v}")
			return v
		except Exception as e:
			logger.error(f"Invalid URL format: {v} - {e}")
			raise ValueError(f"Invalid URL format: {v}")


# =============================================================================
# Ingestion Results
# =============================================================================

class ContentChunk(BaseModel):
	"""
	A chunk of processed content.
	
	Content is split into chunks for processing and storage. Each chunk maintains
	references to its source and position within the original content.
	"""

	model_config = ConfigDict(extra='forbid')

	chunk_id: str = Field(description="Unique identifier for this chunk")
	content: str = Field(description="The actual content text")
	chunk_index: int = Field(description="Position of this chunk in the source", ge=0)
	token_count: int = Field(description="Approximate token count", ge=0)

	# Metadata
	chunk_type: str | None = Field(
		default=None,
		description="Type of content (e.g., 'heading', 'code_block', 'paragraph')"
	)
	section_title: str | None = Field(
		default=None,
		description="Title of the section this chunk belongs to"
	)
	page_number: int | None = Field(default=None, description="Page number (for paginated content)")

	# References
	start_offset: int | None = Field(default=None, description="Character offset in source")
	end_offset: int | None = Field(default=None, description="End character offset in source")


class IngestionError(BaseModel):
	"""Record of an error encountered during ingestion."""

	model_config = ConfigDict(extra='forbid')

	error_type: str = Field(description="Type of error (e.g., 'ParsingError', 'NetworkError')")
	error_message: str = Field(description="Human-readable error message")
	timestamp: datetime = Field(default_factory=datetime.utcnow)
	context: dict[str, Any] = Field(
		default_factory=dict,
		description="Additional context about where the error occurred"
	)


class IngestionResult(BaseModel):
	"""
	Result of a source ingestion operation.
	
	This model captures the outcome of ingesting a single source, including
	all generated chunks, metadata, and any errors encountered.
	"""

	model_config = ConfigDict(extra='forbid')

	# Identification
	ingestion_id: str = Field(description="Unique ID for this ingestion operation")
	source_type: SourceType = Field(description="Detected or provided source type")

	# Results
	content_chunks: list[ContentChunk] = Field(
		default_factory=list,
		description="Processed content chunks"
	)
	metadata: SourceMetadata = Field(description="Source metadata")

	# Statistics
	total_chunks: int = Field(default=0, description="Total number of chunks created", ge=0)
	total_tokens: int = Field(
		default=0,
		description="Total approximate token count across all chunks",
		ge=0
	)

	# Status and errors
	success: bool = Field(default=True, description="Whether ingestion was successful")
	errors: list[IngestionError] = Field(
		default_factory=list,
		description="List of errors encountered"
	)

	# Timestamps
	started_at: datetime = Field(default_factory=datetime.utcnow)
	completed_at: datetime | None = Field(default=None)

	def add_error(self, error_type: str, error_message: str, context: dict[str, Any] | None = None) -> None:
		"""Add an error to the result."""
		self.errors.append(IngestionError(
			error_type=error_type,
			error_message=error_message,
			context=context or {}
		))
		self.success = False

	def mark_complete(self) -> None:
		"""Mark ingestion as complete."""
		self.completed_at = datetime.utcnow()
		self.total_chunks = len(self.content_chunks)
		self.total_tokens = sum(chunk.token_count for chunk in self.content_chunks)


# =============================================================================
# Source Type Detection
# =============================================================================

def detect_source_type(source_url: str) -> SourceType:
	"""
	Detect source type from URL or file path.
	
	Args:
		source_url: URL or file path of the source
	
	Returns:
		Detected SourceType
	
	Examples:
		>>> detect_source_type("/path/to/doc.md")
		SourceType.TECHNICAL_DOCUMENTATION
		>>> detect_source_type("https://docs.example.com/api")
		SourceType.WEBSITE_DOCUMENTATION
		>>> detect_source_type("/videos/tutorial.mp4")
		SourceType.VIDEO_WALKTHROUGH
	"""
	url_lower = source_url.lower()

	# Check for video formats
	video_extensions = ['.mp4', '.webm', '.avi', '.mov', '.mkv']
	if any(url_lower.endswith(ext) for ext in video_extensions):
		return SourceType.VIDEO_WALKTHROUGH

	# Check for document formats
	doc_extensions = ['.md', '.markdown', '.html', '.htm', '.pdf', '.txt']
	if any(url_lower.endswith(ext) for ext in doc_extensions):
		return SourceType.TECHNICAL_DOCUMENTATION

	# Check if it's a web URL
	parsed = urlparse(source_url)
	if parsed.scheme in ['http', 'https'] and parsed.netloc:
		return SourceType.WEBSITE_DOCUMENTATION

	# Default to documentation for file paths
	if source_url.startswith('/') or source_url.startswith('./'):
		return SourceType.TECHNICAL_DOCUMENTATION

	# Default to website for everything else
	logger.warning(f"Could not determine source type for {source_url}, defaulting to WEBSITE_DOCUMENTATION")
	return SourceType.WEBSITE_DOCUMENTATION


# =============================================================================
# Video Frame Analysis Schemas (Structured Outputs)
# =============================================================================

class UIElement(BaseModel):
	"""Single UI element detected in a video frame."""

	model_config = ConfigDict(extra='forbid')

	type: str = Field(description="UI element type (button, form, menu, etc.)")
	label: str | None = Field(default=None, description="Label or text content of the element")
	position: dict[str, Any] | None = Field(default=None, description="Position information (x, y, width, height)")
	state: str | None = Field(default=None, description="Element state (active, hover, disabled, etc.)")


class DataElement(BaseModel):
	"""Data element (table, list, card) detected in a video frame."""

	model_config = ConfigDict(extra='forbid')

	type: str = Field(description="Data element type (table, list, card, etc.)")
	# Content can be: string (text), dict (single object), or list[dict] (table rows)
	content: str | dict[str, Any] | list[dict[str, Any]] = Field(description="Content of the data element")


class VisualIndicator(BaseModel):
	"""Visual indicator (loading, error, success) detected in a video frame."""

	model_config = ConfigDict(extra='forbid')

	type: str = Field(description="Indicator type (loading, error, success, warning, info)")
	message: str | None = Field(default=None, description="Message or text associated with the indicator")


class FrameAnalysisResponse(BaseModel):
	"""
	Structured response model for video frame analysis.
	
	This model enforces a consistent structure for LLM vision analysis responses,
	ensuring reliable parsing and validation for knowledge extraction.
	"""

	model_config = ConfigDict(extra='forbid')

	# Core frame information
	ui_elements: list[UIElement] = Field(
		default_factory=list,
		description="List of all visible UI elements (buttons, forms, menus, etc.)"
	)
	screen_state: str = Field(
		default="Unknown",
		description="Current screen/page state (exact screen name, page type, application state)"
	)
	business_function: str = Field(
		default="",
		description="Business function being demonstrated (what domain/application?)"
	)
	operational_aspect: str = Field(
		default="",
		description="Operational workflow step (what process/step?)"
	)
	visible_actions: list[str] = Field(
		default_factory=list,
		description="All visible user interactions (cursor position, hover states, active states, etc.)"
	)
	visible_text: str = Field(
		default="",
		description="All text visible on screen (labels, headings, body text, button text, etc.)"
	)
	layout_structure: str | None = Field(
		default=None,
		description="Description of page layout (sections, columns, regions)"
	)
	data_elements: list[DataElement] = Field(
		default_factory=list,
		description="Data visible (tables, lists, cards, any displayed data)"
	)
	visual_indicators: list[VisualIndicator] = Field(
		default_factory=list,
		description="Visual indicators (loading states, success indicators, error states, etc.)"
	)

	@classmethod
	def from_dict(cls, data: dict[str, Any]) -> "FrameAnalysisResponse":
		"""
		Create FrameAnalysisResponse from dictionary with validation.
		
		This method ensures proper parsing even if LLM returns slightly malformed JSON.
		"""
		# Normalize UI elements
		ui_elements = []
		for elem in data.get('ui_elements', []):
			if isinstance(elem, dict):
				# Normalize position: convert string to dict if needed
				position = elem.get('position')
				if isinstance(position, str):
					# Convert string position like 'top-left' to dict format
					position_map = {
						'top-left': {'x': 'left', 'y': 'top'},
						'top-right': {'x': 'right', 'y': 'top'},
						'top-center': {'x': 'center', 'y': 'top'},
						'bottom-left': {'x': 'left', 'y': 'bottom'},
						'bottom-right': {'x': 'right', 'y': 'bottom'},
						'bottom-center': {'x': 'center', 'y': 'bottom'},
						'center': {'x': 'center', 'y': 'center'},
						'left-sidebar': {'x': 'left', 'y': 'center'},
						'right-sidebar': {'x': 'right', 'y': 'center'},
						'main-content': {'x': 'center', 'y': 'center'},
					}
					position = position_map.get(position.lower(), {'region': position})

				try:
					ui_elements.append(UIElement(
						type=elem.get('type', 'unknown'),
						label=elem.get('label'),
						position=position if isinstance(position, dict) else None,
						state=elem.get('state'),
					))
				except Exception:
					# Fallback: create minimal UI element
					ui_elements.append(UIElement(
						type=elem.get('type', 'unknown'),
						label=elem.get('label'),
						position=position if isinstance(position, dict) else None,
						state=elem.get('state'),
					))

		# Normalize data elements
		data_elements = []
		for elem in data.get('data_elements', []):
			if isinstance(elem, dict):
				# Normalize content: handle various formats (str, dict, list[dict])
				content = elem.get('content')

				# Convert content to appropriate type
				if content is None:
					content = ''
				elif isinstance(content, (str, dict, list)):
					# Already in valid format (str, dict, or list[dict])
					pass
				else:
					# Convert other types to string representation
					content = str(content)

				try:
					data_elements.append(DataElement(
						type=elem.get('type', 'unknown'),
						content=content,
					))
				except Exception as e:
					# Fallback: create minimal data element with string content
					# If content is complex, convert to string representation
					if isinstance(content, (dict, list)):
						content_str = str(content)
					else:
						content_str = content if isinstance(content, str) else str(content)

					data_elements.append(DataElement(
						type=elem.get('type', 'unknown'),
						content=content_str,
					))

		# Normalize visual indicators
		visual_indicators = []
		for indicator in data.get('visual_indicators', []):
			if isinstance(indicator, dict):
				try:
					visual_indicators.append(VisualIndicator(**indicator))
				except Exception:
					# Fallback: create minimal visual indicator
					visual_indicators.append(VisualIndicator(
						type=indicator.get('type', 'unknown'),
						message=indicator.get('message'),
					))

		return cls(
			ui_elements=ui_elements,
			screen_state=data.get('screen_state', 'Unknown'),
			business_function=data.get('business_function', ''),
			operational_aspect=data.get('operational_aspect', ''),
			visible_actions=data.get('visible_actions', []),
			visible_text=data.get('visible_text', ''),
			layout_structure=data.get('layout_structure'),
			data_elements=data_elements,
			visual_indicators=visual_indicators,
		)


def detect_document_format(file_path: str) -> DocumentFormat:
	"""
	Detect document format from file path.
	
	Args:
		file_path: Path to the document file
	
	Returns:
		Detected DocumentFormat
	"""
	path_lower = file_path.lower()

	if path_lower.endswith('.md') or path_lower.endswith('.markdown'):
		return DocumentFormat.MARKDOWN
	elif path_lower.endswith('.html') or path_lower.endswith('.htm'):
		return DocumentFormat.HTML
	elif path_lower.endswith('.pdf'):
		return DocumentFormat.PDF
	elif path_lower.endswith('.txt') or path_lower.endswith('.text'):
		return DocumentFormat.PLAIN_TEXT
	elif path_lower.endswith('.docx') or path_lower.endswith('.doc'):
		return DocumentFormat.DOCX
	else:
		return DocumentFormat.UNKNOWN


def detect_video_format(file_path: str) -> VideoFormat:
	"""
	Detect video format from file path.
	
	Args:
		file_path: Path to the video file
	
	Returns:
		Detected VideoFormat
	"""
	path_lower = file_path.lower()

	if path_lower.endswith('.mp4'):
		return VideoFormat.MP4
	elif path_lower.endswith('.webm'):
		return VideoFormat.WEBM
	elif path_lower.endswith('.avi'):
		return VideoFormat.AVI
	elif path_lower.endswith('.mov'):
		return VideoFormat.MOV
	elif path_lower.endswith('.mkv'):
		return VideoFormat.MKV
	else:
		return VideoFormat.UNKNOWN

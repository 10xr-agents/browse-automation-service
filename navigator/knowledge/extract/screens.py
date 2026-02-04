"""
Screen extraction from ingested content.

Extracts screen definitions with critical focus on:
- **Negative indicators** (Agent-Killer edge case #2): Distinguishing features
- State signatures for accurate screen recognition
- URL pattern extraction
- UI element identification with affordances
"""

import hashlib
import logging
import re
from collections import Counter
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from navigator.schemas import ContentChunk

logger = logging.getLogger(__name__)


# =============================================================================
# Screen Definition Models (aligned with KNOWLEDGE_SCHEMA_DESIGN.md)
# =============================================================================

class Indicator(BaseModel):
	"""State signature indicator."""
	type: str = Field(..., description="Indicator type (dom_contains, url_matches, etc.)")
	value: str | None = Field(None, description="Value to match")
	pattern: str | None = Field(None, description="Pattern to match")
	selector: str | None = Field(None, description="CSS/XPath selector")
	reason: str | None = Field(None, description="Explanation of this indicator")

	@field_validator('type')
	@classmethod
	def validate_type(cls, v: str) -> str:
		valid_types = ['dom_contains', 'url_matches', 'url_exact', 'dom_class', 'dom_id', 'dom_attribute']
		if v not in valid_types:
			raise ValueError(f"Invalid indicator type: {v}. Must be one of {valid_types}")
		return v


class StateSignature(BaseModel):
	"""Screen state signature for recognition."""
	required_indicators: list[Indicator] = Field(default_factory=list, description="Must be present")
	optional_indicators: list[Indicator] = Field(default_factory=list, description="May be present")
	exclusion_indicators: list[Indicator] = Field(default_factory=list, description="Must NOT be present")
	negative_indicators: list[Indicator] = Field(
		default_factory=list,
		description="Agent-Killer: Distinguishing features (e.g., 'Delete button = Edit mode, NOT Create mode')"
	)


class SelectorStrategy(BaseModel):
	"""Element selector strategy."""
	type: str = Field(..., description="Strategy type (semantic, dom_index, xpath, css)")
	label_contains: str | None = Field(None, description="Label text for semantic selection")
	text_contains: str | None = Field(None, description="Button/link text for semantic selection")
	field_type: str | None = Field(None, description="Input field type")
	button_type: str | None = Field(None, description="Button type")
	index: str | None = Field(None, description="DOM index (parameterized)")
	xpath: str | None = Field(None, description="XPath selector")
	css: str | None = Field(None, description="CSS selector")
	fallback: bool = Field(default=False, description="Whether this is a fallback strategy")


class ElementSelector(BaseModel):
	"""UI element selector."""
	strategies: list[SelectorStrategy] = Field(..., description="Selection strategies (ordered by preference)")
	parameterized: bool = Field(default=False, description="Whether selector uses parameters")


class Affordance(BaseModel):
	"""Action affordance for UI element."""
	action_type: str = Field(..., description="Action type (click, type, select_option, etc.)")
	required: bool = Field(default=False, description="Whether this action is required")
	validation: dict[str, Any] | None = Field(None, description="Validation rules")
	options: list[dict[str, Any]] | None = Field(None, description="For dropdowns/select elements")


class UIElement(BaseModel):
	"""UI element definition."""
	element_id: str = Field(..., description="Unique element identifier")
	type: str = Field(..., description="Element type (input, button, dropdown, link, etc.)")
	selector: ElementSelector = Field(..., description="Selector strategies")
	affordances: list[Affordance] = Field(default_factory=list, description="Available actions")
	metadata: dict[str, Any] = Field(default_factory=dict, description="Element metadata")
	
	# Phase 8: Spatial Information
	position: dict[str, Any] | None = Field(
		None,
		description="Element position: {x, y, width, height, bounding_box: {x, y, width, height}}"
	)
	layout_context: str | None = Field(
		None,
		description="Layout context: 'header', 'sidebar', 'main', 'footer', 'modal', 'navigation'"
	)
	visual_hierarchy: int | None = Field(
		None,
		description="Visual hierarchy level (1=most important, higher=less important)"
	)
	visual_properties: dict[str, Any] | None = Field(
		None,
		description="Visual properties: {z_index, font_size, color, background, opacity, visibility, display, position}"
	)
	importance_score: float | None = Field(
		None,
		ge=0.0,
		le=1.0,
		description="Visual importance score (0-1, higher=more important)"
	)


class ScreenRegion(BaseModel):
	"""Screen region definition (Phase 8: Spatial Information)."""
	region_id: str = Field(..., description="Unique region identifier")
	region_type: str = Field(..., description="Region type: 'header', 'sidebar', 'main', 'footer', 'modal', 'navigation'")
	bounds: dict[str, Any] = Field(..., description="Region bounds: {x, y, width, height}")
	ui_element_ids: list[str] = Field(default_factory=list, description="UI element IDs in this region")
	metadata: dict[str, Any] = Field(default_factory=dict, description="Region metadata")


class ScreenDefinition(BaseModel):
	"""Complete screen definition (aligned with MongoDB schema)."""
	screen_id: str = Field(..., description="Unique screen identifier")
	name: str = Field(..., description="Human-readable screen name")
	website_id: str = Field(..., description="Website identifier")
	url_patterns: list[str] = Field(default_factory=list, description="URL regex patterns")
	state_signature: StateSignature = Field(..., description="State recognition signature")
	ui_elements: list[UIElement] = Field(default_factory=list, description="UI elements on this screen")
	metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

	# Cross-reference fields (Phase 1: Schema Updates)
	business_function_ids: list[str] = Field(
		default_factory=list,
		description="Business function IDs this screen supports"
	)
	user_flow_ids: list[str] = Field(
		default_factory=list,
		description="User flow IDs that use this screen"
	)
	task_ids: list[str] = Field(
		default_factory=list,
		description="Task IDs that can be performed on this screen"
	)
	action_ids: list[str] = Field(
		default_factory=list,
		description="Action IDs available on this screen"
	)
	incoming_transitions: list[str] = Field(
		default_factory=list,
		description="Transition IDs that lead TO this screen"
	)
	outgoing_transitions: list[str] = Field(
		default_factory=list,
		description="Transition IDs that lead FROM this screen"
	)
	workflow_ids: list[str] = Field(
		default_factory=list,
		description="Workflow IDs that include this screen"
	)
	
	# Content type classification (Phase 1: Content Type Separation)
	content_type: str = Field(
		default="web_ui",
		description="Content type: 'web_ui' | 'documentation' | 'video_transcript' | 'api_docs'"
	)
	is_actionable: bool = Field(
		default=True,
		description="Whether this screen can be navigated to by browser automation"
	)
	
	# Phase 8: Spatial Information
	regions: list[ScreenRegion] = Field(
		default_factory=list,
		description="Screen regions (header, sidebar, main, footer, etc.)"
	)
	layout_structure: dict[str, Any] | None = Field(
		None,
		description="Layout structure: {type: 'grid'|'flexbox'|'columns', columns: int, sections: list, grid: dict}"
	)

	@field_validator('url_patterns')
	@classmethod
	def validate_url_patterns(cls, v: list[str]) -> list[str]:
		"""Validate URL patterns are valid regex."""
		for pattern in v:
			try:
				re.compile(pattern)
			except re.error as e:
				raise ValueError(f"Invalid regex pattern '{pattern}': {e}")
		return v
	
	@field_validator('content_type')
	@classmethod
	def validate_content_type(cls, v: str) -> str:
		"""Validate content type."""
		valid_types = ['web_ui', 'documentation', 'video_transcript', 'api_docs', 'unknown']
		if v not in valid_types:
			raise ValueError(f"Invalid content_type: {v}. Must be one of {valid_types}")
		return v


# =============================================================================
# Screen Extraction Result
# =============================================================================

class ScreenExtractionResult(BaseModel):
	"""Result of screen extraction."""
	extraction_id: str = Field(default_factory=lambda: str(uuid4()), description="Extraction ID")
	screens: list[ScreenDefinition] = Field(default_factory=list, description="Extracted screens")
	success: bool = Field(default=True, description="Whether extraction succeeded")
	errors: list[dict[str, Any]] = Field(default_factory=list, description="Extraction errors")
	statistics: dict[str, Any] = Field(default_factory=dict, description="Extraction statistics")

	def add_error(self, error_type: str, message: str, context: dict[str, Any] | None = None) -> None:
		"""Add an error to the result."""
		self.errors.append({
			'type': error_type,
			'message': message,
			'context': context or {}
		})
		self.success = False

	def calculate_statistics(self) -> None:
		"""Calculate extraction statistics."""
		# Priority 9: Include extraction statistics for visualization
		extraction_stats = ScreenExtractor.generate_extraction_statistics(
			ScreenExtractionResult(screens=self.screens, errors=[])
		)
		
		self.statistics = {
			'total_screens': len(self.screens),
			'screens_with_negative_indicators': sum(
				1 for s in self.screens if s.state_signature.negative_indicators
			),
			'total_ui_elements': sum(len(s.ui_elements) for s in self.screens),
			'screens_with_url_patterns': sum(1 for s in self.screens if s.url_patterns),
			'avg_negative_indicators_per_screen': (
				sum(len(s.state_signature.negative_indicators) for s in self.screens) / len(self.screens)
				if self.screens else 0
			),
			# Content type statistics (Phase 1)
			'web_ui_screens': sum(1 for s in self.screens if s.content_type == "web_ui"),
			'documentation_screens': sum(1 for s in self.screens if s.content_type == "documentation"),
			'actionable_screens': sum(1 for s in self.screens if s.is_actionable),
			'non_actionable_screens': sum(1 for s in self.screens if not s.is_actionable),
			# Priority 9: Extraction statistics for visualization
			'extraction_sources': extraction_stats.get('extraction_sources', {}),
			'confidence_distribution': extraction_stats.get('confidence_distribution', {}),
			'average_confidence': extraction_stats.get('average_confidence', 0.0),
			'cross_reference_matches': extraction_stats.get('cross_reference_matches', 0),
		}


# =============================================================================
# Screen Extractor
# =============================================================================

class ScreenExtractor:
	"""
	Extracts screen definitions from content chunks.
	
	Features:
	- **Negative indicator extraction** (Agent-Killer edge case #2)
	- State signature extraction for accurate recognition
	- URL pattern generation and validation
	- UI element identification with affordances
	- Schema validation
	"""

	def __init__(
		self,
		website_id: str = "unknown",
		confidence_threshold: float = 0.3,
		knowledge_id: str | None = None
	):
		"""
		Initialize screen extractor.
		
		Args:
			website_id: Website identifier for extracted screens
			confidence_threshold: Minimum confidence threshold for auto-rejection (Priority 9, default: 0.3)
			knowledge_id: Optional knowledge ID for cross-reference validation (Priority 9)
		"""
		self.website_id = website_id
		self.confidence_threshold = confidence_threshold
		self.knowledge_id = knowledge_id

	async def extract_screens(self, content_chunks: list[ContentChunk]) -> ScreenExtractionResult:
		"""
		Extract screen definitions from content chunks.
		
		Args:
			content_chunks: Content chunks to extract screens from
		
		Returns:
			ScreenExtractionResult with extracted screens
		"""
		result = ScreenExtractionResult()

		try:
			# Extract screens from content
			logger.info(f"Extracting screens from {len(content_chunks)} content chunks")

			for chunk in content_chunks:
				screens = self._extract_screens_from_chunk(chunk)
				
				# Classify screens and set content_type and is_actionable
				for screen in screens:
					# Use extraction_source to determine content type
					extraction_source = screen.metadata.get('extraction_source', 'unknown')
					extraction_confidence = screen.metadata.get('extraction_confidence', 0.5)
					
					# Web UI screens from DOM are always actionable
					if extraction_source == 'web_ui_dom':
						screen.content_type = "web_ui"
						screen.is_actionable = True
					else:
						# For other sources, check if it's actually a web UI screen
						is_web_ui = self._is_web_ui_screen(chunk.content, screen.name)
						if is_web_ui:
							screen.content_type = "web_ui"
							screen.is_actionable = True
						else:
							screen.content_type = "documentation"
							screen.is_actionable = False
					
					# Log extraction details for visibility
					logger.info(
						f"📊 Screen '{screen.name[:50]}...' - "
						f"Source: {extraction_source}, "
						f"Confidence: {extraction_confidence:.2f}, "
						f"Type: {screen.content_type}, "
						f"Actionable: {screen.is_actionable}"
					)
				
				result.screens.extend(screens)

			# Deduplicate screens
			result.screens = self._deduplicate_screens(result.screens)

			# Priority 9: Auto-reject screens below confidence threshold
			rejected_screens = []
			accepted_screens = []
			for screen in result.screens:
				extraction_confidence = screen.metadata.get('extraction_confidence', 0.5)
				if extraction_confidence < self.confidence_threshold:
					rejected_screens.append(screen)
					result.add_error(
						"LowConfidenceRejection",
						f"Screen '{screen.screen_id}' rejected due to low confidence ({extraction_confidence:.2f} < {self.confidence_threshold})",
						{
							"screen_id": screen.screen_id,
							"screen_name": screen.name,
							"confidence": extraction_confidence,
							"threshold": self.confidence_threshold
						}
					)
					logger.info(
						f"❌ Priority 9: Rejected screen '{screen.name}' due to low confidence "
						f"({extraction_confidence:.2f} < {self.confidence_threshold})"
					)
				else:
					accepted_screens.append(screen)
			
			# Update result with only accepted screens
			result.screens = accepted_screens
			if rejected_screens:
				logger.info(
					f"Priority 9: Auto-rejected {len(rejected_screens)} screens below confidence threshold "
					f"({self.confidence_threshold})"
				)

			# Priority 9: Cross-reference validation (check if extracted screen names match existing screens)
			await self._validate_cross_references(result)

			# Validate extracted screens
			for screen in result.screens:
				validation_errors = self._validate_screen(screen)
				if validation_errors:
					result.add_error(
						"ValidationError",
						f"Screen '{screen.screen_id}' failed validation",
						{"screen_id": screen.screen_id, "errors": validation_errors}
					)

			# Calculate statistics
			result.calculate_statistics()

			# Count actionable vs non-actionable screens
			actionable_count = sum(1 for s in result.screens if s.is_actionable)
			web_ui_count = sum(1 for s in result.screens if s.content_type == "web_ui")
			doc_count = sum(1 for s in result.screens if s.content_type == "documentation")

			# Calculate extraction source statistics
			source_stats = {}
			confidence_stats = {'high': 0, 'medium': 0, 'low': 0}
			for screen in result.screens:
				source = screen.metadata.get('extraction_source', 'unknown')
				source_stats[source] = source_stats.get(source, 0) + 1
				confidence = screen.metadata.get('extraction_confidence', 0.5)
				if confidence >= 0.7:
					confidence_stats['high'] += 1
				elif confidence >= 0.4:
					confidence_stats['medium'] += 1
				else:
					confidence_stats['low'] += 1
			
			logger.info(
				f"✅ Extracted {result.statistics['total_screens']} screens "
				f"({result.statistics['screens_with_negative_indicators']} with negative indicators) - "
				f"{web_ui_count} web UI (actionable: {actionable_count}), {doc_count} documentation"
			)
			logger.info(
				f"📊 Extraction sources: {source_stats} | "
				f"Confidence: {confidence_stats['high']} high, {confidence_stats['medium']} medium, {confidence_stats['low']} low"
			)

		except Exception as e:
			logger.error(f"❌ Error extracting screens: {e}", exc_info=True)
			result.add_error("ExtractionError", str(e), {"exception_type": type(e).__name__})

		return result

	def _extract_screens_from_chunk(self, chunk: ContentChunk) -> list[ScreenDefinition]:
		"""
		Extract screens from a single content chunk.
		
		Tracks what we capture and how it relates to knowledge:
		- extraction_source: Where the screen name came from (web_ui_dom, documentation_heading, section_title, etc.)
		- extraction_confidence: How confident we are this is a real screen (0.0-1.0)
		- extraction_context: What was matched and why
		
		Args:
			chunk: Content chunk to process
		
		Returns:
			List of extracted screen definitions with extraction metadata
		"""
		screens = []
		
		# Check if this chunk already has an extracted screen (from authenticated portal crawling)
		if chunk.metadata and chunk.metadata.get('extracted_screen'):
			# This is a web UI screen extracted from browser DOM
			try:
				screen_dict = chunk.metadata['extracted_screen']
				screen = ScreenDefinition(**screen_dict)
				# Add extraction metadata
				screen.metadata['extraction_source'] = 'web_ui_dom'
				screen.metadata['extraction_confidence'] = 0.95  # High confidence - from actual DOM
				screen.metadata['extraction_context'] = f"Extracted from browser DOM at URL: {chunk.metadata.get('url', 'unknown')}"
				screens.append(screen)
				logger.info(f"✅ Extracted web UI screen from DOM: {screen.name} (confidence: 0.95)")
				return screens
			except Exception as e:
				logger.warning(f"Failed to parse extracted_screen from metadata: {e}")

		# Pattern-based extraction from documentation/text content
		# Pattern 1: Look for headings that indicate screens/pages
		screen_patterns = [
			(r'##\s+([^\n<]{1,100}?)\s+(?:Screen|Page|Form|View|Dialog|Modal)', 'documentation_heading_with_keyword', 0.6),
			(r'(?:Screen|Page|Form|View):\s+([^\n<]{1,100})', 'documentation_label', 0.7),
			(r'### ([^\n<]{1,100}?)\s+(?:Screen|Page)', 'documentation_subheading', 0.5),
		]

		for pattern, source_type, base_confidence in screen_patterns:
			matches = re.finditer(pattern, chunk.content, re.IGNORECASE | re.MULTILINE)
			for match in matches:
				raw_capture = match.group(1).strip()
				original_capture = raw_capture  # Keep for logging
				
				# Clean up screen name: remove HTML tags, limit length, stop at first sentence
				screen_name = self._clean_screen_name(raw_capture)
				
				# Analyze what we captured
				capture_analysis = self._analyze_capture(raw_capture, screen_name, chunk)
				
				# Skip if name is too long or looks like content (not a proper screen name)
				if not self._is_valid_screen_name(screen_name):
					logger.debug(
						f"❌ Skipping invalid screen name from {source_type}: "
						f"'{screen_name[:50]}...' (original: '{original_capture[:50]}...') - "
						f"Reason: {capture_analysis.get('rejection_reason', 'unknown')}"
					)
					continue
				
				# Adjust confidence based on analysis
				confidence = self._calculate_extraction_confidence(
					screen_name, raw_capture, source_type, base_confidence, capture_analysis, chunk
				)
				
				screen_id = self._generate_screen_id(screen_name)

				# Extract context around the match
				start = max(0, match.start() - 500)
				end = min(len(chunk.content), match.end() + 1000)
				context = chunk.content[start:end]

				# Create basic screen definition
				screen = self._create_screen_from_context(screen_id, screen_name, context)
				
				# Add extraction metadata to track what we captured
				screen.metadata['extraction_source'] = source_type
				screen.metadata['extraction_confidence'] = confidence
				screen.metadata['extraction_context'] = (
					f"Matched pattern '{pattern[:50]}...' in {chunk.chunk_type} chunk. "
					f"Raw capture: '{original_capture[:100]}...'. "
					f"Cleaned to: '{screen_name}'. "
					f"Analysis: {capture_analysis.get('summary', 'N/A')}"
				)
				screen.metadata['raw_capture'] = original_capture[:200]  # Store original for debugging
				screen.metadata['capture_analysis'] = capture_analysis
				
				screens.append(screen)
				
				logger.info(
					f"📝 Extracted screen from {source_type}: '{screen_name}' "
					f"(confidence: {confidence:.2f}, original: '{original_capture[:50]}...')"
				)
		
		# Fallback: If no patterns matched, try extracting from section_title or first heading
		if not screens and chunk.section_title:
			screen_name = self._clean_screen_name(chunk.section_title)
			if self._is_valid_screen_name(screen_name):
				capture_analysis = self._analyze_capture(chunk.section_title, screen_name, chunk)
				confidence = self._calculate_extraction_confidence(
					screen_name, chunk.section_title, 'section_title', 0.4, capture_analysis, chunk
				)
				
				screen_id = self._generate_screen_id(screen_name)
				screen = self._create_screen_from_context(screen_id, screen_name, chunk.content)
				
				screen.metadata['extraction_source'] = 'section_title'
				screen.metadata['extraction_confidence'] = confidence
				screen.metadata['extraction_context'] = (
					f"Extracted from chunk.section_title: '{chunk.section_title}'. "
					f"Cleaned to: '{screen_name}'. "
					f"Analysis: {capture_analysis.get('summary', 'N/A')}"
				)
				screen.metadata['raw_capture'] = chunk.section_title
				screen.metadata['capture_analysis'] = capture_analysis
				
				screens.append(screen)
				logger.info(
					f"📝 Extracted screen from section_title fallback: '{screen_name}' "
					f"(confidence: {confidence:.2f})"
				)

		return screens
	
	def _analyze_capture(self, raw_capture: str, cleaned_name: str, chunk: ContentChunk) -> dict[str, Any]:
		"""
		Analyze what we captured to understand its relationship to knowledge.
		
		Args:
			raw_capture: Original text that was matched
			cleaned_name: Cleaned screen name
			chunk: Source content chunk
		
		Returns:
			Analysis dictionary with insights about the capture
		"""
		analysis = {
			'raw_length': len(raw_capture),
			'cleaned_length': len(cleaned_name),
			'length_reduction': len(raw_capture) - len(cleaned_name),
			'contains_html': '<' in raw_capture or '>' in raw_capture,
			'contains_newlines': '\n' in raw_capture,
			'word_count': len(cleaned_name.split()),
			'chunk_type': chunk.chunk_type,
			'is_likely_content': False,
			'is_likely_screen_name': False,
			'rejection_reason': None,
			'summary': ''
		}
		
		# Determine if this looks like content vs screen name
		if len(cleaned_name) > 100:
			analysis['is_likely_content'] = True
			analysis['rejection_reason'] = 'too_long'
			analysis['summary'] = f"Too long ({len(cleaned_name)} chars) - likely content, not screen name"
		elif len(cleaned_name.split()) > 10:
			analysis['is_likely_content'] = True
			analysis['rejection_reason'] = 'too_many_words'
			analysis['summary'] = f"Too many words ({len(cleaned_name.split())}) - likely content"
		elif any(keyword in cleaned_name.lower() for keyword in ['your primary goal', 'you should', 'instruction', 'guideline']):
			analysis['is_likely_content'] = True
			analysis['rejection_reason'] = 'documentation_keywords'
			analysis['summary'] = "Contains documentation keywords - likely instructional content"
		elif 2 <= len(cleaned_name) <= 50 and len(cleaned_name.split()) <= 5:
			analysis['is_likely_screen_name'] = True
			analysis['summary'] = f"Looks like a screen name ({len(cleaned_name)} chars, {len(cleaned_name.split())} words)"
		else:
			analysis['summary'] = f"Uncertain - {len(cleaned_name)} chars, {len(cleaned_name.split())} words"
		
		return analysis
	
	def _calculate_extraction_confidence(
		self,
		screen_name: str,
		raw_capture: str,
		source_type: str,
		base_confidence: float,
		analysis: dict[str, Any],
		chunk: ContentChunk
	) -> float:
		"""
		Calculate confidence that this is actually a screen name.
		
		Args:
			screen_name: Cleaned screen name
			raw_capture: Original capture
			source_type: Where it came from
			base_confidence: Base confidence for this source type
			analysis: Capture analysis
			chunk: Source chunk
		
		Returns:
			Confidence score (0.0-1.0)
		"""
		confidence = base_confidence
		
		# Boost confidence if it looks like a screen name
		if analysis.get('is_likely_screen_name'):
			confidence += 0.2
		
		# Reduce confidence if it looks like content
		if analysis.get('is_likely_content'):
			confidence -= 0.3
		
		# Boost confidence for web UI chunks
		if chunk.chunk_type == 'webpage':
			confidence += 0.1
		
		# Reduce confidence for documentation chunks
		if chunk.chunk_type in ['documentation', 'text_file']:
			confidence -= 0.1
		
		# Boost confidence if name is short and descriptive
		if 3 <= len(screen_name) <= 30 and len(screen_name.split()) <= 3:
			confidence += 0.1
		
		# Reduce confidence if name contains HTML
		if analysis.get('contains_html'):
			confidence -= 0.2
		
		# Clamp to [0.0, 1.0]
		confidence = max(0.0, min(1.0, confidence))
		
		return confidence
	
	def _clean_screen_name(self, name: str) -> str:
		"""
		Clean screen name by removing HTML, limiting length, and extracting just the title.
		
		Args:
			name: Raw screen name
		
		Returns:
			Cleaned screen name (max 100 chars, no HTML, first sentence only)
		"""
		# Remove HTML tags
		name = re.sub(r'<[^>]+>', '', name)
		
		# Remove HTML entities
		name = name.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
		
		# Stop at first sentence (period, exclamation, question mark) or newline
		name = re.split(r'[.!?\n]', name)[0]
		
		# Limit to 100 characters
		name = name[:100].strip()
		
		# Remove leading numbers and dots (e.g., "1. ", "2. ")
		name = re.sub(r'^\d+\.\s*', '', name)
		
		# Remove leading/trailing punctuation
		name = name.strip('.,;:!?')
		
		return name
	
	def _is_valid_screen_name(self, name: str) -> bool:
		"""
		Validate that a screen name is actually a screen name, not content.
		
		Args:
			name: Screen name to validate
		
		Returns:
			True if valid screen name, False if it looks like content
		"""
		if not name or len(name) < 2:
			return False
		
		# Too long = probably content, not a name
		if len(name) > 100:
			return False
		
		# Contains documentation keywords = not a screen name
		doc_keywords = [
			'your primary goal', 'you should', 'you must', 'instruction',
			'guideline', 'protocol', 'how to', 'conversational', 'phone call',
			'empathetic listener', 'follow-up questions', 'baseline emotional'
		]
		name_lower = name.lower()
		if any(keyword in name_lower for keyword in doc_keywords):
			return False
		
		# Contains HTML-like content = not a screen name
		if '<br' in name or '</' in name or '&nbsp;' in name:
			return False
		
		# Multiple sentences = probably content
		if name.count('.') > 1 or name.count('!') > 1 or name.count('?') > 1:
			return False
		
		# Very long words (likely concatenated content)
		words = name.split()
		if any(len(word) > 30 for word in words):
			return False
		
		return True

	def _is_web_ui_screen(self, context: str, screen_name: str) -> bool:
		"""
		Determine if this is a web UI screen or documentation.
		
		Args:
			context: Full context text from content chunk
			screen_name: Name of the screen
		
		Returns:
			True if this is a web UI screen, False if documentation
		"""
		# Documentation indicators (voice AI, conversational, instructional)
		doc_indicators = [
			"conversational", "phone call", "voice assistant", "voice ai",
			"follow-up questions", "empathetic listener", "conversation",
			"instruction", "guideline", "protocol", "how to",
			"your primary goal", "you should", "you must",
			"baseline emotional profile", "emotional intelligence",
			"core goal", "primary goal", "secondary goal"
		]
		
		context_lower = context.lower()
		name_lower = screen_name.lower()
		
		# If contains documentation keywords, it's not a web UI screen
		if any(indicator in context_lower or indicator in name_lower 
		       for indicator in doc_indicators):
			return False
		
		# Web UI indicators
		ui_indicators = [
			"dashboard", "form", "button", "input", "navigation",
			"page", "screen", "modal", "dialog", "menu", "link",
			"submit", "click", "navigate", "url", "route"
		]
		
		# Must have URL pattern or UI element mentions
		has_url = bool(re.search(r'https?://[^\s<>"{}|\\^`\[\]]+|/[\w/-]+', context))
		has_ui = any(indicator in context_lower or indicator in name_lower 
		            for indicator in ui_indicators)
		
		# Check for actual URL patterns (not generic paths)
		url_patterns = self._extract_url_patterns(context)
		has_specific_url = any(
			pattern.startswith('^https://') or pattern.startswith('^http://')
			for pattern in url_patterns
		)
		
		# If it has specific URLs or UI indicators, it's a web UI screen
		return has_specific_url or (has_url and has_ui)

	def _create_screen_from_context(
		self,
		screen_id: str,
		screen_name: str,
		context: str
	) -> ScreenDefinition:
		"""
		Create screen definition from extracted context.
		
		Args:
			screen_id: Screen identifier
			screen_name: Screen name
			context: Surrounding context text
		
		Returns:
			ScreenDefinition
		"""
		# Priority 4: Extract URL patterns with enhanced detection (pass screen_name for documentation detection)
		url_patterns = self._extract_url_patterns(context, screen_name)
		
		# Phase 9: Debug - log URL pattern extraction results
		if url_patterns:
			logger.debug(f"Extracted {len(url_patterns)} URL patterns for screen '{screen_name[:50]}'")
		else:
			logger.debug(f"No URL patterns extracted for screen '{screen_name[:50]}'")

		# Priority 4: Extract state signature (will return empty for documentation screens)
		state_signature = self._extract_state_signature(context, screen_name)

		# Extract UI elements
		ui_elements = self._extract_ui_elements(context)
		
		# Phase 8: Extract spatial information
		# Extract screen regions
		regions = self._extract_screen_regions(context, ui_elements)
		
		# Extract layout structure
		layout_structure = self._extract_layout_structure(context)

		# Phase 9: Determine content type and actionable status
		# Check if this is documentation content
		is_documentation = not self._is_web_ui_screen(context, screen_name)
		
		# Phase 9: If documentation doesn't have URLs, mark clearly as documentation-only
		# Also check if context actually contains URLs (not just empty extraction)
		has_urls_in_content = bool(re.search(r'https?://|www\.|/[a-z]{3,}', context, re.IGNORECASE))
		
		if is_documentation and not url_patterns:
			# Phase 9: Check if documentation content actually contains URLs
			if has_urls_in_content:
				# URLs exist but weren't extracted - log warning
				logger.warning(
					f"Documentation screen '{screen_name[:50]}' has URL-like content but no patterns extracted. "
					f"Context preview: {context[:200]}..."
				)
			content_type = "documentation"
			is_actionable = False
		elif is_documentation and url_patterns:
			# Documentation with URLs might still be actionable (e.g., API docs)
			content_type = "documentation"
			is_actionable = True
		elif not is_documentation and not url_patterns and has_urls_in_content:
			# Phase 9: Web UI screen but URLs weren't extracted - log warning
			logger.warning(
				f"Web UI screen '{screen_name[:50]}' has URL-like content but no patterns extracted. "
				f"May need better URL extraction."
			)
			content_type = "web_ui"
			is_actionable = True
		else:
			content_type = "web_ui"
			is_actionable = True
		
		return ScreenDefinition(
			screen_id=screen_id,
			name=screen_name,
			website_id=self.website_id,
			url_patterns=url_patterns,
			state_signature=state_signature,
			ui_elements=ui_elements,
			regions=regions,
			layout_structure=layout_structure,
			content_type=content_type,
			is_actionable=is_actionable,
			metadata={
				'extraction_method': 'rule_based',
				'extracted_from': 'documentation',
			}
		)

	def _extract_url_patterns(self, context: str, screen_name: str | None = None) -> list[str]:
		"""
		Extract URL patterns from context (Phase 4 & 9 improvements).
		
		Focuses on extracting specific, actionable URL patterns rather than
		generic paths that match too broadly.
		
		Phase 9: Enhanced with better relative URL handling, validation, and debugging.
		Priority 4: Skip URL pattern extraction for documentation content (unless real URLs exist).
		
		Args:
			context: Context text to extract from
			screen_name: Optional screen name for documentation detection
		"""
		patterns = []
		
		# Priority 4: Check if this is documentation content
		excluded_keywords = [
			'instruction', 'protocol', 'guideline', 'conversational',
			'phone call', 'voice assistant', 'empathetic listener',
			'primary goal', 'secondary goal', 'core goal',
			'follow-up question', 'exactly 4', 'exactly 5',
			'your primary', 'you should', 'you must', 'you need',
			'baseline emotional', 'emotional intelligence',
			'part a', 'part b', 'part c', 'part d',
			'quality checklist', 'internal', 'before responding',
			'never use', 'always use', 'critical', 'important',
			'example', 'note', 'warning', 'tip',
		]
		
		is_documentation = any(
			keyword in context.lower() or (screen_name and keyword in screen_name.lower())
			for keyword in excluded_keywords
		) or (screen_name and not self._is_web_ui_screen(context, screen_name))
		
		# Priority 4: For documentation, only extract real URLs (https:// or http://), not patterns from text
		if is_documentation:
			# Only extract full URLs (Pattern 1), skip relative paths and code examples
			url_pattern = r'https?://[^\s<>"{}|\\^`\[\]()]+(?:/[^\s<>"{}|\\^`\[\]()]*)?'
			matches = re.finditer(url_pattern, context)
			
			for match in matches:
				url = match.group(0).rstrip('.,;!?)')
				if not self._is_valid_url(url):
					logger.debug(f"Skipping invalid URL: {url}")
					continue
				
				# Convert to regex pattern
				pattern = re.escape(url)
				pattern = pattern.replace(r'\*', '.*')
				pattern = pattern.replace(r'\?', r'\?')
				pattern = f"^{pattern}(?:\\?.*)?(?:#.*)?$"
				
				if self._is_specific_url_pattern(pattern):
					patterns.append(pattern)
					logger.debug(f"Priority 4: Extracted real URL from documentation: {pattern}")
			
			if not patterns:
				logger.debug(
					f"Priority 4: Skipping URL pattern extraction for documentation screen "
					f"(no real URLs found, only text patterns)"
				)
			return patterns  # Return early for documentation - only real URLs
		
		# Phase 9: Debug - log if context contains any URL-like strings
		has_url_like_content = bool(re.search(r'https?://|www\.|/[a-z]', context, re.IGNORECASE))
		if not has_url_like_content:
			logger.debug("No URL-like content found in context for URL pattern extraction")
			return []

		# Pattern 1: Look for full URL mentions (https:// or http://)
		url_pattern = r'https?://[^\s<>"{}|\\^`\[\]()]+(?:/[^\s<>"{}|\\^`\[\]()]*)?'
		matches = re.finditer(url_pattern, context)

		for match in matches:
			url = match.group(0).rstrip('.,;!?)')  # Remove trailing punctuation
			# Phase 9: Validate URL format
			if not self._is_valid_url(url):
				logger.debug(f"Skipping invalid URL: {url}")
				continue
			
			# Convert to regex pattern
			# Escape special regex characters except for wildcards
			pattern = re.escape(url)
			pattern = pattern.replace(r'\*', '.*')
			# Phase 9: Allow query parameters and fragments
			pattern = pattern.replace(r'\?', r'\?')  # Keep ? escaped
			pattern = f"^{pattern}(?:\\?.*)?(?:#.*)?$"
			
			# Phase 9: Validate pattern is specific enough
			if self._is_specific_url_pattern(pattern):
				patterns.append(pattern)
				logger.debug(f"Extracted URL pattern: {pattern}")
		
		# Pattern 2: Look for domain + path patterns (more specific)
		domain_path_pattern = r'(?:https?://)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})(/[^\s<>"{}|\\^`\[\]()]+)?'
		domain_matches = re.finditer(domain_path_pattern, context)
		
		for match in domain_matches:
			domain = match.group(1)
			path = match.group(2) if match.group(2) else '/'
			
			# Phase 9: Only add if path is specific (not just '/')
			if path != '/' and len(path) > 2:
				# Create pattern: ^https?://domain.com/path.*
				escaped_path = re.escape(path.rstrip('.,;!?)'))
				# Allow trailing variations (query params, fragments)
				pattern = f"^https?://{re.escape(domain)}{escaped_path}(?:\\?.*)?(?:#.*)?$"
				
				# Phase 9: Validate pattern is specific enough
				if self._is_specific_url_pattern(pattern):
					patterns.append(pattern)
					logger.debug(f"Extracted domain+path pattern: {pattern}")

		# Pattern 3: Look for specific relative paths (Phase 9: improved)
		# Match paths like /dashboard, /users/123, /api/v1/endpoint
		relative_path_patterns = [
			r'/(?:[a-zA-Z0-9_-]+/){1,}[a-zA-Z0-9_-]+',  # Multi-segment paths
			r'/[a-zA-Z0-9_-]{3,}(?:/[a-zA-Z0-9_-]+)*',  # Paths with at least 3 chars per segment
		]
		
		for path_pattern in relative_path_patterns:
			path_matches = re.finditer(path_pattern, context)
			for match in path_matches:
				path = match.group(0).rstrip('.,;!?)')
				
				# Phase 9: Filter out generic HTML element paths
				generic_paths = ['/div', '/span', '/p', '/a', '/button', '/input', '/form', '/img', '/script', '/style']
				if path.lower() in generic_paths:
					continue
				
				# Phase 9: Only add if path looks like a route (not HTML element)
				if len(path) > 3 and not path.startswith('/<') and '<' not in path:
					# Create pattern that matches this path
					escaped_path = re.escape(path)
					# Phase 9: Support relative URLs - match at any position in URL
					pattern = f".*{escaped_path}(?:\\?.*)?(?:#.*)?$"
					
					# Phase 9: Validate pattern is specific enough
					if self._is_specific_url_pattern(pattern):
						patterns.append(pattern)
						logger.debug(f"Extracted relative path pattern: {pattern}")

		# Pattern 4: Phase 9 - Look for URL patterns in code/documentation examples
		# Pattern: "Navigate to /path" or "URL: /path" or "Route: /path"
		code_url_patterns = [
			r'(?:navigate|go|route|url|path)[:\s]+["\']?([/][^\s"\']+)["\']?',
			r'["\']([/][a-zA-Z0-9_/-]{3,})["\']',  # Quoted paths
		]
		
		for pattern in code_url_patterns:
			matches = re.finditer(pattern, context, re.IGNORECASE)
			for match in matches:
				path = match.group(1).rstrip('.,;!?)')
				if len(path) > 3 and path.startswith('/'):
					escaped_path = re.escape(path)
					url_pattern = f".*{escaped_path}(?:\\?.*)?(?:#.*)?$"
					if self._is_specific_url_pattern(url_pattern):
						patterns.append(url_pattern)
						logger.debug(f"Extracted code/documentation URL pattern: {url_pattern}")

		# Phase 9: Deduplicate and filter
		unique_patterns = list(set(patterns))
		
		# Phase 9: Enhanced filtering - remove overly generic patterns
		filtered_patterns = []
		for pattern in unique_patterns:
			# Skip patterns that are too generic
			if pattern in ['.*/.*', '.*', '^.*$', '.*/.*$']:
				logger.debug(f"Filtered out generic pattern: {pattern}")
				continue
			
			# Skip patterns that match any single character path
			if pattern.startswith('.*/') and len(pattern) < 10:
				logger.debug(f"Filtered out too-short pattern: {pattern}")
				continue
			
			# Phase 9: Validate pattern is specific (has at least one specific segment)
			if self._is_specific_url_pattern(pattern):
				filtered_patterns.append(pattern)
			else:
				logger.debug(f"Filtered out non-specific pattern: {pattern}")
		
		if filtered_patterns:
			logger.debug(f"Extracted {len(filtered_patterns)} URL patterns from context")
		else:
			logger.debug("No valid URL patterns extracted from context")
		
		return filtered_patterns
	
	def _is_valid_url(self, url: str) -> bool:
		"""Phase 9: Validate that a string is a valid URL format."""
		# Basic URL validation
		if not url or len(url) < 4:
			return False
		
		# Must start with http:// or https://
		if not url.startswith(('http://', 'https://')):
			return False
		
		# Must have a domain
		if '.' not in url.split('://', 1)[1].split('/', 1)[0]:
			return False
		
		return True
	
	def _is_specific_url_pattern(self, pattern: str) -> bool:
		"""
		Phase 9: Validate that URL pattern is specific enough (not generic like .*/.*).
		
		Args:
			pattern: URL pattern to validate
		
		Returns:
			True if pattern is specific enough, False if too generic
		"""
		# Skip if pattern is just wildcards
		if pattern in ['.*', '.*/.*', '^.*$', '.*/.*$']:
			return False
		
		# Skip if pattern is too short (likely generic)
		if len(pattern) < 8:
			return False
		
		# Count specific segments (non-wildcard parts)
		# Remove regex anchors and wildcards
		specific_parts = re.sub(r'[\^$.*?+\[\](){}|\\]', '', pattern)
		
		# Must have at least one specific segment with 3+ characters
		if len(specific_parts) < 3:
			return False
		
		# Check if pattern has too many wildcards relative to specific content
		wildcard_count = pattern.count('.*') + pattern.count('.+')
		specific_char_count = len(specific_parts)
		
		# If more than 50% wildcards, it's too generic
		if wildcard_count > 0 and (wildcard_count * 2) > specific_char_count:
			return False
		
		return True

	def _extract_state_signature(self, context: str, screen_name: str) -> StateSignature:
		"""
		Extract state signature with actual DOM indicators (Phase 4 improvements).
		
		Focuses on extracting actual UI elements (buttons, headings, links) rather than
		instruction text. This ensures screens can be recognized by browser automation.
		
		Phase 9: Enhanced validation and filtering for documentation content.
		Priority 4: Skip state signatures for documentation screens (not needed).
		"""
		signature = StateSignature()

		# Priority 4: Check if this is documentation content early and skip extraction
		excluded_keywords = [
			'instruction', 'protocol', 'guideline', 'conversational',
			'phone call', 'voice assistant', 'empathetic listener',
			'primary goal', 'secondary goal', 'core goal',
			'follow-up question', 'exactly 4', 'exactly 5',
			'your primary', 'you should', 'you must', 'you need',
			'baseline emotional', 'emotional intelligence',
			'part a', 'part b', 'part c', 'part d',
			'quality checklist', 'internal', 'before responding',
			'never use', 'always use', 'critical', 'important',
			'example', 'note', 'warning', 'tip',
		]
		
		# Priority 4: Early check - if documentation, return empty signature
		is_documentation = any(
			keyword in context.lower() or keyword in screen_name.lower()
			for keyword in excluded_keywords
		) or not self._is_web_ui_screen(context, screen_name)
		
		if is_documentation:
			logger.debug(
				f"Priority 4: Skipping state signature extraction for documentation screen: '{screen_name[:50]}'"
			)
			return signature  # Return empty signature for documentation screens

		# Phase 4: Extract actual UI elements, not instruction text
		# Pattern: "button with text 'Submit'", "input field 'email'", "heading 'Dashboard'", etc.
		ui_element_patterns = [
			r'button.*?["\']([^"\']{1,50})["\']',  # Button text (max 50 chars)
			r'input.*?["\']([^"\']{1,50})["\']',  # Input field label
			r'link.*?["\']([^"\']{1,50})["\']',  # Link text
			r'heading.*?["\']([^"\']{1,50})["\']',  # Heading text
			r'title.*?["\']([^"\']{1,50})["\']',  # Page title
			r'label.*?["\']([^"\']{1,50})["\']',  # Form label
		]
		
		# Phase 9: Expanded filter for instruction/documentation keywords (already defined above)
		
		for pattern in ui_element_patterns:
			matches = re.finditer(pattern, context, re.IGNORECASE)
			for match in matches:
				element_text = match.group(1).strip()
				
				# Phase 9: Enhanced validation - ensure all indicator values are < 50 characters
				# and filter out documentation keywords
				if (len(element_text) > 0 and 
				    len(element_text) <= 50 and 
				    not any(keyword in element_text.lower() for keyword in excluded_keywords) and
				    not element_text.startswith('1.') and  # Not a numbered list
				    not element_text.startswith('Your') and  # Not instruction text
				    not element_text.startswith('Part ') and  # Not section headers
				    '<br />' not in element_text and  # Not HTML-formatted documentation
				    not re.match(r'^\d+\.\s+', element_text)):  # Not numbered list items
					
					# Determine selector based on element type
					selector = 'body'
					if 'button' in pattern.lower():
						selector = 'button, .btn, [role="button"]'
					elif 'heading' in pattern.lower() or 'title' in pattern.lower():
						selector = 'h1, h2, h3, .page-title, .screen-title'
					elif 'input' in pattern.lower() or 'label' in pattern.lower():
						selector = 'input, label, [role="textbox"]'
					elif 'link' in pattern.lower():
						selector = 'a, [role="link"]'
					
					signature.required_indicators.append(Indicator(
						type='dom_contains',
						value=element_text,
						selector=selector,
						reason='UI element for screen recognition'
					))
		
		# Phase 9: Extract URL patterns and add as indicators (enhanced validation)
		url_patterns = self._extract_url_patterns(context)
		for pattern in url_patterns:
			# Phase 9: Only add specific URL patterns, validate they're not generic
			if self._is_specific_url_pattern(pattern):
				# Add as URL match indicator
				signature.required_indicators.append(Indicator(
					type='url_matches',
					pattern=pattern,
					reason='URL pattern for screen recognition'
				))
				logger.debug(f"Added URL pattern indicator: {pattern}")
		
		# Extract required indicators from explicit patterns (keep for backward compatibility)
		required_patterns = [
			r'must (?:have|contain|show|display)\s+["\']?([^"\']{1,50})["\']?',
			r'requires\s+["\']?([^"\']{1,50})["\']?',
		]

		for pattern in required_patterns:
			matches = re.finditer(pattern, context, re.IGNORECASE)
			for match in matches:
				value = match.group(1).strip()
				# Phase 9: Enhanced validation - ensure all indicator values are < 50 characters
				if (len(value) > 0 and 
				    len(value) <= 50 and 
				    not any(keyword in value.lower() for keyword in excluded_keywords) and
				    not value.startswith('1.') and
				    not value.startswith('Your') and
				    '<br />' not in value):
					signature.required_indicators.append(Indicator(
						type='dom_contains',
						value=value,
						selector='body',
						reason='Required for screen identification'
					))

		# Extract NEGATIVE indicators (CRITICAL for Agent-Killer edge case #2)
		# Look for "not", "without", "if X is present then", "distinguishes", "indicates NOT", "visible"
		negative_patterns = [
			# Pattern 1: "If X is present/visible, you are in Y"
			r'(?:if|when)\s+(?:the\s+)?["\']?([^"\']+)["\']?\s+(?:is|are)\s+(?:present|visible|shown|displayed)',
			# Pattern 2: "X button is visible" - implies distinguishing feature
			r'["\']?([^"\']+)["\']?\s+(?:button|link|element)\s+is\s+(?:visible|shown|displayed)',
			# Pattern 3: "without X"
			r'without\s+(?:the\s+)?["\']?([^"\']+)["\']?',
			# Pattern 4: "X distinguishes" or "differs by X"
			r'(?:distinguishes?|differs?)\s+(?:from|by).{0,50}?["\']?([^"\']+)["\']?',
			# Pattern 5: "X indicates mode"
			r'["\']?([^"\']+)["\']?\s+(?:indicates?|shows?|signals?)\s+(?:you are in |)(?:edit|create|delete|view|admin)\s+mode',
		]

		for pattern in negative_patterns:
			matches = re.finditer(pattern, context, re.IGNORECASE | re.DOTALL)
			for match in matches:
				if len(match.groups()) >= 1:
					value = match.group(1).strip()

					# Extract reason from surrounding context (±50 chars)
					match_start = max(0, match.start() - 50)
					match_end = min(len(context), match.end() + 50)
					reason_context = context[match_start:match_end].replace('\n', ' ')

					signature.negative_indicators.append(Indicator(
						type='dom_contains',
						value=value,
						selector='button, h1, h2, .page-title, .admin-panel',
						reason=f"Distinguishing feature: {reason_context[:100]}"
					))

		# Phase 9: Post-processing - filter out documentation keywords from indicators
		# and validate all indicator values are < 50 characters
		filtered_indicators = []
		for indicator in signature.required_indicators:
			if indicator.value:
				# Validate length
				if len(indicator.value) > 50:
					logger.debug(f"Skipping indicator with value > 50 chars: {indicator.value[:50]}...")
					continue
				
				# Filter out documentation keywords
				if any(keyword in indicator.value.lower() for keyword in excluded_keywords):
					logger.debug(f"Skipping indicator with documentation keyword: {indicator.value}")
					continue
				
				# Filter out HTML-formatted text
				if '<br />' in indicator.value or '<' in indicator.value:
					logger.debug(f"Skipping indicator with HTML: {indicator.value}")
					continue
				
				filtered_indicators.append(indicator)
		
		signature.required_indicators = filtered_indicators
		
		# Priority 4: is_documentation already checked at the start, so we know it's not documentation here
		# Add default required indicator for screen name ONLY if:
		# 1. Screen name is short (< 50 chars) - not entire documentation text
		# 2. Doesn't contain documentation keywords
		# 3. We have no other indicators (to avoid cluttering with invalid data)
		# 4. NOT a documentation screen (Priority 4 - already checked at start)
		if (len(signature.required_indicators) == 0 and 
		    len(screen_name) <= 50 and
		    not any(keyword in screen_name.lower() for keyword in excluded_keywords) and
		    not screen_name.startswith('1.') and
		    not screen_name.startswith('Your') and
		    not screen_name.startswith('Part ') and
		    '<br />' not in screen_name):  # Filter out HTML-formatted documentation
			signature.required_indicators.append(Indicator(
				type='dom_contains',
				value=screen_name,
				selector='h1, h2, .page-title',
				reason='Screen title indicator'
			))

		return signature

	def _extract_ui_elements(self, context: str) -> list[UIElement]:
		"""Extract UI elements from context."""
		elements = []

		# Pattern: buttons
		button_pattern = r'(?:click|press|select)\s+(?:the\s+)?["\']?([^"\']+)["\']?\s+(?:button|link)'
		button_matches = re.finditer(button_pattern, context, re.IGNORECASE)

		for match in button_matches:
			button_text = match.group(1).strip()
			element_id = self._generate_element_id(button_text, 'button')

			elements.append(UIElement(
				element_id=element_id,
				type='button',
				selector=ElementSelector(
					strategies=[
						SelectorStrategy(
							type='semantic',
							text_contains=button_text,
							button_type='button'
						)
					]
				),
				affordances=[
					Affordance(
						action_type='click',
						required=False
					)
				],
				metadata={'label': button_text}
			))

		# Pattern: input fields
		input_pattern = r'(?:enter|input|type)\s+(?:the\s+|your\s+)?["\']?([^"\']+)["\']?'
		input_matches = re.finditer(input_pattern, context, re.IGNORECASE)

		for match in input_matches:
			field_name = match.group(1).strip()
			element_id = self._generate_element_id(field_name, 'input')

			elements.append(UIElement(
				element_id=element_id,
				type='input',
				selector=ElementSelector(
					strategies=[
						SelectorStrategy(
							type='semantic',
							label_contains=field_name,
							field_type='text'
						)
					]
				),
				affordances=[
					Affordance(
						action_type='type',
						required=False
					),
					Affordance(
						action_type='clear',
						required=False
					)
				],
				metadata={'label': field_name}
			))

		return elements

	def _generate_screen_id(self, screen_name: str) -> str:
		"""
		Generate short screen ID from screen name.
		
		Uses a hash-based approach to keep IDs short while maintaining uniqueness.
		The full name is preserved in the `name` field for human readability.
		"""
		# Sanitize the name
		sanitized = screen_name.lower()
		sanitized = re.sub(r'[^\w\s-]', '', sanitized)
		sanitized = re.sub(r'[-\s]+', '_', sanitized)
		
		# Truncate to first 100 chars to avoid extremely long inputs
		sanitized = sanitized[:100]
		
		# Generate hash and take first 8 characters for short ID
		hash_obj = hashlib.md5(sanitized.encode('utf-8'))
		hash_suffix = hash_obj.hexdigest()[:8]
		
		# Use first 30 chars of sanitized name + hash for readability + uniqueness
		prefix = sanitized[:30].rstrip('_')
		return f"{prefix}_{hash_suffix}" if prefix else f"screen_{hash_suffix}"

	def _generate_element_id(self, element_name: str, element_type: str) -> str:
		"""Generate element ID from element name and type."""
		base_id = self._generate_screen_id(element_name)
		return f"{base_id}_{element_type}"
	
	def _extract_screen_regions(
		self,
		context: str,
		ui_elements: list[UIElement]
	) -> list[ScreenRegion]:
		"""
		Extract screen regions from context (Phase 8).
		
		Identifies common screen regions: header, sidebar, main, footer, modal, navigation.
		
		Args:
			context: Context text
			ui_elements: UI elements to map to regions
		
		Returns:
			List of ScreenRegion objects
		"""
		regions = []
		
		# Region patterns
		region_patterns = {
			'header': [
				r'header',
				r'top\s+(?:navigation|menu|bar)',
				r'page\s+header',
			],
			'sidebar': [
				r'sidebar',
				r'side\s+(?:navigation|menu|panel)',
				r'left\s+(?:panel|menu)',
			],
			'main': [
				r'main\s+(?:content|area|section)',
				r'content\s+area',
				r'body\s+content',
			],
			'footer': [
				r'footer',
				r'bottom\s+(?:navigation|bar)',
				r'page\s+footer',
			],
			'navigation': [
				r'navigation',
				r'nav\s+menu',
				r'top\s+menu',
			],
			'modal': [
				r'modal',
				r'dialog',
				r'popup',
			],
		}
		
		context_lower = context.lower()
		
		for region_type, patterns in region_patterns.items():
			for pattern in patterns:
				if re.search(pattern, context_lower, re.IGNORECASE):
					# Generate region ID
					region_id = f"{self.website_id}_{region_type}_{hashlib.md5(region_type.encode()).hexdigest()[:8]}"
					
					# Estimate bounds (will be populated from actual DOM if available)
					# Default bounds based on region type
					bounds = self._estimate_region_bounds(region_type)
					
					# Map UI elements to this region (simple heuristic)
					ui_element_ids = self._map_elements_to_region(ui_elements, region_type, context)
					
					regions.append(ScreenRegion(
						region_id=region_id,
						region_type=region_type,
						bounds=bounds,
						ui_element_ids=ui_element_ids,
						metadata={
							'extraction_method': 'rule_based',
							'confidence': 0.7,  # Medium confidence for rule-based extraction
						}
					))
					break  # Only create one region per type
		
		return regions
	
	def _estimate_region_bounds(self, region_type: str) -> dict[str, Any]:
		"""Estimate region bounds based on type (default values)."""
		# These are default estimates - actual bounds should come from DOM
		default_bounds = {
			'header': {'x': 0, 'y': 0, 'width': 1920, 'height': 80},
			'sidebar': {'x': 0, 'y': 80, 'width': 250, 'height': 1000},
			'main': {'x': 250, 'y': 80, 'width': 1670, 'height': 1000},
			'footer': {'x': 0, 'y': 1080, 'width': 1920, 'height': 100},
			'navigation': {'x': 0, 'y': 0, 'width': 1920, 'height': 60},
			'modal': {'x': 500, 'y': 300, 'width': 920, 'height': 480},
		}
		return default_bounds.get(region_type, {'x': 0, 'y': 0, 'width': 1920, 'height': 1080})
	
	def _map_elements_to_region(
		self,
		ui_elements: list[UIElement],
		region_type: str,
		context: str
	) -> list[str]:
		"""Map UI elements to a region based on context."""
		element_ids = []
		
		# Simple heuristic: if element label/type matches region keywords
		region_keywords = {
			'header': ['logo', 'menu', 'navigation', 'search', 'user', 'profile'],
			'sidebar': ['menu', 'navigation', 'filter', 'category'],
			'main': ['content', 'form', 'table', 'list', 'card'],
			'footer': ['link', 'copyright', 'social', 'contact'],
			'navigation': ['menu', 'link', 'tab', 'breadcrumb'],
			'modal': ['close', 'button', 'form', 'dialog'],
		}
		
		keywords = region_keywords.get(region_type, [])
		context_lower = context.lower()
		
		for element in ui_elements:
			# Check if element metadata/label contains region keywords
			element_text = str(element.metadata.get('label', '')).lower()
			
			if any(keyword in element_text or keyword in context_lower for keyword in keywords):
				element_ids.append(element.element_id)
		
		return element_ids
	
	def _extract_layout_structure(self, context: str) -> dict[str, Any] | None:
		"""
		Extract layout structure from context (Phase 8).
		
		Identifies layout type: grid, flexbox, columns, etc.
		
		Args:
			context: Context text
		
		Returns:
			Layout structure dict or None
		"""
		context_lower = context.lower()
		
		# Detect layout type
		layout_type = None
		if re.search(r'grid|column\s+layout|multi\s+column', context_lower):
			layout_type = 'grid'
		elif re.search(r'flex|flexbox|flex\s+layout', context_lower):
			layout_type = 'flexbox'
		elif re.search(r'column|sidebar|two\s+column|three\s+column', context_lower):
			layout_type = 'columns'
		else:
			layout_type = 'standard'
		
		# Extract column count
		columns = 1
		column_match = re.search(r'(\d+)\s+column', context_lower)
		if column_match:
			columns = int(column_match.group(1))
		elif 'sidebar' in context_lower or 'two column' in context_lower:
			columns = 2
		elif 'three column' in context_lower:
			columns = 3
		
		# Extract sections
		sections = []
		section_patterns = [
			r'section[:\s]+(.+?)(?:\n|$)',
			r'area[:\s]+(.+?)(?:\n|$)',
		]
		
		for pattern in section_patterns:
			matches = re.finditer(pattern, context_lower)
			for match in matches:
				section_name = match.group(1).strip()
				if section_name and len(section_name) < 100:
					sections.append(section_name)
		
		if layout_type == 'standard' and not sections:
			return None  # Don't create layout structure if nothing detected
		
		return {
			'type': layout_type,
			'columns': columns,
			'sections': sections[:10],  # Limit to 10 sections
			'extraction_method': 'rule_based',
		}
	
	@staticmethod
	async def enrich_ui_elements_with_spatial_info(
		ui_elements: list[UIElement],
		browser_session: Any | None = None,
		dom_data: dict[str, Any] | None = None
	) -> list[UIElement]:
		"""
		Enrich UI elements with spatial information from browser DOM (Phase 8).
		
		This method should be called when browser DOM access is available (e.g., during
		authenticated portal crawling) to populate position, visual properties, etc.
		
		Args:
			ui_elements: List of UI elements to enrich
			browser_session: Optional BrowserSession for DOM access
			dom_data: Optional pre-extracted DOM data with element positions
		
		Returns:
			List of enriched UI elements
		"""
		if not browser_session and not dom_data:
			return ui_elements  # No spatial data available
		
		enriched_elements = []
		
		for element in ui_elements:
			# Try to get spatial information
			position_data = None
			visual_props = None
			layout_context = None
			importance_score = None
			
			# If DOM data provided, extract from it
			if dom_data:
				element_data = dom_data.get(element.element_id) or dom_data.get(element.metadata.get('dom_id'))
				if element_data:
					# Extract position
					if 'bounding_box' in element_data:
						bbox = element_data['bounding_box']
						position_data = {
							'x': bbox.get('x', 0),
							'y': bbox.get('y', 0),
							'width': bbox.get('width', 0),
							'height': bbox.get('height', 0),
							'bounding_box': bbox,
						}
					
					# Extract visual properties
					visual_props = {
						'z_index': element_data.get('z_index'),
						'font_size': element_data.get('font_size'),
						'color': element_data.get('color'),
						'background': element_data.get('background'),
						'opacity': element_data.get('opacity'),
						'visibility': element_data.get('visibility'),
						'display': element_data.get('display'),
						'position': element_data.get('position'),
					}
					
					# Determine layout context from position
					if position_data:
						layout_context = ScreenExtractor._determine_layout_context(
							position_data['x'],
							position_data['y'],
							position_data['width'],
							position_data['height']
						)
					
					# Calculate importance score
					importance_score = ScreenExtractor._calculate_importance_score(
						element,
						position_data,
						visual_props
					)
			
			# If browser session available, try to get element from DOM
			elif browser_session:
				try:
					# Try to find element using selector
					# This would require implementing element lookup from browser
					# For now, we'll skip if browser_session is provided but no dom_data
					pass
				except Exception as e:
					logger.debug(f"Could not enrich element {element.element_id} with spatial info: {e}")
			
			# Create enriched element
			enriched_element = UIElement(
				element_id=element.element_id,
				type=element.type,
				selector=element.selector,
				affordances=element.affordances,
				metadata=element.metadata,
				position=position_data,
				layout_context=layout_context,
				visual_properties=visual_props,
				importance_score=importance_score,
			)
			
			enriched_elements.append(enriched_element)
		
		return enriched_elements
	
	@staticmethod
	def _determine_layout_context(x: float, y: float, width: float, height: float) -> str | None:
		"""Determine layout context from element position."""
		# Simple heuristics based on position
		# Top 100px = header
		if y < 100:
			return 'header'
		# Left 300px = sidebar
		elif x < 300:
			return 'sidebar'
		# Bottom 150px = footer
		elif y > 930:  # Assuming 1080p screen
			return 'footer'
		# Center area = main
		elif 300 < x < 1620:  # Assuming 1920px width
			return 'main'
		return None
	
	@staticmethod
	def _calculate_importance_score(
		element: UIElement,
		position: dict[str, Any] | None,
		visual_props: dict[str, Any] | None
	) -> float | None:
		"""Calculate visual importance score (0-1) for element."""
		if not position and not visual_props:
			return None
		
		score = 0.5  # Base score
		
		# Increase score for elements in header/navigation (typically important)
		if element.layout_context in ['header', 'navigation']:
			score += 0.2
		
		# Increase score for larger elements (more visible)
		if position:
			area = position.get('width', 0) * position.get('height', 0)
			if area > 10000:  # Large elements
				score += 0.1
			elif area < 100:  # Very small elements
				score -= 0.1
		
		# Increase score for higher z-index (on top)
		if visual_props and visual_props.get('z_index'):
			z_index = visual_props['z_index']
			if z_index > 1000:
				score += 0.1
		
		# Increase score for buttons/links (interactive elements)
		if element.type in ['button', 'link']:
			score += 0.1
		
		# Clamp to [0, 1]
		return max(0.0, min(1.0, score))

	def _deduplicate_screens(self, screens: list[ScreenDefinition]) -> list[ScreenDefinition]:
		"""Deduplicate screens by screen_id."""
		seen = set()
		unique = []

		for screen in screens:
			if screen.screen_id not in seen:
				seen.add(screen.screen_id)
				unique.append(screen)

		return unique

	def _validate_screen(self, screen: ScreenDefinition) -> list[str]:
		"""
		Validate screen definition against schema.
		
		Returns:
			List of validation errors (empty if valid)
		"""
		errors = []

		# Validate required fields
		if not screen.screen_id:
			errors.append("Missing screen_id")
		if not screen.name:
			errors.append("Missing name")

		# Validate URL patterns are valid regex
		for pattern in screen.url_patterns:
			try:
				re.compile(pattern)
			except re.error as e:
				errors.append(f"Invalid URL pattern '{pattern}': {e}")

		# Priority 4: Documentation screens may have empty state signatures (they don't need indicators)
		# Only validate for web_ui screens
		is_documentation = screen.content_type == "documentation" if hasattr(screen, 'content_type') else False
		if not is_documentation and not screen.state_signature.required_indicators:
			errors.append("State signature must have at least one required indicator")

		# Validate indicator types
		for indicator in (
			screen.state_signature.required_indicators +
			screen.state_signature.optional_indicators +
			screen.state_signature.exclusion_indicators +
			screen.state_signature.negative_indicators
		):
			valid_types = ['dom_contains', 'url_matches', 'url_exact', 'dom_class', 'dom_id', 'dom_attribute']
			if indicator.type not in valid_types:
				errors.append(f"Invalid indicator type '{indicator.type}'")

		return errors

	async def _validate_cross_references(self, result: ScreenExtractionResult) -> None:
		"""
		Priority 9: Cross-reference validation - check if extracted screen names match existing screens.
		
		Validates that extracted screen names don't conflict with or duplicate existing screens
		in the knowledge base. This helps identify:
		- Duplicate extractions (same screen extracted multiple times)
		- Name conflicts (different screens with similar names)
		- Potential matches (extracted screen might match existing screen)
		
		Args:
			result: Screen extraction result to validate
		"""
		if not self.knowledge_id:
			logger.debug("Priority 9: Skipping cross-reference validation (no knowledge_id provided)")
			return
		
		try:
			from navigator.knowledge.persist.documents.screens import query_screens_by_knowledge_id
			from navigator.knowledge.persist.linking_helpers import find_screens_by_name
			
			# Query existing screens from knowledge base
			existing_screens = await query_screens_by_knowledge_id(
				knowledge_id=self.knowledge_id,
				content_type=None,  # Check all content types
				actionable_only=False
			)
			
			if not existing_screens:
				logger.debug("Priority 9: No existing screens found for cross-reference validation")
				return
			
			logger.info(f"Priority 9: Validating {len(result.screens)} extracted screens against {len(existing_screens)} existing screens")
			
			# Check each extracted screen against existing screens
			for screen in result.screens:
				screen_name = screen.name
				extraction_confidence = screen.metadata.get('extraction_confidence', 0.5)
				
				# Priority 9: Find existing screens with similar names (fuzzy matching)
				matched_screens = find_screens_by_name(
					screen_name,
					existing_screens,
					fuzzy=True,
					threshold=0.7  # 70% similarity threshold for cross-reference validation
				)
				
				if matched_screens:
					# Found existing screens with similar names
					best_match = matched_screens[0]
					similarity = best_match.get('similarity', 0.0)
					existing_screen = best_match.get('screen')
					
					if existing_screen:
						existing_screen_id = existing_screen.screen_id if hasattr(existing_screen, 'screen_id') else existing_screen.get('screen_id', 'unknown')
						existing_screen_name = existing_screen.name if hasattr(existing_screen, 'name') else existing_screen.get('name', 'unknown')
						
						# Priority 9: Check if this is a duplicate (very high similarity)
						if similarity >= 0.9:
							result.add_error(
								"DuplicateScreenName",
								f"Extracted screen '{screen_name}' is likely a duplicate of existing screen '{existing_screen_name}' (similarity: {similarity:.2f})",
								{
									"extracted_screen_id": screen.screen_id,
									"extracted_screen_name": screen_name,
									"existing_screen_id": existing_screen_id,
									"existing_screen_name": existing_screen_name,
									"similarity": similarity,
									"extraction_confidence": extraction_confidence
								}
							)
							logger.warning(
								f"Priority 9: Potential duplicate screen detected - "
								f"'{screen_name}' matches existing screen '{existing_screen_name}' "
								f"(similarity: {similarity:.2f})"
							)
						# Priority 9: Check if this is a name conflict (high similarity but different screens)
						elif similarity >= 0.7:
							# Store cross-reference info in metadata for later review
							screen.metadata['cross_reference_match'] = {
								'existing_screen_id': existing_screen_id,
								'existing_screen_name': existing_screen_name,
								'similarity': similarity,
								'status': 'potential_match'
							}
							logger.info(
								f"Priority 9: Cross-reference match found - "
								f"'{screen_name}' similar to existing screen '{existing_screen_name}' "
								f"(similarity: {similarity:.2f})"
							)
		
		except Exception as e:
			logger.warning(f"Priority 9: Cross-reference validation failed: {e}", exc_info=True)
			# Don't fail extraction if cross-reference validation fails
			pass

	@staticmethod
	def generate_extraction_statistics(result: ScreenExtractionResult) -> dict[str, Any]:
		"""
		Priority 9: Generate extraction statistics for visualization dashboard.
		
		Creates comprehensive statistics about screen extraction including:
		- Extraction sources distribution
		- Confidence score distribution
		- Content type breakdown
		- Rejection reasons
		- Cross-reference matches
		
		Args:
			result: Screen extraction result
		
		Returns:
			Dictionary with extraction statistics for visualization
		"""
		stats = {
			'total_extracted': len(result.screens),
			'total_errors': len(result.errors),
			'extraction_sources': {},
			'confidence_distribution': {
				'high': 0,  # >= 0.7
				'medium': 0,  # 0.4-0.7
				'low': 0,  # < 0.4
			},
			'content_type_breakdown': {
				'web_ui': 0,
				'documentation': 0,
			},
			'actionable_breakdown': {
				'actionable': 0,
				'non_actionable': 0,
			},
			'rejection_reasons': {},
			'cross_reference_matches': 0,
			'average_confidence': 0.0,
		}
		
		# Calculate statistics from screens
		confidence_scores = []
		for screen in result.screens:
			# Extraction source
			source = screen.metadata.get('extraction_source', 'unknown')
			stats['extraction_sources'][source] = stats['extraction_sources'].get(source, 0) + 1
			
			# Confidence distribution
			confidence = screen.metadata.get('extraction_confidence', 0.5)
			confidence_scores.append(confidence)
			if confidence >= 0.7:
				stats['confidence_distribution']['high'] += 1
			elif confidence >= 0.4:
				stats['confidence_distribution']['medium'] += 1
			else:
				stats['confidence_distribution']['low'] += 1
			
			# Content type breakdown
			content_type = screen.content_type or 'unknown'
			if content_type in stats['content_type_breakdown']:
				stats['content_type_breakdown'][content_type] += 1
			
			# Actionable breakdown
			if screen.is_actionable:
				stats['actionable_breakdown']['actionable'] += 1
			else:
				stats['actionable_breakdown']['non_actionable'] += 1
			
			# Cross-reference matches
			if screen.metadata.get('cross_reference_match'):
				stats['cross_reference_matches'] += 1
		
		# Calculate average confidence
		if confidence_scores:
			stats['average_confidence'] = sum(confidence_scores) / len(confidence_scores)
		
		# Count rejection reasons from errors
		for error in result.errors:
			if error.get('type') == 'LowConfidenceRejection':
				reason = 'low_confidence'
				stats['rejection_reasons'][reason] = stats['rejection_reasons'].get(reason, 0) + 1
			elif error.get('type') == 'DuplicateScreenName':
				reason = 'duplicate_name'
				stats['rejection_reasons'][reason] = stats['rejection_reasons'].get(reason, 0) + 1
			elif error.get('type') == 'ValidationError':
				reason = 'validation_failed'
				stats['rejection_reasons'][reason] = stats['rejection_reasons'].get(reason, 0) + 1
		
		return stats

	@staticmethod
	async def validate_screen_name_with_llm(
		screen_name: str,
		context: str,
		llm_client: Any | None = None
	) -> dict[str, Any]:
		"""
		Priority 9: Optional LLM validation for screen names.
		
		Uses an LLM to verify if extracted text is actually a screen name.
		This is an optional enhancement that can be called when LLM is available.
		
		Args:
			screen_name: Extracted screen name to validate
			context: Context around the screen name
			llm_client: Optional LLM client for validation
		
		Returns:
			Dictionary with validation result: {'is_screen_name': bool, 'confidence': float, 'reasoning': str}
		"""
		if not llm_client:
			# Return default validation if no LLM provided
			return {
				'is_screen_name': True,  # Default to accepting if no LLM validation
				'confidence': 0.5,
				'reasoning': 'LLM validation not available, using default acceptance'
			}
		
		try:
			# Priority 9: Use LLM to validate if this is actually a screen name
			prompt = f"""Analyze if the following text is a screen name or page title for a web application:

Screen Name: "{screen_name}"
Context: "{context[:500]}"

Is this text a valid screen name/page title? Consider:
- Screen names are typically short (2-50 characters)
- Screen names describe a page or view (e.g., "Dashboard", "Login Page", "User Settings")
- Screen names are NOT instructions, guidelines, or documentation text
- Screen names are NOT full sentences or paragraphs

Respond with JSON:
{{
  "is_screen_name": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}"""
			
			# Call LLM (implementation depends on LLM client interface)
			# This is a placeholder - actual implementation would depend on the LLM client API
			# For now, return default validation
			logger.debug(f"Priority 9: LLM validation requested for '{screen_name}' (LLM client provided but not yet implemented)")
			return {
				'is_screen_name': True,
				'confidence': 0.5,
				'reasoning': 'LLM validation not yet fully implemented'
			}
		
		except Exception as e:
			logger.warning(f"Priority 9: LLM validation failed for '{screen_name}': {e}")
			return {
				'is_screen_name': True,  # Default to accepting on error
				'confidence': 0.5,
				'reasoning': f'LLM validation error: {str(e)}'
			}

	@staticmethod
	def enrich_screens_with_video_spatial_info(
		screens: list[ScreenDefinition],
		frame_analyses: list[dict[str, Any]]
	) -> list[ScreenDefinition]:
		"""
		Phase 5.2: Enrich screens with spatial information from video frame analyses.
		
		Extracts spatial information (position, layout structure, visual hierarchy) from
		video frame analyses and links it to matching screens.
		
		Args:
			screens: List of screen definitions to enrich
			frame_analyses: List of frame analysis dictionaries from video processing
		
		Returns:
			List of enriched screen definitions
		"""
		if not frame_analyses:
			return screens
		
		# Group frame analyses by screen_state
		frames_by_screen: dict[str, list[dict[str, Any]]] = {}
		for frame_analysis in frame_analyses:
			screen_state = frame_analysis.get('screen_state', 'Unknown')
			if screen_state and screen_state != 'Unknown':
				if screen_state not in frames_by_screen:
					frames_by_screen[screen_state] = []
				frames_by_screen[screen_state].append(frame_analysis)
		
		# Enrich each screen with spatial info from matching frames
		enriched_screens = []
		for screen in screens:
			# Find matching frames by screen name
			matching_frames = []
			for screen_state, frames in frames_by_screen.items():
				# Match by screen name similarity
				if screen_state.lower() in screen.name.lower() or screen.name.lower() in screen_state.lower():
					matching_frames.extend(frames)
			
			if matching_frames:
				# Extract spatial information from matching frames
				spatial_info = ScreenExtractor._extract_spatial_info_from_frames(matching_frames)
				
				# Enrich UI elements with position data
				if spatial_info.get('ui_elements'):
					screen = ScreenExtractor._enrich_screen_ui_elements(screen, spatial_info['ui_elements'])
				
				# Enrich layout structure
				if spatial_info.get('layout_structure'):
					screen.layout_structure = spatial_info['layout_structure']
				
				# Enrich regions
				if spatial_info.get('regions'):
					screen.regions = spatial_info['regions']
				
				logger.debug(f"Enriched screen {screen.screen_id} with spatial info from {len(matching_frames)} frames")
			
			enriched_screens.append(screen)
		
		return enriched_screens
	
	@staticmethod
	def _extract_spatial_info_from_frames(
		frames: list[dict[str, Any]]
	) -> dict[str, Any]:
		"""
		Phase 5.2: Extract spatial information from video frame analyses.
		
		Aggregates position data, layout structure, and visual hierarchy from frames.
		"""
		spatial_info = {
			'ui_elements': [],
			'layout_structure': None,
			'regions': [],
		}
		
		# Aggregate UI elements with position data
		ui_elements_map: dict[str, dict[str, Any]] = {}
		for frame in frames:
			ui_elements = frame.get('ui_elements', [])
			for elem in ui_elements:
				if isinstance(elem, dict):
					label = elem.get('label', '')
					if label:
						# Use label as key to aggregate elements
						if label not in ui_elements_map:
							ui_elements_map[label] = {
								'type': elem.get('type', 'element'),
								'label': label,
								'positions': [],
								'importance_scores': [],
								'layout_contexts': [],
							}
						
						# Collect position data
						if elem.get('position'):
							ui_elements_map[label]['positions'].append(elem['position'])
						
						# Collect importance scores
						if elem.get('importance_score') is not None:
							ui_elements_map[label]['importance_scores'].append(elem['importance_score'])
						
						# Collect layout contexts
						if elem.get('layout_context'):
							ui_elements_map[label]['layout_contexts'].append(elem['layout_context'])
		
		# Convert aggregated data to UI element structures
		for label, elem_data in ui_elements_map.items():
			# Average position (if multiple frames)
			avg_position = None
			if elem_data['positions']:
				positions = elem_data['positions']
				avg_x = sum(p.get('x', 0) for p in positions) / len(positions)
				avg_y = sum(p.get('y', 0) for p in positions) / len(positions)
				avg_width = sum(p.get('width', 0) for p in positions) / len(positions)
				avg_height = sum(p.get('height', 0) for p in positions) / len(positions)
				avg_position = {
					'x': avg_x,
					'y': avg_y,
					'width': avg_width,
					'height': avg_height,
					'bounding_box': {
						'x': avg_x,
						'y': avg_y,
						'width': avg_width,
						'height': avg_height,
					}
				}
			
			# Average importance score
			avg_importance = None
			if elem_data['importance_scores']:
				avg_importance = sum(elem_data['importance_scores']) / len(elem_data['importance_scores'])
			
			# Most common layout context
			most_common_context = None
			if elem_data['layout_contexts']:
				from collections import Counter
				context_counts = Counter(elem_data['layout_contexts'])
				most_common_context = context_counts.most_common(1)[0][0]
			
			spatial_info['ui_elements'].append({
				'label': label,
				'type': elem_data['type'],
				'position': avg_position,
				'importance_score': avg_importance,
				'layout_context': most_common_context,
			})
		
		# Extract layout structure (use most common or first structured one)
		layout_structures = []
		for frame in frames:
			layout = frame.get('layout_structure')
			if isinstance(layout, dict):
				layout_structures.append(layout)
		
		if layout_structures:
			# Use first structured layout (or could merge/average)
			spatial_info['layout_structure'] = layout_structures[0]
		
		# Extract regions from layout structure
		if spatial_info['layout_structure'] and isinstance(spatial_info['layout_structure'], dict):
			regions_data = spatial_info['layout_structure'].get('regions', [])
			if regions_data:
				from navigator.knowledge.extract.screens import ScreenRegion
				for region_data in regions_data:
					if isinstance(region_data, dict):
						region_type = region_data.get('type', 'main')
						bounds = region_data.get('bounds', {})
						if bounds:
							# Generate region ID
							import hashlib
							region_id = f"video_region_{region_type}_{hashlib.md5(str(bounds).encode()).hexdigest()[:8]}"
							
							spatial_info['regions'].append(ScreenRegion(
								region_id=region_id,
								region_type=region_type,
								bounds=bounds,
								ui_element_ids=[],  # Will be populated when linking
								metadata={'extraction_method': 'video_frame_analysis'}
							))
		
		return spatial_info
	
	@staticmethod
	def _enrich_screen_ui_elements(
		screen: ScreenDefinition,
		spatial_ui_elements: list[dict[str, Any]]
	) -> ScreenDefinition:
		"""
		Phase 5.2: Enrich screen UI elements with spatial information from video frames.
		
		Matches UI elements by label and enriches them with position, importance_score, layout_context.
		"""
		# Create mapping of label -> spatial data
		spatial_map = {elem['label']: elem for elem in spatial_ui_elements if elem.get('label')}
		
		# Enrich existing UI elements
		enriched_elements = []
		for ui_elem in screen.ui_elements:
			# Try to match by label
			label = ui_elem.metadata.get('label') or ui_elem.element_id
			spatial_data = spatial_map.get(label)
			
			if spatial_data:
				# Enrich with spatial information
				if spatial_data.get('position'):
					ui_elem.position = spatial_data['position']
				
				if spatial_data.get('importance_score') is not None:
					ui_elem.importance_score = spatial_data['importance_score']
				
				if spatial_data.get('layout_context'):
					ui_elem.layout_context = spatial_data['layout_context']
			
			enriched_elements.append(ui_elem)
		
		# Add new UI elements from video frames that weren't in screen
		for spatial_elem in spatial_ui_elements:
			label = spatial_elem.get('label', '')
			if label and not any(e.metadata.get('label') == label for e in screen.ui_elements):
				# Create new UI element from spatial data
				from navigator.knowledge.extract.screens import ElementSelector, SelectorStrategy, UIElement
				
				element_id = f"{screen.screen_id}_{label.lower().replace(' ', '_')}"
				new_elem = UIElement(
					element_id=element_id,
					type=spatial_elem.get('type', 'element'),
					selector=ElementSelector(
						strategies=[SelectorStrategy(
							type='semantic',
							text_contains=label,
						)]
					),
					affordances=[],
					metadata={'label': label, 'source': 'video_frame_analysis'},
					position=spatial_elem.get('position'),
					layout_context=spatial_elem.get('layout_context'),
					importance_score=spatial_elem.get('importance_score'),
				)
				enriched_elements.append(new_elem)
		
		screen.ui_elements = enriched_elements
		return screen


def validate_screen_definition(screen: ScreenDefinition) -> bool:
	"""
	Validate a screen definition against schema.
	
	Args:
		screen: Screen definition to validate
	
	Returns:
		True if valid, False otherwise
	"""
	extractor = ScreenExtractor()
	errors = extractor._validate_screen(screen)

	if errors:
		logger.error(f"Screen validation failed: {errors}")
		return False

	return True

"""
Screen extraction from ingested content.

Extracts screen definitions with critical focus on:
- **Negative indicators** (Agent-Killer edge case #2): Distinguishing features
- State signatures for accurate screen recognition
- URL pattern extraction
- UI element identification with affordances
"""

import logging
import re
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

	def __init__(self, website_id: str = "unknown"):
		"""
		Initialize screen extractor.
		
		Args:
			website_id: Website identifier for extracted screens
		"""
		self.website_id = website_id

	def extract_screens(self, content_chunks: list[ContentChunk]) -> ScreenExtractionResult:
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
				result.screens.extend(screens)

			# Deduplicate screens
			result.screens = self._deduplicate_screens(result.screens)

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

			logger.info(
				f"✅ Extracted {result.statistics['total_screens']} screens "
				f"({result.statistics['screens_with_negative_indicators']} with negative indicators)"
			)

		except Exception as e:
			logger.error(f"❌ Error extracting screens: {e}", exc_info=True)
			result.add_error("ExtractionError", str(e), {"exception_type": type(e).__name__})

		return result

	def _extract_screens_from_chunk(self, chunk: ContentChunk) -> list[ScreenDefinition]:
		"""
		Extract screens from a single content chunk.
		
		Args:
			chunk: Content chunk to process
		
		Returns:
			List of extracted screen definitions
		"""
		screens = []

		# TODO: Implement LLM-based extraction in next phase
		# For now, use rule-based extraction as a foundation

		# Pattern 1: Look for headings that indicate screens/pages
		screen_patterns = [
			r'##\s+(.+?)\s+(?:Screen|Page|Form|View|Dialog|Modal)',
			r'(?:Screen|Page|Form|View):\s+(.+)',
			r'### (.+?) (?:Screen|Page)',
		]

		for pattern in screen_patterns:
			matches = re.finditer(pattern, chunk.content, re.IGNORECASE | re.MULTILINE)
			for match in matches:
				screen_name = match.group(1).strip()
				screen_id = self._generate_screen_id(screen_name)

				# Extract context around the match
				start = max(0, match.start() - 500)
				end = min(len(chunk.content), match.end() + 1000)
				context = chunk.content[start:end]

				# Create basic screen definition
				screen = self._create_screen_from_context(screen_id, screen_name, context)
				screens.append(screen)

		return screens

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
		# Extract URL patterns
		url_patterns = self._extract_url_patterns(context)

		# Extract state signature
		state_signature = self._extract_state_signature(context, screen_name)

		# Extract UI elements
		ui_elements = self._extract_ui_elements(context)

		return ScreenDefinition(
			screen_id=screen_id,
			name=screen_name,
			website_id=self.website_id,
			url_patterns=url_patterns,
			state_signature=state_signature,
			ui_elements=ui_elements,
			metadata={
				'extraction_method': 'rule_based',
				'extracted_from': 'documentation',
			}
		)

	def _extract_url_patterns(self, context: str) -> list[str]:
		"""Extract URL patterns from context."""
		patterns = []

		# Look for URL mentions
		url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
		matches = re.finditer(url_pattern, context)

		for match in matches:
			url = match.group(0)
			# Convert to regex pattern
			# Escape special regex characters except for wildcards
			pattern = re.escape(url)
			pattern = pattern.replace(r'\*', '.*')
			pattern = f"^{pattern}$"
			patterns.append(pattern)

		# Look for relative paths
		path_pattern = r'/[a-zA-Z0-9/_-]+'
		path_matches = re.finditer(path_pattern, context)

		for match in path_matches:
			path = match.group(0)
			patterns.append(f".*{re.escape(path)}.*")

		# Deduplicate
		return list(set(patterns))

	def _extract_state_signature(self, context: str, screen_name: str) -> StateSignature:
		"""
		Extract state signature with **critical focus on negative indicators**.
		
		This is Agent-Killer Edge Case #2: Extract distinguishing features.
		"""
		signature = StateSignature()

		# Extract required indicators
		# Look for "must have" or "requires" patterns
		required_patterns = [
			r'must (?:have|contain|show|display)\s+["\']?([^"\']+)["\']?',
			r'requires\s+["\']?([^"\']+)["\']?',
			r'should (?:have|contain)\s+["\']?([^"\']+)["\']?',
		]

		for pattern in required_patterns:
			matches = re.finditer(pattern, context, re.IGNORECASE)
			for match in matches:
				value = match.group(1).strip()
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

		# Add default required indicator for screen name
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
		"""Generate screen ID from screen name."""
		# Convert to lowercase, replace spaces with underscores, remove special chars
		screen_id = screen_name.lower()
		screen_id = re.sub(r'[^\w\s-]', '', screen_id)
		screen_id = re.sub(r'[-\s]+', '_', screen_id)
		return screen_id

	def _generate_element_id(self, element_name: str, element_type: str) -> str:
		"""Generate element ID from element name and type."""
		base_id = self._generate_screen_id(element_name)
		return f"{base_id}_{element_type}"

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

		# Validate state signature has at least one required indicator
		if not screen.state_signature.required_indicators:
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

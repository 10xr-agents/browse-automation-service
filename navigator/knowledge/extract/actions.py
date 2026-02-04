"""
Action extraction from ingested content.

Extracts atomic action definitions with:
- Action types and categories
- Selector strategies
- Preconditions and postconditions
- Error handling and idempotency
"""

import hashlib
import logging
import re
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from navigator.schemas import ContentChunk

logger = logging.getLogger(__name__)


# =============================================================================
# Action Definition Models (aligned with KNOWLEDGE_SCHEMA_DESIGN.md)
# =============================================================================

class ActionPrecondition(BaseModel):
	"""Action precondition."""
	type: str = Field(..., description="Precondition type")
	hard_dependency: bool = Field(default=True, description="Whether this is a hard requirement")
	auto_remediate: bool = Field(default=False, description="Whether to auto-fix")


class ActionPostcondition(BaseModel):
	"""Action postcondition."""
	type: str = Field(..., description="Postcondition type")
	success: bool = Field(default=True, description="Whether this indicates success")


class ActionErrorHandling(BaseModel):
	"""Action error handling strategy."""
	condition: str = Field(..., description="Error condition")
	recovery: str = Field(..., description="Recovery action")
	retry: bool = Field(default=False, description="Whether to retry")
	max_retries: int = Field(default=3, description="Max retry attempts")


class ActionDefinition(BaseModel):
	"""Complete action definition (aligned with MongoDB schema)."""
	action_id: str = Field(..., description="Unique action identifier")
	name: str = Field(..., description="Human-readable action name")
	website_id: str = Field(..., description="Website identifier")
	action_type: str = Field(..., description="Action type (click, type, navigate, etc.)")
	category: str = Field(default="interaction", description="Action category")
	target_selector: str | None = Field(None, description="Target element selector")
	parameters: dict[str, Any] = Field(default_factory=dict, description="Action parameters")
	preconditions: list[ActionPrecondition] = Field(default_factory=list, description="Preconditions")
	postconditions: list[ActionPostcondition] = Field(default_factory=list, description="Postconditions")
	error_handling: list[ActionErrorHandling] = Field(default_factory=list, description="Error handlers")
	idempotent: bool = Field(default=True, description="Whether action is idempotent")
	reversible_by: str | None = Field(None, description="Action that reverses this one")
	metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
	
	# Delay Intelligence (captured from actual execution)
	delay_intelligence: dict[str, Any] | None = Field(
		None,
		description="Delay intelligence: average_delay_ms, recommended_wait_time_ms, is_slow, is_fast, variability, confidence"
	)

	# Phase 1.4: Browser-Use Action Mappings
	browser_use_action: dict[str, Any] | None = Field(
		None,
		description="Browser-use action mapping (tool_name, parameters, description, confidence)"
	)
	confidence_score: float | None = Field(
		None,
		ge=0.0,
		le=1.0,
		description="Confidence score for extracted action (0-1, higher=more confident)"
	)

	# Cross-reference fields (Phase 1: Schema Updates)
	screen_ids: list[str] = Field(
		default_factory=list,
		description="Screen IDs where this action is available"
	)
	user_flow_ids: list[str] = Field(
		default_factory=list,
		description="User flow IDs that use this action"
	)
	task_ids: list[str] = Field(
		default_factory=list,
		description="Task IDs that require this action"
	)
	business_function_ids: list[str] = Field(
		default_factory=list,
		description="Business function IDs that use this action"
	)
	triggered_transitions: list[str] = Field(
		default_factory=list,
		description="Transition IDs that this action triggers"
	)
	workflow_ids: list[str] = Field(
		default_factory=list,
		description="Workflow IDs that include this action"
	)


# =============================================================================
# Action Extraction Result
# =============================================================================

class ActionExtractionResult(BaseModel):
	"""Result of action extraction."""
	extraction_id: str = Field(default_factory=lambda: str(uuid4()), description="Extraction ID")
	actions: list[ActionDefinition] = Field(default_factory=list, description="Extracted actions")
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
		action_types = {}
		for action in self.actions:
			action_types[action.action_type] = action_types.get(action.action_type, 0) + 1

		self.statistics = {
			'total_actions': len(self.actions),
			'idempotent_actions': sum(1 for a in self.actions if a.idempotent),
			'reversible_actions': sum(1 for a in self.actions if a.reversible_by),
			'actions_with_preconditions': sum(1 for a in self.actions if a.preconditions),
			'actions_with_error_handling': sum(1 for a in self.actions if a.error_handling),
			'action_types': action_types,
		}


# =============================================================================
# Action Extractor
# =============================================================================

class ActionExtractor:
	"""
	Extracts action definitions from content chunks.
	
	Features:
	- Action type detection (click, type, navigate, etc.)
	- Selector extraction
	- Precondition and postcondition extraction
	- Idempotency detection
	- Error handling extraction
	"""

	def __init__(self, website_id: str = "unknown"):
		"""
		Initialize action extractor.
		
		Args:
			website_id: Website identifier for extracted actions
		"""
		self.website_id = website_id

	def extract_actions(self, content_chunks: list[ContentChunk]) -> ActionExtractionResult:
		"""
		Extract action definitions from content chunks.
		
		Args:
			content_chunks: Content chunks to extract actions from
		
		Returns:
			ActionExtractionResult with extracted actions
		"""
		result = ActionExtractionResult()

		try:
			logger.info(f"Extracting actions from {len(content_chunks)} content chunks")

			for chunk in content_chunks:
				actions = self._extract_actions_from_chunk(chunk)
				result.actions.extend(actions)

			# Deduplicate actions
			result.actions = self._deduplicate_actions(result.actions)
			
			# Phase 9: Translate actions to browser-use format
			from navigator.knowledge.extract.browser_use_mapping import ActionTranslator
			translator = ActionTranslator()
			
			for action in result.actions:
				# For navigation actions, ensure URL is in browser_use_action if we extracted it
				if action.action_type == 'navigate' and action.parameters.get('url'):
					# Update browser_use_action to include the extracted URL
					if not action.browser_use_action:
						action.browser_use_action = {}
					if 'parameters' not in action.browser_use_action:
						action.browser_use_action['parameters'] = {}
					action.browser_use_action['parameters']['url'] = action.parameters['url']
				
				# Translate to browser-use action
				try:
					browser_use_action = translator.translate_action(action)
					if browser_use_action:
						# Merge extracted URL if available
						if action.action_type == 'navigate' and action.parameters.get('url'):
							browser_use_action.parameters['url'] = action.parameters['url']
						action.browser_use_action = browser_use_action.model_dump()
						# Calculate confidence score based on translation success
						action.confidence_score = 0.8 if browser_use_action.confidence is None else browser_use_action.confidence
					else:
						# Lower confidence if translation failed
						action.confidence_score = 0.5
				except Exception as e:
					logger.debug(f"Failed to translate action {action.action_id} to browser-use: {e}")
					action.confidence_score = 0.3

			# Validate extracted actions
			for action in result.actions:
				validation_errors = self._validate_action(action)
				if validation_errors:
					result.add_error(
						"ValidationError",
						f"Action '{action.action_id}' failed validation",
						{"action_id": action.action_id, "errors": validation_errors}
					)

			# Calculate statistics
			result.calculate_statistics()

			logger.info(
				f"✅ Extracted {result.statistics['total_actions']} actions "
				f"({result.statistics['idempotent_actions']} idempotent, "
				f"{sum(1 for a in result.actions if a.browser_use_action)} with browser-use mappings)"
			)

		except Exception as e:
			logger.error(f"❌ Error extracting actions: {e}", exc_info=True)
			result.add_error("ExtractionError", str(e), {"exception_type": type(e).__name__})

		return result

	def _extract_actions_from_chunk(self, chunk: ContentChunk) -> list[ActionDefinition]:
		"""Extract actions from a single content chunk.
		
		Phase 9: Enhanced filtering to exclude table headers and documentation text.
		"""
		actions = []

		# Phase 9: Detect table headers in content (markdown tables)
		# Pattern: "| Column1 | Column2 |" or similar table header patterns
		table_header_pattern = r'^\s*\|[^|]+\|[^|]*\|'
		has_table_headers = bool(re.search(table_header_pattern, chunk.content, re.MULTILINE))

		# Action patterns: verb + target (greedy capture to get full target)
		action_patterns = [
			(r'click\s+(?:the\s+)?["\']?([^"\'\n\.]+?)["\']?\s+(?:button|link|to)', 'click'),
			(r'type\s+(?:your\s+|the\s+)?["\']?([^"\'\n\.]+)["\']?(?:\s+in)?', 'type'),
			(r'navigate\s+to\s+["\']?([^"\'\n\.]+)["\']?', 'navigate'),
			(r'select\s+["\']?([^"\'\n\.]+)["\']?', 'select_option'),
			(r'scroll\s+(?:to\s+)?["\']?([^"\'\n\.]+)["\']?', 'scroll'),
			(r'wait\s+for\s+["\']?([^"\'\n\.]+)["\']?', 'wait'),
		]

		for pattern, action_type in action_patterns:
			matches = re.finditer(pattern, chunk.content, re.IGNORECASE)
			for match in matches:
				target = match.group(1).strip()

				# Phase 9: Skip if target is too short or generic
				if len(target) < 2 or target.lower() in ['the', 'a', 'an', 'it']:
					continue
				
				# Phase 9: Filter out table headers
				# Check if target looks like a table header (contains | or is in table context)
				if '|' in target or (has_table_headers and self._is_table_header(target, chunk.content, match.start())):
					logger.debug(f"Skipping table header as action: {target}")
					continue
				
				# Phase 9: Only extract actions from actual UI interaction descriptions
				# Skip if context suggests this is documentation/instruction text
				context_start = max(0, match.start() - 100)
				context_end = min(len(chunk.content), match.end() + 100)
				context = chunk.content[context_start:context_end]
				
				if self._is_documentation_text(context):
					logger.debug(f"Skipping documentation text as action: {target}")
					continue

				action_id = self._generate_action_id(action_type, target)

				# Extract full context
				start = max(0, match.start() - 200)
				end = min(len(chunk.content), match.end() + 500)
				full_context = chunk.content[start:end]

				action = self._create_action_from_context(
					action_id, action_type, target, full_context
				)
				
				# Phase 9: Validate action before adding
				if self._is_valid_action(action):
					actions.append(action)
				else:
					logger.debug(f"Skipping invalid action: {action.action_id}")

		return actions
	
	def _is_table_header(self, target: str, content: str, match_pos: int) -> bool:
		"""Phase 9: Check if target is part of a table header."""
		# Check if target appears in a table row pattern
		# Look for patterns like "| target |" or "| Column1 | Column2 |"
		table_row_pattern = rf'\|\s*{re.escape(target)}\s*\|'
		if re.search(table_row_pattern, content, re.IGNORECASE):
			# Check if it's in a header row (usually first row after table start)
			# Simple heuristic: if it's near the start of content or after "| --- |" separator
			context_start = max(0, match_pos - 200)
			context = content[context_start:match_pos + 200]
			# Table headers often have separator rows like "| --- | --- |"
			if re.search(r'\|\s*-+\s*\|', context):
				return True
		return False
	
	def _is_documentation_text(self, context: str) -> bool:
		"""Phase 9: Check if context is documentation/instruction text rather than UI interaction."""
		doc_indicators = [
			'instruction', 'protocol', 'guideline', 'example',
			'note:', 'warning:', 'tip:', 'important:',
			'you should', 'you must', 'you need', 'your primary',
			'follow-up question', 'conversational', 'empathetic',
		]
		context_lower = context.lower()
		return any(indicator in context_lower for indicator in doc_indicators)
	
	def _is_valid_action(self, action: ActionDefinition) -> bool:
		"""Phase 9: Validate action has reasonable action type and target."""
		# Valid action types
		valid_action_types = [
			'click', 'type', 'navigate', 'select_option', 'scroll', 'wait',
			'upload_file', 'submit', 'hover', 'drag_drop', 'screenshot',
		]
		
		if action.action_type not in valid_action_types:
			return False
		
		# Target should not be empty
		if not action.target_selector and not action.metadata.get('target'):
			return False
		
		return True

	def _create_action_from_context(
		self,
		action_id: str,
		action_type: str,
		target: str,
		context: str
	) -> ActionDefinition:
		"""Create action definition from extracted context."""
		# Determine idempotency
		idempotent = self._is_idempotent(action_type, context)

		# Extract preconditions
		preconditions = self._extract_preconditions(context)

		# Extract postconditions
		postconditions = self._extract_postconditions(context)
		
		# Extract URL for navigation actions
		parameters = {}
		if action_type == 'navigate':
			extracted_url = self._extract_url_from_navigation_action(target, context)
			if extracted_url:
				parameters['url'] = extracted_url
				# Also update browser_use_action if it exists
				# This will be set later in extract_actions, but we can prepare it here

		return ActionDefinition(
			action_id=action_id,
			name=f"{action_type.title()} {target}",
			website_id=self.website_id,
			action_type=action_type,
			category=self._categorize_action(action_type),
			target_selector=self._generate_selector(target),
			parameters=parameters,  # Include extracted URL
			preconditions=preconditions,
			postconditions=postconditions,
			idempotent=idempotent,
			metadata={
				'extraction_method': 'rule_based',
				'target': target,
			}
		)
	
	def _extract_url_from_navigation_action(self, target: str, context: str) -> str | None:
		"""
		Extract actual URL from navigation action context.
		
		Looks for:
		- Explicit URLs in context (https://, http://)
		- Relative paths (/dashboard, /users/123)
		- Link hrefs mentioned in context
		- URL patterns in context
		
		Args:
			target: Action target (e.g., "Dashboard", "Agent page")
			context: Full context around the action
		
		Returns:
			Extracted URL or None if not found
		"""
		# Strategy 1: Look for explicit URLs in context
		url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
		url_matches = re.finditer(url_pattern, context, re.IGNORECASE)
		for match in url_matches:
			url = match.group(0)
			# Check if URL is related to the target (contains target keywords)
			target_lower = target.lower()
			url_lower = url.lower()
			# If target mentions a page name, check if URL path matches
			if any(keyword in url_lower for keyword in target_lower.split() if len(keyword) > 3):
				return url
			# If no match, return first URL found (might be the navigation target)
			return url
		
		# Strategy 2: Look for relative paths in context
		# Pattern: /path/to/page or /dashboard, /users/123
		relative_path_pattern = r'/(?:[a-zA-Z0-9_-]+/)*[a-zA-Z0-9_-]+(?:\?[^\s<>"{}|\\^`\[\]]+)?'
		path_matches = re.finditer(relative_path_pattern, context)
		for match in path_matches:
			path = match.group(0)
			# Check if path segment matches target
			path_segments = [s for s in path.split('/') if s]
			if path_segments:
				last_segment = path_segments[-1].split('?')[0]  # Remove query params
				target_words = target.lower().split()
				# Check if any target word appears in path
				if any(word in last_segment.lower() for word in target_words if len(word) > 3):
					# Return as relative path (will be resolved to full URL later)
					return path
		
		# Strategy 3: Look for href attributes in context
		href_pattern = r'href=["\']([^"\']+)["\']'
		href_matches = re.finditer(href_pattern, context, re.IGNORECASE)
		for match in href_matches:
			href = match.group(1)
			# Check if href matches target
			if any(word in href.lower() for word in target.lower().split() if len(word) > 3):
				return href
		
		# Strategy 4: Infer from target name (convert "Dashboard" -> "/dashboard")
		# Only if target looks like a page name (not a generic word)
		if len(target.split()) <= 3 and not target.lower() in ['the', 'a', 'an', 'it', 'page']:
			# Convert to URL-friendly format
			url_segment = target.lower().replace(' ', '-').replace('_', '-')
			# Remove special characters
			url_segment = re.sub(r'[^\w-]', '', url_segment)
			if url_segment and len(url_segment) > 2:
				return f"/{url_segment}"
		
		return None

	def _is_idempotent(self, action_type: str, context: str) -> bool:
		"""Determine if action is idempotent."""
		# Non-idempotent keywords
		non_idempotent_keywords = ['submit', 'create', 'delete', 'send', 'post']

		if action_type in ['submit', 'click']:
			# Check context for non-idempotent indicators
			context_lower = context.lower()
			return not any(keyword in context_lower for keyword in non_idempotent_keywords)

		# Type, navigate, scroll are generally idempotent
		return action_type in ['type', 'navigate', 'scroll', 'wait']

	def _extract_preconditions(self, context: str) -> list[ActionPrecondition]:
		"""Extract preconditions from context."""
		preconditions = []

		# Look for "must", "requires", "ensure"
		precondition_patterns = [
			r'(?:must|requires?|ensure)\s+(.+?)(?:\.|$)',
			r'before\s+(.+?),\s+(?:you must|ensure)',
		]

		for pattern in precondition_patterns:
			matches = re.finditer(pattern, context, re.IGNORECASE)
			for match in matches:
				condition_text = match.group(1).strip()
				preconditions.append(ActionPrecondition(
					type='custom',
					hard_dependency=True,
					auto_remediate=False
				))

		return preconditions

	def _extract_postconditions(self, context: str) -> list[ActionPostcondition]:
		"""Extract postconditions from context."""
		postconditions = []

		# Look for "after", "then", "results in"
		postcondition_patterns = [
			r'(?:after|then|results? in)\s+(.+?)(?:\.|$)',
			r'(?:navigates? to|redirects? to)\s+(.+?)(?:\.|$)',
		]

		for pattern in postcondition_patterns:
			matches = re.finditer(pattern, context, re.IGNORECASE)
			for match in matches:
				condition_text = match.group(1).strip()
				postconditions.append(ActionPostcondition(
					type='custom',
					success=True
				))

		return postconditions

	def _categorize_action(self, action_type: str) -> str:
		"""Categorize action."""
		categories = {
			'click': 'interaction',
			'type': 'input',
			'navigate': 'navigation',
			'select_option': 'selection',
			'scroll': 'navigation',
			'wait': 'timing',
		}
		return categories.get(action_type, 'interaction')

	def _generate_selector(self, target: str) -> str:
		"""Generate CSS selector from target description."""
		# Simple heuristic: convert to lowercase, make CSS-friendly
		selector = target.lower().strip()
		selector = re.sub(r'[^\w\s-]', '', selector)
		selector = re.sub(r'[-\s]+', '-', selector)
		return f".{selector}"

	def _generate_action_id(self, action_type: str, target: str) -> str:
		"""
		Generate short action ID from action type and target.
		
		Uses a hash-based approach to keep IDs short while maintaining uniqueness.
		The full name is preserved in the `name` field for human readability.
		"""
		# Sanitize target
		target_id = target.lower().strip()
		target_id = re.sub(r'[^\w\s-]', '', target_id)
		target_id = re.sub(r'[-\s]+', '_', target_id)
		
		# Truncate to first 30 chars to avoid extremely long inputs
		target_id = target_id[:30]
		
		# Generate hash and take first 8 characters for short ID
		full_id = f"{action_type}_{target_id}"
		hash_obj = hashlib.md5(full_id.encode('utf-8'))
		hash_suffix = hash_obj.hexdigest()[:8]
		
		# Use first 20 chars of action_type + target + hash for readability + uniqueness
		prefix = f"{action_type}_{target_id[:20]}".rstrip('_')
		return f"{prefix}_{hash_suffix}" if prefix else f"action_{hash_suffix}"

	def _deduplicate_actions(self, actions: list[ActionDefinition]) -> list[ActionDefinition]:
		"""Deduplicate actions by action_id."""
		seen = set()
		unique = []

		for action in actions:
			if action.action_id not in seen:
				seen.add(action.action_id)
				unique.append(action)

		return unique

	def _validate_action(self, action: ActionDefinition) -> list[str]:
		"""Validate action definition against schema."""
		errors = []

		# Validate required fields
		if not action.action_id:
			errors.append("Missing action_id")
		if not action.name:
			errors.append("Missing name")
		if not action.action_type:
			errors.append("Missing action_type")

		# Validate action type
		valid_action_types = [
			'click', 'type', 'navigate', 'select_option', 'scroll',
			'wait', 'extract', 'submit', 'clear', 'hover'
		]
		if action.action_type not in valid_action_types:
			errors.append(f"Invalid action type: {action.action_type}")

		return errors


def validate_action_definition(action: ActionDefinition) -> bool:
	"""
	Validate an action definition against schema.
	
	Args:
		action: Action definition to validate
	
	Returns:
		True if valid, False otherwise
	"""
	extractor = ActionExtractor()
	errors = extractor._validate_action(action)

	if errors:
		logger.error(f"Action validation failed: {errors}")
		return False

	return True

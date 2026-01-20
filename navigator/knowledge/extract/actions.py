"""
Action extraction from ingested content.

Extracts atomic action definitions with:
- Action types and categories
- Selector strategies
- Preconditions and postconditions
- Error handling and idempotency
"""

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
				f"({result.statistics['idempotent_actions']} idempotent)"
			)

		except Exception as e:
			logger.error(f"❌ Error extracting actions: {e}", exc_info=True)
			result.add_error("ExtractionError", str(e), {"exception_type": type(e).__name__})

		return result

	def _extract_actions_from_chunk(self, chunk: ContentChunk) -> list[ActionDefinition]:
		"""Extract actions from a single content chunk."""
		actions = []

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

				# Skip if target is too short or generic
				if len(target) < 2 or target.lower() in ['the', 'a', 'an', 'it']:
					continue

				action_id = self._generate_action_id(action_type, target)

				# Extract context
				start = max(0, match.start() - 200)
				end = min(len(chunk.content), match.end() + 500)
				context = chunk.content[start:end]

				action = self._create_action_from_context(
					action_id, action_type, target, context
				)
				actions.append(action)

		return actions

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

		return ActionDefinition(
			action_id=action_id,
			name=f"{action_type.title()} {target}",
			website_id=self.website_id,
			action_type=action_type,
			category=self._categorize_action(action_type),
			target_selector=self._generate_selector(target),
			preconditions=preconditions,
			postconditions=postconditions,
			idempotent=idempotent,
			metadata={
				'extraction_method': 'rule_based',
				'target': target,
			}
		)

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
		"""Generate action ID."""
		target_id = target.lower().strip()
		target_id = re.sub(r'[^\w\s-]', '', target_id)
		target_id = re.sub(r'[-\s]+', '_', target_id)
		return f"{action_type}_{target_id}"

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

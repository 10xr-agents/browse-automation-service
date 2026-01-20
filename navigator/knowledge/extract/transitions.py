"""
Transition extraction from ingested content.

Extracts state transition definitions with:
- Source and target screen identification
- Trigger actions
- Transition conditions
- Cost and reliability metrics
"""

import logging
import re
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from navigator.schemas import ContentChunk

logger = logging.getLogger(__name__)


# =============================================================================
# Transition Definition Models (aligned with KNOWLEDGE_SCHEMA_DESIGN.md)
# =============================================================================

class TransitionTrigger(BaseModel):
	"""What triggers this transition."""
	action_type: str = Field(..., description="Action type that triggers transition")
	element_id: str | None = Field(None, description="Element that triggers transition")


class TransitionCondition(BaseModel):
	"""Transition condition."""
	type: str = Field(..., description="Condition type")
	value: Any | None = Field(None, description="Condition value")


class TransitionEffect(BaseModel):
	"""Transition effect/outcome."""
	type: str = Field(..., description="Effect type")
	value: Any | None = Field(None, description="Effect value")


class TransitionDefinition(BaseModel):
	"""Complete transition definition for MongoDB storage."""
	transition_id: str = Field(..., description="Unique transition identifier")
	from_screen_id: str = Field(..., description="Source screen ID")
	to_screen_id: str = Field(..., description="Target screen ID")
	triggered_by: TransitionTrigger = Field(..., description="Trigger action")
	conditions: dict[str, list[TransitionCondition]] = Field(
		default_factory=lambda: {"required": [], "optional": []},
		description="Transition conditions"
	)
	effects: list[TransitionEffect] = Field(default_factory=list, description="Transition effects")
	cost: dict[str, Any] = Field(
		default_factory=lambda: {"estimated_ms": 2000, "complexity_score": 0.5},
		description="Cost metrics"
	)
	reliability_score: float = Field(default=0.95, description="Reliability score (0-1)")
	metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

	# Cross-reference fields (Phase 1: Schema Updates)
	user_flow_ids: list[str] = Field(
		default_factory=list,
		description="User flow IDs that include this transition"
	)
	action_id: str | None = Field(
		None,
		description="Action ID that triggers this transition (from triggered_by.element_id)"
	)
	business_function_ids: list[str] = Field(
		default_factory=list,
		description="Business function IDs that use this transition"
	)
	workflow_ids: list[str] = Field(
		default_factory=list,
		description="Workflow IDs that include this transition"
	)


# =============================================================================
# Transition Extraction Result
# =============================================================================

class TransitionExtractionResult(BaseModel):
	"""Result of transition extraction."""
	extraction_id: str = Field(default_factory=lambda: str(uuid4()), description="Extraction ID")
	transitions: list[TransitionDefinition] = Field(default_factory=list, description="Extracted transitions")
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
		trigger_types = {}
		for transition in self.transitions:
			action_type = transition.triggered_by.action_type
			trigger_types[action_type] = trigger_types.get(action_type, 0) + 1

		self.statistics = {
			'total_transitions': len(self.transitions),
			'transitions_with_conditions': sum(
				1 for t in self.transitions
				if t.conditions.get('required') or t.conditions.get('optional')
			),
			'transitions_with_effects': sum(1 for t in self.transitions if t.effects),
			'trigger_types': trigger_types,
			'avg_reliability': sum(t.reliability_score for t in self.transitions) / len(self.transitions) if self.transitions else 0,
		}


# =============================================================================
# Transition Extractor
# =============================================================================

class TransitionExtractor:
	"""
	Extracts transition definitions from content chunks.
	
	Features:
	- Source/target screen identification
	- Trigger action extraction
	- Condition extraction
	- Effect extraction
	- Cost and reliability estimation
	"""

	def __init__(self, website_id: str = "unknown"):
		"""
		Initialize transition extractor.
		
		Args:
			website_id: Website identifier for extracted transitions
		"""
		self.website_id = website_id

	def extract_transitions(self, content_chunks: list[ContentChunk]) -> TransitionExtractionResult:
		"""
		Extract transition definitions from content chunks.
		
		Args:
			content_chunks: Content chunks to extract transitions from
		
		Returns:
			TransitionExtractionResult with extracted transitions
		"""
		result = TransitionExtractionResult()

		try:
			logger.info(f"Extracting transitions from {len(content_chunks)} content chunks")

			for chunk in content_chunks:
				transitions = self._extract_transitions_from_chunk(chunk)
				result.transitions.extend(transitions)

			# Deduplicate transitions
			result.transitions = self._deduplicate_transitions(result.transitions)

			# Validate extracted transitions
			for transition in result.transitions:
				validation_errors = self._validate_transition(transition)
				if validation_errors:
					result.add_error(
						"ValidationError",
						f"Transition '{transition.transition_id}' failed validation",
						{"transition_id": transition.transition_id, "errors": validation_errors}
					)

			# Calculate statistics
			result.calculate_statistics()

			logger.info(
				f"✅ Extracted {result.statistics['total_transitions']} transitions "
				f"(avg reliability: {result.statistics['avg_reliability']:.2f})"
			)

		except Exception as e:
			logger.error(f"❌ Error extracting transitions: {e}", exc_info=True)
			result.add_error("ExtractionError", str(e), {"exception_type": type(e).__name__})

		return result

	def _extract_transitions_from_chunk(self, chunk: ContentChunk) -> list[TransitionDefinition]:
		"""Extract transitions from a single content chunk."""
		transitions = []

		# Transition patterns: "from X to Y" or "clicking Z navigates to W"
		transition_patterns = [
			r'(?:from|after)\s+["\']?([^"\']+?)["\']?\s+(?:to|navigates? to|goes to|redirects? to)\s+["\']?([^"\']+)["\']?',
			r'clicking\s+["\']?([^"\']+?)["\']?\s+(?:navigates?|goes|takes you)\s+to\s+["\']?([^"\']+)["\']?',
			r'submitting\s+["\']?([^"\']+?)["\']?\s+(?:navigates?|redirects?)\s+to\s+["\']?([^"\']+)["\']?',
		]

		for pattern in transition_patterns:
			matches = re.finditer(pattern, chunk.content, re.IGNORECASE)
			for match in matches:
				source = match.group(1).strip()
				target = match.group(2).strip()

				# Generate screen IDs
				source_id = self._normalize_id(source)
				target_id = self._normalize_id(target)

				# Extract context
				start = max(0, match.start() - 300)
				end = min(len(chunk.content), match.end() + 300)
				context = chunk.content[start:end]

				# Create transition
				transition = self._create_transition_from_context(
					source_id, target_id, context
				)
				transitions.append(transition)

		return transitions

	def _create_transition_from_context(
		self,
		from_screen_id: str,
		to_screen_id: str,
		context: str
	) -> TransitionDefinition:
		"""Create transition definition from extracted context."""
		transition_id = f"{from_screen_id}_to_{to_screen_id}"

		# Extract trigger
		trigger = self._extract_trigger(context)

		# Extract conditions
		conditions = self._extract_conditions(context)

		# Extract effects
		effects = self._extract_effects(context)

		return TransitionDefinition(
			transition_id=transition_id,
			from_screen_id=from_screen_id,
			to_screen_id=to_screen_id,
			triggered_by=trigger,
			conditions=conditions,
			effects=effects,
			metadata={
				'extraction_method': 'rule_based',
			}
		)

	def _extract_trigger(self, context: str) -> TransitionTrigger:
		"""Extract transition trigger."""
		# Look for action verbs
		trigger_patterns = [
			(r'clicking\s+["\']?([^"\']+)["\']?', 'click'),
			(r'submitting\s+["\']?([^"\']+)["\']?', 'submit'),
			(r'selecting\s+["\']?([^"\']+)["\']?', 'select_option'),
		]

		for pattern, action_type in trigger_patterns:
			match = re.search(pattern, context, re.IGNORECASE)
			if match:
				element_name = match.group(1).strip()
				return TransitionTrigger(
					action_type=action_type,
					element_id=self._normalize_id(element_name)
				)

		# Default trigger
		return TransitionTrigger(action_type='click')

	def _extract_conditions(self, context: str) -> dict[str, list[TransitionCondition]]:
		"""Extract transition conditions."""
		conditions: dict[str, list[TransitionCondition]] = {
			"required": [],
			"optional": []
		}

		# Pattern 1: Inline conditions ("must X", "requires Y")
		inline_patterns = [
			r'(?:must|requires?|only if)\s+(?:be\s+)?(.+?)(?:\.|,|\n|$)',
		]

		for pattern in inline_patterns:
			matches = re.finditer(pattern, context, re.IGNORECASE)
			for match in matches:
				condition_text = match.group(1).strip()
				if len(condition_text) > 2:  # Skip very short matches
					conditions['required'].append(TransitionCondition(
						type='custom',
						value=condition_text
					))

		# Pattern 2: List format ("- Must be X", "- Requires Y")
		list_pattern = r'^\s*[-*]\s*(?:must|requires?)\s+(?:be\s+)?(.+?)$'
		list_matches = re.finditer(list_pattern, context, re.IGNORECASE | re.MULTILINE)

		for match in list_matches:
			condition_text = match.group(1).strip()
			if len(condition_text) > 2:
				conditions['required'].append(TransitionCondition(
					type='custom',
					value=condition_text
				))

		return conditions

	def _extract_effects(self, context: str) -> list[TransitionEffect]:
		"""Extract transition effects."""
		effects = []

		# Look for "creates", "shows", "displays"
		effect_patterns = [
			r'(?:creates?|generates?)\s+(?:a\s+|an\s+)?([^\.]+)',
			r'(?:shows?|displays?)\s+(?:a\s+|an\s+)?([^\.]+)',
		]

		for pattern in effect_patterns:
			matches = re.finditer(pattern, context, re.IGNORECASE)
			for match in matches:
				effect_text = match.group(1).strip()
				effects.append(TransitionEffect(
					type='shows_message',
					value=effect_text
				))

		return effects

	def _normalize_id(self, name: str) -> str:
		"""Normalize name to ID format."""
		normalized = name.lower().strip()
		normalized = re.sub(r'[^\w\s-]', '', normalized)
		normalized = re.sub(r'[-\s]+', '_', normalized)
		return normalized

	def _deduplicate_transitions(self, transitions: list[TransitionDefinition]) -> list[TransitionDefinition]:
		"""Deduplicate transitions by transition_id."""
		seen = set()
		unique = []

		for transition in transitions:
			if transition.transition_id not in seen:
				seen.add(transition.transition_id)
				unique.append(transition)

		return unique

	def _validate_transition(self, transition: TransitionDefinition) -> list[str]:
		"""Validate transition definition against schema."""
		errors = []

		# Validate required fields
		if not transition.transition_id:
			errors.append("Missing transition_id")
		if not transition.from_screen_id:
			errors.append("Missing from_screen_id")
		if not transition.to_screen_id:
			errors.append("Missing to_screen_id")

		# Validate reliability score
		if not (0 <= transition.reliability_score <= 1):
			errors.append(f"Invalid reliability_score: {transition.reliability_score} (must be 0-1)")

		return errors


def validate_transition_definition(transition: TransitionDefinition) -> bool:
	"""
	Validate a transition definition against schema.
	
	Args:
		transition: Transition definition to validate
	
	Returns:
		True if valid, False otherwise
	"""
	extractor = TransitionExtractor()
	errors = extractor._validate_transition(transition)

	if errors:
		logger.error(f"Transition validation failed: {errors}")
		return False

	return True

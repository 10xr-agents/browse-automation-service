"""
Reference resolution for cross-entity links.

Resolves cross-references between screens, tasks, actions, and transitions:
- Match entity references by name, ID, or description
- Resolve ambiguous references using context
- Validate reference integrity
"""

import logging
from difflib import SequenceMatcher
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from navigator.knowledge.extract.actions import ActionDefinition
from navigator.knowledge.extract.screens import ScreenDefinition
from navigator.knowledge.extract.tasks import TaskDefinition
from navigator.knowledge.extract.transitions import TransitionDefinition

logger = logging.getLogger(__name__)


# =============================================================================
# Resolution Models
# =============================================================================

class ResolvedReference(BaseModel):
	"""Resolved entity reference."""
	reference_id: str = Field(..., description="Reference identifier")
	source_entity_id: str = Field(..., description="Source entity ID")
	source_field: str = Field(..., description="Source field name")
	target_entity_id: str = Field(..., description="Target entity ID")
	target_entity_type: str = Field(..., description="Target entity type")
	confidence: float = Field(..., description="Resolution confidence (0-1)")
	resolution_method: str = Field(..., description="How reference was resolved")


class AmbiguousReference(BaseModel):
	"""Ambiguous reference that needs manual review."""
	reference_id: str = Field(..., description="Reference identifier")
	source_entity_id: str = Field(..., description="Source entity ID")
	reference_text: str = Field(..., description="Reference text")
	candidates: list[dict[str, Any]] = Field(default_factory=list, description="Candidate entities")
	reason: str = Field(..., description="Why reference is ambiguous")


class DanglingReference(BaseModel):
	"""Dangling reference that couldn't be resolved."""
	reference_id: str = Field(..., description="Reference identifier")
	source_entity_id: str = Field(..., description="Source entity ID")
	reference_text: str = Field(..., description="Reference text")
	reason: str = Field(..., description="Why reference couldn't be resolved")


# =============================================================================
# Resolution Result
# =============================================================================

class ReferenceResolutionResult(BaseModel):
	"""Result of reference resolution."""
	resolution_id: str = Field(default_factory=lambda: str(uuid4()), description="Resolution ID")

	# Resolution results
	resolved: list[ResolvedReference] = Field(default_factory=list, description="Successfully resolved")
	ambiguous: list[AmbiguousReference] = Field(default_factory=list, description="Ambiguous references")
	dangling: list[DanglingReference] = Field(default_factory=list, description="Dangling references")

	# Metadata
	success: bool = Field(default=True, description="Whether resolution succeeded")
	statistics: dict[str, Any] = Field(default_factory=dict, description="Resolution statistics")

	def calculate_statistics(self) -> None:
		"""Calculate resolution statistics."""
		total = len(self.resolved) + len(self.ambiguous) + len(self.dangling)

		self.statistics = {
			'total_references': total,
			'resolved_count': len(self.resolved),
			'ambiguous_count': len(self.ambiguous),
			'dangling_count': len(self.dangling),
			'resolution_rate': len(self.resolved) / total if total > 0 else 0.0,
			'confidence_avg': sum(r.confidence for r in self.resolved) / len(self.resolved) if self.resolved else 0.0,
		}


# =============================================================================
# Reference Resolver
# =============================================================================

class ReferenceResolver:
	"""
	Resolves cross-references between entities.
	
	Features:
	- Name-based matching
	- ID-based matching
	- Fuzzy matching with confidence scores
	- Context-aware disambiguation
	"""

	def __init__(self, min_confidence: float = 0.7):
		"""
		Initialize reference resolver.
		
		Args:
			min_confidence: Minimum confidence threshold for fuzzy matches
		"""
		self.min_confidence = min_confidence

	def resolve_references(
		self,
		screens: list[ScreenDefinition],
		tasks: list[TaskDefinition],
		actions: list[ActionDefinition],
		transitions: list[TransitionDefinition]
	) -> ReferenceResolutionResult:
		"""
		Resolve all cross-references between entities.
		
		Args:
			screens: Screen definitions
			tasks: Task definitions
			actions: Action definitions
			transitions: Transition definitions
		
		Returns:
			ReferenceResolutionResult
		"""
		result = ReferenceResolutionResult()

		try:
			logger.info("Resolving cross-references between entities")

			# Build entity index for lookups
			entity_index = self._build_entity_index(screens, tasks, actions, transitions)

			# Resolve transition screen references
			self._resolve_transition_screen_refs(transitions, entity_index, result)

			# Resolve task action references
			self._resolve_task_action_refs(tasks, entity_index, result)

			# Resolve action element references (by selector)
			self._resolve_action_element_refs(actions, screens, result)

			# Calculate statistics
			result.calculate_statistics()

			logger.info(
				f"✅ Resolved {result.statistics['resolved_count']}/{result.statistics['total_references']} "
				f"references ({result.statistics['resolution_rate']:.1%})"
			)

			if result.statistics['ambiguous_count'] > 0:
				logger.warning(f"⚠️ {result.statistics['ambiguous_count']} ambiguous references need review")

			if result.statistics['dangling_count'] > 0:
				logger.error(f"❌ {result.statistics['dangling_count']} dangling references found")

		except Exception as e:
			logger.error(f"❌ Error resolving references: {e}", exc_info=True)
			result.success = False

		return result

	def _build_entity_index(
		self,
		screens: list[ScreenDefinition],
		tasks: list[TaskDefinition],
		actions: list[ActionDefinition],
		transitions: list[TransitionDefinition]
	) -> dict[str, dict[str, Any]]:
		"""Build index of all entities for quick lookup."""
		index: dict[str, dict[str, Any]] = {}

		for screen in screens:
			index[screen.screen_id] = {
				'type': 'screen',
				'name': screen.name,
				'url_patterns': screen.url_patterns,
				'entity': screen
			}

		for task in tasks:
			index[task.task_id] = {
				'type': 'task',
				'name': task.name,
				'entity': task
			}

		for action in actions:
			index[action.action_id] = {
				'type': 'action',
				'name': action.name,
				'entity': action
			}

		for transition in transitions:
			index[transition.transition_id] = {
				'type': 'transition',
				'from_screen': transition.from_screen_id,
				'to_screen': transition.to_screen_id,
				'entity': transition
			}

		return index

	def _resolve_transition_screen_refs(
		self,
		transitions: list[TransitionDefinition],
		entity_index: dict[str, dict[str, Any]],
		result: ReferenceResolutionResult
	) -> None:
		"""Resolve transition screen references."""
		for transition in transitions:
			# Resolve from_screen_id
			from_ref = self._resolve_reference(
				source_entity_id=transition.transition_id,
				source_field='from_screen_id',
				reference_text=transition.from_screen_id,
				target_type='screen',
				entity_index=entity_index
			)

			if from_ref['status'] == 'resolved':
				result.resolved.append(ResolvedReference(
					reference_id=str(uuid4()),
					source_entity_id=transition.transition_id,
					source_field='from_screen_id',
					target_entity_id=from_ref['target_id'],
					target_entity_type='screen',
					confidence=from_ref['confidence'],
					resolution_method=from_ref['method']
				))
			elif from_ref['status'] == 'ambiguous':
				result.ambiguous.append(AmbiguousReference(
					reference_id=str(uuid4()),
					source_entity_id=transition.transition_id,
					reference_text=transition.from_screen_id,
					candidates=from_ref['candidates'],
					reason=from_ref['reason']
				))
			else:
				result.dangling.append(DanglingReference(
					reference_id=str(uuid4()),
					source_entity_id=transition.transition_id,
					reference_text=transition.from_screen_id,
					reason=from_ref['reason']
				))

			# Resolve to_screen_id
			to_ref = self._resolve_reference(
				source_entity_id=transition.transition_id,
				source_field='to_screen_id',
				reference_text=transition.to_screen_id,
				target_type='screen',
				entity_index=entity_index
			)

			if to_ref['status'] == 'resolved':
				result.resolved.append(ResolvedReference(
					reference_id=str(uuid4()),
					source_entity_id=transition.transition_id,
					source_field='to_screen_id',
					target_entity_id=to_ref['target_id'],
					target_entity_type='screen',
					confidence=to_ref['confidence'],
					resolution_method=to_ref['method']
				))
			elif to_ref['status'] == 'ambiguous':
				result.ambiguous.append(AmbiguousReference(
					reference_id=str(uuid4()),
					source_entity_id=transition.transition_id,
					reference_text=transition.to_screen_id,
					candidates=to_ref['candidates'],
					reason=to_ref['reason']
				))
			else:
				result.dangling.append(DanglingReference(
					reference_id=str(uuid4()),
					source_entity_id=transition.transition_id,
					reference_text=transition.to_screen_id,
					reason=to_ref['reason']
				))

	def _resolve_task_action_refs(
		self,
		tasks: list[TaskDefinition],
		entity_index: dict[str, dict[str, Any]],
		result: ReferenceResolutionResult
	) -> None:
		"""Resolve task step action references."""
		for task in tasks:
			for step in task.steps:
				# Match step action type with actions
				step_action_type = step.type

				# Find matching actions
				matching_actions = [
					entity_id for entity_id, entity_data in entity_index.items()
					if entity_data['type'] == 'action' and entity_data['entity'].action_type == step_action_type
				]

				if len(matching_actions) == 1:
					# Exact match
					result.resolved.append(ResolvedReference(
						reference_id=str(uuid4()),
						source_entity_id=f"{task.task_id}__step__{step.step_id}",
						source_field='action_type',
						target_entity_id=matching_actions[0],
						target_entity_type='action',
						confidence=1.0,
						resolution_method='action_type_match'
					))
				elif len(matching_actions) > 1:
					# Ambiguous
					result.ambiguous.append(AmbiguousReference(
						reference_id=str(uuid4()),
						source_entity_id=f"{task.task_id}__step__{step.step_id}",
						reference_text=step_action_type,
						candidates=[{'entity_id': aid, 'type': 'action'} for aid in matching_actions],
						reason=f"Multiple actions match type '{step_action_type}'"
					))
				else:
					# Not found
					result.dangling.append(DanglingReference(
						reference_id=str(uuid4()),
						source_entity_id=f"{task.task_id}__step__{step.step_id}",
						reference_text=step_action_type,
						reason=f"No action found with type '{step_action_type}'"
					))

	def _resolve_action_element_refs(
		self,
		actions: list[ActionDefinition],
		screens: list[ScreenDefinition],
		result: ReferenceResolutionResult
	) -> None:
		"""Resolve action → UI element references (by selector)."""
		for action in actions:
			if not action.target_selector:
				continue

			# Find UI elements with matching selectors
			for screen in screens:
				for element in screen.ui_elements:
					# Extract CSS selector from element's strategies
					element_css = None
					if element.selector and element.selector.strategies:
						for strategy in element.selector.strategies:
							if strategy.type == "css" and strategy.css:
								element_css = strategy.css
								break

					if element_css and element_css == action.target_selector:
						result.resolved.append(ResolvedReference(
							reference_id=str(uuid4()),
							source_entity_id=action.action_id,
							source_field='target_selector',
							target_entity_id=element.element_id,
							target_entity_type='ui_element',
							confidence=1.0,
							resolution_method='selector_match'
						))

	def _resolve_reference(
		self,
		source_entity_id: str,
		source_field: str,
		reference_text: str,
		target_type: str,
		entity_index: dict[str, dict[str, Any]]
	) -> dict[str, Any]:
		"""
		Resolve a single reference.
		
		Returns:
			dict with status ('resolved', 'ambiguous', 'dangling'), target_id, confidence, etc.
		"""
		# Try exact ID match first
		if reference_text in entity_index and entity_index[reference_text]['type'] == target_type:
			return {
				'status': 'resolved',
				'target_id': reference_text,
				'confidence': 1.0,
				'method': 'exact_id_match'
			}

		# Try fuzzy name matching
		candidates = []
		for entity_id, entity_data in entity_index.items():
			if entity_data['type'] == target_type:
				# Calculate similarity
				name = entity_data.get('name', '')
				similarity = self._calculate_similarity(reference_text, name)

				if similarity >= self.min_confidence:
					candidates.append({
						'entity_id': entity_id,
						'name': name,
						'similarity': similarity
					})

		# Sort by similarity
		candidates.sort(key=lambda x: x['similarity'], reverse=True)

		if len(candidates) == 1:
			return {
				'status': 'resolved',
				'target_id': candidates[0]['entity_id'],
				'confidence': candidates[0]['similarity'],
				'method': 'fuzzy_name_match'
			}
		elif len(candidates) > 1:
			# Check if top candidate is significantly better
			if candidates[0]['similarity'] - candidates[1]['similarity'] > 0.2:
				return {
					'status': 'resolved',
					'target_id': candidates[0]['entity_id'],
					'confidence': candidates[0]['similarity'],
					'method': 'best_fuzzy_match'
				}
			else:
				return {
					'status': 'ambiguous',
					'candidates': candidates,
					'reason': f"Multiple {target_type} entities match '{reference_text}'"
				}
		else:
			return {
				'status': 'dangling',
				'reason': f"No {target_type} entity found matching '{reference_text}'"
			}

	def _calculate_similarity(self, text1: str, text2: str) -> float:
		"""Calculate similarity between two strings (0-1)."""
		# Normalize
		t1 = text1.lower().strip()
		t2 = text2.lower().strip()

		# Use SequenceMatcher
		return SequenceMatcher(None, t1, t2).ratio()


def resolve_references(
	screens: list[ScreenDefinition],
	tasks: list[TaskDefinition],
	actions: list[ActionDefinition],
	transitions: list[TransitionDefinition],
	min_confidence: float = 0.7
) -> ReferenceResolutionResult:
	"""
	Resolve cross-references between entities.
	
	Args:
		screens: Screen definitions
		tasks: Task definitions
		actions: Action definitions
		transitions: Transition definitions
		min_confidence: Minimum confidence for fuzzy matches
	
	Returns:
		ReferenceResolutionResult
	"""
	resolver = ReferenceResolver(min_confidence=min_confidence)
	return resolver.resolve_references(screens, tasks, actions, transitions)

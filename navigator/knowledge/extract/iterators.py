"""
Iterator and logic extraction/validation.

Critical validation layer for Agent-Killer edge cases:
- Detects loops in documentation
- Validates step linearity (no backward references)
- Ensures graph remains acyclic
- Validates iterator spec correctness
"""

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from navigator.knowledge.extract.tasks import IteratorSpec, TaskStep

logger = logging.getLogger(__name__)


# =============================================================================
# Validation Result Models
# =============================================================================

class LinearityValidationResult(BaseModel):
	"""Result of step linearity validation."""
	is_linear: bool = Field(..., description="Whether steps are linear (no loops)")
	backward_references: list[dict[str, Any]] = Field(
		default_factory=list,
		description="List of detected backward references"
	)
	validation_errors: list[str] = Field(default_factory=list, description="Validation errors")


class IteratorValidationResult(BaseModel):
	"""Result of iterator spec validation."""
	is_valid: bool = Field(..., description="Whether iterator spec is valid")
	iterator_type: str = Field(..., description="Iterator type detected")
	requires_conversion: bool = Field(default=False, description="Whether loops need conversion to iterator")
	suggestions: list[str] = Field(default_factory=list, description="Improvement suggestions")


class GraphCyclicityResult(BaseModel):
	"""Result of graph acyclic validation."""
	is_acyclic: bool = Field(..., description="Whether graph is acyclic")
	cycles_detected: list[list[str]] = Field(default_factory=list, description="Detected cycles")
	validation_errors: list[str] = Field(default_factory=list, description="Validation errors")


# =============================================================================
# Iterator Extractor / Validator
# =============================================================================

class IteratorExtractor:
	"""
	Validates and extracts iterator logic.
	
	Features:
	- Loop detection in documentation
	- Step linearity validation (Agent-Killer #1)
	- Iterator spec validation
	- Graph acyclic validation
	"""

	def __init__(self):
		"""Initialize iterator extractor."""
		pass

	def validate_step_linearity(self, steps: list[TaskStep]) -> LinearityValidationResult:
		"""
		Validate that task steps are linear (no backward references).
		
		Agent-Killer #1: CRITICAL - steps must form a DAG!
		
		Args:
			steps: Task steps to validate
		
		Returns:
			LinearityValidationResult
		"""
		result = LinearityValidationResult(is_linear=True)

		if not steps:
			return result

		# Check sequential ordering
		for i, step in enumerate(steps, start=1):
			if step.order != i:
				result.validation_errors.append(
					f"Step order not sequential: expected {i}, got {step.order}"
				)

		# Check for backward references
		for step in steps:
			# Check action description for backward references
			action_text = str(step.action)

			# Patterns indicating loops
			backward_patterns = [
				r'(?:go back to|return to|repeat|back to)\s+step\s+(\d+)',
				r'step\s+(\d+)\s+(?:again|once more)',
				r'repeat\s+(?:step|from)\s+(\d+)',
			]

			for pattern in backward_patterns:
				match = re.search(pattern, action_text, re.IGNORECASE)
				if match:
					ref_step = int(match.group(1))
					if ref_step <= step.order:
						result.is_linear = False
						result.backward_references.append({
							'from_step': step.order,
							'to_step': ref_step,
							'pattern_matched': match.group(0),
							'error': f"Step {step.order} references step {ref_step} (backward)"
						})
						result.validation_errors.append(
							f"LOOP DETECTED: Step {step.order} has backward reference to step {ref_step}"
						)

		return result

	def validate_iterator_spec(self, iterator_spec: IteratorSpec) -> IteratorValidationResult:
		"""
		Validate iterator specification.
		
		Args:
			iterator_spec: Iterator specification to validate
		
		Returns:
			IteratorValidationResult
		"""
		result = IteratorValidationResult(
			is_valid=True,
			iterator_type=iterator_spec.type
		)

		# Validate based on type
		if iterator_spec.type == 'collection_processing':
			# Must have collection_selector
			if not iterator_spec.collection_selector:
				result.is_valid = False
				result.suggestions.append("collection_processing iterator must have collection_selector")

			# Must have item_action
			if not iterator_spec.item_action:
				result.is_valid = False
				result.suggestions.append("collection_processing iterator must have item_action")

			# Should have termination_condition
			if not iterator_spec.termination_condition:
				result.suggestions.append("Consider adding termination_condition for robustness")

		elif iterator_spec.type == 'pagination':
			# Must have termination_condition
			if not iterator_spec.termination_condition:
				result.is_valid = False
				result.suggestions.append("pagination iterator must have termination_condition")

			# Should have item_action
			if not iterator_spec.item_action:
				result.suggestions.append("Consider adding item_action for pagination")

		# Validate max_iterations is reasonable
		if iterator_spec.max_iterations > 1000:
			result.suggestions.append(f"max_iterations ({iterator_spec.max_iterations}) is very high")

		return result

	def detect_loops_in_text(self, text: str) -> list[str]:
		"""
		Detect loop patterns in text that should be converted to iterator_spec.
		
		Args:
			text: Text to analyze
		
		Returns:
			List of detected loop patterns
		"""
		detected_patterns = []

		# Loop patterns that indicate iteration
		loop_indicators = [
			r'(?:for each|for every)\s+([^\n\.]+)',
			r'repeat\s+(?:until|while)\s+([^\n\.]+)',
			r'(?:delete|remove|process)\s+all\s+([^\n\.]+)',
			r'iterate\s+(?:over|through)\s+([^\n\.]+)',
			r'go through\s+(?:each|every)\s+([^\n\.]+)',
			r'while\s+([^\n\.]+?)\s+(?:is|are)',
		]

		for pattern in loop_indicators:
			matches = re.finditer(pattern, text, re.IGNORECASE)
			for match in matches:
				detected_patterns.append(match.group(0))

		return detected_patterns

	def validate_graph_acyclicity(
		self,
		transitions: list[tuple[str, str]]
	) -> GraphCyclicityResult:
		"""
		Validate that transition graph is acyclic (no cycles).
		
		Agent-Killer #1: Schema explicitly bans graph loops!
		
		Args:
			transitions: List of (from_screen_id, to_screen_id) tuples
		
		Returns:
			GraphCyclicityResult
		"""
		result = GraphCyclicityResult(is_acyclic=True)

		if not transitions:
			return result

		# Build adjacency list
		graph: dict[str, list[str]] = {}
		for from_id, to_id in transitions:
			if from_id not in graph:
				graph[from_id] = []
			graph[from_id].append(to_id)

		# Detect cycles using DFS
		visited = set()
		rec_stack = set()

		def dfs(node: str, path: list[str]) -> bool:
			"""DFS to detect cycles."""
			visited.add(node)
			rec_stack.add(node)
			path.append(node)

			# Visit neighbors
			for neighbor in graph.get(node, []):
				if neighbor not in visited:
					if dfs(neighbor, path):
						return True
				elif neighbor in rec_stack:
					# Cycle detected!
					cycle_start = path.index(neighbor)
					cycle = path[cycle_start:] + [neighbor]
					result.cycles_detected.append(cycle)
					result.is_acyclic = False
					result.validation_errors.append(
						f"CYCLE DETECTED: {' → '.join(cycle)}"
					)
					return True

			path.pop()
			rec_stack.remove(node)
			return False

		# Check all nodes
		for node in graph:
			if node not in visited:
				dfs(node, [])

		return result


def validate_step_linearity(steps: list[TaskStep]) -> LinearityValidationResult:
	"""
	Validate that steps are linear (no backward references).
	
	Args:
		steps: Task steps to validate
	
	Returns:
		LinearityValidationResult
	"""
	extractor = IteratorExtractor()
	return extractor.validate_step_linearity(steps)


def validate_iterator_spec(iterator_spec: IteratorSpec) -> IteratorValidationResult:
	"""
	Validate iterator specification.
	
	Args:
		iterator_spec: Iterator spec to validate
	
	Returns:
		IteratorValidationResult
	"""
	extractor = IteratorExtractor()
	return extractor.validate_iterator_spec(iterator_spec)

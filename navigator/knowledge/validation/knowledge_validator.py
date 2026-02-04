"""
Phase 4.1: Knowledge Validation Module

Comprehensive validation for all knowledge entities:
- Cross-reference validation (ensure IDs exist)
- State signature validation (ensure indicators are valid)
- URL pattern validation (ensure regex is valid)
- Action validation (ensure selectors are valid)
- Transition validation (ensure screens exist)
- Task validation (ensure steps are valid)
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from navigator.knowledge.persist.collections import (
	get_actions_collection,
	get_business_functions_collection,
	get_screens_collection,
	get_tasks_collection,
	get_transitions_collection,
	get_user_flows_collection,
	get_workflows_collection,
)

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
	"""A validation issue found during validation."""
	issue_type: str  # 'missing_reference', 'invalid_indicator', 'invalid_regex', etc.
	severity: str  # 'critical', 'warning', 'info'
	entity_type: str  # 'screen', 'task', 'action', 'transition', etc.
	entity_id: str
	field_name: str | None = None
	description: str = ""
	details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
	"""Result of knowledge validation."""
	total_checks: int = 0
	passed_checks: int = 0
	failed_checks: int = 0
	issues: list[ValidationIssue] = field(default_factory=list)
	entity_counts: dict[str, int] = field(default_factory=dict)

	@property
	def success_rate(self) -> float:
		"""Calculate success rate percentage."""
		if self.total_checks == 0:
			return 100.0
		return (self.passed_checks / self.total_checks) * 100

	@property
	def has_critical_issues(self) -> bool:
		"""Check if there are any critical issues."""
		return any(issue.severity == 'critical' for issue in self.issues)

	def add_issue(
		self,
		issue_type: str,
		severity: str,
		entity_type: str,
		entity_id: str,
		description: str,
		field_name: str | None = None,
		details: dict[str, Any] | None = None
	) -> None:
		"""Add a validation issue."""
		self.issues.append(ValidationIssue(
			issue_type=issue_type,
			severity=severity,
			entity_type=entity_type,
			entity_id=entity_id,
			field_name=field_name,
			description=description,
			details=details or {}
		))
		if severity == 'critical':
			self.failed_checks += 1
		self.total_checks += 1


class KnowledgeValidator:
	"""
	Phase 4.1: Comprehensive knowledge validator.
	
	Validates:
	1. Cross-references (ensure all referenced IDs exist)
	2. State signatures (ensure indicators are valid)
	3. URL patterns (ensure regex is valid)
	4. Actions (ensure selectors are valid)
	5. Transitions (ensure screens exist)
	6. Tasks (ensure steps are valid)
	"""

	def __init__(self, knowledge_id: str | None = None):
		"""
		Initialize knowledge validator.
		
		Args:
			knowledge_id: Optional knowledge ID to validate specific knowledge set
		"""
		self.knowledge_id = knowledge_id
		self._entity_cache: dict[str, dict[str, Any]] = {}

	async def validate_all(self) -> ValidationResult:
		"""
		Run all validation checks.
		
		Returns:
			ValidationResult with all validation results
		"""
		result = ValidationResult()
		
		logger.info(f"Starting knowledge validation (knowledge_id={self.knowledge_id})")
		
		try:
			# Build entity cache for efficient lookups
			await self._build_entity_cache()
			
			# Store entity counts
			for entity_type, cache in self._entity_cache.items():
				result.entity_counts[entity_type] = len(cache)
			
			# Run all validation checks
			await self._validate_cross_references(result)
			await self._validate_state_signatures(result)
			await self._validate_url_patterns(result)
			await self._validate_actions(result)
			await self._validate_transitions(result)
			await self._validate_tasks(result)
			await self._validate_spatial_information(result)  # Priority 7: Verify spatial information extraction
			await self._validate_business_function_mapping(result)  # Priority 8: Verify business function mapping and bidirectional linking
			await self._validate_relationship_quality(result)  # Priority 10: Comprehensive relationship quality validation
			
			# Calculate passed checks
			result.passed_checks = result.total_checks - result.failed_checks
			
			if result.has_critical_issues:
				logger.error(f"❌ Knowledge validation failed: {result.failed_checks} critical issues found")
			else:
				logger.info(f"✅ Knowledge validation passed: {result.passed_checks}/{result.total_checks} checks passed")
			
		except Exception as e:
			logger.error(f"❌ Knowledge validation failed with exception: {e}", exc_info=True)
			result.add_issue(
				"ValidationError",
				"critical",
				"system",
				"unknown",
				f"Validation exception: {str(e)}"
			)
		
		return result

	async def _build_entity_cache(self) -> None:
		"""Build cache of all entities for efficient ID lookups."""
		self._entity_cache = {
			'screens': {},
			'actions': {},
			'tasks': {},
			'transitions': {},
			'workflows': {},
			'user_flows': {},
			'business_functions': {},
		}
		
		# Build query filter
		query_filter: dict[str, Any] = {}
		if self.knowledge_id:
			query_filter['knowledge_id'] = self.knowledge_id
		
		# Cache screens
		screens_collection = await get_screens_collection()
		if screens_collection:
			async for doc in screens_collection.find(query_filter):
				screen_id = doc.get('screen_id')
				if screen_id:
					self._entity_cache['screens'][screen_id] = doc
		
		# Cache actions
		actions_collection = await get_actions_collection()
		if actions_collection:
			async for doc in actions_collection.find(query_filter):
				action_id = doc.get('action_id')
				if action_id:
					self._entity_cache['actions'][action_id] = doc
		
		# Cache tasks
		tasks_collection = await get_tasks_collection()
		if tasks_collection:
			async for doc in tasks_collection.find(query_filter):
				task_id = doc.get('task_id')
				if task_id:
					self._entity_cache['tasks'][task_id] = doc
		
		# Cache transitions
		transitions_collection = await get_transitions_collection()
		if transitions_collection:
			async for doc in transitions_collection.find(query_filter):
				transition_id = doc.get('transition_id')
				if transition_id:
					self._entity_cache['transitions'][transition_id] = doc
		
		# Cache workflows
		workflows_collection = await get_workflows_collection()
		if workflows_collection:
			async for doc in workflows_collection.find(query_filter):
				workflow_id = doc.get('workflow_id')
				if workflow_id:
					self._entity_cache['workflows'][workflow_id] = doc
		
		# Cache user flows
		user_flows_collection = await get_user_flows_collection()
		if user_flows_collection:
			async for doc in user_flows_collection.find(query_filter):
				user_flow_id = doc.get('user_flow_id')
				if user_flow_id:
					self._entity_cache['user_flows'][user_flow_id] = doc
		
		# Cache business functions
		bf_collection = await get_business_functions_collection()
		if bf_collection:
			async for doc in bf_collection.find(query_filter):
				bf_id = doc.get('business_function_id')
				if bf_id:
					self._entity_cache['business_functions'][bf_id] = doc
		
		# Store entity counts (will be populated in result during validation)
		
		logger.debug(f"Built entity cache: {sum(len(cache) for cache in self._entity_cache.values())} entities")

	async def _validate_cross_references(self, result: ValidationResult) -> None:
		"""Phase 4.1: Validate all cross-references (ensure IDs exist)."""
		logger.info("Validating cross-references...")
		
		# Validate screen references
		for screen_id, screen in self._entity_cache['screens'].items():
			# Check business_function_ids
			bf_ids = screen.get('business_function_ids', [])
			for bf_id in bf_ids:
				if bf_id not in self._entity_cache['business_functions']:
					result.add_issue(
						"MissingReference",
						"critical",
						"screen",
						screen_id,
						f"Screen references non-existent business function: {bf_id}",
						field_name="business_function_ids",
						details={'referenced_id': bf_id, 'entity_type': 'business_function'}
					)
			
			# Check user_flow_ids
			flow_ids = screen.get('user_flow_ids', [])
			for flow_id in flow_ids:
				if flow_id not in self._entity_cache['user_flows']:
					result.add_issue(
						"MissingReference",
						"critical",
						"screen",
						screen_id,
						f"Screen references non-existent user flow: {flow_id}",
						field_name="user_flow_ids",
						details={'referenced_id': flow_id, 'entity_type': 'user_flow'}
					)
			
			# Check task_ids
			task_ids = screen.get('task_ids', [])
			for task_id in task_ids:
				if task_id not in self._entity_cache['tasks']:
					result.add_issue(
						"MissingReference",
						"critical",
						"screen",
						screen_id,
						f"Screen references non-existent task: {task_id}",
						field_name="task_ids",
						details={'referenced_id': task_id, 'entity_type': 'task'}
					)
			
			# Check action_ids
			action_ids = screen.get('action_ids', [])
			for action_id in action_ids:
				if action_id not in self._entity_cache['actions']:
					result.add_issue(
						"MissingReference",
						"critical",
						"screen",
						screen_id,
						f"Screen references non-existent action: {action_id}",
						field_name="action_ids",
						details={'referenced_id': action_id, 'entity_type': 'action'}
					)
		
		# Validate action references
		for action_id, action in self._entity_cache['actions'].items():
			# Check screen_ids
			screen_ids = action.get('screen_ids', [])
			for screen_id in screen_ids:
				if screen_id not in self._entity_cache['screens']:
					result.add_issue(
						"MissingReference",
						"critical",
						"action",
						action_id,
						f"Action references non-existent screen: {screen_id}",
						field_name="screen_ids",
						details={'referenced_id': screen_id, 'entity_type': 'screen'}
					)
			
			# Check business_function_ids
			bf_ids = action.get('business_function_ids', [])
			for bf_id in bf_ids:
				if bf_id not in self._entity_cache['business_functions']:
					result.add_issue(
						"MissingReference",
						"critical",
						"action",
						action_id,
						f"Action references non-existent business function: {bf_id}",
						field_name="business_function_ids",
						details={'referenced_id': bf_id, 'entity_type': 'business_function'}
					)
		
		# Validate task references
		for task_id, task in self._entity_cache['tasks'].items():
			# Check screen_ids
			screen_ids = task.get('screen_ids', [])
			for screen_id in screen_ids:
				if screen_id not in self._entity_cache['screens']:
					result.add_issue(
						"MissingReference",
						"critical",
						"task",
						task_id,
						f"Task references non-existent screen: {screen_id}",
						field_name="screen_ids",
						details={'referenced_id': screen_id, 'entity_type': 'screen'}
					)
			
			# Check business_function_ids
			bf_ids = task.get('business_function_ids', [])
			for bf_id in bf_ids:
				if bf_id not in self._entity_cache['business_functions']:
					result.add_issue(
						"MissingReference",
						"critical",
						"task",
						task_id,
						f"Task references non-existent business function: {bf_id}",
						field_name="business_function_ids",
						details={'referenced_id': bf_id, 'entity_type': 'business_function'}
					)
		
		# Validate transition references
		for transition_id, transition in self._entity_cache['transitions'].items():
			# Check from_screen_id
			from_screen_id = transition.get('from_screen_id')
			if from_screen_id and from_screen_id not in self._entity_cache['screens']:
				result.add_issue(
					"MissingReference",
					"critical",
					"transition",
					transition_id,
					f"Transition references non-existent from_screen: {from_screen_id}",
					field_name="from_screen_id",
					details={'referenced_id': from_screen_id, 'entity_type': 'screen'}
				)
			
			# Check to_screen_id
			to_screen_id = transition.get('to_screen_id')
			if to_screen_id and to_screen_id not in self._entity_cache['screens']:
				result.add_issue(
					"MissingReference",
					"critical",
					"transition",
					transition_id,
					f"Transition references non-existent to_screen: {to_screen_id}",
					field_name="to_screen_id",
					details={'referenced_id': to_screen_id, 'entity_type': 'screen'}
				)
		
		# Validate workflow references
		for workflow_id, workflow in self._entity_cache['workflows'].items():
			# Check business_function_id
			bf_id = workflow.get('business_function_id')
			if bf_id and bf_id not in self._entity_cache['business_functions']:
				result.add_issue(
					"MissingReference",
					"critical",
					"workflow",
					workflow_id,
					f"Workflow references non-existent business function: {bf_id}",
					field_name="business_function_id",
					details={'referenced_id': bf_id, 'entity_type': 'business_function'}
				)
			
			# Check screen_ids
			screen_ids = workflow.get('screen_ids', [])
			for screen_id in screen_ids:
				if screen_id not in self._entity_cache['screens']:
					result.add_issue(
						"MissingReference",
						"critical",
						"workflow",
						workflow_id,
						f"Workflow references non-existent screen: {screen_id}",
						field_name="screen_ids",
						details={'referenced_id': screen_id, 'entity_type': 'screen'}
					)
		
		# Validate user flow references
		for user_flow_id, user_flow in self._entity_cache['user_flows'].items():
			# Check related_business_functions
			bf_ids = user_flow.get('related_business_functions', [])
			for bf_id in bf_ids:
				if bf_id not in self._entity_cache['business_functions']:
					result.add_issue(
						"MissingReference",
						"critical",
						"user_flow",
						user_flow_id,
						f"User flow references non-existent business function: {bf_id}",
						field_name="related_business_functions",
						details={'referenced_id': bf_id, 'entity_type': 'business_function'}
					)
			
			# Check related_screens
			screen_ids = user_flow.get('related_screens', [])
			for screen_id in screen_ids:
				if screen_id not in self._entity_cache['screens']:
					result.add_issue(
						"MissingReference",
						"warning",
						"user_flow",
						user_flow_id,
						f"User flow references non-existent screen: {screen_id}",
						field_name="related_screens",
						details={'referenced_id': screen_id, 'entity_type': 'screen'}
					)
			
			# Check related_actions
			action_ids = user_flow.get('related_actions', [])
			for action_id in action_ids:
				if action_id not in self._entity_cache['actions']:
					result.add_issue(
						"MissingReference",
						"warning",
						"user_flow",
						user_flow_id,
						f"User flow references non-existent action: {action_id}",
						field_name="related_actions",
						details={'referenced_id': action_id, 'entity_type': 'action'}
					)
		
		logger.info(f"Cross-reference validation complete: {len([i for i in result.issues if i.issue_type == 'MissingReference'])} issues found")

	async def _validate_state_signatures(self, result: ValidationResult) -> None:
		"""Phase 4.1: Validate state signatures (ensure indicators are valid)."""
		logger.info("Validating state signatures...")
		
		valid_indicator_types = ['dom_contains', 'url_matches', 'url_exact', 'dom_class', 'dom_id', 'dom_attribute']
		
		for screen_id, screen in self._entity_cache['screens'].items():
			state_signature = screen.get('state_signature', {})
			
			# Validate required_indicators
			required_indicators = state_signature.get('required_indicators', [])
			for idx, indicator in enumerate(required_indicators):
				if not isinstance(indicator, dict):
					result.add_issue(
						"InvalidIndicator",
						"critical",
						"screen",
						screen_id,
						f"Required indicator {idx} is not a dict",
						field_name="state_signature.required_indicators",
						details={'indicator_index': idx}
					)
					continue
				
				indicator_type = indicator.get('type')
				if indicator_type not in valid_indicator_types:
					result.add_issue(
						"InvalidIndicator",
						"critical",
						"screen",
						screen_id,
						f"Invalid indicator type: {indicator_type}",
						field_name="state_signature.required_indicators",
						details={'indicator_index': idx, 'indicator_type': indicator_type, 'valid_types': valid_indicator_types}
					)
				
				# Validate that value or pattern is provided
				if not indicator.get('value') and not indicator.get('pattern'):
					result.add_issue(
						"InvalidIndicator",
						"warning",
						"screen",
						screen_id,
						f"Indicator {idx} has neither value nor pattern",
						field_name="state_signature.required_indicators",
						details={'indicator_index': idx}
					)
			
			# Validate optional_indicators
			optional_indicators = state_signature.get('optional_indicators', [])
			for idx, indicator in enumerate(optional_indicators):
				if not isinstance(indicator, dict):
					continue
				
				indicator_type = indicator.get('type')
				if indicator_type not in valid_indicator_types:
					result.add_issue(
						"InvalidIndicator",
						"warning",
						"screen",
						screen_id,
						f"Invalid optional indicator type: {indicator_type}",
						field_name="state_signature.optional_indicators",
						details={'indicator_index': idx, 'indicator_type': indicator_type}
					)
			
			# Validate exclusion_indicators
			exclusion_indicators = state_signature.get('exclusion_indicators', [])
			for idx, indicator in enumerate(exclusion_indicators):
				if not isinstance(indicator, dict):
					continue
				
				indicator_type = indicator.get('type')
				if indicator_type not in valid_indicator_types:
					result.add_issue(
						"InvalidIndicator",
						"warning",
						"screen",
						screen_id,
						f"Invalid exclusion indicator type: {indicator_type}",
						field_name="state_signature.exclusion_indicators",
						details={'indicator_index': idx, 'indicator_type': indicator_type}
					)
			
			# Validate negative_indicators
			negative_indicators = state_signature.get('negative_indicators', [])
			for idx, indicator in enumerate(negative_indicators):
				if not isinstance(indicator, dict):
					continue
				
				indicator_type = indicator.get('type')
				if indicator_type not in valid_indicator_types:
					result.add_issue(
						"InvalidIndicator",
						"warning",
						"screen",
						screen_id,
						f"Invalid negative indicator type: {indicator_type}",
						field_name="state_signature.negative_indicators",
						details={'indicator_index': idx, 'indicator_type': indicator_type}
					)
		
		logger.info(f"State signature validation complete: {len([i for i in result.issues if i.issue_type == 'InvalidIndicator'])} issues found")

	async def _validate_url_patterns(self, result: ValidationResult) -> None:
		"""Phase 4.1: Validate URL patterns (ensure regex is valid)."""
		logger.info("Validating URL patterns...")
		
		for screen_id, screen in self._entity_cache['screens'].items():
			url_patterns = screen.get('url_patterns', [])
			
			for idx, pattern in enumerate(url_patterns):
				if not isinstance(pattern, str):
					result.add_issue(
						"InvalidURLPattern",
						"critical",
						"screen",
						screen_id,
						f"URL pattern {idx} is not a string",
						field_name="url_patterns",
						details={'pattern_index': idx}
					)
					continue
				
				# Try to compile regex pattern
				try:
					re.compile(pattern)
				except re.error as e:
					result.add_issue(
						"InvalidURLPattern",
						"critical",
						"screen",
						screen_id,
						f"Invalid regex pattern: {pattern} - {str(e)}",
						field_name="url_patterns",
						details={'pattern_index': idx, 'pattern': pattern, 'error': str(e)}
					)
		
		logger.info(f"URL pattern validation complete: {len([i for i in result.issues if i.issue_type == 'InvalidURLPattern'])} issues found")

	async def _validate_actions(self, result: ValidationResult) -> None:
		"""Phase 4.1: Validate actions (ensure selectors are valid)."""
		logger.info("Validating actions...")
		
		for action_id, action in self._entity_cache['actions'].items():
			# Validate selector if present
			selector = action.get('selector')
			if selector:
				if not isinstance(selector, str):
					result.add_issue(
						"InvalidSelector",
						"warning",
						"action",
						action_id,
						f"Selector is not a string",
						field_name="selector",
						details={'selector': selector}
					)
				elif len(selector.strip()) == 0:
					result.add_issue(
						"InvalidSelector",
						"warning",
						"action",
						action_id,
						"Selector is empty",
						field_name="selector",
						details={}
					)
			
			# Validate action_type
			action_type = action.get('action_type')
			valid_action_types = ['click', 'type', 'scroll', 'wait', 'navigate', 'extract', 'upload', 'select', 'send_keys']
			if action_type and action_type not in valid_action_types:
				result.add_issue(
					"InvalidActionType",
					"warning",
					"action",
					action_id,
					f"Invalid action_type: {action_type}",
					field_name="action_type",
					details={'action_type': action_type, 'valid_types': valid_action_types}
				)
		
		logger.info(f"Action validation complete: {len([i for i in result.issues if i.issue_type in ['InvalidSelector', 'InvalidActionType']])} issues found")

	async def _validate_transitions(self, result: ValidationResult) -> None:
		"""Phase 4.1: Validate transitions (ensure screens exist)."""
		logger.info("Validating transitions...")
		
		# This is partially covered in _validate_cross_references, but we add specific checks here
		for transition_id, transition in self._entity_cache['transitions'].items():
			from_screen_id = transition.get('from_screen_id')
			to_screen_id = transition.get('to_screen_id')
			
			# Both screens must exist (already checked in cross-references, but we add explicit check)
			if not from_screen_id:
				result.add_issue(
					"MissingTransitionScreen",
					"critical",
					"transition",
					transition_id,
					"Transition missing from_screen_id",
					field_name="from_screen_id",
					details={}
				)
			
			if not to_screen_id:
				result.add_issue(
					"MissingTransitionScreen",
					"critical",
					"transition",
					transition_id,
					"Transition missing to_screen_id",
					field_name="to_screen_id",
					details={}
				)
			
			# Validate that from and to are different
			if from_screen_id and to_screen_id and from_screen_id == to_screen_id:
				result.add_issue(
					"InvalidTransition",
					"warning",
					"transition",
					transition_id,
					"Transition from_screen_id and to_screen_id are the same",
					field_name="to_screen_id",
					details={'from_screen_id': from_screen_id, 'to_screen_id': to_screen_id}
				)
		
		logger.info(f"Transition validation complete: {len([i for i in result.issues if i.issue_type in ['MissingTransitionScreen', 'InvalidTransition']])} issues found")

	async def _validate_tasks(self, result: ValidationResult) -> None:
		"""Phase 4.1: Validate tasks (ensure steps are valid)."""
		logger.info("Validating tasks...")
		
		for task_id, task in self._entity_cache['tasks'].items():
			steps = task.get('steps', [])
			
			if not steps:
				result.add_issue(
					"InvalidTaskSteps",
					"warning",
					"task",
					task_id,
					"Task has no steps",
					field_name="steps",
					details={}
				)
				continue
			
			# Validate step order and structure
			step_orders = []
			for idx, step in enumerate(steps):
				if not isinstance(step, dict):
					result.add_issue(
						"InvalidTaskSteps",
						"critical",
						"task",
						task_id,
						f"Step {idx} is not a dict",
						field_name="steps",
						details={'step_index': idx}
					)
					continue
				
				# Check for order field
				order = step.get('order')
				if order is None:
					result.add_issue(
						"InvalidTaskSteps",
						"critical",
						"task",
						task_id,
						f"Step {idx} missing order field",
						field_name="steps",
						details={'step_index': idx}
					)
				else:
					step_orders.append(order)
				
				# Check for action field
				if not step.get('action'):
					result.add_issue(
						"InvalidTaskSteps",
						"warning",
						"task",
						task_id,
						f"Step {idx} missing action field",
						field_name="steps",
						details={'step_index': idx, 'order': order}
					)
			
			# Validate step order sequence
			if step_orders:
				expected_orders = list(range(1, len(step_orders) + 1))
				if sorted(step_orders) != expected_orders:
					result.add_issue(
						"InvalidTaskSteps",
						"warning",
						"task",
						task_id,
						f"Step orders are not sequential: {step_orders}",
						field_name="steps",
						details={'step_orders': step_orders, 'expected': expected_orders}
					)
		
		logger.info(f"Task validation complete: {len([i for i in result.issues if i.issue_type == 'InvalidTaskSteps'])} issues found")

	async def _validate_spatial_information(self, result: ValidationResult) -> None:
		"""
		Priority 7: Validate spatial information extraction for web UI screens.
		
		Verifies:
		- Regions are populated for web UI screens
		- Layout structure is populated
		- UI element position, layout_context, importance_score are populated
		- ScreenRegion objects are created correctly
		"""
		logger.info("Priority 7: Validating spatial information extraction...")
		
		web_ui_screens = [
			screen for screen_id, screen in self._entity_cache['screens'].items()
			if screen.get('content_type') == 'web_ui'
		]
		
		if not web_ui_screens:
			logger.debug("Priority 7: No web UI screens found to validate spatial information")
			return
		
		for screen_id, screen in self._entity_cache['screens'].items():
			# Only validate web UI screens (documentation screens don't need spatial info)
			if screen.get('content_type') != 'web_ui':
				continue
			
			screen_name = screen.get('name', 'Unknown')
			metadata = screen.get('metadata', {})
			ui_elements = screen.get('ui_elements', [])
			
			# Priority 7: Verify regions are populated
			regions = metadata.get('regions')
			if not regions:
				result.add_issue(
					"MissingSpatialRegions",
					"warning",  # Warning, not critical - regions are optional but recommended
					"screen",
					screen_id,
					f"Web UI screen '{screen_name}' has no regions (header, main, footer, etc.)",
					field_name="metadata.regions",
					details={
						'screen_name': screen_name,
						'content_type': screen.get('content_type'),
						'extraction_method': metadata.get('extraction_method', 'unknown')
					}
				)
			else:
				# Priority 7: Verify ScreenRegion objects are created correctly
				for idx, region in enumerate(regions):
					if not isinstance(region, dict):
						result.add_issue(
							"InvalidSpatialRegion",
							"critical",
							"screen",
							screen_id,
							f"Region {idx} is not a valid dict",
							field_name="metadata.regions",
							details={'region_index': idx}
						)
						continue
					
					# Check required fields
					if not region.get('region_id'):
						result.add_issue(
							"InvalidSpatialRegion",
							"critical",
							"screen",
							screen_id,
							f"Region {idx} missing region_id",
							field_name="metadata.regions",
							details={'region_index': idx}
						)
					
					if not region.get('region_type'):
						result.add_issue(
							"InvalidSpatialRegion",
							"critical",
							"screen",
							screen_id,
							f"Region {idx} missing region_type",
							field_name="metadata.regions",
							details={'region_index': idx}
						)
					
					if not region.get('bounds'):
						result.add_issue(
							"InvalidSpatialRegion",
							"warning",
							"screen",
							screen_id,
							f"Region {idx} missing bounds (x, y, width, height)",
							field_name="metadata.regions",
							details={'region_index': idx, 'region_type': region.get('region_type')}
						)
					else:
						# Validate bounds structure
						bounds = region.get('bounds', {})
						required_bounds = ['x', 'y', 'width', 'height']
						for bound_key in required_bounds:
							if bound_key not in bounds:
								result.add_issue(
									"InvalidSpatialRegion",
									"warning",
									"screen",
									screen_id,
									f"Region {idx} bounds missing '{bound_key}'",
									field_name="metadata.regions",
									details={'region_index': idx, 'region_type': region.get('region_type')}
								)
			
			# Priority 7: Verify layout_structure is populated
			layout_structure = metadata.get('layout_structure')
			if not layout_structure:
				result.add_issue(
					"MissingLayoutStructure",
					"warning",  # Warning, not critical - layout structure is optional but recommended
					"screen",
					screen_id,
					f"Web UI screen '{screen_name}' has no layout_structure",
					field_name="metadata.layout_structure",
					details={
						'screen_name': screen_name,
						'content_type': screen.get('content_type')
					}
				)
			else:
				# Validate layout_structure has type
				if not layout_structure.get('type'):
					result.add_issue(
						"InvalidLayoutStructure",
						"warning",
						"screen",
						screen_id,
						f"Layout structure missing 'type' field",
						field_name="metadata.layout_structure",
						details={'screen_name': screen_name}
					)
			
			# Priority 7: Verify UI element position, layout_context, importance_score are populated
			elements_with_spatial = 0
			elements_without_spatial = 0
			
			for elem_idx, element in enumerate(ui_elements):
				if not isinstance(element, dict):
					continue
				
				has_position = bool(element.get('position'))
				has_layout_context = bool(element.get('layout_context'))
				has_importance_score = element.get('importance_score') is not None
				
				# Count elements with spatial info
				if has_position or has_layout_context or has_importance_score:
					elements_with_spatial += 1
				else:
					elements_without_spatial += 1
				
				# Priority 7: Validate position structure if present
				if has_position:
					position = element.get('position', {})
					if isinstance(position, dict):
						# Check for required position fields
						if 'x' not in position or 'y' not in position:
							result.add_issue(
								"InvalidElementPosition",
								"warning",
								"screen",
								screen_id,
								f"UI element {elem_idx} position missing x or y coordinates",
								field_name="ui_elements.position",
								details={
									'element_index': elem_idx,
									'element_type': element.get('type', 'unknown')
								}
							)
					
					# Check for bounding_box
					if 'bounding_box' not in position and isinstance(position, dict):
						result.add_issue(
							"MissingElementBoundingBox",
							"info",  # Info level - bounding_box is optional
							"screen",
							screen_id,
							f"UI element {elem_idx} position missing bounding_box",
							field_name="ui_elements.position",
							details={
								'element_index': elem_idx,
								'element_type': element.get('type', 'unknown')
							}
						)
				
				# Priority 7: Validate layout_context if present
				if has_layout_context:
					layout_context = element.get('layout_context')
					valid_contexts = ['header', 'sidebar', 'main', 'footer', 'modal', 'navigation']
					if layout_context not in valid_contexts:
						result.add_issue(
							"InvalidElementLayoutContext",
							"warning",
							"screen",
							screen_id,
							f"UI element {elem_idx} has invalid layout_context: {layout_context}",
							field_name="ui_elements.layout_context",
							details={
								'element_index': elem_idx,
								'element_type': element.get('type', 'unknown'),
								'invalid_value': layout_context,
								'valid_values': valid_contexts
							}
						)
				
				# Priority 7: Validate importance_score if present
				if has_importance_score:
					importance_score = element.get('importance_score')
					if not isinstance(importance_score, (int, float)):
						result.add_issue(
							"InvalidElementImportanceScore",
							"warning",
							"screen",
							screen_id,
							f"UI element {elem_idx} importance_score is not a number: {importance_score}",
							field_name="ui_elements.importance_score",
							details={
								'element_index': elem_idx,
								'element_type': element.get('type', 'unknown')
							}
						)
					elif not (0.0 <= importance_score <= 1.0):
						result.add_issue(
							"InvalidElementImportanceScore",
							"warning",
							"screen",
							screen_id,
							f"UI element {elem_idx} importance_score out of range [0.0-1.0]: {importance_score}",
							field_name="ui_elements.importance_score",
							details={
								'element_index': elem_idx,
								'element_type': element.get('type', 'unknown')
							}
						)
			
			# Priority 7: Report if many elements lack spatial info
			total_elements = len(ui_elements)
			if total_elements > 0:
				spatial_coverage = elements_with_spatial / total_elements
				if spatial_coverage < 0.5:  # Less than 50% of elements have spatial info
					result.add_issue(
						"LowSpatialCoverage",
						"warning",
						"screen",
						screen_id,
						f"Web UI screen '{screen_name}' has low spatial coverage: {spatial_coverage:.1%} "
						f"({elements_with_spatial}/{total_elements} elements have spatial info)",
						field_name="ui_elements",
						details={
							'screen_name': screen_name,
							'total_elements': total_elements,
							'elements_with_spatial': elements_with_spatial,
							'elements_without_spatial': elements_without_spatial,
							'spatial_coverage': spatial_coverage
						}
					)
		
		spatial_issues = [
			i for i in result.issues
			if i.issue_type in [
				'MissingSpatialRegions', 'InvalidSpatialRegion', 'MissingLayoutStructure',
				'InvalidLayoutStructure', 'InvalidElementPosition', 'MissingElementBoundingBox',
				'InvalidElementLayoutContext', 'InvalidElementImportanceScore', 'LowSpatialCoverage'
			]
		]
		logger.info(
			f"Priority 7: Spatial information validation complete: "
			f"{len(spatial_issues)} issues found for {len(web_ui_screens)} web UI screens"
		)

	async def _validate_business_function_mapping(self, result: ValidationResult) -> None:
		"""
		Priority 8: Validate business function mapping and bidirectional linking.
		
		Verifies:
		- All entities are linked after post-extraction linking phase
		- Bidirectional linking is established correctly (screens ↔ business functions, tasks ↔ screens, etc.)
		- Relationship arrays are populated in all entities
		- Relationship consistency (if A links to B, then B should link to A)
		"""
		logger.info("Priority 8: Validating business function mapping and bidirectional linking...")
		
		screens = self._entity_cache['screens']
		actions = self._entity_cache['actions']
		tasks = self._entity_cache['tasks']
		business_functions = self._entity_cache['business_functions']
		transitions = self._entity_cache['transitions']
		workflows = self._entity_cache['workflows']
		
		# Priority 8: Verify relationship arrays are populated
		entities_without_relationships = 0
		entities_with_relationships = 0
		
		# Check screens
		for screen_id, screen in screens.items():
			has_relationships = (
				bool(screen.get('business_function_ids')) or
				bool(screen.get('user_flow_ids')) or
				bool(screen.get('task_ids')) or
				bool(screen.get('action_ids'))
			)
			if has_relationships:
				entities_with_relationships += 1
			else:
				entities_without_relationships += 1
				result.add_issue(
					"MissingEntityRelationships",
					"warning",
					"screen",
					screen_id,
					f"Screen '{screen.get('name', 'Unknown')}' has no relationships (business_function_ids, user_flow_ids, task_ids, action_ids)",
					field_name="relationships",
					details={
						'screen_name': screen.get('name', 'Unknown'),
						'content_type': screen.get('content_type', 'unknown')
					}
				)
		
		# Check actions
		for action_id, action in actions.items():
			has_relationships = (
				bool(action.get('screen_ids')) or
				bool(action.get('business_function_ids'))
			)
			if has_relationships:
				entities_with_relationships += 1
			else:
				entities_without_relationships += 1
				result.add_issue(
					"MissingEntityRelationships",
					"warning",
					"action",
					action_id,
					f"Action '{action.get('name', 'Unknown')}' has no relationships (screen_ids, business_function_ids)",
					field_name="relationships",
					details={
						'action_name': action.get('name', 'Unknown'),
						'action_type': action.get('action_type', 'unknown')
					}
				)
		
		# Check tasks
		for task_id, task in tasks.items():
			has_relationships = (
				bool(task.get('screen_ids')) or
				bool(task.get('business_function_ids'))
			)
			if has_relationships:
				entities_with_relationships += 1
			else:
				entities_without_relationships += 1
				result.add_issue(
					"MissingEntityRelationships",
					"warning",
					"task",
					task_id,
					f"Task '{task.get('name', 'Unknown')}' has no relationships (screen_ids, business_function_ids)",
					field_name="relationships",
					details={
						'task_name': task.get('name', 'Unknown')
					}
				)
		
		# Priority 8: Verify bidirectional linking (screens ↔ business functions)
		for screen_id, screen in screens.items():
			business_function_ids = screen.get('business_function_ids', [])
			for bf_id in business_function_ids:
				if bf_id in business_functions:
					bf = business_functions[bf_id]
					bf_screen_ids = bf.get('screen_ids', [])
					if screen_id not in bf_screen_ids:
						result.add_issue(
							"MissingBidirectionalLink",
							"warning",
							"screen",
							screen_id,
							f"Screen '{screen.get('name', 'Unknown')}' links to business function '{bf.get('name', bf_id)}', "
							f"but business function does not link back to screen (bidirectional link missing)",
							field_name="business_function_ids",
							details={
								'screen_name': screen.get('name', 'Unknown'),
								'business_function_id': bf_id,
								'business_function_name': bf.get('name', 'Unknown'),
								'expected_field': 'business_function.screen_ids'
							}
						)
		
		# Priority 8: Verify bidirectional linking (business functions ↔ screens)
		for bf_id, bf in business_functions.items():
			screen_ids = bf.get('screen_ids', [])
			for screen_id in screen_ids:
				if screen_id in screens:
					screen = screens[screen_id]
					screen_bf_ids = screen.get('business_function_ids', [])
					if bf_id not in screen_bf_ids:
						result.add_issue(
							"MissingBidirectionalLink",
							"warning",
							"business_function",
							bf_id,
							f"Business function '{bf.get('name', 'Unknown')}' links to screen '{screen.get('name', screen_id)}', "
							f"but screen does not link back to business function (bidirectional link missing)",
							field_name="screen_ids",
							details={
								'business_function_name': bf.get('name', 'Unknown'),
								'screen_id': screen_id,
								'screen_name': screen.get('name', 'Unknown'),
								'expected_field': 'screen.business_function_ids'
							}
						)
		
		# Priority 8: Verify bidirectional linking (tasks ↔ screens)
		for task_id, task in tasks.items():
			screen_ids = task.get('screen_ids', [])
			for screen_id in screen_ids:
				if screen_id in screens:
					screen = screens[screen_id]
					screen_task_ids = screen.get('task_ids', [])
					if task_id not in screen_task_ids:
						result.add_issue(
							"MissingBidirectionalLink",
							"warning",
							"task",
							task_id,
							f"Task '{task.get('name', 'Unknown')}' links to screen '{screen.get('name', screen_id)}', "
							f"but screen does not link back to task (bidirectional link missing)",
							field_name="screen_ids",
							details={
								'task_name': task.get('name', 'Unknown'),
								'screen_id': screen_id,
								'screen_name': screen.get('name', 'Unknown'),
								'expected_field': 'screen.task_ids'
							}
						)
		
		# Priority 8: Verify bidirectional linking (screens ↔ tasks)
		for screen_id, screen in screens.items():
			task_ids = screen.get('task_ids', [])
			for task_id in task_ids:
				if task_id in tasks:
					task = tasks[task_id]
					task_screen_ids = task.get('screen_ids', [])
					if screen_id not in task_screen_ids:
						result.add_issue(
							"MissingBidirectionalLink",
							"warning",
							"screen",
							screen_id,
							f"Screen '{screen.get('name', 'Unknown')}' links to task '{task.get('name', task_id)}', "
							f"but task does not link back to screen (bidirectional link missing)",
							field_name="task_ids",
							details={
								'screen_name': screen.get('name', 'Unknown'),
								'task_id': task_id,
								'task_name': task.get('name', 'Unknown'),
								'expected_field': 'task.screen_ids'
							}
						)
		
		# Priority 8: Verify bidirectional linking (actions ↔ screens)
		for action_id, action in actions.items():
			screen_ids = action.get('screen_ids', [])
			for screen_id in screen_ids:
				if screen_id in screens:
					screen = screens[screen_id]
					screen_action_ids = screen.get('action_ids', [])
					if action_id not in screen_action_ids:
						result.add_issue(
							"MissingBidirectionalLink",
							"warning",
							"action",
							action_id,
							f"Action '{action.get('name', 'Unknown')}' links to screen '{screen.get('name', screen_id)}', "
							f"but screen does not link back to action (bidirectional link missing)",
							field_name="screen_ids",
							details={
								'action_name': action.get('name', 'Unknown'),
								'screen_id': screen_id,
								'screen_name': screen.get('name', 'Unknown'),
								'expected_field': 'screen.action_ids'
							}
						)
		
		# Priority 8: Verify bidirectional linking (screens ↔ actions)
		for screen_id, screen in screens.items():
			action_ids = screen.get('action_ids', [])
			for action_id in action_ids:
				if action_id in actions:
					action = actions[action_id]
					action_screen_ids = action.get('screen_ids', [])
					if screen_id not in action_screen_ids:
						result.add_issue(
							"MissingBidirectionalLink",
							"warning",
							"screen",
							screen_id,
							f"Screen '{screen.get('name', 'Unknown')}' links to action '{action.get('name', action_id)}', "
							f"but action does not link back to screen (bidirectional link missing)",
							field_name="action_ids",
							details={
								'screen_name': screen.get('name', 'Unknown'),
								'action_id': action_id,
								'action_name': action.get('name', 'Unknown'),
								'expected_field': 'action.screen_ids'
							}
						)
		
		# Priority 8: Verify bidirectional linking (tasks ↔ business functions)
		for task_id, task in tasks.items():
			bf_ids = task.get('business_function_ids', [])
			for bf_id in bf_ids:
				if bf_id in business_functions:
					bf = business_functions[bf_id]
					bf_task_ids = bf.get('task_ids', [])
					if task_id not in bf_task_ids:
						result.add_issue(
							"MissingBidirectionalLink",
							"warning",
							"task",
							task_id,
							f"Task '{task.get('name', 'Unknown')}' links to business function '{bf.get('name', bf_id)}', "
							f"but business function does not link back to task (bidirectional link missing)",
							field_name="business_function_ids",
							details={
								'task_name': task.get('name', 'Unknown'),
								'business_function_id': bf_id,
								'business_function_name': bf.get('name', 'Unknown'),
								'expected_field': 'business_function.task_ids'
							}
						)
		
		# Priority 8: Verify bidirectional linking (actions ↔ business functions)
		for action_id, action in actions.items():
			bf_ids = action.get('business_function_ids', [])
			for bf_id in bf_ids:
				if bf_id in business_functions:
					bf = business_functions[bf_id]
					bf_action_ids = bf.get('action_ids', [])
					if action_id not in bf_action_ids:
						result.add_issue(
							"MissingBidirectionalLink",
							"warning",
							"action",
							action_id,
							f"Action '{action.get('name', 'Unknown')}' links to business function '{bf.get('name', bf_id)}', "
							f"but business function does not link back to action (bidirectional link missing)",
							field_name="business_function_ids",
							details={
								'action_name': action.get('name', 'Unknown'),
								'business_function_id': bf_id,
								'business_function_name': bf.get('name', 'Unknown'),
								'expected_field': 'business_function.action_ids'
							}
						)
		
		# Priority 8: Calculate relationship coverage statistics
		total_entities = len(screens) + len(actions) + len(tasks)
		if total_entities > 0:
			relationship_coverage = entities_with_relationships / total_entities
			if relationship_coverage < 0.5:  # Less than 50% of entities have relationships
				result.add_issue(
					"LowRelationshipCoverage",
					"warning",
					"system",
					"all",
					f"Low relationship coverage: {relationship_coverage:.1%} "
					f"({entities_with_relationships}/{total_entities} entities have relationships). "
					f"Post-extraction linking phase may not have run or may have failed.",
					field_name="relationships",
					details={
						'relationship_coverage': relationship_coverage,
						'entities_with_relationships': entities_with_relationships,
						'entities_without_relationships': entities_without_relationships,
						'total_entities': total_entities
					}
				)
		
		mapping_issues = [
			i for i in result.issues
			if i.issue_type in [
				'MissingEntityRelationships', 'MissingBidirectionalLink', 'LowRelationshipCoverage'
			]
		]
		logger.info(
			f"Priority 8: Business function mapping validation complete: "
			f"{len(mapping_issues)} issues found for {total_entities} entities "
			f"({entities_with_relationships} with relationships, {entities_without_relationships} without)"
		)

	async def _validate_relationship_quality(self, result: ValidationResult) -> None:
		"""
		Priority 10: Comprehensive relationship quality validation.
		
		Validates:
		1. Duplicate relationships (same entity pair linked multiple times)
		2. Conflicting relationships (contradictory relationship types)
		3. Invalid relationship references (references to non-existent entities)
		4. Relationship completeness (all expected relationships present)
		5. Relationship accuracy (relationships match actual entity connections)
		
		Args:
			result: Validation result to add issues to
		"""
		logger.info("Priority 10: Starting comprehensive relationship quality validation")
		
		# Use entity cache from _build_entity_cache()
		screens = self._entity_cache.get('screens', {})
		actions = self._entity_cache.get('actions', {})
		tasks = self._entity_cache.get('tasks', {})
		business_functions = self._entity_cache.get('business_functions', {})
		
		# Priority 10: Check for duplicate relationships
		await self._check_duplicate_relationships(result, screens, actions, tasks, business_functions)
		
		# Priority 10: Check for invalid relationship references
		await self._check_invalid_relationship_references(result, screens, actions, tasks, business_functions)
		
		# Priority 10: Check for conflicting relationships
		await self._check_conflicting_relationships(result, screens, actions, tasks, business_functions)
		
		# Priority 10: Calculate relationship quality metrics
		await self._calculate_relationship_quality_metrics(result, screens, actions, tasks, business_functions)
		
		relationship_quality_issues = [
			i for i in result.issues
			if i.issue_type in [
				'DuplicateRelationship', 'InvalidRelationshipReference', 'ConflictingRelationship',
				'LowRelationshipCompleteness', 'LowRelationshipAccuracy'
			]
		]
		logger.info(
			f"Priority 10: Relationship quality validation complete: "
			f"{len(relationship_quality_issues)} issues found"
		)

	async def _check_duplicate_relationships(
		self,
		result: ValidationResult,
		screens: dict[str, dict[str, Any]],
		actions: dict[str, dict[str, Any]],
		tasks: dict[str, dict[str, Any]],
		business_functions: dict[str, dict[str, Any]]
	) -> None:
		"""Priority 10: Check for duplicate relationships (same entity pair linked multiple times)."""
		# Check screens -> business functions
		for screen_id, screen in screens.items():
			bf_ids = screen.get('business_function_ids', [])
			seen_bf_ids = set()
			for bf_id in bf_ids:
				if bf_id in seen_bf_ids:
					result.add_issue(
						"DuplicateRelationship",
						"warning",
						"screen",
						screen_id,
						f"Screen '{screen.get('name', 'Unknown')}' has duplicate link to business function '{bf_id}'",
						field_name="business_function_ids",
						details={
							'screen_name': screen.get('name', 'Unknown'),
							'business_function_id': bf_id,
							'duplicate_count': bf_ids.count(bf_id)
						}
					)
				seen_bf_ids.add(bf_id)
		
		# Check screens -> tasks
		for screen_id, screen in screens.items():
			task_ids = screen.get('task_ids', [])
			seen_task_ids = set()
			for task_id in task_ids:
				if task_id in seen_task_ids:
					result.add_issue(
						"DuplicateRelationship",
						"warning",
						"screen",
						screen_id,
						f"Screen '{screen.get('name', 'Unknown')}' has duplicate link to task '{task_id}'",
						field_name="task_ids",
						details={
							'screen_name': screen.get('name', 'Unknown'),
							'task_id': task_id,
							'duplicate_count': task_ids.count(task_id)
						}
					)
				seen_task_ids.add(task_id)
		
		# Check screens -> actions
		for screen_id, screen in screens.items():
			action_ids = screen.get('action_ids', [])
			seen_action_ids = set()
			for action_id in action_ids:
				if action_id in seen_action_ids:
					result.add_issue(
						"DuplicateRelationship",
						"warning",
						"screen",
						screen_id,
						f"Screen '{screen.get('name', 'Unknown')}' has duplicate link to action '{action_id}'",
						field_name="action_ids",
						details={
							'screen_name': screen.get('name', 'Unknown'),
							'action_id': action_id,
							'duplicate_count': action_ids.count(action_id)
						}
					)
				seen_action_ids.add(action_id)
		
		# Check actions -> screens
		for action_id, action in actions.items():
			screen_ids = action.get('screen_ids', [])
			seen_screen_ids = set()
			for screen_id in screen_ids:
				if screen_id in seen_screen_ids:
					result.add_issue(
						"DuplicateRelationship",
						"warning",
						"action",
						action_id,
						f"Action '{action.get('name', 'Unknown')}' has duplicate link to screen '{screen_id}'",
						field_name="screen_ids",
						details={
							'action_name': action.get('name', 'Unknown'),
							'screen_id': screen_id,
							'duplicate_count': screen_ids.count(screen_id)
						}
					)
				seen_screen_ids.add(screen_id)
		
		# Check tasks -> screens
		for task_id, task in tasks.items():
			screen_ids = task.get('screen_ids', [])
			seen_screen_ids = set()
			for screen_id in screen_ids:
				if screen_id in seen_screen_ids:
					result.add_issue(
						"DuplicateRelationship",
						"warning",
						"task",
						task_id,
						f"Task '{task.get('name', 'Unknown')}' has duplicate link to screen '{screen_id}'",
						field_name="screen_ids",
						details={
							'task_name': task.get('name', 'Unknown'),
							'screen_id': screen_id,
							'duplicate_count': screen_ids.count(screen_id)
						}
					)
				seen_screen_ids.add(screen_id)

	async def _check_invalid_relationship_references(
		self,
		result: ValidationResult,
		screens: dict[str, dict[str, Any]],
		actions: dict[str, dict[str, Any]],
		tasks: dict[str, dict[str, Any]],
		business_functions: dict[str, dict[str, Any]]
	) -> None:
		"""Priority 10: Check for invalid relationship references (references to non-existent entities)."""
		# Check screens -> business functions
		for screen_id, screen in screens.items():
			bf_ids = screen.get('business_function_ids', [])
			for bf_id in bf_ids:
				if bf_id not in business_functions:
					result.add_issue(
						"InvalidRelationshipReference",
						"critical",
						"screen",
						screen_id,
						f"Screen '{screen.get('name', 'Unknown')}' references non-existent business function '{bf_id}'",
						field_name="business_function_ids",
						details={
							'screen_name': screen.get('name', 'Unknown'),
							'referenced_entity_type': 'business_function',
							'referenced_entity_id': bf_id
						}
					)
		
		# Check screens -> tasks
		for screen_id, screen in screens.items():
			task_ids = screen.get('task_ids', [])
			for task_id in task_ids:
				if task_id not in tasks:
					result.add_issue(
						"InvalidRelationshipReference",
						"critical",
						"screen",
						screen_id,
						f"Screen '{screen.get('name', 'Unknown')}' references non-existent task '{task_id}'",
						field_name="task_ids",
						details={
							'screen_name': screen.get('name', 'Unknown'),
							'referenced_entity_type': 'task',
							'referenced_entity_id': task_id
						}
					)
		
		# Check screens -> actions
		for screen_id, screen in screens.items():
			action_ids = screen.get('action_ids', [])
			for action_id in action_ids:
				if action_id not in actions:
					result.add_issue(
						"InvalidRelationshipReference",
						"critical",
						"screen",
						screen_id,
						f"Screen '{screen.get('name', 'Unknown')}' references non-existent action '{action_id}'",
						field_name="action_ids",
						details={
							'screen_name': screen.get('name', 'Unknown'),
							'referenced_entity_type': 'action',
							'referenced_entity_id': action_id
						}
					)
		
		# Check actions -> screens
		for action_id, action in actions.items():
			screen_ids = action.get('screen_ids', [])
			for screen_id in screen_ids:
				if screen_id not in screens:
					result.add_issue(
						"InvalidRelationshipReference",
						"critical",
						"action",
						action_id,
						f"Action '{action.get('name', 'Unknown')}' references non-existent screen '{screen_id}'",
						field_name="screen_ids",
						details={
							'action_name': action.get('name', 'Unknown'),
							'referenced_entity_type': 'screen',
							'referenced_entity_id': screen_id
						}
					)
		
		# Check tasks -> screens
		for task_id, task in tasks.items():
			screen_ids = task.get('screen_ids', [])
			for screen_id in screen_ids:
				if screen_id not in screens:
					result.add_issue(
						"InvalidRelationshipReference",
						"critical",
						"task",
						task_id,
						f"Task '{task.get('name', 'Unknown')}' references non-existent screen '{screen_id}'",
						field_name="screen_ids",
						details={
							'task_name': task.get('name', 'Unknown'),
							'referenced_entity_type': 'screen',
							'referenced_entity_id': screen_id
						}
					)
		
		# Check business functions -> screens, tasks, actions
		for bf_id, bf in business_functions.items():
			screen_ids = bf.get('screen_ids', [])
			for screen_id in screen_ids:
				if screen_id not in screens:
					result.add_issue(
						"InvalidRelationshipReference",
						"critical",
						"business_function",
						bf_id,
						f"Business function '{bf.get('name', 'Unknown')}' references non-existent screen '{screen_id}'",
						field_name="screen_ids",
						details={
							'business_function_name': bf.get('name', 'Unknown'),
							'referenced_entity_type': 'screen',
							'referenced_entity_id': screen_id
						}
					)
			
			task_ids = bf.get('task_ids', [])
			for task_id in task_ids:
				if task_id not in tasks:
					result.add_issue(
						"InvalidRelationshipReference",
						"critical",
						"business_function",
						bf_id,
						f"Business function '{bf.get('name', 'Unknown')}' references non-existent task '{task_id}'",
						field_name="task_ids",
						details={
							'business_function_name': bf.get('name', 'Unknown'),
							'referenced_entity_type': 'task',
							'referenced_entity_id': task_id
						}
					)
			
			action_ids = bf.get('action_ids', [])
			for action_id in action_ids:
				if action_id not in actions:
					result.add_issue(
						"InvalidRelationshipReference",
						"critical",
						"business_function",
						bf_id,
						f"Business function '{bf.get('name', 'Unknown')}' references non-existent action '{action_id}'",
						field_name="action_ids",
						details={
							'business_function_name': bf.get('name', 'Unknown'),
							'referenced_entity_type': 'action',
							'referenced_entity_id': action_id
						}
					)

	async def _check_conflicting_relationships(
		self,
		result: ValidationResult,
		screens: dict[str, dict[str, Any]],
		actions: dict[str, dict[str, Any]],
		tasks: dict[str, dict[str, Any]],
		business_functions: dict[str, dict[str, Any]]
	) -> None:
		"""Priority 10: Check for conflicting relationships (contradictory relationship patterns)."""
		# Check for screens that are linked to business functions but not to any tasks/actions
		# This might indicate incomplete linking
		for screen_id, screen in screens.items():
			bf_ids = screen.get('business_function_ids', [])
			task_ids = screen.get('task_ids', [])
			action_ids = screen.get('action_ids', [])
			
			# If screen is linked to business function but has no tasks/actions, it might be incomplete
			if bf_ids and not task_ids and not action_ids:
				result.add_issue(
					"ConflictingRelationship",
					"info",
					"screen",
					screen_id,
					f"Screen '{screen.get('name', 'Unknown')}' is linked to business function(s) but has no tasks or actions",
					field_name="relationships",
					details={
						'screen_name': screen.get('name', 'Unknown'),
						'business_function_ids': bf_ids,
						'has_tasks': False,
						'has_actions': False
					}
				)

	async def _calculate_relationship_quality_metrics(
		self,
		result: ValidationResult,
		screens: dict[str, dict[str, Any]],
		actions: dict[str, dict[str, Any]],
		tasks: dict[str, dict[str, Any]],
		business_functions: dict[str, dict[str, Any]]
	) -> None:
		"""Priority 10: Calculate relationship quality metrics (coverage, completeness, accuracy)."""
		total_entities = len(screens) + len(actions) + len(tasks)
		if total_entities == 0:
			return
		
		# Calculate relationship completeness (how many entities have expected relationships)
		entities_with_complete_relationships = 0
		
		# Screens should ideally have: business_function_ids, task_ids, action_ids
		for screen_id, screen in screens.items():
			has_bf = bool(screen.get('business_function_ids'))
			has_tasks = bool(screen.get('task_ids'))
			has_actions = bool(screen.get('action_ids'))
			# Consider complete if has at least 2 out of 3 relationship types
			if sum([has_bf, has_tasks, has_actions]) >= 2:
				entities_with_complete_relationships += 1
		
		# Actions should ideally have: screen_ids, business_function_ids
		for action_id, action in actions.items():
			has_screens = bool(action.get('screen_ids'))
			has_bf = bool(action.get('business_function_ids'))
			# Consider complete if has both relationship types
			if has_screens and has_bf:
				entities_with_complete_relationships += 1
		
		# Tasks should ideally have: screen_ids, business_function_ids
		for task_id, task in tasks.items():
			has_screens = bool(task.get('screen_ids'))
			has_bf = bool(task.get('business_function_ids'))
			# Consider complete if has both relationship types
			if has_screens and has_bf:
				entities_with_complete_relationships += 1
		
		relationship_completeness = entities_with_complete_relationships / total_entities if total_entities > 0 else 0.0
		
		# Calculate relationship accuracy (bidirectional links are correct)
		total_bidirectional_links = 0
		correct_bidirectional_links = 0
		
		# Check screens <-> business functions
		for screen_id, screen in screens.items():
			bf_ids = screen.get('business_function_ids', [])
			for bf_id in bf_ids:
				if bf_id in business_functions:
					total_bidirectional_links += 1
					bf = business_functions[bf_id]
					if screen_id in bf.get('screen_ids', []):
						correct_bidirectional_links += 1
		
		# Check screens <-> tasks
		for screen_id, screen in screens.items():
			task_ids = screen.get('task_ids', [])
			for task_id in task_ids:
				if task_id in tasks:
					total_bidirectional_links += 1
					task = tasks[task_id]
					if screen_id in task.get('screen_ids', []):
						correct_bidirectional_links += 1
		
		# Check screens <-> actions
		for screen_id, screen in screens.items():
			action_ids = screen.get('action_ids', [])
			for action_id in action_ids:
				if action_id in actions:
					total_bidirectional_links += 1
					action = actions[action_id]
					if screen_id in action.get('screen_ids', []):
						correct_bidirectional_links += 1
		
		relationship_accuracy = (
			correct_bidirectional_links / total_bidirectional_links
			if total_bidirectional_links > 0 else 1.0
		)
		
		# Report low completeness
		if relationship_completeness < 0.5:
			result.add_issue(
				"LowRelationshipCompleteness",
				"warning",
				"system",
				"all",
				f"Low relationship completeness: {relationship_completeness:.1%} "
				f"({entities_with_complete_relationships}/{total_entities} entities have complete relationships)",
				field_name="relationships",
				details={
					'relationship_completeness': relationship_completeness,
					'entities_with_complete_relationships': entities_with_complete_relationships,
					'total_entities': total_entities
				}
			)
		
		# Report low accuracy
		if relationship_accuracy < 0.8:
			result.add_issue(
				"LowRelationshipAccuracy",
				"warning",
				"system",
				"all",
				f"Low relationship accuracy: {relationship_accuracy:.1%} "
				f"({correct_bidirectional_links}/{total_bidirectional_links} bidirectional links are correct)",
				field_name="relationships",
				details={
					'relationship_accuracy': relationship_accuracy,
					'correct_bidirectional_links': correct_bidirectional_links,
					'total_bidirectional_links': total_bidirectional_links
				}
			)
		
		logger.info(
			f"Priority 10: Relationship quality metrics - "
			f"Completeness: {relationship_completeness:.1%}, "
			f"Accuracy: {relationship_accuracy:.1%}"
		)


async def validate_knowledge(knowledge_id: str | None = None) -> ValidationResult:
	"""
	Phase 4.1: Convenience function to validate knowledge.
	
	Args:
		knowledge_id: Optional knowledge ID to validate specific knowledge set
	
	Returns:
		ValidationResult with all validation results
	"""
	validator = KnowledgeValidator(knowledge_id=knowledge_id)
	return await validator.validate_all()

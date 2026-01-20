"""
Task extraction from ingested content.

Extracts task definitions with critical focus on:
- **Iterator Spec** (Agent-Killer #1): Convert loops to iterator_spec JSON
- **IO Spec** (Agent-Killer #3): Extract inputs/outputs with volatility
- **Linear Step Validation**: Ensure steps are DAG (no backward references)
"""

import logging
import re
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from navigator.schemas import ContentChunk

logger = logging.getLogger(__name__)


# =============================================================================
# Task Definition Models (aligned with KNOWLEDGE_SCHEMA_DESIGN.md)
# =============================================================================

class IOInput(BaseModel):
	"""Task input specification."""
	name: str = Field(..., description="Input variable name")
	type: str = Field(..., description="Data type (string, integer, boolean, etc.)")
	required: bool = Field(default=True, description="Whether input is required")
	description: str = Field(..., description="Human-readable description")
	source: str = Field(..., description="Where to get value: user_input|task_context|session_context|global_context")
	volatility: str = Field(..., description="Volatility level: high|medium|low")
	default: Any | None = Field(None, description="Default value if not provided")

	@field_validator('volatility')
	@classmethod
	def validate_volatility(cls, v: str) -> str:
		valid_levels = ['high', 'medium', 'low']
		if v not in valid_levels:
			raise ValueError(f"Invalid volatility: {v}. Must be one of {valid_levels}")
		return v

	@field_validator('source')
	@classmethod
	def validate_source(cls, v: str) -> str:
		valid_sources = ['user_input', 'task_context', 'session_context', 'global_context', 'generated_value', 'hardcoded']
		if v not in valid_sources:
			raise ValueError(f"Invalid source: {v}. Must be one of {valid_sources}")
		return v


class IOOutput(BaseModel):
	"""Task output specification."""
	name: str = Field(..., description="Output variable name")
	type: str = Field(..., description="Data type")
	description: str = Field(..., description="Human-readable description")
	extraction: dict[str, Any] = Field(..., description="How to extract this output")


class IOSpec(BaseModel):
	"""Task IO specification (Agent-Killer #3)."""
	inputs: list[IOInput] = Field(default_factory=list, description="Task inputs")
	outputs: list[IOOutput] = Field(default_factory=list, description="Task outputs")
	context_persistence: str = Field(default="session", description="How long to persist context")
	variable_resolution: dict[str, Any] = Field(
		default_factory=lambda: {
			"runtime_context_store": True,
			"resolution_order": ["task_context", "session_context", "global_context", "user_input"]
		},
		description="Variable resolution strategy"
	)


class IteratorSpec(BaseModel):
	"""Iterator specification (Agent-Killer #1 - prevents graph loops)."""
	type: str = Field(..., description="Iterator type: none|collection_processing|pagination")
	collection_selector: str | None = Field(None, description="CSS selector for collection items")
	item_action: dict[str, Any] | None = Field(None, description="Action to perform on each item")
	termination_condition: dict[str, Any] | None = Field(None, description="When to stop iterating")
	max_iterations: int = Field(default=50, description="Maximum iterations to prevent infinite loops")
	continue_on_error: bool = Field(default=False, description="Whether to continue if item processing fails")
	error_handling: dict[str, Any] = Field(
		default_factory=lambda: {
			"max_consecutive_errors": 3,
			"on_error": "abort"
		},
		description="Error handling strategy"
	)

	@field_validator('type')
	@classmethod
	def validate_type(cls, v: str) -> str:
		valid_types = ['none', 'collection_processing', 'pagination']
		if v not in valid_types:
			raise ValueError(f"Invalid iterator type: {v}. Must be one of {valid_types}")
		return v


class TaskPrecondition(BaseModel):
	"""Task step precondition."""
	type: str = Field(..., description="Precondition type")
	hard_dependency: bool = Field(default=True, description="Whether this is a hard requirement")
	auto_remediate: bool = Field(default=False, description="Whether to auto-fix if not met")
	remediation_task_id: str | None = Field(None, description="Task to run for remediation")


class TaskPostcondition(BaseModel):
	"""Task step postcondition."""
	type: str = Field(..., description="Postcondition type")
	success: bool = Field(default=True, description="Whether this indicates success")


class TaskStep(BaseModel):
	"""Task step definition."""
	step_id: str = Field(..., description="Unique step identifier")
	order: int = Field(..., description="Step order (must be sequential)")
	type: str = Field(..., description="Step type (navigation, form_fill, submit, etc.)")
	action: dict[str, Any] = Field(..., description="Action to perform")
	preconditions: list[TaskPrecondition] = Field(default_factory=list, description="Preconditions")
	postconditions: list[TaskPostcondition] = Field(default_factory=list, description="Postconditions")
	required: bool = Field(default=True, description="Whether step is required")
	can_skip: bool = Field(default=False, description="Whether step can be skipped")


class TaskDefinition(BaseModel):
	"""Complete task definition (aligned with MongoDB schema)."""
	task_id: str = Field(..., description="Unique task identifier")
	name: str = Field(..., description="Human-readable task name")
	website_id: str = Field(..., description="Website identifier")
	description: str = Field(..., description="Task description")
	category: str = Field(default="general", description="Task category")
	complexity: str = Field(default="medium", description="Complexity level: low|medium|high")
	estimated_duration: int = Field(default=30, description="Estimated duration in seconds")
	io_spec: IOSpec = Field(..., description="IO specification (Agent-Killer #3)")
	iterator_spec: IteratorSpec = Field(..., description="Iterator specification (Agent-Killer #1)")
	steps: list[TaskStep] = Field(default_factory=list, description="Task steps (MUST be linear)")
	success_criteria: list[dict[str, Any]] = Field(default_factory=list, description="Success criteria")
	failure_recovery: dict[str, Any] = Field(default_factory=dict, description="Failure recovery strategies")
	metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

	# Cross-reference fields (Phase 1: Schema Updates)
	business_function_ids: list[str] = Field(
		default_factory=list,
		description="Business function IDs this task supports"
	)
	user_flow_ids: list[str] = Field(
		default_factory=list,
		description="User flow IDs that include this task"
	)
	screen_ids: list[str] = Field(
		default_factory=list,
		description="Screen IDs where this task can be performed"
	)
	action_ids: list[str] = Field(
		default_factory=list,
		description="Action IDs required to complete this task"
	)
	workflow_ids: list[str] = Field(
		default_factory=list,
		description="Workflow IDs that include this task"
	)
	prerequisite_task_ids: list[str] = Field(
		default_factory=list,
		description="Task IDs that must be completed before this task"
	)
	dependent_task_ids: list[str] = Field(
		default_factory=list,
		description="Task IDs that depend on this task"
	)


# =============================================================================
# Task Extraction Result
# =============================================================================

class TaskExtractionResult(BaseModel):
	"""Result of task extraction."""
	extraction_id: str = Field(default_factory=lambda: str(uuid4()), description="Extraction ID")
	tasks: list[TaskDefinition] = Field(default_factory=list, description="Extracted tasks")
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
			'total_tasks': len(self.tasks),
			'tasks_with_iterators': sum(1 for t in self.tasks if t.iterator_spec.type != 'none'),
			'tasks_with_io_spec': sum(1 for t in self.tasks if t.io_spec.inputs or t.io_spec.outputs),
			'total_steps': sum(len(t.steps) for t in self.tasks),
			'avg_steps_per_task': sum(len(t.steps) for t in self.tasks) / len(self.tasks) if self.tasks else 0,
			'tasks_with_high_volatility_inputs': sum(
				1 for t in self.tasks
				if any(inp.volatility == 'high' for inp in t.io_spec.inputs)
			),
		}


# =============================================================================
# Task Extractor
# =============================================================================

class TaskExtractor:
	"""
	Extracts task definitions from content chunks.
	
	Features:
	- **Iterator spec extraction** (Agent-Killer #1)
	- **IO spec extraction** (Agent-Killer #3)
	- **Linear step validation** (no backward references)
	- Schema validation
	"""

	def __init__(self, website_id: str = "unknown"):
		"""
		Initialize task extractor.
		
		Args:
			website_id: Website identifier for extracted tasks
		"""
		self.website_id = website_id

	def extract_tasks(self, content_chunks: list[ContentChunk]) -> TaskExtractionResult:
		"""
		Extract task definitions from content chunks.
		
		Args:
			content_chunks: Content chunks to extract tasks from
		
		Returns:
			TaskExtractionResult with extracted tasks
		"""
		result = TaskExtractionResult()

		try:
			logger.info(f"Extracting tasks from {len(content_chunks)} content chunks")

			for chunk in content_chunks:
				tasks = self._extract_tasks_from_chunk(chunk)
				result.tasks.extend(tasks)

			# Deduplicate tasks
			result.tasks = self._deduplicate_tasks(result.tasks)

			# Validate extracted tasks
			for task in result.tasks:
				validation_errors = self._validate_task(task)
				if validation_errors:
					result.add_error(
						"ValidationError",
						f"Task '{task.task_id}' failed validation",
						{"task_id": task.task_id, "errors": validation_errors}
					)

			# Calculate statistics
			result.calculate_statistics()

			logger.info(
				f"✅ Extracted {result.statistics['total_tasks']} tasks "
				f"({result.statistics['tasks_with_iterators']} with iterators, "
				f"{result.statistics['tasks_with_io_spec']} with IO specs)"
			)

		except Exception as e:
			logger.error(f"❌ Error extracting tasks: {e}", exc_info=True)
			result.add_error("ExtractionError", str(e), {"exception_type": type(e).__name__})

		return result

	def _extract_tasks_from_chunk(self, chunk: ContentChunk) -> list[TaskDefinition]:
		"""
		Extract tasks from a single content chunk.
		
		Args:
			chunk: Content chunk to process
		
		Returns:
			List of extracted task definitions
		"""
		tasks = []

		# Pattern: Look for task/workflow descriptions
		task_patterns = [
			r'(?:Task|Workflow|Procedure):\s+(.+)',
			r'##\s+(?:How to|To)\s+(.+)',
			r'### (.+?)\s+(?:Task|Workflow|Process)',
		]

		for pattern in task_patterns:
			matches = re.finditer(pattern, chunk.content, re.IGNORECASE | re.MULTILINE)
			for match in matches:
				task_name = match.group(1).strip()
				task_id = self._generate_task_id(task_name)

				# Extract context around the match
				start = max(0, match.start() - 200)
				end = min(len(chunk.content), match.end() + 1500)
				context = chunk.content[start:end]

				# Create task definition
				task = self._create_task_from_context(task_id, task_name, context)
				tasks.append(task)

		return tasks

	def _create_task_from_context(
		self,
		task_id: str,
		task_name: str,
		context: str
	) -> TaskDefinition:
		"""
		Create task definition from extracted context.
		
		Args:
			task_id: Task identifier
			task_name: Task name
			context: Surrounding context text
		
		Returns:
			TaskDefinition
		"""
		# Extract iterator spec (Agent-Killer #1)
		iterator_spec = self._extract_iterator_spec(context)

		# Extract IO spec (Agent-Killer #3)
		io_spec = self._extract_io_spec(context)

		# Extract steps
		steps = self._extract_steps(context)

		# Validate linearity
		self._validate_step_linearity(steps)

		return TaskDefinition(
			task_id=task_id,
			name=task_name,
			website_id=self.website_id,
			description=self._extract_description(context),
			io_spec=io_spec,
			iterator_spec=iterator_spec,
			steps=steps,
			metadata={
				'extraction_method': 'rule_based',
				'extracted_from': 'documentation',
			}
		)

	def _extract_iterator_spec(self, context: str) -> IteratorSpec:
		"""
		Extract iterator specification (Agent-Killer #1).
		
		Detects loop patterns and converts to iterator_spec to prevent circular graphs.
		"""
		# Patterns that indicate iteration
		iterator_patterns = {
			'collection_processing': [
				r'(?:for each|for every)\s+([^\s]+)',
				r'delete\s+all\s+([^\s]+)',
				r'go through\s+(?:each|every)\s+([^\s]+)',
				r'iterate\s+(?:over|through)\s+([^\s]+)',
			],
			'pagination': [
				r'repeat\s+until\s+(.+)',
				r'while\s+(.+?)\s+(?:is|are)',
				r'continue\s+until\s+(.+)',
				r'paginate\s+through\s+(.+)',
			]
		}

		# Check for collection processing
		for pattern in iterator_patterns['collection_processing']:
			match = re.search(pattern, context, re.IGNORECASE)
			if match:
				collection_name = match.group(1).strip()
				logger.info(f"🔁 Detected collection_processing iterator: {collection_name}")

				return IteratorSpec(
					type='collection_processing',
					collection_selector=f".{collection_name}-row",  # Infer selector
					item_action={
						"task_id": f"process_{collection_name}",
						"reuse_task": True
					},
					termination_condition={
						"type": "element_disappears",
						"selector": f".{collection_name}-row",
						"timeout": 5.0
					},
					max_iterations=50,
					continue_on_error=False
				)

		# Check for pagination
		for pattern in iterator_patterns['pagination']:
			match = re.search(pattern, context, re.IGNORECASE)
			if match:
				condition = match.group(1).strip()
				logger.info(f"🔁 Detected pagination iterator: {condition}")

				return IteratorSpec(
					type='pagination',
					item_action={
						"task_id": "process_page",
						"reuse_task": True
					},
					termination_condition={
						"type": "condition_met",
						"condition": condition,
						"timeout": 5.0
					},
					max_iterations=50,
					continue_on_error=False
				)

		# No iterator detected
		return IteratorSpec(type='none')

	def _extract_io_spec(self, context: str) -> IOSpec:
		"""
		Extract IO specification (Agent-Killer #3).
		
		Extracts inputs/outputs with volatility levels for context resolution.
		"""
		io_spec = IOSpec()

		# Extract inputs (variables that need to be provided)
		input_patterns = [
			r'enter\s+(?:your\s+|the\s+)?([A-Z][a-z\s]+)',
			r'provide\s+(?:a\s+|your\s+|the\s+)?([A-Z][a-z\s]+)',
			r'input\s+(?:the\s+)?([A-Z][a-z\s]+)',
			r'type\s+(?:in\s+|your\s+)?([A-Z][a-z\s]+)',
		]

		for pattern in input_patterns:
			matches = re.finditer(pattern, context, re.IGNORECASE)
			for match in matches:
				input_name = match.group(1).strip()
				input_var_name = self._normalize_variable_name(input_name)

				# Determine volatility based on keywords
				volatility = self._determine_volatility(input_name)

				# Don't add duplicates
				if not any(inp.name == input_var_name for inp in io_spec.inputs):
					io_spec.inputs.append(IOInput(
						name=input_var_name,
						type="string",  # Default to string
						required=True,
						description=input_name,
						source="user_input",
						volatility=volatility
					))

		# Extract outputs (values that will be produced)
		output_patterns = [
			r'(?:creates?|generates?)\s+(?:a\s+|an\s+)?([A-Z][a-z\s]+)',
			r'(?:returns?|outputs?)\s+(?:the\s+)?([A-Z][a-z\s]+)',
			r'note\s+the\s+([A-Z][a-z\s]+)',
		]

		for pattern in output_patterns:
			matches = re.finditer(pattern, context, re.IGNORECASE)
			for match in matches:
				output_name = match.group(1).strip()
				output_var_name = self._normalize_variable_name(output_name)

				if not any(out.name == output_var_name for out in io_spec.outputs):
					io_spec.outputs.append(IOOutput(
						name=output_var_name,
						type="string",
						description=output_name,
						extraction={
							"method": "dom_extraction",
							"selector": f".{output_var_name}",
							"attribute": "text"
						}
					))

		return io_spec

	def _determine_volatility(self, input_name: str) -> str:
		"""
		Determine volatility level based on input name.
		
		Agent-Killer #3: Volatility determines caching strategy.
		- high: Tokens, passwords, MFA codes (always refresh)
		- medium: Session data (cache with TTL)
		- low: Names, emails (cache indefinitely)
		"""
		input_lower = input_name.lower()

		# High volatility (always refresh)
		high_volatility_keywords = [
			'token', 'password', 'mfa', '2fa', 'otp', 'code',
			'secret', 'key', 'credential', 'auth'
		]
		for keyword in high_volatility_keywords:
			if keyword in input_lower:
				return 'high'

		# Medium volatility (cache with TTL)
		medium_volatility_keywords = [
			'session', 'status', 'count', 'balance', 'quota'
		]
		for keyword in medium_volatility_keywords:
			if keyword in input_lower:
				return 'medium'

		# Low volatility (cache indefinitely)
		return 'low'

	def _extract_steps(self, context: str) -> list[TaskStep]:
		"""Extract task steps from context."""
		steps = []

		# Look for numbered steps
		step_pattern = r'(?:^|\n)\s*(\d+)[\.\)]\s+(.+?)(?=\n\s*\d+[\.\)]|\n\n|$)'
		matches = re.finditer(step_pattern, context, re.MULTILINE | re.DOTALL)

		for match in matches:
			step_num = int(match.group(1))
			step_text = match.group(2).strip()

			# Determine step type
			step_type = self._determine_step_type(step_text)

			steps.append(TaskStep(
				step_id=f"step_{step_num}",
				order=step_num,
				type=step_type,
				action={
					"action_type": step_type,
					"description": step_text
				}
			))

		return steps

	def _determine_step_type(self, step_text: str) -> str:
		"""Determine step type from text."""
		step_lower = step_text.lower()

		if any(word in step_lower for word in ['navigate', 'go to', 'open']):
			return 'navigation'
		elif any(word in step_lower for word in ['enter', 'type', 'input', 'fill']):
			return 'form_fill'
		elif any(word in step_lower for word in ['click', 'press', 'submit']):
			return 'submit'
		elif any(word in step_lower for word in ['wait', 'pause']):
			return 'wait'
		elif any(word in step_lower for word in ['select', 'choose']):
			return 'selection'
		else:
			return 'action'

	def _extract_description(self, context: str) -> str:
		"""Extract task description from context."""
		# Get first few sentences
		sentences = context.split('.')[:3]
		description = '. '.join(s.strip() for s in sentences if s.strip())
		return description[:200] if description else "No description"

	def _validate_step_linearity(self, steps: list[TaskStep]) -> None:
		"""
		Validate that steps are linear (DAG) with no backward references.
		
		Agent-Killer #1: Critical validation - steps must not create loops!
		"""
		if not steps:
			return

		# Check that steps are sequentially ordered
		for i, step in enumerate(steps, start=1):
			if step.order != i:
				logger.warning(f"⚠️ Step order mismatch: expected {i}, got {step.order}")

		# Check for backward references (would create loops)
		for step in steps:
			# In action description, look for references to previous steps
			action_text = str(step.action)

			# Pattern: "go back to step X" or "repeat step Y"
			backward_patterns = [
				r'(?:go back to|return to|repeat)\s+step\s+(\d+)',
				r'step\s+(\d+)\s+again',
			]

			for pattern in backward_patterns:
				match = re.search(pattern, action_text, re.IGNORECASE)
				if match:
					ref_step = int(match.group(1))
					if ref_step <= step.order:
						logger.error(
							f"❌ LOOP DETECTED: Step {step.order} references step {ref_step} (backward reference)"
						)
						raise ValueError(
							f"Step {step.order} contains backward reference to step {ref_step}. "
							f"This creates a graph loop. Convert to iterator_spec instead!"
						)

	def _normalize_variable_name(self, name: str) -> str:
		"""Normalize variable name (snake_case)."""
		# Convert to lowercase, replace spaces with underscores
		normalized = name.lower().strip()
		normalized = re.sub(r'[^\w\s-]', '', normalized)
		normalized = re.sub(r'[-\s]+', '_', normalized)
		return normalized

	def _generate_task_id(self, task_name: str) -> str:
		"""Generate task ID from task name."""
		return self._normalize_variable_name(task_name)

	def _deduplicate_tasks(self, tasks: list[TaskDefinition]) -> list[TaskDefinition]:
		"""Deduplicate tasks by task_id."""
		seen = set()
		unique = []

		for task in tasks:
			if task.task_id not in seen:
				seen.add(task.task_id)
				unique.append(task)

		return unique

	def _validate_task(self, task: TaskDefinition) -> list[str]:
		"""
		Validate task definition against schema.
		
		Returns:
			List of validation errors (empty if valid)
		"""
		errors = []

		# Validate required fields
		if not task.task_id:
			errors.append("Missing task_id")
		if not task.name:
			errors.append("Missing name")

		# Validate iterator spec type
		if task.iterator_spec.type not in ['none', 'collection_processing', 'pagination']:
			errors.append(f"Invalid iterator type: {task.iterator_spec.type}")

		# Validate steps are sequential
		for i, step in enumerate(task.steps, start=1):
			if step.order != i:
				errors.append(f"Step order not sequential: expected {i}, got {step.order}")

		# Validate IO spec
		for inp in task.io_spec.inputs:
			if inp.volatility not in ['high', 'medium', 'low']:
				errors.append(f"Invalid volatility for input '{inp.name}': {inp.volatility}")

		return errors


def validate_task_definition(task: TaskDefinition) -> bool:
	"""
	Validate a task definition against schema.
	
	Args:
		task: Task definition to validate
	
	Returns:
		True if valid, False otherwise
	"""
	extractor = TaskExtractor()
	errors = extractor._validate_task(task)

	if errors:
		logger.error(f"Task validation failed: {errors}")
		return False

	return True

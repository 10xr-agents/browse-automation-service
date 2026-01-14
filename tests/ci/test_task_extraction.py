"""
Tests for Phase 3.2: Task Extraction.

Validates:
- Task extraction from documentation
- Iterator spec extraction (Agent-Killer edge case #1)
- IO spec extraction (Agent-Killer edge case #3)
- Linear step validation (no backward references)
- Schema validation
"""

import pytest

from navigator.knowledge.extract import TaskExtractor
from navigator.knowledge.extract.tasks import (
	IOInput,
	IOSpec,
	IteratorSpec,
	TaskDefinition,
	TaskStep,
	validate_task_definition,
)
from navigator.schemas import ContentChunk


# =============================================================================
# Phase 3.2.1: Basic Task Extraction
# =============================================================================

def test_3_2_1_task_extractor_initialization():
	"""Test Phase 3.2.1 - TaskExtractor initialization."""
	extractor = TaskExtractor(website_id="test_site")
	
	assert extractor.website_id == "test_site"


def test_3_2_2_extract_tasks_from_basic_content():
	"""Test Phase 3.2.2 - Extract tasks from basic content."""
	extractor = TaskExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			## How to Create an Agent
			
			1. Navigate to the agent creation page
			2. Enter the agent name
			3. Click Save
			""",
			chunk_index=0,
			token_count=50,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_tasks(chunks)
	
	assert result.success is True
	assert result.statistics['total_tasks'] > 0
	assert len(result.tasks) > 0


# =============================================================================
# Phase 3.2.2: Iterator Spec Extraction (Agent-Killer Edge Case #1)
# =============================================================================

def test_3_2_3_extract_collection_processing_iterator():
	"""Test Phase 3.2.3 - Extract collection_processing iterator."""
	extractor = TaskExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			Task: Delete All Emails
			
			For each email in the inbox:
			1. Click the delete button
			2. Confirm deletion
			
			Continue until no emails remain.
			""",
			chunk_index=0,
			token_count=50,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_tasks(chunks)
	
	assert result.success is True
	assert result.statistics['tasks_with_iterators'] > 0
	
	# Verify iterator spec was extracted
	task = result.tasks[0]
	assert task.iterator_spec.type == 'collection_processing'
	assert task.iterator_spec.max_iterations == 50


def test_3_2_4_extract_pagination_iterator():
	"""Test Phase 3.2.4 - Extract pagination iterator."""
	extractor = TaskExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			Task: Process All Pages
			
			Repeat until the last page is reached:
			1. Process current page
			2. Click next button
			""",
			chunk_index=0,
			token_count=40,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_tasks(chunks)
	
	assert result.success is True
	task = result.tasks[0]
	assert task.iterator_spec.type == 'pagination'


def test_3_2_5_no_iterator_for_linear_task():
	"""Test Phase 3.2.5 - No iterator for linear tasks."""
	extractor = TaskExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			Task: Create Single Agent
			
			1. Navigate to create page
			2. Fill form
			3. Submit
			""",
			chunk_index=0,
			token_count=30,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_tasks(chunks)
	
	assert result.success is True
	task = result.tasks[0]
	assert task.iterator_spec.type == 'none'


# =============================================================================
# Phase 3.2.3: IO Spec Extraction (Agent-Killer Edge Case #3)
# =============================================================================

def test_3_2_6_extract_io_spec_inputs():
	"""Test Phase 3.2.6 - Extract IO spec inputs."""
	extractor = TaskExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			Task: Create Account
			
			Enter your Email Address in the email field.
			Provide your API Key for authentication.
			Type your Username.
			""",
			chunk_index=0,
			token_count=40,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_tasks(chunks)
	
	assert result.success is True
	assert result.statistics['tasks_with_io_spec'] > 0
	
	task = result.tasks[0]
	assert len(task.io_spec.inputs) > 0
	
	# Check that inputs were extracted
	input_names = [inp.name for inp in task.io_spec.inputs]
	assert any('email' in name.lower() for name in input_names)


def test_3_2_7_volatility_assignment():
	"""Test Phase 3.2.7 - Volatility assignment (Agent-Killer #3)."""
	extractor = TaskExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			Task: Secure Login
			
			Enter your Username (low volatility).
			Provide your Password (high volatility).
			Enter the MFA Token (high volatility).
			Input your Session ID (medium volatility).
			""",
			chunk_index=0,
			token_count=50,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_tasks(chunks)
	
	assert result.success is True
	task = result.tasks[0]
	
	# Check volatility assignments
	for inp in task.io_spec.inputs:
		if 'password' in inp.name.lower() or 'token' in inp.name.lower():
			assert inp.volatility == 'high', f"Expected high volatility for {inp.name}"
		elif 'session' in inp.name.lower():
			assert inp.volatility == 'medium', f"Expected medium volatility for {inp.name}"


def test_3_2_8_extract_io_spec_outputs():
	"""Test Phase 3.2.8 - Extract IO spec outputs."""
	extractor = TaskExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			Task: Create Agent
			
			1. Fill agent form
			2. Submit
			
			The system creates a new Agent ID.
			Note the Transaction ID for your records.
			""",
			chunk_index=0,
			token_count=40,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_tasks(chunks)
	
	assert result.success is True
	task = result.tasks[0]
	assert len(task.io_spec.outputs) > 0


# =============================================================================
# Phase 3.2.4: Linear Step Validation
# =============================================================================

def test_3_2_9_extract_sequential_steps():
	"""Test Phase 3.2.9 - Extract sequential steps."""
	extractor = TaskExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			Task: Complete Form
			
			1. Navigate to page
			2. Fill field A
			3. Fill field B
			4. Submit form
			""",
			chunk_index=0,
			token_count=40,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_tasks(chunks)
	
	assert result.success is True
	task = result.tasks[0]
	assert len(task.steps) == 4
	
	# Verify steps are sequential
	for i, step in enumerate(task.steps, start=1):
		assert step.order == i


def test_3_2_10_detect_backward_reference():
	"""Test Phase 3.2.10 - Detect backward references (loops)."""
	extractor = TaskExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			Task: Invalid Loop Task
			
			1. Do action A
			2. Do action B
			3. Go back to step 1
			""",
			chunk_index=0,
			token_count=30,
			chunk_type="documentation"
		)
	]
	
	# Extract and check for error
	result = extractor.extract_tasks(chunks)
	
	# Should fail with error due to backward reference
	assert result.success is False
	assert len(result.errors) > 0
	
	# Verify error message mentions loop/backward reference
	error_messages = [e['message'] for e in result.errors]
	assert any('loop' in msg.lower() or 'backward' in msg.lower() for msg in error_messages)


def test_3_2_11_linear_validation_passes():
	"""Test Phase 3.2.11 - Linear validation passes for valid steps."""
	steps = [
		TaskStep(step_id="step_1", order=1, type="navigation", action={}),
		TaskStep(step_id="step_2", order=2, type="form_fill", action={}),
		TaskStep(step_id="step_3", order=3, type="submit", action={}),
	]
	
	extractor = TaskExtractor()
	# Should not raise
	extractor._validate_step_linearity(steps)


# =============================================================================
# Phase 3.2.5: Schema Validation
# =============================================================================

def test_3_2_12_validate_task_definition():
	"""Test Phase 3.2.12 - Validate task definition."""
	task = TaskDefinition(
		task_id="test_task",
		name="Test Task",
		website_id="test_site",
		description="Test task description",
		io_spec=IOSpec(),
		iterator_spec=IteratorSpec(type='none'),
		steps=[
			TaskStep(step_id="step_1", order=1, type="action", action={})
		]
	)
	
	is_valid = validate_task_definition(task)
	assert is_valid is True


def test_3_2_13_invalid_iterator_type_fails():
	"""Test Phase 3.2.13 - Invalid iterator type fails validation."""
	with pytest.raises(ValueError):
		IteratorSpec(type='invalid_type')


def test_3_2_14_invalid_volatility_fails():
	"""Test Phase 3.2.14 - Invalid volatility fails validation."""
	with pytest.raises(ValueError):
		IOInput(
			name="test",
			type="string",
			description="Test input",
			source="user_input",
			volatility="invalid_level"
		)


# =============================================================================
# Integration Tests
# =============================================================================

def test_3_2_integration_full_extraction():
	"""Integration test - Full task extraction pipeline."""
	extractor = TaskExtractor(website_id="example_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			Task: Process All Customer Orders
			
			For each order in the order list:
			1. Navigate to order details
			2. Enter the Order Number
			3. Provide the API Token for verification
			4. Review and approve
			
			The system generates a Confirmation Code.
			""",
			chunk_index=0,
			token_count=100,
			chunk_type="documentation"
		),
		ContentChunk(
			chunk_id="chunk_2",
			content="""
			Workflow: Create New Product
			
			1. Navigate to products page
			2. Enter Product Name
			3. Type Product Description
			4. Submit form
			
			Note the Product ID created.
			""",
			chunk_index=1,
			token_count=50,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_tasks(chunks)
	
	# Verify results
	assert result.success is True
	assert result.statistics['total_tasks'] >= 2
	assert result.statistics['tasks_with_iterators'] >= 1
	assert result.statistics['tasks_with_io_spec'] >= 2
	
	# Verify first task has iterator (collection processing)
	task1 = result.tasks[0]
	assert task1.iterator_spec.type == 'collection_processing'
	
	# Verify tasks have IO specs
	assert len(task1.io_spec.inputs) > 0
	
	# Verify high volatility for API Token
	high_volatility_found = False
	for inp in task1.io_spec.inputs:
		if 'token' in inp.name.lower():
			assert inp.volatility == 'high'
			high_volatility_found = True
	assert high_volatility_found, "Should detect API Token as high volatility"
	
	# Verify statistics
	assert 'avg_steps_per_task' in result.statistics


def test_3_2_deduplication():
	"""Test task deduplication."""
	extractor = TaskExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="Task: Create Agent\n1. Fill form\n2. Submit",
			chunk_index=0,
			token_count=10,
			chunk_type="documentation"
		),
		ContentChunk(
			chunk_id="chunk_2",
			content="Task: Create Agent\n1. Navigate\n2. Fill form",
			chunk_index=1,
			token_count=10,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_tasks(chunks)
	
	# Should deduplicate tasks with same ID
	assert result.success is True
	task_ids = [t.task_id for t in result.tasks]
	assert len(task_ids) == len(set(task_ids)), "Duplicate task IDs found"

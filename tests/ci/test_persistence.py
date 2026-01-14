"""
Test Suite for Phase 5: Persistence & State Management

Tests MongoDB persistence layer for knowledge extraction workflow:
- Collections and schemas (5.1)
- Workflow state persistence (5.2)
- Checkpoint-based recovery (5.3)
- Ingestion deduplication (5.4)
- Full-definition storage (5.5)
"""

import asyncio
import pytest
from datetime import datetime

from navigator.knowledge.persist.collections import (
	WorkflowStatus,
	SourceType,
	WorkflowStateCollection,
	IngestionMetadataCollection,
	ProcessingCheckpointCollection,
	get_workflow_state_collection,
	get_ingestion_metadata_collection,
	get_checkpoint_collection,
	clear_all_collections,
)
from navigator.knowledge.persist.state import (
	WorkflowState,
	save_workflow_state,
	load_workflow_state,
	update_workflow_progress,
	record_workflow_error,
	mark_workflow_completed,
	query_workflows_by_status,
)
from navigator.knowledge.persist.checkpoints import (
	ProcessingCheckpoint,
	save_checkpoint,
	load_checkpoint,
	get_resume_point,
	create_checkpoint_from_progress,
	should_skip_item,
)
from navigator.knowledge.persist.deduplication import (
	IngestionMetadata,
	compute_content_hash,
	check_already_ingested,
	save_ingestion_metadata,
	is_content_changed,
)
from navigator.knowledge.persist.documents import (
	save_screen,
	get_screen,
	save_task,
	get_task,
)
from navigator.knowledge.extract.screens import ScreenDefinition, StateSignature, Indicator
from navigator.knowledge.extract.tasks import TaskDefinition


@pytest.fixture
async def clean_collections():
	"""Clean all test collections before and after tests."""
	try:
		await clear_all_collections()
		yield
		await clear_all_collections()
	except Exception as e:
		# Skip test if MongoDB unavailable
		pytest.skip(f"MongoDB not available: {e}")


# ============================================================================
# Phase 5.1: Collections Tests
# ============================================================================

@pytest.mark.asyncio
async def test_5_1_1_workflow_state_collection_schema():
	"""Test WorkflowStateCollection Pydantic schema validation."""
	# Valid workflow state
	state = WorkflowStateCollection(
		workflow_id="wf-123",
		job_id="job-456",
		status=WorkflowStatus.RUNNING,
		phase="ingestion",
		progress=50.0,
	)
	
	assert state.workflow_id == "wf-123"
	assert state.job_id == "job-456"
	assert state.status == WorkflowStatus.RUNNING
	assert state.phase == "ingestion"
	assert state.progress == 50.0
	assert isinstance(state.errors, list)
	assert isinstance(state.warnings, list)


@pytest.mark.asyncio
async def test_5_1_2_ingestion_metadata_collection_schema():
	"""Test IngestionMetadataCollection Pydantic schema validation."""
	# Valid ingestion metadata
	metadata = IngestionMetadataCollection(
		source_id="src-789",
		source_type=SourceType.DOCUMENTATION,
		source_url="https://example.com/docs",
		content_hash="abc123def456",
	)
	
	assert metadata.source_id == "src-789"
	assert metadata.source_type == SourceType.DOCUMENTATION
	assert metadata.source_url == "https://example.com/docs"
	assert metadata.content_hash == "abc123def456"


@pytest.mark.asyncio
async def test_5_1_3_processing_checkpoint_collection_schema():
	"""Test ProcessingCheckpointCollection Pydantic schema validation."""
	# Valid checkpoint
	checkpoint = ProcessingCheckpointCollection(
		workflow_id="wf-123",
		activity_name="extract_screens",
		checkpoint_id=0,
		items_processed=50,
		total_items=100,
		last_item_id="item-50",
	)
	
	assert checkpoint.workflow_id == "wf-123"
	assert checkpoint.activity_name == "extract_screens"
	assert checkpoint.checkpoint_id == 0
	assert checkpoint.items_processed == 50
	assert checkpoint.total_items == 100
	assert checkpoint.last_item_id == "item-50"


# ============================================================================
# Phase 5.2: Workflow State Persistence Tests
# ============================================================================

@pytest.mark.asyncio
async def test_5_2_1_save_and_load_workflow_state(clean_collections):
	"""Test saving and loading workflow state."""
	# Create workflow state
	state = WorkflowState(
		workflow_id="wf-test-1",
		job_id="job-test-1",
		status=WorkflowStatus.QUEUED,
		phase="initialization",
		progress=0.0,
	)
	
	# Save state
	success = await save_workflow_state(state)
	assert success, "Failed to save workflow state"
	
	# Load state
	loaded_state = await load_workflow_state("wf-test-1")
	assert loaded_state is not None, "Failed to load workflow state"
	assert loaded_state.workflow_id == "wf-test-1"
	assert loaded_state.job_id == "job-test-1"
	assert loaded_state.status == WorkflowStatus.QUEUED


@pytest.mark.asyncio
async def test_5_2_2_update_workflow_progress(clean_collections):
	"""Test updating workflow progress."""
	# Create initial state
	state = WorkflowState(workflow_id="wf-test-2", job_id="job-test-2")
	await save_workflow_state(state)
	
	# Update progress
	success = await update_workflow_progress(
		workflow_id="wf-test-2",
		phase="ingestion",
		progress=25.0,
		status=WorkflowStatus.RUNNING
	)
	assert success, "Failed to update workflow progress"
	
	# Verify update
	loaded_state = await load_workflow_state("wf-test-2")
	assert loaded_state.phase == "ingestion"
	assert loaded_state.progress == 25.0
	assert loaded_state.status == WorkflowStatus.RUNNING


@pytest.mark.asyncio
async def test_5_2_3_record_workflow_error(clean_collections):
	"""Test recording workflow errors."""
	# Create initial state
	state = WorkflowState(workflow_id="wf-test-3", job_id="job-test-3")
	await save_workflow_state(state)
	
	# Record error
	success = await record_workflow_error("wf-test-3", "Test error message")
	assert success, "Failed to record workflow error"
	
	# Verify error recorded
	loaded_state = await load_workflow_state("wf-test-3")
	assert len(loaded_state.errors) == 1
	assert "Test error message" in loaded_state.errors
	assert loaded_state.status == WorkflowStatus.FAILED


@pytest.mark.asyncio
async def test_5_2_4_mark_workflow_completed(clean_collections):
	"""Test marking workflow as completed."""
	# Create initial state
	state = WorkflowState(workflow_id="wf-test-4", job_id="job-test-4", status=WorkflowStatus.RUNNING)
	await save_workflow_state(state)
	
	# Mark as completed
	success = await mark_workflow_completed("wf-test-4")
	assert success, "Failed to mark workflow as completed"
	
	# Verify completion
	loaded_state = await load_workflow_state("wf-test-4")
	assert loaded_state.status == WorkflowStatus.COMPLETED
	assert loaded_state.progress == 100.0


# ============================================================================
# Phase 5.3: Checkpoint-Based Recovery Tests
# ============================================================================

@pytest.mark.asyncio
async def test_5_3_1_save_and_load_checkpoint(clean_collections):
	"""Test saving and loading checkpoints."""
	# Create checkpoint
	checkpoint = ProcessingCheckpoint(
		workflow_id="wf-cp-1",
		activity_name="test_activity",
		checkpoint_id=0,
		items_processed=10,
		total_items=100,
		last_item_id="item-10",
	)
	
	# Save checkpoint
	success = await save_checkpoint(checkpoint)
	assert success, "Failed to save checkpoint"
	
	# Load checkpoint
	loaded_checkpoint = await load_checkpoint("wf-cp-1", "test_activity", 0)
	assert loaded_checkpoint is not None, "Failed to load checkpoint"
	assert loaded_checkpoint.items_processed == 10
	assert loaded_checkpoint.last_item_id == "item-10"


@pytest.mark.asyncio
async def test_5_3_2_get_resume_point(clean_collections):
	"""Test getting the last checkpoint (resume point)."""
	# Save multiple checkpoints
	for i in range(3):
		checkpoint = ProcessingCheckpoint(
			workflow_id="wf-cp-2",
			activity_name="test_activity",
			checkpoint_id=i,
			items_processed=(i + 1) * 10,
			total_items=100,
			last_item_id=f"item-{(i + 1) * 10}",
		)
		await save_checkpoint(checkpoint)
	
	# Get resume point (should be last checkpoint)
	resume_point = await get_resume_point("wf-cp-2", "test_activity")
	assert resume_point is not None, "Failed to get resume point"
	assert resume_point.checkpoint_id == 2
	assert resume_point.items_processed == 30
	assert resume_point.last_item_id == "item-30"


@pytest.mark.asyncio
async def test_5_3_3_create_checkpoint_from_progress(clean_collections):
	"""Test creating checkpoint from progress information."""
	# Create checkpoint from progress
	checkpoint = await create_checkpoint_from_progress(
		workflow_id="wf-cp-3",
		activity_name="test_activity",
		items_processed=50,
		total_items=100,
		last_item_id="item-50",
	)
	
	assert checkpoint is not None, "Failed to create checkpoint"
	assert checkpoint.checkpoint_id == 0  # First checkpoint
	assert checkpoint.progress_percentage == 50.0


@pytest.mark.asyncio
async def test_5_3_4_should_skip_item(clean_collections):
	"""Test item skip logic based on checkpoint."""
	# Save checkpoint at item-50
	checkpoint = ProcessingCheckpoint(
		workflow_id="wf-cp-4",
		activity_name="test_activity",
		checkpoint_id=0,
		items_processed=50,
		total_items=100,
		last_item_id="50",
	)
	await save_checkpoint(checkpoint)
	
	# Items 1-50 should be skipped
	assert await should_skip_item("wf-cp-4", "test_activity", "25") == True
	assert await should_skip_item("wf-cp-4", "test_activity", "50") == True
	
	# Items 51+ should not be skipped
	assert await should_skip_item("wf-cp-4", "test_activity", "51") == False
	assert await should_skip_item("wf-cp-4", "test_activity", "75") == False


# ============================================================================
# Phase 5.4: Ingestion Deduplication Tests
# ============================================================================

@pytest.mark.asyncio
async def test_5_4_1_compute_content_hash():
	"""Test SHA-256 content hash computation."""
	# Test string input
	hash1 = compute_content_hash("Hello, World!")
	assert isinstance(hash1, str)
	assert len(hash1) == 64  # SHA-256 produces 64 hex characters
	
	# Test bytes input
	hash2 = compute_content_hash(b"Hello, World!")
	assert hash1 == hash2  # Same content should produce same hash
	
	# Different content should produce different hash
	hash3 = compute_content_hash("Different content")
	assert hash3 != hash1


@pytest.mark.asyncio
async def test_5_4_2_check_already_ingested(clean_collections):
	"""Test duplicate source detection."""
	# Save ingestion metadata
	metadata = IngestionMetadata(
		source_id="src-test-1",
		source_type=SourceType.DOCUMENTATION,
		source_url="https://example.com/docs",
		content_hash="hash123",
	)
	await save_ingestion_metadata(metadata)
	
	# Check if already ingested (by content_hash)
	found = await check_already_ingested(content_hash="hash123")
	assert found is not None, "Failed to find ingested source"
	assert found.source_id == "src-test-1"
	
	# Check if already ingested (by source_url)
	found2 = await check_already_ingested(source_url="https://example.com/docs")
	assert found2 is not None, "Failed to find ingested source by URL"


@pytest.mark.asyncio
async def test_5_4_3_is_content_changed(clean_collections):
	"""Test content change detection."""
	# Save initial metadata
	metadata = IngestionMetadata(
		source_id="src-test-2",
		source_type=SourceType.DOCUMENTATION,
		source_url="https://example.com/docs2",
		content_hash="hash-original",
	)
	await save_ingestion_metadata(metadata)
	
	# Same hash - content unchanged
	changed = await is_content_changed(
		source_url="https://example.com/docs2",
		source_path=None,
		new_content_hash="hash-original"
	)
	assert changed == False, "Content should be unchanged"
	
	# Different hash - content changed
	changed2 = await is_content_changed(
		source_url="https://example.com/docs2",
		source_path=None,
		new_content_hash="hash-modified"
	)
	assert changed2 == True, "Content should be changed"


# ============================================================================
# Phase 5.5: Full-Definition Storage Tests
# ============================================================================

@pytest.mark.asyncio
async def test_5_5_1_save_and_retrieve_screen(clean_collections):
	"""Test saving and retrieving full screen definition."""
	# Create screen definition
	screen = ScreenDefinition(
		screen_id="screen-test-1",
		name="Test Screen",
		website_id="website-1",
		url_patterns=[".*/test"],
		state_signature=StateSignature(
			required_indicators=[Indicator(pattern="Test", type="dom_contains")],
			optional_indicators=[],
			exclusion_indicators=[],
		),
		ui_elements=[],
		metadata={},
	)
	
	# Save screen
	success = await save_screen(screen)
	assert success, "Failed to save screen"
	
	# Retrieve screen
	loaded_screen = await get_screen("screen-test-1")
	assert loaded_screen is not None, "Failed to retrieve screen"
	assert loaded_screen.screen_id == "screen-test-1"
	assert loaded_screen.name == "Test Screen"
	assert loaded_screen.website_id == "website-1"


@pytest.mark.asyncio
async def test_5_5_2_save_and_retrieve_task(clean_collections):
	"""Test saving and retrieving full task definition."""
	# Create task definition
	task = TaskDefinition(
		task_id="task-test-1",
		name="Test Task",
		website_id="website-1",
		description="Test task description",
		goal="Test goal",
		steps=[],
		preconditions=[],
		postconditions=[],
	)
	
	# Save task
	success = await save_task(task)
	assert success, "Failed to save task"
	
	# Retrieve task
	loaded_task = await get_task("task-test-1")
	assert loaded_task is not None, "Failed to retrieve task"
	assert loaded_task.task_id == "task-test-1"
	assert loaded_task.name == "Test Task"
	assert loaded_task.website_id == "website-1"


# ============================================================================
# Integration Test
# ============================================================================

@pytest.mark.asyncio
async def test_5_6_integration_full_workflow(clean_collections):
	"""Test full workflow with state, checkpoints, and deduplication."""
	# 1. Create workflow state
	state = WorkflowState(
		workflow_id="wf-integration",
		job_id="job-integration",
		status=WorkflowStatus.RUNNING,
		phase="ingestion",
	)
	await save_workflow_state(state)
	
	# 2. Check for duplicate source
	content = "Test content for ingestion"
	content_hash = compute_content_hash(content)
	duplicate = await check_already_ingested(content_hash=content_hash)
	assert duplicate is None, "Should not find duplicate on first run"
	
	# 3. Save ingestion metadata
	metadata = IngestionMetadata(
		source_id="src-integration",
		source_type=SourceType.DOCUMENTATION,
		content_hash=content_hash,
	)
	await save_ingestion_metadata(metadata)
	
	# 4. Create checkpoint
	checkpoint = await create_checkpoint_from_progress(
		workflow_id="wf-integration",
		activity_name="ingest_source",
		items_processed=1,
		total_items=1,
	)
	assert checkpoint is not None
	
	# 5. Update progress
	await update_workflow_progress("wf-integration", "extraction", 50.0)
	
	# 6. Mark completed
	await mark_workflow_completed("wf-integration")
	
	# Verify final state
	final_state = await load_workflow_state("wf-integration")
	assert final_state.status == WorkflowStatus.COMPLETED
	assert final_state.progress == 100.0

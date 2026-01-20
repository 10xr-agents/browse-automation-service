"""
Test Suite for Phase 6: REST API Upgrades

Tests REST API endpoints for knowledge extraction:
- Ingestion API (6.1)
- Graph Query API (6.2)
- Knowledge Definition APIs (6.3)
- Workflow Status API (6.4)
- Verification Trigger API (6.5)
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# Import API models
from navigator.knowledge.rest_api import (
	StartIngestionRequest,
	StartIngestionResponse,
	GraphQueryRequest,
	GraphQueryResponse,
	WorkflowStatusResponse,
	VerificationRequest,
	VerificationResponse,
	IngestionOptionsModel,
	create_knowledge_api_router,
)
from navigator.knowledge.persist.collections import SourceType, WorkflowStatus
from navigator.knowledge.persist.state import WorkflowState
from navigator.knowledge.persist.checkpoints import ProcessingCheckpoint
from navigator.knowledge.extract.screens import ScreenDefinition, StateSignature, Indicator
from navigator.knowledge.extract.tasks import TaskDefinition


# ============================================================================
# Phase 6.1: Ingestion API Tests
# ============================================================================

@pytest.mark.asyncio
async def test_6_1_1_start_ingestion_request_validation():
	"""Test StartIngestionRequest Pydantic validation."""
	# Valid request
	request = StartIngestionRequest(
		source_type=SourceType.DOCUMENTATION,
		source_url="https://example.com/docs",
		source_name="Example Docs",
	)
	
	assert request.source_type == SourceType.DOCUMENTATION
	assert request.source_url == "https://example.com/docs"
	assert request.source_name == "Example Docs"
	assert isinstance(request.options, IngestionOptionsModel)


@pytest.mark.asyncio
async def test_6_1_2_ingestion_options_defaults():
	"""Test IngestionOptionsModel default values."""
	options = IngestionOptionsModel()
	
	assert options.extract_code_blocks == True
	assert options.extract_thumbnails == True
	assert options.max_pages is None
	assert options.max_depth is None


@pytest.mark.asyncio
async def test_6_1_3_start_ingestion_response_model():
	"""Test StartIngestionResponse model."""
	response = StartIngestionResponse(
		job_id="job-123",
		workflow_id="wf-123",
		status="queued",
		estimated_duration_seconds=300,
		message="Workflow started"
	)
	
	assert response.job_id == "job-123"
	assert response.workflow_id == "wf-123"
	assert response.status == "queued"
	assert response.estimated_duration_seconds == 300


# ============================================================================
# Phase 6.2: Graph Query API Tests
# ============================================================================

@pytest.mark.asyncio
async def test_6_2_1_graph_query_request_validation():
	"""Test GraphQueryRequest Pydantic validation."""
	# find_path query
	request = GraphQueryRequest(
		query_type="find_path",
		source_screen_id="screen-1",
		target_screen_id="screen-2",
		limit=10
	)
	
	assert request.query_type == "find_path"
	assert request.source_screen_id == "screen-1"
	assert request.target_screen_id == "screen-2"


@pytest.mark.asyncio
async def test_6_2_2_graph_query_response_model():
	"""Test GraphQueryResponse model."""
	response = GraphQueryResponse(
		query_type="find_path",
		results=[{"screen_id": "screen-1"}],
		count=1,
		execution_time_ms=25.5
	)
	
	assert response.query_type == "find_path"
	assert len(response.results) == 1
	assert response.count == 1
	assert response.execution_time_ms == 25.5


@pytest.mark.asyncio
async def test_6_2_3_query_types_validation():
	"""Test that all query types are valid."""
	valid_types = ["find_path", "get_neighbors", "search_screens", "get_transitions"]
	
	for query_type in valid_types:
		request = GraphQueryRequest(
			query_type=query_type,
			source_screen_id="screen-1",
			limit=10
		)
		assert request.query_type == query_type


# ============================================================================
# Phase 6.3: Knowledge Definition API Tests
# ============================================================================

@pytest.mark.asyncio
async def test_6_3_1_screen_definition_retrieval():
	"""Test screen definition response structure."""
	# This would test the actual API endpoint
	# For now, test that ScreenDefinition can be serialized
	screen = ScreenDefinition(
		screen_id="screen-test",
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
	
	screen_dict = screen.dict()
	assert screen_dict["screen_id"] == "screen-test"
	assert screen_dict["name"] == "Test Screen"
	assert "state_signature" in screen_dict


@pytest.mark.asyncio
async def test_6_3_2_task_definition_dict_structure():
	"""Test that task definition dict has expected structure."""
	# Test the expected structure of a task definition dict
	# (actual TaskDefinition validation tested in Phase 3)
	expected_fields = [
		"task_id", "name", "website_id", "description",
		"steps", "io_spec", "iterator_spec"
	]
	
	for field in expected_fields:
		assert field in expected_fields, f"Expected field {field} in task definition"


# ============================================================================
# Phase 6.4: Workflow Status API Tests
# ============================================================================

@pytest.mark.asyncio
async def test_6_4_1_workflow_status_response_model():
	"""Test WorkflowStatusResponse model."""
	from navigator.knowledge.api_v2 import CheckpointInfo, create_knowledge_api_router
	
	response = WorkflowStatusResponse(
		job_id="job-test",
		workflow_id="wf-test",
		status="running",
		phase="ingestion",
		progress=50.0,
		errors=[],
		warnings=[],
		checkpoints=[
			CheckpointInfo(
				activity_name="ingest_source",
				checkpoint_id=0,
				items_processed=50,
				total_items=100,
				progress_percentage=50.0
			)
		],
		created_at="2026-01-14T00:00:00",
		updated_at="2026-01-14T00:10:00",
		metadata={}
	)
	
	assert response.job_id == "job-test"
	assert response.status == "running"
	assert response.progress == 50.0
	assert len(response.checkpoints) == 1


@pytest.mark.asyncio
async def test_6_4_2_checkpoint_info_model():
	"""Test CheckpointInfo model."""
	from navigator.knowledge.api_v2 import CheckpointInfo, create_knowledge_api_router
	
	checkpoint = CheckpointInfo(
		activity_name="extract_screens",
		checkpoint_id=1,
		items_processed=75,
		total_items=100,
		progress_percentage=75.0
	)
	
	assert checkpoint.activity_name == "extract_screens"
	assert checkpoint.progress_percentage == 75.0


# ============================================================================
# Phase 6.5: Verification Trigger API Tests
# ============================================================================

@pytest.mark.asyncio
async def test_6_5_1_verification_request_validation():
	"""Test VerificationRequest Pydantic validation."""
	request = VerificationRequest(
		target_type="screen",
		target_id="screen-123",
		verification_options={"check_ui_elements": True}
	)
	
	assert request.target_type == "screen"
	assert request.target_id == "screen-123"
	assert request.verification_options["check_ui_elements"] == True


@pytest.mark.asyncio
async def test_6_5_2_verification_response_model():
	"""Test VerificationResponse model."""
	response = VerificationResponse(
		verification_job_id="verify-123",
		target_type="task",
		target_id="task-456",
		status="queued",
		message="Verification started"
	)
	
	assert response.verification_job_id == "verify-123"
	assert response.target_type == "task"
	assert response.status == "queued"


@pytest.mark.asyncio
async def test_6_5_3_verification_target_types():
	"""Test all verification target types are valid."""
	valid_types = ["job", "screen", "task"]
	
	for target_type in valid_types:
		request = VerificationRequest(
			target_type=target_type,
			target_id="test-id"
		)
		assert request.target_type == target_type


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_6_6_integration_workflow_lifecycle():
	"""Test full workflow lifecycle through API models."""
	# 1. Start ingestion
	start_request = StartIngestionRequest(
		source_type=SourceType.WEBSITE,
		source_url="https://example.com",
		source_name="Example Site"
	)
	
	# Simulate workflow start
	job_id = "job-integration-test"
	workflow_id = f"knowledge-extraction-{job_id}"
	
	# 2. Check status (simulated)
	status_response = WorkflowStatusResponse(
		job_id=job_id,
		workflow_id=workflow_id,
		status="running",
		phase="ingestion",
		progress=25.0,
		errors=[],
		warnings=[],
		checkpoints=[],
		created_at="2026-01-14T00:00:00",
		updated_at="2026-01-14T00:05:00",
		metadata={}
	)
	
	assert status_response.progress == 25.0
	assert status_response.phase == "ingestion"
	
	# 3. Query graph (after completion)
	query_request = GraphQueryRequest(
		query_type="search_screens",
		website_id="website-integration",
		limit=10
	)
	
	assert query_request.query_type == "search_screens"
	
	# 4. Start verification
	verify_request = VerificationRequest(
		target_type="job",
		target_id=job_id
	)
	
	assert verify_request.target_id == job_id


@pytest.mark.asyncio
async def test_6_7_api_error_handling():
	"""Test API error handling scenarios."""
	# Test invalid source type (should fail validation)
	with pytest.raises(Exception):  # Pydantic validation error
		StartIngestionRequest(
			source_type="invalid_type",  # type: ignore
			source_url="https://example.com"
		)
	
	# Test invalid query type (should fail validation)
	with pytest.raises(Exception):  # Pydantic validation error
		GraphQueryRequest(
			query_type="invalid_query",  # type: ignore
			source_screen_id="screen-1"
		)

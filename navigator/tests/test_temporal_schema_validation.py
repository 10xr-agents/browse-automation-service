"""
Test suite for Temporal activity schema validation.

This test suite validates that:
1. All activity input schemas match their function signatures
2. All activity calls use correct parameter names
3. Required parameters are provided
4. Function calls match their expected signatures
"""

import inspect
import logging
from dataclasses import fields, is_dataclass
from typing import Any, get_type_hints

import pytest

from navigator.schemas import (
	AnalyzeFramesBatchInput,
	AssembleVideoIngestionInput,
	BuildGraphInput,
	DeleteKnowledgeInput,
	EnrichKnowledgeInput,
	ExplorePrimaryUrlInput,
	ExtractActionsInput,
	ExtractBusinessFunctionsInput,
	ExtractScreensInput,
	ExtractTasksInput,
	ExtractTransitionsInput,
	ExtractUserFlowsInput,
	ExtractWorkflowsInput,
	FilterFramesInput,
	IngestSourceInput,
	KnowledgeExtractionInputV2,
	TranscribeVideoInput,
	VerifyExtractionInput,
)

logger = logging.getLogger(__name__)


# Map activity names to their input schemas
ACTIVITY_SCHEMA_MAP = {
	'ingest_source': IngestSourceInput,
	'transcribe_video': TranscribeVideoInput,
	'filter_frames': FilterFramesInput,
	'analyze_frames_batch': AnalyzeFramesBatchInput,
	'assemble_video_ingestion': AssembleVideoIngestionInput,
	'extract_screens': ExtractScreensInput,
	'extract_tasks': ExtractTasksInput,
	'extract_actions': ExtractActionsInput,
	'extract_transitions': ExtractTransitionsInput,
	'extract_business_functions': ExtractBusinessFunctionsInput,
	'extract_workflows': ExtractWorkflowsInput,
	'extract_user_flows': ExtractUserFlowsInput,
	'build_graph': BuildGraphInput,
	'explore_primary_url': ExplorePrimaryUrlInput,
	'verify_extraction': VerifyExtractionInput,
	'enrich_knowledge': EnrichKnowledgeInput,
	'delete_knowledge': DeleteKnowledgeInput,
}


def get_dataclass_fields(schema_class: type) -> dict[str, Any]:
	"""Get all fields from a dataclass schema."""
	if not is_dataclass(schema_class):
		return {}
	
	field_dict = {}
	for field_obj in fields(schema_class):
		field_dict[field_obj.name] = {
			'type': field_obj.type,
			'default': field_obj.default if field_obj.default != inspect.Parameter.empty else None,
			'default_factory': field_obj.default_factory if hasattr(field_obj, 'default_factory') else None,
			'required': field_obj.default == inspect.Parameter.empty and not hasattr(field_obj, 'default_factory'),
		}
	return field_dict


def validate_schema_instantiation(schema_class: type, test_data: dict[str, Any] | None = None) -> tuple[bool, str]:
	"""
	Validate that a schema can be instantiated with test data.
	
	Returns:
		(bool, str): (is_valid, error_message)
	"""
	if test_data is None:
		test_data = {}
	
	try:
		# Get required fields
		schema_fields = get_dataclass_fields(schema_class)
		required_fields = {k: v for k, v in schema_fields.items() if v['required']}
		
		# Check if all required fields are provided
		missing_fields = set(required_fields.keys()) - set(test_data.keys())
		if missing_fields:
			return False, f"Missing required fields: {missing_fields}"
		
		# Try to instantiate
		instance = schema_class(**test_data)
		return True, "OK"
	except TypeError as e:
		return False, f"TypeError: {e}"
	except Exception as e:
		return False, f"Unexpected error: {e}"


class TestActivitySchemaValidation:
	"""Test suite for validating Temporal activity schemas."""
	
	def test_all_schemas_are_dataclasses(self):
		"""Verify all activity input schemas are dataclasses."""
		for activity_name, schema_class in ACTIVITY_SCHEMA_MAP.items():
			assert is_dataclass(schema_class), (
				f"Schema for activity '{activity_name}' ({schema_class.__name__}) "
				f"is not a dataclass"
			)
	
	def test_schema_field_names(self):
		"""Verify schema field names are valid Python identifiers."""
		for activity_name, schema_class in ACTIVITY_SCHEMA_MAP.items():
			schema_fields = get_dataclass_fields(schema_class)
			for field_name in schema_fields.keys():
				assert field_name.isidentifier(), (
					f"Schema '{schema_class.__name__}' has invalid field name: '{field_name}'"
				)
	
	def test_filter_frames_input_schema(self):
		"""Test FilterFramesInput schema matches activity expectations."""
		# Test with all required fields
		test_data = {
			'video_path': '/path/to/video.mp4',
			'ingestion_id': 'test-ingestion-123',
			'duration': 120.5,
			'job_id': 'test-job-123',
		}
		
		is_valid, error_msg = validate_schema_instantiation(FilterFramesInput, test_data)
		assert is_valid, f"FilterFramesInput validation failed: {error_msg}"
		
		# Test with optional scene_changes
		test_data['scene_changes'] = [10.0, 20.0, 30.0]
		is_valid, error_msg = validate_schema_instantiation(FilterFramesInput, test_data)
		assert is_valid, f"FilterFramesInput with scene_changes failed: {error_msg}"
		
		# Test missing required field
		test_data_missing = test_data.copy()
		del test_data_missing['duration']
		is_valid, error_msg = validate_schema_instantiation(FilterFramesInput, test_data_missing)
		assert not is_valid, "FilterFramesInput should fail without required 'duration' field"
	
	def test_transcribe_video_input_schema(self):
		"""Test TranscribeVideoInput schema."""
		test_data = {
			'video_path': '/path/to/video.mp4',
			'ingestion_id': 'test-ingestion-123',
			'job_id': 'test-job-123',
		}
		
		is_valid, error_msg = validate_schema_instantiation(TranscribeVideoInput, test_data)
		assert is_valid, f"TranscribeVideoInput validation failed: {error_msg}"
	
	def test_assemble_video_ingestion_input_schema(self):
		"""Test AssembleVideoIngestionInput schema."""
		test_data = {
			'video_path': '/path/to/video.mp4',
			'ingestion_id': 'test-ingestion-123',
			'job_id': 'test-job-123',
			'transcription_data': {'segments': []},
			'analysis_result_s3_keys': [],
			'filtered_frame_paths': [],
			'duplicate_map': {},
			'metadata': {'duration': 120.0},
		}
		
		is_valid, error_msg = validate_schema_instantiation(AssembleVideoIngestionInput, test_data)
		assert is_valid, f"AssembleVideoIngestionInput validation failed: {error_msg}"
	
	def test_knowledge_extraction_input_v2_schema(self):
		"""Test KnowledgeExtractionInputV2 schema."""
		test_data = {
			'job_id': 'test-job-123',
			'source_url': 'https://example.com',
			'source_urls': ['https://example.com'],
			'options': {},
		}
		
		is_valid, error_msg = validate_schema_instantiation(KnowledgeExtractionInputV2, test_data)
		assert is_valid, f"KnowledgeExtractionInputV2 validation failed: {error_msg}"
	
	def test_all_schemas_have_required_fields_documented(self):
		"""Verify we can identify required vs optional fields."""
		for activity_name, schema_class in ACTIVITY_SCHEMA_MAP.items():
			schema_fields = get_dataclass_fields(schema_class)
			required_fields = [k for k, v in schema_fields.items() if v['required']]
			
			# Log field information (some schemas may have all optional fields by design)
			logger.debug(
				f"Schema '{schema_class.__name__}': "
				f"{len(required_fields)} required, {len(schema_fields) - len(required_fields)} optional"
			)
			
			# At least one field should exist (sanity check)
			assert len(schema_fields) > 0, (
				f"Schema '{schema_class.__name__}' has no fields - "
				"this indicates a schema design issue"
			)


class TestFunctionSignatureValidation:
	"""Test suite for validating function signatures match their schemas."""
	
	def test_generate_thumbnails_signature(self):
		"""Test generate_thumbnails function signature."""
		from navigator.knowledge.ingest.video.thumbnails import generate_thumbnails
		from pathlib import Path
		
		sig = inspect.signature(generate_thumbnails)
		params = list(sig.parameters.keys())
		
		# Should have: video_path, ingestion_id, duration, thumbnail_count (optional)
		assert 'video_path' in params, "generate_thumbnails missing 'video_path' parameter"
		assert 'ingestion_id' in params, "generate_thumbnails missing 'ingestion_id' parameter"
		assert 'duration' in params, "generate_thumbnails missing 'duration' parameter"
		
		# Check parameter order
		assert params.index('video_path') < params.index('ingestion_id'), "Parameter order incorrect"
		assert params.index('ingestion_id') < params.index('duration'), "Parameter order incorrect"
	
	def test_detect_scene_changes_signature(self):
		"""Test detect_scene_changes function signature."""
		from navigator.knowledge.ingest.video.frame_analysis.filtering import detect_scene_changes
		from pathlib import Path
		
		sig = inspect.signature(detect_scene_changes)
		params = list(sig.parameters.keys())
		
		# Should have: video_path, duration
		assert 'video_path' in params, "detect_scene_changes missing 'video_path' parameter"
		assert 'duration' in params, "detect_scene_changes missing 'duration' parameter"
	
	def test_smart_filter_pass1_signature(self):
		"""Test smart_filter_pass1 function signature."""
		from navigator.knowledge.ingest.video.frame_analysis.filtering import smart_filter_pass1
		from pathlib import Path
		
		sig = inspect.signature(smart_filter_pass1)
		params = list(sig.parameters.keys())
		
		# Should have: video_path, duration, strategic_timestamps, and optional params
		assert 'video_path' in params, "smart_filter_pass1 missing 'video_path' parameter"
		assert 'duration' in params, "smart_filter_pass1 missing 'duration' parameter"
		assert 'strategic_timestamps' in params, "smart_filter_pass1 missing 'strategic_timestamps' parameter"
		
		# Should NOT have frame_interval (this was the bug)
		assert 'frame_interval' not in params, (
			"smart_filter_pass1 should NOT have 'frame_interval' parameter - "
			"this was removed in favor of strategic_timestamps"
		)


class TestActivityCallValidation:
	"""Test suite for validating activity calls in workflows."""
	
	def test_filter_frames_input_has_all_required_fields(self):
		"""Verify FilterFramesInput can be created with all required fields."""
		# This test ensures the schema matches what's used in video_processing.py
		from navigator.schemas import FilterFramesInput
		
		# Simulate the call from video_processing.py
		test_input = FilterFramesInput(
			video_path='/test/video.mp4',
			ingestion_id='test-123',
			duration=0.0,  # Will be extracted by activity
			job_id='job-123',
			scene_changes=[],  # Activity will detect if needed
		)
		
		assert test_input.video_path == '/test/video.mp4'
		assert test_input.duration == 0.0
		assert test_input.scene_changes == []
	
	def test_generate_thumbnails_call_has_duration(self):
		"""Verify generate_thumbnails is called with duration parameter."""
		# This test documents the correct call pattern
		from navigator.knowledge.ingest.video.thumbnails import generate_thumbnails
		from pathlib import Path
		
		# Correct call pattern (should have duration)
		video_path = Path('/test/video.mp4')
		ingestion_id = 'test-123'
		duration = 120.0
		
		# This should work (we're just testing the signature, not actually calling)
		sig = inspect.signature(generate_thumbnails)
		params = list(sig.parameters.keys())
		
		# Verify we can construct a valid call
		call_params = {
			'video_path': video_path,
			'ingestion_id': ingestion_id,
			'duration': duration,
		}
		
		# Check all required params are provided
		required_params = [p for p, param in sig.parameters.items() 
		                  if param.default == inspect.Parameter.empty]
		for param in required_params:
			assert param in call_params, f"Missing required parameter: {param}"


if __name__ == '__main__':
	pytest.main([__file__, '-v'])

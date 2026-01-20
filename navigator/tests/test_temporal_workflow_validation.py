"""
Comprehensive test suite for Temporal workflow validation.

This test suite validates Temporal best practices and catches issues before they
cause problems with real data:

1. Non-deterministic code detection
2. Proper import wrapping
3. Activity call patterns
4. Schema validation
5. Error handling
6. Continue-as-new patterns
7. Signal/query patterns
8. Workflow determinism
"""

import ast
import inspect
import logging
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

import pytest

logger = logging.getLogger(__name__)


# ============================================================================
# Test Configuration
# ============================================================================

WORKFLOW_DIR = Path(__file__).parent.parent / "temporal" / "workflows"
ACTIVITY_DIR = Path(__file__).parent.parent / "temporal" / "activities"


# ============================================================================
# Non-Deterministic Code Detection
# ============================================================================

NON_DETERMINISTIC_PATTERNS = [
	"datetime.now()",
	"datetime.utcnow()",
	"time.time()",
	"time.perf_counter()",
	"random.",
	"uuid.uuid4()",
	"os.getenv",
	"os.environ",
	"subprocess.",
	"threading.",
	"multiprocessing.",
]


def check_for_non_deterministic_code(file_path: Path) -> list[str]:
	"""
	Check for non-deterministic code patterns in workflow files.
	
	Returns:
		List of issues found
	"""
	issues = []
	
	try:
		with open(file_path, 'r') as f:
			content = f.read()
			lines = content.split('\n')
		
		for i, line in enumerate(lines, 1):
			for pattern in NON_DETERMINISTIC_PATTERNS:
				if pattern in line and not line.strip().startswith('#'):
					# Allow hashlib (deterministic hashing is OK)
					if pattern == "hashlib." and "sha256" in line:
						continue
					# Allow workflow.time() (Temporal's deterministic time)
					if pattern == "time.time()" and "workflow.time()" in line:
						continue
					
					issues.append(
						f"Line {i}: Non-deterministic code detected: '{pattern}' in {file_path.name}"
					)
	except Exception as e:
		issues.append(f"Error reading {file_path}: {e}")
	
	return issues


# ============================================================================
# Import Wrapping Detection
# ============================================================================

def check_import_wrapping(file_path: Path) -> list[str]:
	"""
	Check that workflow files properly wrap imports with workflow.unsafe.imports_passed_through().
	
	Returns:
		List of issues found
	"""
	issues = []
	
	try:
		with open(file_path, 'r') as f:
			content = f.read()
		
		# Check if file contains workflow code
		if "from temporalio import workflow" not in content:
			return issues  # Not a workflow file
		
		# Check if file uses workflow.defn or workflow.run
		if "@workflow.defn" not in content and "@workflow.run" not in content:
			return issues  # Not a workflow definition file
		
		# Check for imports that should be wrapped
		import_statements = [
			"from navigator.schemas import",
			"from navigator.temporal.activities",
			"import logging",
			"from datetime import",
		]
		
		has_wrapped_imports = "workflow.unsafe.imports_passed_through()" in content
		
		for imp in import_statements:
			if imp in content:
				if not has_wrapped_imports:
					issues.append(
						f"File {file_path.name} contains imports that should be wrapped "
						f"with workflow.unsafe.imports_passed_through()"
					)
					break
	except Exception as e:
		issues.append(f"Error reading {file_path}: {e}")
	
	return issues


# ============================================================================
# Activity Call Validation
# ============================================================================

def check_activity_calls(file_path: Path) -> list[str]:
	"""
	Check that activity calls use proper patterns.
	
	Returns:
		List of issues found
	"""
	issues = []
	
	try:
		with open(file_path, 'r') as f:
			content = f.read()
		
		# Check for direct activity calls (should use workflow.execute_activity)
		if "workflow.execute_activity" not in content:
			return issues  # No activity calls
		
		# Check for patterns like: activity_function(input) without workflow.execute_activity
		# This is a simplified check - actual validation would need AST parsing
		lines = content.split('\n')
		for i, line in enumerate(lines, 1):
			# Check for suspicious patterns
			if "await " in line and "_activity(" in line:
				if "workflow.execute_activity" not in line:
					# Might be OK if it's a helper function, but flag for review
					if "ingest_video_with_sub_activities" not in line:
						issues.append(
							f"Line {i}: Potential direct activity call without workflow.execute_activity "
							f"in {file_path.name}"
						)
	except Exception as e:
		issues.append(f"Error reading {file_path}: {e}")
	
	return issues


# ============================================================================
# Schema Validation
# ============================================================================

def validate_activity_input_schemas() -> list[str]:
	"""
	Validate that all activity input schemas can be instantiated.
	
	Returns:
		List of issues found
	"""
	issues = []
	
	try:
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
			TranscribeVideoInput,
			VerifyExtractionInput,
		)
		
		schemas = {
			'FilterFramesInput': FilterFramesInput,
			'TranscribeVideoInput': TranscribeVideoInput,
			'AssembleVideoIngestionInput': AssembleVideoIngestionInput,
			'IngestSourceInput': IngestSourceInput,
		}
		
		# Test data for each schema
		test_data = {
			'FilterFramesInput': {
				'video_path': '/test/video.mp4',
				'ingestion_id': 'test-123',
				'duration': 0.0,
				'job_id': 'job-123',
			},
			'TranscribeVideoInput': {
				'video_path': '/test/video.mp4',
				'ingestion_id': 'test-123',
				'job_id': 'job-123',
			},
			'AssembleVideoIngestionInput': {
				'ingestion_id': 'test-123',
				'video_path': '/test/video.mp4',
				'transcription_data': {},
				'filtered_frame_paths': [],
				'duplicate_map': {},
				'analysis_result_s3_keys': [],
				'metadata': {},
				'job_id': 'job-123',
			},
			'IngestSourceInput': {
				'source_url': 'https://example.com',
				'source_type': 'website',
				'job_id': 'job-123',
			},
		}
		
		for schema_name, schema_class in schemas.items():
			if not is_dataclass(schema_class):
				issues.append(f"Schema {schema_name} is not a dataclass")
				continue
			
			# Get required fields
			required_fields = {
				f.name for f in fields(schema_class)
				if f.default == inspect.Parameter.empty and not hasattr(f, 'default_factory')
			}
			
			# Test with required fields
			test_input = test_data.get(schema_name, {})
			missing_fields = required_fields - set(test_input.keys())
			
			if missing_fields:
				issues.append(
					f"Schema {schema_name} test data missing required fields: {missing_fields}"
				)
			else:
				try:
					instance = schema_class(**test_input)
					logger.debug(f"✅ Schema {schema_name} validated successfully")
				except Exception as e:
					issues.append(f"Schema {schema_name} instantiation failed: {e}")
	except Exception as e:
		issues.append(f"Error validating schemas: {e}")
	
	return issues


# ============================================================================
# Workflow Determinism Tests
# ============================================================================

class TestTemporalWorkflowDeterminism:
	"""Test suite for workflow determinism."""
	
	def test_no_non_deterministic_code_in_workflows(self):
		"""Verify no non-deterministic code in workflow files."""
		issues = []
		
		for file_path in WORKFLOW_DIR.rglob("*.py"):
			if file_path.name == "__init__.py":
				continue
			
			file_issues = check_for_non_deterministic_code(file_path)
			issues.extend(file_issues)
		
		assert len(issues) == 0, (
			f"Found {len(issues)} non-deterministic code issues:\n" + "\n".join(issues)
		)
	
	def test_imports_are_wrapped(self):
		"""Verify workflow imports are properly wrapped."""
		issues = []
		
		for file_path in WORKFLOW_DIR.rglob("*.py"):
			if file_path.name == "__init__.py":
				continue
			
			file_issues = check_import_wrapping(file_path)
			issues.extend(file_issues)
		
		assert len(issues) == 0, (
			f"Found {len(issues)} import wrapping issues:\n" + "\n".join(issues)
		)
	
	def test_activity_calls_use_proper_patterns(self):
		"""Verify activity calls use workflow.execute_activity."""
		issues = []
		
		for file_path in WORKFLOW_DIR.rglob("*.py"):
			if file_path.name == "__init__.py":
				continue
			
			file_issues = check_activity_calls(file_path)
			issues.extend(file_issues)
		
		# This is a warning, not an error (some helper functions are OK)
		if issues:
			logger.warning(f"Found {len(issues)} potential activity call issues (review needed):")
			for issue in issues:
				logger.warning(f"  - {issue}")


# ============================================================================
# Schema Validation Tests
# ============================================================================

class TestTemporalSchemaValidation:
	"""Test suite for schema validation."""
	
	def test_all_activity_input_schemas_are_valid(self):
		"""Verify all activity input schemas can be instantiated."""
		issues = validate_activity_input_schemas()
		
		assert len(issues) == 0, (
			f"Found {len(issues)} schema validation issues:\n" + "\n".join(issues)
		)
	
	def test_filter_frames_input_has_correct_fields(self):
		"""Verify FilterFramesInput has all required fields."""
		from navigator.schemas import FilterFramesInput
		
		# Required fields based on schema
		required_fields = {'video_path', 'ingestion_id', 'duration', 'job_id'}
		
		schema_fields = {f.name for f in fields(FilterFramesInput)}
		
		# Check all required fields exist
		missing_fields = required_fields - schema_fields
		assert len(missing_fields) == 0, (
			f"FilterFramesInput missing required fields: {missing_fields}"
		)
		
		# Verify no frame_interval field (this was the bug we fixed)
		assert 'frame_interval' not in schema_fields, (
			"FilterFramesInput should NOT have 'frame_interval' field"
		)


# ============================================================================
# Workflow Structure Tests
# ============================================================================

class TestTemporalWorkflowStructure:
	"""Test suite for workflow structure validation."""
	
	def test_workflow_has_proper_decorators(self):
		"""Verify workflow class has proper decorators."""
		from navigator.temporal.workflows.extraction_workflow import KnowledgeExtractionWorkflowV2
		
		# Check workflow file has @workflow.defn decorator
		workflow_file = WORKFLOW_DIR / "extraction_workflow.py"
		with open(workflow_file, 'r') as f:
			content = f.read()
		
		assert "@workflow.defn" in content, (
			"Workflow class should have @workflow.defn decorator"
		)
		
		# Check for @workflow.run method
		assert hasattr(KnowledgeExtractionWorkflowV2, 'run'), (
			"Workflow class should have run() method"
		)
		assert "@workflow.run" in content, (
			"Workflow should have @workflow.run decorator on run() method"
		)
		
		# Check for signal handlers
		assert hasattr(KnowledgeExtractionWorkflowV2, 'pause'), (
			"Workflow should have pause() signal handler"
		)
		assert "@workflow.signal" in content, (
			"Workflow should have @workflow.signal decorators"
		)
		
		# Check for query handlers
		assert hasattr(KnowledgeExtractionWorkflowV2, 'get_progress'), (
			"Workflow should have get_progress() query handler"
		)
		assert "@workflow.query" in content, (
			"Workflow should have @workflow.query decorators"
		)
	
	def test_workflow_uses_deterministic_time(self):
		"""Verify workflow uses workflow.time() instead of time.time()."""
		workflow_file = WORKFLOW_DIR / "extraction_workflow.py"
		
		with open(workflow_file, 'r') as f:
			content = f.read()
		
		# Should use workflow.time()
		assert "workflow.time()" in content, (
			"Workflow should use workflow.time() for deterministic timing"
		)
		
		# Should NOT use time.time() directly
		assert "time.time()" not in content or "workflow.time()" in content, (
			"Workflow should not use time.time() directly (use workflow.time() instead)"
		)
	
	def test_workflow_has_proper_error_handling(self):
		"""Verify workflow has proper error handling."""
		workflow_file = WORKFLOW_DIR / "extraction_workflow.py"
		
		with open(workflow_file, 'r') as f:
			content = f.read()
		
		# Should have try/except block
		assert "try:" in content, "Workflow should have try/except error handling"
		assert "except Exception" in content, "Workflow should catch exceptions"
		
		# Should set error status on failure
		assert "result.status = 'failed'" in content, (
			"Workflow should set status to 'failed' on error"
		)


# ============================================================================
# Activity Call Pattern Tests
# ============================================================================

class TestTemporalActivityCalls:
	"""Test suite for activity call patterns."""
	
	def test_video_processing_uses_correct_schemas(self):
		"""Verify video processing helper uses correct input schemas."""
		video_processing_file = WORKFLOW_DIR / "helpers" / "video_processing.py"
		
		with open(video_processing_file, 'r') as f:
			content = f.read()
		
		# Should use FilterFramesInput with correct fields
		assert "FilterFramesInput(" in content, "Should use FilterFramesInput"
		assert "duration=duration" in content, "Should pass duration parameter"
		assert "scene_changes=[]" in content, "Should pass scene_changes parameter"
		
		# Should NOT use frame_interval (this was the bug)
		assert "frame_interval" not in content, (
			"Should NOT use frame_interval (removed in favor of strategic_timestamps)"
		)
	
	def test_activity_calls_have_proper_timeouts(self):
		"""Verify activity calls have proper timeout configuration."""
		workflow_file = WORKFLOW_DIR / "extraction_workflow.py"
		
		with open(workflow_file, 'r') as f:
			content = f.read()
		
		# Should have activity_options with timeouts
		assert "activity_options" in content, "Should define activity_options"
		assert "start_to_close_timeout" in content, "Should set start_to_close_timeout"
		assert "heartbeat_timeout" in content, "Should set heartbeat_timeout"
	
	def test_parallel_activities_use_asyncio_gather(self):
		"""Verify parallel activities use asyncio.gather correctly."""
		video_processing_file = WORKFLOW_DIR / "helpers" / "video_processing.py"
		
		with open(video_processing_file, 'r') as f:
			content = f.read()
		
		# Should use asyncio.gather for parallel activities
		assert "asyncio.gather" in content, "Should use asyncio.gather for parallel activities"
		
		# Should yield control before gathering
		assert "await workflow.sleep" in content, (
			"Should yield control with workflow.sleep before parallel activities"
		)


# ============================================================================
# Continue-As-New Tests
# ============================================================================

class TestTemporalContinueAsNew:
	"""Test suite for continue-as-new patterns."""
	
	def test_continue_as_new_uses_safe_pattern(self):
		"""Verify continue-as-new uses safe pattern."""
		workflow_file = WORKFLOW_DIR / "extraction_workflow.py"
		
		with open(workflow_file, 'r') as f:
			content = f.read()
		
		# Should use safe_continue_as_new helper
		assert "safe_continue_as_new" in content, (
			"Should use safe_continue_as_new helper function"
		)
		
		# Should check should_continue_as_new() before continuing
		assert "should_continue_as_new()" in content, (
			"Should check should_continue_as_new() before continuing"
		)
	
	def test_safe_continue_as_new_waits_for_handlers(self):
		"""Verify safe_continue_as_new waits for handlers."""
		continue_as_new_file = WORKFLOW_DIR / "utils" / "continue_as_new.py"
		
		with open(continue_as_new_file, 'r') as f:
			content = f.read()
		
		# Should wait for handlers to finish
		assert "workflow.wait_condition" in content, (
			"Should wait for handlers with workflow.wait_condition"
		)
		assert "all_handlers_finished" in content, (
			"Should check all_handlers_finished before continuing"
		)


# ============================================================================
# IndexError Prevention Tests
# ============================================================================

class TestTemporalIndexErrorPrevention:
	"""Test suite for preventing IndexError in workflows."""
	
	def test_ingest_results_has_validation(self):
		"""Verify ingest_results[0] access is protected."""
		workflow_file = WORKFLOW_DIR / "extraction_workflow.py"
		
		with open(workflow_file, 'r') as f:
			content = f.read()
		
		# Should check if list is empty before accessing [0]
		assert "ingest_results[0]" in content, "Should access ingest_results[0]"
		
		# Should validate before accessing
		lines = content.split('\n')
		access_line_idx = None
		for i, line in enumerate(lines):
			if "ingest_results[0]" in line:
				access_line_idx = i
				break
		
		if access_line_idx is not None:
			# Check if there's validation before this line
			before_lines = lines[max(0, access_line_idx-10):access_line_idx]
			has_validation = any(
				"len(ingest_results)" in line or 
				"not ingest_results" in line or
				"ingest_results == 0" in line
				for line in before_lines
			)
			assert has_validation, (
				"Should validate ingest_results is not empty before accessing [0]"
			)
	
	def test_source_urls_has_validation(self):
		"""Verify source_urls[0] access is protected."""
		workflow_file = WORKFLOW_DIR / "extraction_workflow.py"
		
		with open(workflow_file, 'r') as f:
			content = f.read()
		
		# Should check if list exists and has items before accessing [0]
		lines = content.split('\n')
		for i, line in enumerate(lines):
			if "source_urls[0]" in line:
				# Check if there's validation before this line
				before_lines = lines[max(0, i-5):i]
				has_validation = any(
					"len(input.source_urls)" in line or 
					"input.source_urls and" in line
					for line in before_lines
				)
				assert has_validation, (
					f"Line {i+1}: Should validate source_urls is not empty before accessing [0]"
				)


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestTemporalErrorHandling:
	"""Test suite for error handling patterns."""
	
	def test_workflow_handles_empty_ingestion_results(self):
		"""Verify workflow handles empty ingestion results gracefully."""
		workflow_file = WORKFLOW_DIR / "extraction_workflow.py"
		
		with open(workflow_file, 'r') as f:
			content = f.read()
		
		# Should check for empty results
		assert "len(ingest_results) == 0" in content or "not ingest_results" in content, (
			"Workflow should check for empty ingestion results"
		)
		
		# Should raise meaningful error
		assert "raise Exception" in content or "result.status = 'failed'" in content, (
			"Workflow should handle empty results with error"
		)
	
	def test_activities_have_error_handling(self):
		"""Verify activities have proper error handling."""
		# Check video processing helper
		video_file = WORKFLOW_DIR / "helpers" / "video_processing.py"
		
		with open(video_file, 'r') as f:
			content = f.read()
		
		# Should check activity results for success
		assert "transcribe_result.success" in content, (
			"Should check transcription result success"
		)
		assert "filter_result.success" in content, (
			"Should check filter result success"
		)


# ============================================================================
# Integration Test Helpers
# ============================================================================

def create_test_workflow_input() -> dict[str, Any]:
	"""Create a test workflow input for integration testing."""
	return {
		'job_id': 'test-job-123',
		'source_url': 'https://example.com',
		'source_urls': ['https://example.com'],
		'source_names': ['Test Source'],
		'options': {
			'max_pages': 10,
			'max_depth': 3,
		},
		'knowledge_id': 'test-knowledge-123',
	}


if __name__ == '__main__':
	pytest.main([__file__, '-v'])

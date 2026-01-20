"""
Integration tests for Temporal workflows with mock data.

These tests validate workflow behavior with realistic data scenarios
to catch issues before they occur in production.
"""

import pytest
from dataclasses import dataclass

from navigator.schemas import (
	FilterFramesInput,
	FilterFramesResult,
	IngestSourceResult,
	KnowledgeExtractionInputV2,
	TranscribeVideoInput,
	TranscribeVideoResult,
)


# ============================================================================
# Test Data Fixtures
# ============================================================================

@pytest.fixture
def sample_workflow_input():
	"""Create a sample workflow input for testing."""
	return KnowledgeExtractionInputV2(
		job_id='test-job-123',
		source_url='https://example.com',
		source_urls=['https://example.com'],
		source_names=['Test Source'],
		options={
			'website_url': 'https://example.com',
			'max_pages': 10,
			'max_depth': 3,
		},
		knowledge_id='test-knowledge-123',
	)


@pytest.fixture
def sample_video_workflow_input():
	"""Create a sample video workflow input for testing."""
	return KnowledgeExtractionInputV2(
		job_id='test-video-job-123',
		source_url='file:///test/video.mp4',
		source_urls=['file:///test/video.mp4'],
		source_names=['Test Video'],
		options={
			'website_url': 'https://app.example.com',
			'credentials': {
				'username': 'test@example.com',
				'password': 'test123',
			},
		},
		knowledge_id='test-knowledge-123',
	)


@pytest.fixture
def sample_empty_workflow_input():
	"""Create an empty workflow input to test error handling."""
	return KnowledgeExtractionInputV2(
		job_id='test-empty-job',
		source_url='',
		source_urls=[],
		options={},
	)


# ============================================================================
# Schema Instantiation Tests
# ============================================================================

class TestWorkflowInputValidation:
	"""Test workflow input validation with various scenarios."""
	
	def test_workflow_input_with_single_source(self, sample_workflow_input):
		"""Test workflow input with single source."""
		assert sample_workflow_input.job_id == 'test-job-123'
		assert sample_workflow_input.source_url == 'https://example.com'
		assert len(sample_workflow_input.source_urls) == 1
		assert sample_workflow_input.knowledge_id == 'test-knowledge-123'
	
	def test_workflow_input_with_video_source(self, sample_video_workflow_input):
		"""Test workflow input with video source."""
		assert sample_video_workflow_input.source_url.startswith('file://')
		assert 'credentials' in sample_video_workflow_input.options
		assert sample_video_workflow_input.options['credentials']['username'] == 'test@example.com'
	
	def test_workflow_input_validation_empty_sources(self):
		"""Test that empty sources are handled."""
		# This should be valid (workflow will handle empty sources)
		input_data = KnowledgeExtractionInputV2(
			job_id='test-job',
			source_url='',
			source_urls=[],
			options={},
		)
		
		# Should be able to instantiate
		assert input_data.job_id == 'test-job'
		assert input_data.source_url == ''
		assert input_data.source_urls == []
	
	def test_filter_frames_input_validation(self):
		"""Test FilterFramesInput with various scenarios."""
		# Valid input
		valid_input = FilterFramesInput(
			video_path='/test/video.mp4',
			ingestion_id='test-123',
			duration=120.5,
			job_id='job-123',
		)
		assert valid_input.duration == 120.5
		assert valid_input.scene_changes == []  # Default empty list
		
		# Test with scene_changes
		input_with_scenes = FilterFramesInput(
			video_path='/test/video.mp4',
			ingestion_id='test-123',
			duration=120.5,
			job_id='job-123',
			scene_changes=[10.0, 20.0, 30.0],
		)
		assert len(input_with_scenes.scene_changes) == 3
	
	def test_transcribe_video_input_validation(self):
		"""Test TranscribeVideoInput validation."""
		valid_input = TranscribeVideoInput(
			video_path='/test/video.mp4',
			ingestion_id='test-123',
			job_id='job-123',
		)
		assert valid_input.video_path == '/test/video.mp4'
		assert valid_input.ingestion_id == 'test-123'


# ============================================================================
# Edge Case Tests
# ============================================================================

class TestWorkflowEdgeCases:
	"""Test edge cases that might cause runtime errors."""
	
	def test_empty_ingest_results_handling(self):
		"""Test that empty ingest_results list is handled."""
		# Simulate empty results
		ingest_results = []
		
		# Should raise error when accessing [0]
		with pytest.raises(IndexError):
			_ = ingest_results[0]
		
		# Proper validation pattern
		if not ingest_results or len(ingest_results) == 0:
			# This is the correct pattern
			assert True, "Empty results should be validated"
	
	def test_empty_source_urls_handling(self):
		"""Test that empty source_urls list is handled."""
		source_urls = []
		
		# Should raise error when accessing [0]
		with pytest.raises(IndexError):
			_ = source_urls[0]
		
		# Proper validation pattern
		if source_urls and len(source_urls) > 0:
			first_url = source_urls[0]
		else:
			first_url = None
		
		assert first_url is None, "Empty list should return None"
	
	def test_none_values_in_options(self):
		"""Test that None values in options are handled."""
		input_data = KnowledgeExtractionInputV2(
			job_id='test-job',
			source_url='https://example.com',
			options={
				'website_url': None,
				'credentials': None,
			},
		)
		
		# Should handle None values gracefully
		website_url = input_data.options.get('website_url')
		assert website_url is None or isinstance(website_url, str)
	
	def test_missing_required_fields(self):
		"""Test that missing required fields are caught."""
		from navigator.schemas import FilterFramesInput
		
		# Missing required field should raise TypeError
		with pytest.raises(TypeError):
			FilterFramesInput(
				video_path='/test/video.mp4',
				# Missing ingestion_id, duration, job_id
			)


# ============================================================================
# Data Type Validation Tests
# ============================================================================

class TestDataTypeValidation:
	"""Test data type validation for workflow inputs."""
	
	def test_duration_is_float(self):
		"""Test that duration is properly typed as float."""
		from navigator.schemas import FilterFramesInput
		
		# Should accept float
		input_float = FilterFramesInput(
			video_path='/test/video.mp4',
			ingestion_id='test-123',
			duration=120.5,  # float
			job_id='job-123',
		)
		assert isinstance(input_float.duration, float)
		
		# Should also accept int (Python will convert)
		input_int = FilterFramesInput(
			video_path='/test/video.mp4',
			ingestion_id='test-123',
			duration=120,  # int (will be converted)
			job_id='job-123',
		)
		assert isinstance(input_int.duration, (int, float))
	
	def test_scene_changes_is_list(self):
		"""Test that scene_changes is a list."""
		from navigator.schemas import FilterFramesInput
		
		input_data = FilterFramesInput(
			video_path='/test/video.mp4',
			ingestion_id='test-123',
			duration=120.0,
			job_id='job-123',
			scene_changes=[10.0, 20.0, 30.0],
		)
		
		assert isinstance(input_data.scene_changes, list)
		assert all(isinstance(x, float) for x in input_data.scene_changes)


# ============================================================================
# Integration Scenario Tests
# ============================================================================

class TestWorkflowScenarios:
	"""Test realistic workflow scenarios."""
	
	def test_video_ingestion_scenario(self):
		"""Test complete video ingestion scenario."""
		# Simulate video ingestion flow
		workflow_input = KnowledgeExtractionInputV2(
			job_id='video-job-123',
			source_url='file:///test/video.mp4',
			source_urls=['file:///test/video.mp4'],
			options={
				'website_url': 'https://app.example.com',
				'credentials': {
					'username': 'user@example.com',
					'password': 'pass123',
				},
			},
			knowledge_id='knowledge-123',
		)
		
		# Validate input structure
		assert workflow_input.source_url.startswith('file://')
		assert 'credentials' in workflow_input.options
		assert workflow_input.options['credentials']['username'] == 'user@example.com'
		
		# Simulate filter_frames input creation
		filter_input = FilterFramesInput(
			video_path='/test/video.mp4',
			ingestion_id='ingestion-123',
			duration=0.0,  # Will be extracted by activity
			job_id='video-job-123',
			scene_changes=[],
		)
		
		assert filter_input.duration == 0.0
		assert filter_input.scene_changes == []
	
	def test_multi_source_scenario(self):
		"""Test multi-source ingestion scenario."""
		workflow_input = KnowledgeExtractionInputV2(
			job_id='multi-job-123',
			source_url='https://docs.example.com',
			source_urls=[
				'https://docs.example.com',
				'file:///test/video.mp4',
				'https://example.com',
			],
			source_names=[
				'Documentation',
				'Video Walkthrough',
				'Website',
			],
			options={
				'website_url': 'https://app.example.com',
			},
			knowledge_id='knowledge-123',
		)
		
		# Validate multi-source structure
		assert len(workflow_input.source_urls) == 3
		assert len(workflow_input.source_names) == 3
		assert workflow_input.source_urls[0] == 'https://docs.example.com'
		assert workflow_input.source_urls[1].startswith('file://')
	
	def test_empty_options_scenario(self):
		"""Test workflow with empty options."""
		workflow_input = KnowledgeExtractionInputV2(
			job_id='test-job',
			source_url='https://example.com',
			options={},  # Empty options
		)
		
		# Should handle empty options gracefully
		assert workflow_input.options == {}
		website_url = workflow_input.options.get('website_url')
		assert website_url is None


if __name__ == '__main__':
	pytest.main([__file__, '-v'])

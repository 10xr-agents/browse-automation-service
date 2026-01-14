"""
Phase 8: Validation Test Suite

Comprehensive tests for end-to-end validation components.
"""

import pytest
from datetime import datetime


class TestConsistencyValidator:
	"""Test database consistency validation."""
	
	def test_consistency_issue_creation(self):
		"""Test ConsistencyIssue dataclass."""
		from navigator.knowledge.validation.consistency import ConsistencyIssue
		
		issue = ConsistencyIssue(
			issue_type='missing_document',
			severity='critical',
			entity_type='screen',
			entity_id='screen-123',
			description='Screen missing in MongoDB',
			details={'key': 'value'},
		)
		
		assert issue.issue_type == 'missing_document'
		assert issue.severity == 'critical'
		assert issue.entity_type == 'screen'
	
	def test_consistency_report_success_rate(self):
		"""Test ConsistencyReport success rate calculation."""
		from navigator.knowledge.validation.consistency import ConsistencyReport
		
		report = ConsistencyReport(
			total_checks=10,
			passed_checks=8,
			failed_checks=2,
			issues=[],
			mongodb_stats={},
			arangodb_stats={},
		)
		
		assert report.success_rate == 80.0
	
	def test_consistency_report_critical_issues(self):
		"""Test ConsistencyReport critical issue detection."""
		from navigator.knowledge.validation.consistency import (
			ConsistencyReport,
			ConsistencyIssue,
		)
		
		issue = ConsistencyIssue(
			issue_type='orphaned_edge',
			severity='critical',
			entity_type='transition',
			entity_id='trans-1',
			description='Edge references non-existent node',
			details={},
		)
		
		report = ConsistencyReport(
			total_checks=5,
			passed_checks=4,
			failed_checks=1,
			issues=[issue],
			mongodb_stats={},
			arangodb_stats={},
		)
		
		assert report.has_critical_issues == True
	
	def test_consistency_report_no_critical_issues(self):
		"""Test ConsistencyReport with only warnings."""
		from navigator.knowledge.validation.consistency import (
			ConsistencyReport,
			ConsistencyIssue,
		)
		
		issue = ConsistencyIssue(
			issue_type='broken_reference',
			severity='warning',
			entity_type='task',
			entity_id='task-1',
			description='Task references non-existent screen',
			details={},
		)
		
		report = ConsistencyReport(
			total_checks=5,
			passed_checks=4,
			failed_checks=1,
			issues=[issue],
			mongodb_stats={},
			arangodb_stats={},
		)
		
		assert report.has_critical_issues == False


class TestPipelineMetrics:
	"""Test pipeline metrics collection."""
	
	def test_pipeline_metrics_creation(self):
		"""Test PipelineMetrics dataclass."""
		from navigator.knowledge.validation.metrics import PipelineMetrics
		
		metrics = PipelineMetrics(
			pipeline_name='test_pipeline',
			started_at=datetime.utcnow(),
			input_type='documentation',
			input_size=20,
		)
		
		assert metrics.pipeline_name == 'test_pipeline'
		assert metrics.input_type == 'documentation'
		assert metrics.input_size == 20
	
	def test_pipeline_metrics_total_entities(self):
		"""Test total entities calculation."""
		from navigator.knowledge.validation.metrics import PipelineMetrics
		
		metrics = PipelineMetrics(
			pipeline_name='test',
			started_at=datetime.utcnow(),
			screens_extracted=10,
			tasks_extracted=5,
			actions_extracted=20,
			transitions_extracted=15,
		)
		
		assert metrics.total_entities == 50
	
	def test_pipeline_metrics_success_property(self):
		"""Test success property."""
		from navigator.knowledge.validation.metrics import PipelineMetrics
		
		# Successful pipeline
		metrics_success = PipelineMetrics(
			pipeline_name='test',
			started_at=datetime.utcnow(),
			completed_at=datetime.utcnow(),
			errors_count=0,
		)
		assert metrics_success.success == True
		
		# Failed pipeline
		metrics_failed = PipelineMetrics(
			pipeline_name='test',
			started_at=datetime.utcnow(),
			completed_at=datetime.utcnow(),
			errors_count=1,
		)
		assert metrics_failed.success == False
		
		# Incomplete pipeline
		metrics_incomplete = PipelineMetrics(
			pipeline_name='test',
			started_at=datetime.utcnow(),
			completed_at=None,
			errors_count=0,
		)
		assert metrics_incomplete.success == False
	
	def test_pipeline_metrics_to_dict(self):
		"""Test metrics serialization to dict."""
		from navigator.knowledge.validation.metrics import PipelineMetrics
		
		metrics = PipelineMetrics(
			pipeline_name='test',
			started_at=datetime.utcnow(),
			input_type='website',
			input_size=50,
		)
		
		data = metrics.to_dict()
		
		assert data['pipeline_name'] == 'test'
		assert data['input_type'] == 'website'
		assert data['input_size'] == 50
		assert 'started_at' in data


class TestBenchmarkResults:
	"""Test benchmark results aggregation."""
	
	def test_benchmark_results_creation(self):
		"""Test BenchmarkResults dataclass."""
		from navigator.knowledge.validation.metrics import (
			BenchmarkResults,
			PipelineMetrics,
		)
		
		scenario1 = PipelineMetrics(
			pipeline_name='small',
			started_at=datetime.utcnow(),
			completed_at=datetime.utcnow(),
			duration_seconds=120.0,
		)
		
		results = BenchmarkResults(
			benchmark_name='test_benchmark',
			scenarios=[scenario1],
		)
		
		assert results.benchmark_name == 'test_benchmark'
		assert len(results.scenarios) == 1
	
	def test_benchmark_results_avg_duration(self):
		"""Test average duration calculation."""
		from navigator.knowledge.validation.metrics import (
			BenchmarkResults,
			PipelineMetrics,
		)
		
		scenarios = [
			PipelineMetrics(
				pipeline_name='test1',
				started_at=datetime.utcnow(),
				duration_seconds=100.0,
			),
			PipelineMetrics(
				pipeline_name='test2',
				started_at=datetime.utcnow(),
				duration_seconds=200.0,
			),
		]
		
		results = BenchmarkResults(
			benchmark_name='test',
			scenarios=scenarios,
		)
		
		assert results.avg_duration == 150.0
	
	def test_benchmark_results_success_rate(self):
		"""Test success rate calculation."""
		from navigator.knowledge.validation.metrics import (
			BenchmarkResults,
			PipelineMetrics,
		)
		
		scenarios = [
			PipelineMetrics(
				pipeline_name='test1',
				started_at=datetime.utcnow(),
				completed_at=datetime.utcnow(),
				errors_count=0,
			),
			PipelineMetrics(
				pipeline_name='test2',
				started_at=datetime.utcnow(),
				completed_at=datetime.utcnow(),
				errors_count=1,
			),
			PipelineMetrics(
				pipeline_name='test3',
				started_at=datetime.utcnow(),
				completed_at=datetime.utcnow(),
				errors_count=0,
			),
		]
		
		results = BenchmarkResults(
			benchmark_name='test',
			scenarios=scenarios,
		)
		
		# 2 out of 3 successful = 66.67%
		assert abs(results.success_rate - 66.67) < 0.1


class TestMetricsCollector:
	"""Test metrics collector."""
	
	@pytest.mark.asyncio
	async def test_metrics_collector_initialization(self):
		"""Test MetricsCollector initialization."""
		from navigator.knowledge.validation.metrics import collect_pipeline_metrics
		
		collector = await collect_pipeline_metrics(
			pipeline_name='test',
			input_type='documentation',
			input_size=10,
		)
		
		assert collector.metrics.pipeline_name == 'test'
		assert collector.metrics.input_type == 'documentation'
		assert collector.metrics.input_size == 10
	
	@pytest.mark.asyncio
	async def test_metrics_collector_record_extraction(self):
		"""Test recording extraction metrics."""
		from navigator.knowledge.validation.metrics import collect_pipeline_metrics
		
		collector = await collect_pipeline_metrics(
			pipeline_name='test',
			input_type='documentation',
			input_size=10,
		)
		
		collector.record_extraction(screens=5, tasks=3, actions=10)
		
		assert collector.metrics.screens_extracted == 5
		assert collector.metrics.tasks_extracted == 3
		assert collector.metrics.actions_extracted == 10
	
	@pytest.mark.asyncio
	async def test_metrics_collector_complete(self):
		"""Test completing metrics collection."""
		from navigator.knowledge.validation.metrics import collect_pipeline_metrics
		import time
		
		collector = await collect_pipeline_metrics(
			pipeline_name='test',
			input_type='documentation',
			input_size=10,
		)
		
		time.sleep(0.1)  # Simulate work
		
		metrics = collector.complete()
		
		assert metrics.completed_at is not None
		assert metrics.duration_seconds > 0


def test_phase8_validation_module_exports():
	"""Test that validation module exports all required components."""
	from navigator.knowledge.validation import (
		ConsistencyValidator,
		ConsistencyReport,
		check_database_consistency,
		PipelineMetrics,
		BenchmarkResults,
		collect_pipeline_metrics,
	)
	
	assert ConsistencyValidator is not None
	assert ConsistencyReport is not None
	assert check_database_consistency is not None
	assert PipelineMetrics is not None
	assert BenchmarkResults is not None
	assert collect_pipeline_metrics is not None

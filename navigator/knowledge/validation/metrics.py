"""
Pipeline Metrics Collection

Phase 8.8: Performance metrics and benchmarking utilities.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PipelineMetrics:
	"""Metrics for a single pipeline run."""
	pipeline_name: str
	started_at: datetime
	completed_at: datetime | None = None
	duration_seconds: float = 0.0

	# Input metrics
	input_size: int = 0  # pages, files, etc.
	input_type: str = ''  # 'documentation', 'website', 'video'

	# Extraction metrics
	screens_extracted: int = 0
	tasks_extracted: int = 0
	actions_extracted: int = 0
	transitions_extracted: int = 0

	# Performance metrics
	ingestion_rate: float = 0.0  # pages per minute
	extraction_rate: float = 0.0  # entities per minute
	graph_build_time: float = 0.0  # seconds

	# Resource metrics
	peak_memory_mb: float = 0.0
	cpu_usage_percent: float = 0.0

	# Error metrics
	errors_count: int = 0
	warnings_count: int = 0

	# Additional metadata
	metadata: dict[str, Any] = field(default_factory=dict)

	@property
	def success(self) -> bool:
		"""Whether the pipeline completed successfully."""
		return self.completed_at is not None and self.errors_count == 0

	@property
	def total_entities(self) -> int:
		"""Total entities extracted."""
		return (
			self.screens_extracted +
			self.tasks_extracted +
			self.actions_extracted +
			self.transitions_extracted
		)

	def to_dict(self) -> dict[str, Any]:
		"""Convert to dictionary for serialization."""
		return {
			'pipeline_name': self.pipeline_name,
			'started_at': self.started_at.isoformat() if self.started_at else None,
			'completed_at': self.completed_at.isoformat() if self.completed_at else None,
			'duration_seconds': self.duration_seconds,
			'input_size': self.input_size,
			'input_type': self.input_type,
			'screens_extracted': self.screens_extracted,
			'tasks_extracted': self.tasks_extracted,
			'actions_extracted': self.actions_extracted,
			'transitions_extracted': self.transitions_extracted,
			'ingestion_rate': self.ingestion_rate,
			'extraction_rate': self.extraction_rate,
			'graph_build_time': self.graph_build_time,
			'peak_memory_mb': self.peak_memory_mb,
			'cpu_usage_percent': self.cpu_usage_percent,
			'errors_count': self.errors_count,
			'warnings_count': self.warnings_count,
			'success': self.success,
			'total_entities': self.total_entities,
			'metadata': self.metadata,
		}


@dataclass
class BenchmarkResults:
	"""Results from performance benchmarking."""
	benchmark_name: str
	scenarios: list[PipelineMetrics]
	run_at: datetime = field(default_factory=datetime.utcnow)

	@property
	def avg_duration(self) -> float:
		"""Average duration across all scenarios."""
		if not self.scenarios:
			return 0.0
		return sum(s.duration_seconds for s in self.scenarios) / len(self.scenarios)

	@property
	def avg_extraction_rate(self) -> float:
		"""Average extraction rate across all scenarios."""
		if not self.scenarios:
			return 0.0
		return sum(s.extraction_rate for s in self.scenarios) / len(self.scenarios)

	@property
	def success_rate(self) -> float:
		"""Percentage of successful runs."""
		if not self.scenarios:
			return 0.0
		successful = sum(1 for s in self.scenarios if s.success)
		return (successful / len(self.scenarios)) * 100

	def to_dict(self) -> dict[str, Any]:
		"""Convert to dictionary for serialization."""
		return {
			'benchmark_name': self.benchmark_name,
			'run_at': self.run_at.isoformat(),
			'scenario_count': len(self.scenarios),
			'avg_duration': self.avg_duration,
			'avg_extraction_rate': self.avg_extraction_rate,
			'success_rate': self.success_rate,
			'scenarios': [s.to_dict() for s in self.scenarios],
		}


class MetricsCollector:
	"""Collects metrics during pipeline execution."""

	def __init__(self, pipeline_name: str, input_type: str, input_size: int):
		"""
		Initialize metrics collector.
		
		Args:
			pipeline_name: Name of the pipeline
			input_type: Type of input (documentation, website, video)
			input_size: Size of input (number of pages/files)
		"""
		self.metrics = PipelineMetrics(
			pipeline_name=pipeline_name,
			started_at=datetime.utcnow(),
			input_type=input_type,
			input_size=input_size,
		)
		self.start_time = time.time()

	def record_extraction(
		self,
		screens: int = 0,
		tasks: int = 0,
		actions: int = 0,
		transitions: int = 0,
	):
		"""Record extraction metrics."""
		self.metrics.screens_extracted += screens
		self.metrics.tasks_extracted += tasks
		self.metrics.actions_extracted += actions
		self.metrics.transitions_extracted += transitions

	def record_error(self):
		"""Record an error."""
		self.metrics.errors_count += 1

	def record_warning(self):
		"""Record a warning."""
		self.metrics.warnings_count += 1

	def record_graph_build_time(self, seconds: float):
		"""Record graph build time."""
		self.metrics.graph_build_time = seconds

	def record_resource_usage(self, memory_mb: float, cpu_percent: float):
		"""Record resource usage."""
		self.metrics.peak_memory_mb = max(self.metrics.peak_memory_mb, memory_mb)
		self.metrics.cpu_usage_percent = cpu_percent

	def complete(self) -> PipelineMetrics:
		"""Mark pipeline as complete and calculate final metrics."""
		self.metrics.completed_at = datetime.utcnow()
		self.metrics.duration_seconds = time.time() - self.start_time

		# Calculate rates
		if self.metrics.duration_seconds > 0:
			duration_minutes = self.metrics.duration_seconds / 60

			if self.metrics.input_size > 0:
				self.metrics.ingestion_rate = self.metrics.input_size / duration_minutes

			if self.metrics.total_entities > 0:
				self.metrics.extraction_rate = self.metrics.total_entities / duration_minutes

		logger.info(
			f"Pipeline '{self.metrics.pipeline_name}' completed in "
			f"{self.metrics.duration_seconds:.2f}s: "
			f"{self.metrics.total_entities} entities extracted"
		)

		return self.metrics


async def collect_pipeline_metrics(
	pipeline_name: str,
	input_type: str,
	input_size: int,
) -> MetricsCollector:
	"""
	Create a metrics collector for a pipeline run.
	
	Args:
		pipeline_name: Name of the pipeline
		input_type: Type of input
		input_size: Size of input
	
	Returns:
		MetricsCollector instance
	"""
	return MetricsCollector(pipeline_name, input_type, input_size)

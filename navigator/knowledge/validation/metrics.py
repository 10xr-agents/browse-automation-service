"""
Pipeline Metrics Collection

Phase 8.8: Performance metrics and benchmarking utilities.
Phase 4.2: Knowledge Quality Metrics - completeness, relationship coverage, spatial information, business context.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
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


# =============================================================================
# Phase 4.2: Knowledge Quality Metrics
# =============================================================================

@dataclass
class KnowledgeQualityMetrics:
	"""Phase 4.2: Knowledge quality metrics."""
	knowledge_id: str | None = None
	calculated_at: datetime = field(default_factory=datetime.utcnow)
	
	# Completeness scores (0-1, higher is better)
	completeness_score: float = 0.0
	screens_completeness: float = 0.0
	actions_completeness: float = 0.0
	tasks_completeness: float = 0.0
	transitions_completeness: float = 0.0
	
	# Relationship coverage (0-1, higher is better)
	relationship_coverage_score: float = 0.0
	screen_relationship_coverage: float = 0.0
	action_relationship_coverage: float = 0.0
	task_relationship_coverage: float = 0.0
	
	# Spatial information coverage (0-1, higher is better)
	spatial_information_coverage: float = 0.0
	screens_with_spatial_info: int = 0
	total_screens: int = 0
	elements_with_spatial_info: int = 0
	total_elements: int = 0
	
	# Business context coverage (0-1, higher is better)
	business_context_coverage: float = 0.0
	screens_with_business_context: int = 0
	actions_with_business_context: int = 0
	tasks_with_business_context: int = 0
	business_functions_count: int = 0
	
	# Entity counts
	entity_counts: dict[str, int] = field(default_factory=dict)
	
	# Priority 10: Relationship quality metrics
	relationship_completeness: float = 0.0  # How many entities have expected relationships
	relationship_accuracy: float = 0.0  # How many bidirectional links are correct
	relationship_duplicates_count: int = 0  # Number of duplicate relationships found
	relationship_invalid_references_count: int = 0  # Number of invalid relationship references
	
	# Detailed breakdown
	details: dict[str, Any] = field(default_factory=dict)
	
	@property
	def overall_quality_score(self) -> float:
		"""Calculate overall quality score (weighted average)."""
		# Weighted average: completeness 35%, relationships 30%, spatial 15%, business 15%, relationship quality 5%
		# Priority 10: Include relationship quality metrics in overall score
		relationship_quality_score = (
			(self.relationship_completeness * 0.5 + self.relationship_accuracy * 0.5)
			if (self.relationship_completeness > 0 or self.relationship_accuracy > 0) else 1.0
		)
		# Penalize for duplicates and invalid references
		if self.relationship_duplicates_count > 0 or self.relationship_invalid_references_count > 0:
			relationship_quality_score *= 0.9  # 10% penalty
		
		return (
			self.completeness_score * 0.35 +
			self.relationship_coverage_score * 0.3 +
			self.spatial_information_coverage * 0.15 +
			self.business_context_coverage * 0.15 +
			relationship_quality_score * 0.05
		)
	
	def to_dict(self) -> dict[str, Any]:
		"""Convert to dictionary for serialization."""
		return {
			'knowledge_id': self.knowledge_id,
			'calculated_at': self.calculated_at.isoformat(),
			'overall_quality_score': self.overall_quality_score,
			'completeness_score': self.completeness_score,
			'screens_completeness': self.screens_completeness,
			'actions_completeness': self.actions_completeness,
			'tasks_completeness': self.tasks_completeness,
			'transitions_completeness': self.transitions_completeness,
			'relationship_coverage_score': self.relationship_coverage_score,
			'screen_relationship_coverage': self.screen_relationship_coverage,
			'action_relationship_coverage': self.action_relationship_coverage,
			'task_relationship_coverage': self.task_relationship_coverage,
			'spatial_information_coverage': self.spatial_information_coverage,
			'screens_with_spatial_info': self.screens_with_spatial_info,
			'total_screens': self.total_screens,
			'elements_with_spatial_info': self.elements_with_spatial_info,
			'total_elements': self.total_elements,
			'business_context_coverage': self.business_context_coverage,
			'screens_with_business_context': self.screens_with_business_context,
			'actions_with_business_context': self.actions_with_business_context,
			'tasks_with_business_context': self.tasks_with_business_context,
			'business_functions_count': self.business_functions_count,
			'entity_counts': self.entity_counts,
			# Priority 10: Relationship quality metrics
			'relationship_completeness': self.relationship_completeness,
			'relationship_accuracy': self.relationship_accuracy,
			'relationship_duplicates_count': self.relationship_duplicates_count,
			'relationship_invalid_references_count': self.relationship_invalid_references_count,
			'details': self.details,
		}


@dataclass
class QualityReport:
	"""Phase 4.2: Quality report with recommendations."""
	knowledge_id: str | None = None
	generated_at: datetime = field(default_factory=datetime.utcnow)
	metrics: KnowledgeQualityMetrics | None = None
	
	# Recommendations
	recommendations: list[str] = field(default_factory=list)
	priority_issues: list[str] = field(default_factory=list)
	
	def to_dict(self) -> dict[str, Any]:
		"""Convert to dictionary for serialization."""
		return {
			'knowledge_id': self.knowledge_id,
			'generated_at': self.generated_at.isoformat(),
			'metrics': self.metrics.to_dict() if self.metrics else None,
			'recommendations': self.recommendations,
			'priority_issues': self.priority_issues,
		}


class KnowledgeQualityCalculator:
	"""
	Phase 4.2: Calculate knowledge quality metrics.
	
	Calculates:
	1. Knowledge completeness score
	2. Relationship coverage score
	3. Spatial information coverage
	4. Business context coverage
	"""
	
	def __init__(self, knowledge_id: str | None = None):
		"""
		Initialize quality calculator.
		
		Args:
			knowledge_id: Optional knowledge ID to calculate metrics for specific knowledge set
		"""
		self.knowledge_id = knowledge_id
	
	async def calculate_quality_metrics(self) -> KnowledgeQualityMetrics:
		"""
		Calculate all quality metrics.
		
		Returns:
			KnowledgeQualityMetrics with all calculated scores
		"""
		metrics = KnowledgeQualityMetrics(knowledge_id=self.knowledge_id)
		
		logger.info(f"Calculating quality metrics (knowledge_id={self.knowledge_id})")
		
		try:
			# Build entity cache
			entity_cache = await self._build_entity_cache()
			metrics.entity_counts = {k: len(v) for k, v in entity_cache.items()}
			
			# Calculate completeness scores
			await self._calculate_completeness(metrics, entity_cache)
			
			# Calculate relationship coverage
			await self._calculate_relationship_coverage(metrics, entity_cache)
			
			# Priority 10: Calculate relationship quality metrics
			await self._calculate_relationship_quality_metrics(metrics, entity_cache)
			
			# Calculate spatial information coverage
			await self._calculate_spatial_coverage(metrics, entity_cache)
			
			# Calculate business context coverage
			await self._calculate_business_context_coverage(metrics, entity_cache)
			
			logger.info(
				f"✅ Quality metrics calculated: "
				f"Overall={metrics.overall_quality_score:.2%}, "
				f"Completeness={metrics.completeness_score:.2%}, "
				f"Relationships={metrics.relationship_coverage_score:.2%}, "
				f"Spatial={metrics.spatial_information_coverage:.2%}, "
				f"Business={metrics.business_context_coverage:.2%}"
			)
			logger.info(
				f"Priority 10: Relationship quality metrics - "
				f"Completeness={metrics.relationship_completeness:.2%}, "
				f"Accuracy={metrics.relationship_accuracy:.2%}, "
				f"Duplicates={metrics.relationship_duplicates_count}, "
				f"Invalid References={metrics.relationship_invalid_references_count}"
			)
			
		except Exception as e:
			logger.error(f"❌ Failed to calculate quality metrics: {e}", exc_info=True)
		
		return metrics
	
	async def _build_entity_cache(self) -> dict[str, dict[str, Any]]:
		"""Build cache of all entities."""
		cache = {
			'screens': {},
			'actions': {},
			'tasks': {},
			'transitions': {},
			'workflows': {},
			'user_flows': {},
			'business_functions': {},
		}
		
		query_filter: dict[str, Any] = {}
		if self.knowledge_id:
			query_filter['knowledge_id'] = self.knowledge_id
		
		# Cache screens
		screens_collection = await get_screens_collection()
		if screens_collection:
			async for doc in screens_collection.find(query_filter):
				screen_id = doc.get('screen_id')
				if screen_id:
					cache['screens'][screen_id] = doc
		
		# Cache actions
		actions_collection = await get_actions_collection()
		if actions_collection:
			async for doc in actions_collection.find(query_filter):
				action_id = doc.get('action_id')
				if action_id:
					cache['actions'][action_id] = doc
		
		# Cache tasks
		tasks_collection = await get_tasks_collection()
		if tasks_collection:
			async for doc in tasks_collection.find(query_filter):
				task_id = doc.get('task_id')
				if task_id:
					cache['tasks'][task_id] = doc
		
		# Cache transitions
		transitions_collection = await get_transitions_collection()
		if transitions_collection:
			async for doc in transitions_collection.find(query_filter):
				transition_id = doc.get('transition_id')
				if transition_id:
					cache['transitions'][transition_id] = doc
		
		# Cache workflows
		workflows_collection = await get_workflows_collection()
		if workflows_collection:
			async for doc in workflows_collection.find(query_filter):
				workflow_id = doc.get('workflow_id')
				if workflow_id:
					cache['workflows'][workflow_id] = doc
		
		# Cache user flows
		user_flows_collection = await get_user_flows_collection()
		if user_flows_collection:
			async for doc in user_flows_collection.find(query_filter):
				user_flow_id = doc.get('user_flow_id')
				if user_flow_id:
					cache['user_flows'][user_flow_id] = doc
		
		# Cache business functions
		bf_collection = await get_business_functions_collection()
		if bf_collection:
			async for doc in bf_collection.find(query_filter):
				bf_id = doc.get('business_function_id')
				if bf_id:
					cache['business_functions'][bf_id] = doc
		
		return cache
	
	async def _calculate_completeness(
		self,
		metrics: KnowledgeQualityMetrics,
		entity_cache: dict[str, dict[str, Any]]
	) -> None:
		"""Phase 4.2: Calculate knowledge completeness score."""
		screens = entity_cache['screens']
		actions = entity_cache['actions']
		tasks = entity_cache['tasks']
		transitions = entity_cache['transitions']
		
		# Screen completeness: has name, url_patterns, state_signature, ui_elements
		screen_scores = []
		for screen_id, screen in screens.items():
			score = 0.0
			if screen.get('name'):
				score += 0.25
			if screen.get('url_patterns'):
				score += 0.25
			if screen.get('state_signature'):
				score += 0.25
			if screen.get('ui_elements'):
				score += 0.25
			screen_scores.append(score)
		
		metrics.screens_completeness = (
			sum(screen_scores) / len(screen_scores) if screen_scores else 0.0
		)
		
		# Action completeness: has name, action_type, selector, browser_use_action
		action_scores = []
		for action_id, action in actions.items():
			score = 0.0
			if action.get('name'):
				score += 0.25
			if action.get('action_type'):
				score += 0.25
			if action.get('selector') or action.get('screen_ids'):
				score += 0.25
			if action.get('browser_use_action'):
				score += 0.25
			action_scores.append(score)
		
		metrics.actions_completeness = (
			sum(action_scores) / len(action_scores) if action_scores else 0.0
		)
		
		# Task completeness: has name, description, steps
		task_scores = []
		for task_id, task in tasks.items():
			score = 0.0
			if task.get('name'):
				score += 0.33
			if task.get('description'):
				score += 0.33
			if task.get('steps'):
				score += 0.34
			task_scores.append(score)
		
		metrics.tasks_completeness = (
			sum(task_scores) / len(task_scores) if task_scores else 0.0
		)
		
		# Transition completeness: has from_screen_id, to_screen_id, trigger
		transition_scores = []
		for transition_id, transition in transitions.items():
			score = 0.0
			if transition.get('from_screen_id'):
				score += 0.33
			if transition.get('to_screen_id'):
				score += 0.33
			if transition.get('trigger'):
				score += 0.34
			transition_scores.append(score)
		
		metrics.transitions_completeness = (
			sum(transition_scores) / len(transition_scores) if transition_scores else 0.0
		)
		
		# Overall completeness (weighted average)
		total_entities = len(screens) + len(actions) + len(tasks) + len(transitions)
		if total_entities > 0:
			metrics.completeness_score = (
				metrics.screens_completeness * len(screens) +
				metrics.actions_completeness * len(actions) +
				metrics.tasks_completeness * len(tasks) +
				metrics.transitions_completeness * len(transitions)
			) / total_entities
		
		metrics.details['completeness'] = {
			'screen_scores': screen_scores,
			'action_scores': action_scores,
			'task_scores': task_scores,
			'transition_scores': transition_scores,
		}
	
	async def _calculate_relationship_coverage(
		self,
		metrics: KnowledgeQualityMetrics,
		entity_cache: dict[str, dict[str, Any]]
	) -> None:
		"""Phase 4.2: Calculate relationship coverage score."""
		screens = entity_cache['screens']
		actions = entity_cache['actions']
		tasks = entity_cache['tasks']
		
		# Screen relationship coverage: linked to business functions, user flows, tasks, actions
		screen_relationship_scores = []
		for screen_id, screen in screens.items():
			score = 0.0
			if screen.get('business_function_ids'):
				score += 0.25
			if screen.get('user_flow_ids'):
				score += 0.25
			if screen.get('task_ids'):
				score += 0.25
			if screen.get('action_ids'):
				score += 0.25
			screen_relationship_scores.append(score)
		
		metrics.screen_relationship_coverage = (
			sum(screen_relationship_scores) / len(screen_relationship_scores)
			if screen_relationship_scores else 0.0
		)
		
		# Action relationship coverage: linked to screens, business functions
		action_relationship_scores = []
		for action_id, action in actions.items():
			score = 0.0
			if action.get('screen_ids'):
				score += 0.5
			if action.get('business_function_ids'):
				score += 0.5
			action_relationship_scores.append(score)
		
		metrics.action_relationship_coverage = (
			sum(action_relationship_scores) / len(action_relationship_scores)
			if action_relationship_scores else 0.0
		)
		
		# Task relationship coverage: linked to screens, business functions
		task_relationship_scores = []
		for task_id, task in tasks.items():
			score = 0.0
			if task.get('screen_ids'):
				score += 0.5
			if task.get('business_function_ids'):
				score += 0.5
			task_relationship_scores.append(score)
		
		metrics.task_relationship_coverage = (
			sum(task_relationship_scores) / len(task_relationship_scores)
			if task_relationship_scores else 0.0
		)
		
		# Overall relationship coverage (weighted average)
		total_entities = len(screens) + len(actions) + len(tasks)
		if total_entities > 0:
			metrics.relationship_coverage_score = (
				metrics.screen_relationship_coverage * len(screens) +
				metrics.action_relationship_coverage * len(actions) +
				metrics.task_relationship_coverage * len(tasks)
			) / total_entities
		
		metrics.details['relationship_coverage'] = {
			'screen_scores': screen_relationship_scores,
			'action_scores': action_relationship_scores,
			'task_scores': task_relationship_scores,
		}
	
	async def _calculate_spatial_coverage(
		self,
		metrics: KnowledgeQualityMetrics,
		entity_cache: dict[str, dict[str, Any]]
	) -> None:
		"""Phase 4.2: Calculate spatial information coverage."""
		screens = entity_cache['screens']
		
		metrics.total_screens = len(screens)
		metrics.total_elements = 0
		metrics.screens_with_spatial_info = 0
		metrics.elements_with_spatial_info = 0
		
		for screen_id, screen in screens.items():
			ui_elements = screen.get('ui_elements', [])
			metrics.total_elements += len(ui_elements)
			
			# Check if screen has spatial info (regions, layout_structure)
			has_spatial = (
				screen.get('metadata', {}).get('regions') or
				screen.get('metadata', {}).get('layout_structure')
			)
			if has_spatial:
				metrics.screens_with_spatial_info += 1
			
			# Check elements with spatial info
			for element in ui_elements:
				if isinstance(element, dict):
					has_element_spatial = (
						element.get('position') or
						element.get('layout_context') or
						element.get('visual_hierarchy') is not None or
						element.get('importance_score') is not None
					)
					if has_element_spatial:
						metrics.elements_with_spatial_info += 1
		
		# Calculate coverage
		if metrics.total_screens > 0:
			screen_coverage = metrics.screens_with_spatial_info / metrics.total_screens
		else:
			screen_coverage = 0.0
		
		if metrics.total_elements > 0:
			element_coverage = metrics.elements_with_spatial_info / metrics.total_elements
		else:
			element_coverage = 0.0
		
		# Overall spatial coverage (weighted: screens 40%, elements 60%)
		metrics.spatial_information_coverage = screen_coverage * 0.4 + element_coverage * 0.6
		
		metrics.details['spatial_coverage'] = {
			'screen_coverage': screen_coverage,
			'element_coverage': element_coverage,
		}
	
	async def _calculate_business_context_coverage(
		self,
		metrics: KnowledgeQualityMetrics,
		entity_cache: dict[str, dict[str, Any]]
	) -> None:
		"""Phase 4.2: Calculate business context coverage."""
		screens = entity_cache['screens']
		actions = entity_cache['actions']
		tasks = entity_cache['tasks']
		business_functions = entity_cache['business_functions']
		
		metrics.business_functions_count = len(business_functions)
		
		# Screens with business context (linked to business functions)
		metrics.screens_with_business_context = sum(
			1 for screen in screens.values()
			if screen.get('business_function_ids')
		)
		
		# Actions with business context
		metrics.actions_with_business_context = sum(
			1 for action in actions.values()
			if action.get('business_function_ids')
		)
		
		# Tasks with business context
		metrics.tasks_with_business_context = sum(
			1 for task in tasks.values()
			if task.get('business_function_ids')
		)
		
		# Calculate coverage
		total_entities = len(screens) + len(actions) + len(tasks)
		if total_entities > 0:
			entities_with_context = (
				metrics.screens_with_business_context +
				metrics.actions_with_business_context +
				metrics.tasks_with_business_context
			)
			metrics.business_context_coverage = entities_with_context / total_entities
		else:
			metrics.business_context_coverage = 0.0
		
		# Also check business function completeness (has reasoning, impact, requirements)
		bf_completeness_scores = []
		for bf_id, bf in business_functions.items():
			score = 0.0
			if bf.get('business_reasoning'):
				score += 0.33
			if bf.get('business_impact'):
				score += 0.33
			if bf.get('business_requirements'):
				score += 0.34
			bf_completeness_scores.append(score)
		
		bf_completeness = (
			sum(bf_completeness_scores) / len(bf_completeness_scores)
			if bf_completeness_scores else 0.0
		)
		
		# Overall business context coverage (entity coverage 70%, BF completeness 30%)
		metrics.business_context_coverage = (
			metrics.business_context_coverage * 0.7 + bf_completeness * 0.3
		)
		
		metrics.details['business_context'] = {
			'bf_completeness': bf_completeness,
			'bf_completeness_scores': bf_completeness_scores,
		}
	
	async def _calculate_relationship_quality_metrics(
		self,
		metrics: KnowledgeQualityMetrics,
		entity_cache: dict[str, dict[str, Any]]
	) -> None:
		"""Priority 10: Calculate relationship quality metrics (completeness, accuracy, duplicates, invalid references)."""
		screens = entity_cache['screens']
		actions = entity_cache['actions']
		tasks = entity_cache['tasks']
		business_functions = entity_cache['business_functions']
		
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
		
		metrics.relationship_completeness = (
			entities_with_complete_relationships / total_entities
			if total_entities > 0 else 0.0
		)
		
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
		
		metrics.relationship_accuracy = (
			correct_bidirectional_links / total_bidirectional_links
			if total_bidirectional_links > 0 else 1.0
		)
		
		# Count duplicate relationships
		duplicates_count = 0
		for screen_id, screen in screens.items():
			bf_ids = screen.get('business_function_ids', [])
			if len(bf_ids) != len(set(bf_ids)):
				duplicates_count += len(bf_ids) - len(set(bf_ids))
			task_ids = screen.get('task_ids', [])
			if len(task_ids) != len(set(task_ids)):
				duplicates_count += len(task_ids) - len(set(task_ids))
			action_ids = screen.get('action_ids', [])
			if len(action_ids) != len(set(action_ids)):
				duplicates_count += len(action_ids) - len(set(action_ids))
		
		for action_id, action in actions.items():
			screen_ids = action.get('screen_ids', [])
			if len(screen_ids) != len(set(screen_ids)):
				duplicates_count += len(screen_ids) - len(set(screen_ids))
			bf_ids = action.get('business_function_ids', [])
			if len(bf_ids) != len(set(bf_ids)):
				duplicates_count += len(bf_ids) - len(set(bf_ids))
		
		for task_id, task in tasks.items():
			screen_ids = task.get('screen_ids', [])
			if len(screen_ids) != len(set(screen_ids)):
				duplicates_count += len(screen_ids) - len(set(screen_ids))
			bf_ids = task.get('business_function_ids', [])
			if len(bf_ids) != len(set(bf_ids)):
				duplicates_count += len(bf_ids) - len(set(bf_ids))
		
		for bf_id, bf in business_functions.items():
			screen_ids = bf.get('screen_ids', [])
			if len(screen_ids) != len(set(screen_ids)):
				duplicates_count += len(screen_ids) - len(set(screen_ids))
			task_ids = bf.get('task_ids', [])
			if len(task_ids) != len(set(task_ids)):
				duplicates_count += len(task_ids) - len(set(task_ids))
			action_ids = bf.get('action_ids', [])
			if len(action_ids) != len(set(action_ids)):
				duplicates_count += len(action_ids) - len(set(action_ids))
		
		metrics.relationship_duplicates_count = duplicates_count
		
		# Count invalid relationship references
		invalid_references_count = 0
		for screen_id, screen in screens.items():
			bf_ids = screen.get('business_function_ids', [])
			invalid_references_count += sum(1 for bf_id in bf_ids if bf_id not in business_functions)
			task_ids = screen.get('task_ids', [])
			invalid_references_count += sum(1 for task_id in task_ids if task_id not in tasks)
			action_ids = screen.get('action_ids', [])
			invalid_references_count += sum(1 for action_id in action_ids if action_id not in actions)
		
		for action_id, action in actions.items():
			screen_ids = action.get('screen_ids', [])
			invalid_references_count += sum(1 for screen_id in screen_ids if screen_id not in screens)
			bf_ids = action.get('business_function_ids', [])
			invalid_references_count += sum(1 for bf_id in bf_ids if bf_id not in business_functions)
		
		for task_id, task in tasks.items():
			screen_ids = task.get('screen_ids', [])
			invalid_references_count += sum(1 for screen_id in screen_ids if screen_id not in screens)
			bf_ids = task.get('business_function_ids', [])
			invalid_references_count += sum(1 for bf_id in bf_ids if bf_id not in business_functions)
		
		for bf_id, bf in business_functions.items():
			screen_ids = bf.get('screen_ids', [])
			invalid_references_count += sum(1 for screen_id in screen_ids if screen_id not in screens)
			task_ids = bf.get('task_ids', [])
			invalid_references_count += sum(1 for task_id in task_ids if task_id not in tasks)
			action_ids = bf.get('action_ids', [])
			invalid_references_count += sum(1 for action_id in action_ids if action_id not in actions)
		
		metrics.relationship_invalid_references_count = invalid_references_count
		
		# Store in details for visualization
		metrics.details['relationship_quality'] = {
			'relationship_completeness': metrics.relationship_completeness,
			'relationship_accuracy': metrics.relationship_accuracy,
			'relationship_duplicates_count': metrics.relationship_duplicates_count,
			'relationship_invalid_references_count': metrics.relationship_invalid_references_count,
			'entities_with_complete_relationships': entities_with_complete_relationships,
			'total_entities': total_entities,
			'correct_bidirectional_links': correct_bidirectional_links,
			'total_bidirectional_links': total_bidirectional_links,
		}


async def calculate_knowledge_quality(knowledge_id: str | None = None) -> KnowledgeQualityMetrics:
	"""
	Phase 4.2: Convenience function to calculate knowledge quality metrics.
	
	Args:
		knowledge_id: Optional knowledge ID to calculate metrics for specific knowledge set
	
	Returns:
		KnowledgeQualityMetrics with all calculated scores
	"""
	calculator = KnowledgeQualityCalculator(knowledge_id=knowledge_id)
	return await calculator.calculate_quality_metrics()


async def generate_quality_report(knowledge_id: str | None = None) -> QualityReport:
	"""
	Phase 4.2: Generate comprehensive quality report with recommendations.
	
	Args:
		knowledge_id: Optional knowledge ID to generate report for specific knowledge set
	
	Returns:
		QualityReport with metrics and recommendations
	"""
	report = QualityReport(knowledge_id=knowledge_id)
	
	# Calculate metrics
	report.metrics = await calculate_knowledge_quality(knowledge_id=knowledge_id)
	
	# Generate recommendations
	if report.metrics.overall_quality_score < 0.5:
		report.priority_issues.append("Overall quality score is below 50% - significant improvements needed")
	
	if report.metrics.completeness_score < 0.7:
		report.recommendations.append(
			f"Improve completeness (current: {report.metrics.completeness_score:.1%}). "
			"Ensure all entities have required fields (name, description, etc.)"
		)
	
	if report.metrics.relationship_coverage_score < 0.6:
		report.recommendations.append(
			f"Improve relationship coverage (current: {report.metrics.relationship_coverage_score:.1%}). "
			"Link entities to business functions, user flows, and other related entities"
		)
	
	if report.metrics.spatial_information_coverage < 0.5:
		report.recommendations.append(
			f"Improve spatial information coverage (current: {report.metrics.spatial_information_coverage:.1%}). "
			"Add position, layout context, and visual hierarchy information to screens and elements"
		)
	
	if report.metrics.business_context_coverage < 0.6:
		report.recommendations.append(
			f"Improve business context coverage (current: {report.metrics.business_context_coverage:.1%}). "
			"Link entities to business functions and ensure business functions have reasoning, impact, and requirements"
		)
	
	if report.metrics.business_functions_count == 0:
		report.priority_issues.append("No business functions found - extract business functions from content")
	
	# Priority 10: Relationship quality recommendations
	if report.metrics.relationship_completeness < 0.5:
		report.recommendations.append(
			f"Improve relationship completeness (current: {report.metrics.relationship_completeness:.1%}). "
			"Ensure entities have all expected relationship types (screens: BF, tasks, actions; actions/tasks: screens, BF)"
		)
	
	if report.metrics.relationship_accuracy < 0.8:
		report.recommendations.append(
			f"Improve relationship accuracy (current: {report.metrics.relationship_accuracy:.1%}). "
			"Fix bidirectional links - if entity A links to B, B should link back to A"
		)
	
	if report.metrics.relationship_duplicates_count > 0:
		report.priority_issues.append(
			f"Found {report.metrics.relationship_duplicates_count} duplicate relationships - "
			"run relationship deduplication to clean up"
		)
	
	if report.metrics.relationship_invalid_references_count > 0:
		report.priority_issues.append(
			f"Found {report.metrics.relationship_invalid_references_count} invalid relationship references - "
			"fix references to non-existent entities"
		)
	
	return report


async def generate_relationship_visualization_data(knowledge_id: str | None = None) -> dict[str, Any]:
	"""
	Priority 10: Generate relationship visualization data for dashboard.
	
	Creates comprehensive data structure for visualizing entity relationships including:
	- Relationship network graph data (nodes and edges)
	- Relationship type distribution
	- Entity connectivity statistics
	- Relationship quality metrics
	
	Args:
		knowledge_id: Optional knowledge ID to generate visualization for specific knowledge set
	
	Returns:
		Dictionary with visualization data for dashboard
	"""
	from navigator.knowledge.validation.metrics import calculate_knowledge_quality
	
	# Calculate quality metrics (includes relationship quality)
	metrics = await calculate_knowledge_quality(knowledge_id=knowledge_id)
	
	# Build entity cache for relationship graph
	calculator = KnowledgeQualityCalculator(knowledge_id=knowledge_id)
	entity_cache = await calculator._build_entity_cache()
	
	screens = entity_cache['screens']
	actions = entity_cache['actions']
	tasks = entity_cache['tasks']
	business_functions = entity_cache['business_functions']
	
	# Priority 10: Build relationship graph (nodes and edges)
	nodes = []
	edges = []
	
	# Add nodes
	for screen_id, screen in screens.items():
		nodes.append({
			'id': screen_id,
			'type': 'screen',
			'name': screen.get('name', 'Unknown'),
			'relationship_count': (
				len(screen.get('business_function_ids', [])) +
				len(screen.get('task_ids', [])) +
				len(screen.get('action_ids', []))
			)
		})
	
	for action_id, action in actions.items():
		nodes.append({
			'id': action_id,
			'type': 'action',
			'name': action.get('name', 'Unknown'),
			'relationship_count': (
				len(action.get('screen_ids', [])) +
				len(action.get('business_function_ids', []))
			)
		})
	
	for task_id, task in tasks.items():
		nodes.append({
			'id': task_id,
			'type': 'task',
			'name': task.get('name', 'Unknown'),
			'relationship_count': (
				len(task.get('screen_ids', [])) +
				len(task.get('business_function_ids', []))
			)
		})
	
	for bf_id, bf in business_functions.items():
		nodes.append({
			'id': bf_id,
			'type': 'business_function',
			'name': bf.get('name', 'Unknown'),
			'relationship_count': (
				len(bf.get('screen_ids', [])) +
				len(bf.get('task_ids', [])) +
				len(bf.get('action_ids', []))
			)
		})
	
	# Add edges (relationships)
	# Screens -> Business Functions
	for screen_id, screen in screens.items():
		for bf_id in screen.get('business_function_ids', []):
			edges.append({
				'source': screen_id,
				'target': bf_id,
				'type': 'screen_to_business_function',
				'bidirectional': bf_id in business_functions and screen_id in business_functions[bf_id].get('screen_ids', [])
			})
	
	# Screens -> Tasks
	for screen_id, screen in screens.items():
		for task_id in screen.get('task_ids', []):
			edges.append({
				'source': screen_id,
				'target': task_id,
				'type': 'screen_to_task',
				'bidirectional': task_id in tasks and screen_id in tasks[task_id].get('screen_ids', [])
			})
	
	# Screens -> Actions
	for screen_id, screen in screens.items():
		for action_id in screen.get('action_ids', []):
			edges.append({
				'source': screen_id,
				'target': action_id,
				'type': 'screen_to_action',
				'bidirectional': action_id in actions and screen_id in actions[action_id].get('screen_ids', [])
			})
	
	# Actions -> Business Functions
	for action_id, action in actions.items():
		for bf_id in action.get('business_function_ids', []):
			edges.append({
				'source': action_id,
				'target': bf_id,
				'type': 'action_to_business_function',
				'bidirectional': bf_id in business_functions and action_id in business_functions[bf_id].get('action_ids', [])
			})
	
	# Tasks -> Business Functions
	for task_id, task in tasks.items():
		for bf_id in task.get('business_function_ids', []):
			edges.append({
				'source': task_id,
				'target': bf_id,
				'type': 'task_to_business_function',
				'bidirectional': bf_id in business_functions and task_id in business_functions[bf_id].get('task_ids', [])
			})
	
	# Priority 10: Calculate relationship type distribution
	relationship_type_distribution = {}
	for edge in edges:
		rel_type = edge['type']
		relationship_type_distribution[rel_type] = relationship_type_distribution.get(rel_type, 0) + 1
	
	# Priority 10: Calculate entity connectivity statistics
	entity_connectivity = {
		'screens': {
			'total': len(screens),
			'with_relationships': sum(1 for s in screens.values() if s.get('business_function_ids') or s.get('task_ids') or s.get('action_ids')),
			'avg_relationships': sum(
				len(s.get('business_function_ids', [])) + len(s.get('task_ids', [])) + len(s.get('action_ids', []))
				for s in screens.values()
			) / len(screens) if screens else 0.0
		},
		'actions': {
			'total': len(actions),
			'with_relationships': sum(1 for a in actions.values() if a.get('screen_ids') or a.get('business_function_ids')),
			'avg_relationships': sum(
				len(a.get('screen_ids', [])) + len(a.get('business_function_ids', []))
				for a in actions.values()
			) / len(actions) if actions else 0.0
		},
		'tasks': {
			'total': len(tasks),
			'with_relationships': sum(1 for t in tasks.values() if t.get('screen_ids') or t.get('business_function_ids')),
			'avg_relationships': sum(
				len(t.get('screen_ids', [])) + len(t.get('business_function_ids', []))
				for t in tasks.values()
			) / len(tasks) if tasks else 0.0
		},
		'business_functions': {
			'total': len(business_functions),
			'with_relationships': sum(1 for bf in business_functions.values() if bf.get('screen_ids') or bf.get('task_ids') or bf.get('action_ids')),
			'avg_relationships': sum(
				len(bf.get('screen_ids', [])) + len(bf.get('task_ids', [])) + len(bf.get('action_ids', []))
				for bf in business_functions.values()
			) / len(business_functions) if business_functions else 0.0
		}
	}
	
	# Priority 10: Calculate bidirectional link statistics
	bidirectional_edges = sum(1 for edge in edges if edge.get('bidirectional', False))
	bidirectional_percentage = (bidirectional_edges / len(edges) * 100) if edges else 0.0
	
	return {
		'knowledge_id': knowledge_id,
		'graph': {
			'nodes': nodes,
			'edges': edges,
			'total_nodes': len(nodes),
			'total_edges': len(edges),
		},
		'relationship_type_distribution': relationship_type_distribution,
		'entity_connectivity': entity_connectivity,
		'relationship_quality': {
			'completeness': metrics.relationship_completeness,
			'accuracy': metrics.relationship_accuracy,
			'duplicates_count': metrics.relationship_duplicates_count,
			'invalid_references_count': metrics.relationship_invalid_references_count,
			'bidirectional_percentage': bidirectional_percentage,
			'bidirectional_edges': bidirectional_edges,
			'total_edges': len(edges),
		},
		'metrics': {
			'relationship_coverage_score': metrics.relationship_coverage_score,
			'screen_relationship_coverage': metrics.screen_relationship_coverage,
			'action_relationship_coverage': metrics.action_relationship_coverage,
			'task_relationship_coverage': metrics.task_relationship_coverage,
		}
	}

"""
Knowledge Extraction Workflow V2 - Temporal Orchestration.

This workflow orchestrates the complete knowledge extraction pipeline:
ingestion → extraction → graph construction → verification → enrichment.
"""

import logging
import time
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activities and schemas
with workflow.unsafe.imports_passed_through():
	from navigator.temporal.activities_v2 import (
		build_graph_activity,
		enrich_knowledge_activity,
		extract_actions_activity,
		extract_screens_activity,
		extract_tasks_activity,
		extract_transitions_activity,
		ingest_source_activity,
		verify_extraction_activity,
	)
	from navigator.schemas import (
		BuildGraphInput,
		BuildGraphResult,
		EnrichKnowledgeInput,
		EnrichKnowledgeResult,
		ExtractActionsInput,
		ExtractActionsResult,
		ExtractScreensInput,
		ExtractScreensResult,
		ExtractTasksInput,
		ExtractTasksResult,
		ExtractTransitionsInput,
		ExtractTransitionsResult,
		IngestSourceInput,
		IngestSourceResult,
		KnowledgeExtractionInputV2,
		KnowledgeExtractionProgressV2,
		KnowledgeExtractionResultV2,
		VerifyExtractionInput,
		VerifyExtractionResult,
		WorkflowPhase,
	)

logger = logging.getLogger(__name__)


@workflow.defn(name="knowledge-extraction-workflow-v2")
class KnowledgeExtractionWorkflowV2:
	"""
	Knowledge Extraction Workflow V2.
	
	Features:
	- Multi-source ingestion (docs, website, video)
	- Semantic extraction and normalization
	- ArangoDB graph construction
	- Browser-based verification
	- Automated enrichment
	- Pause/resume/cancel support
	- Progress tracking via queries
	- Long-running execution (24 hour timeout)
	- Checkpoint-based recovery
	"""
	
	def __init__(self):
		"""Initialize workflow state."""
		# Control flags
		self._paused = False
		self._cancelled = False
		
		# Progress tracking
		self._progress = KnowledgeExtractionProgressV2()
		
		# Timing
		self._start_time = time.time()
	
	# ========================================================================
	# Workflow Execution
	# ========================================================================
	
	@workflow.run
	async def run(self, input: KnowledgeExtractionInputV2) -> KnowledgeExtractionResultV2:
		"""
		Execute knowledge extraction workflow.
		
		Phases:
		1. Ingestion - Ingest source content
		2. Extraction - Extract screens, tasks, actions, transitions
		3. Graph Construction - Build ArangoDB graph
		4. Verification - Browser-based verification
		5. Enrichment - Update definitions based on verification
		
		Args:
			input: Workflow input parameters
		
		Returns:
			Workflow result with statistics
		"""
		workflow.logger.info(f"🚀 Starting Knowledge Extraction Workflow V2: {input.job_id}")
		workflow.logger.info(f"   Source: {input.source_url}")
		workflow.logger.info(f"   Type: {input.source_type}")
		
		# Define retry policy for activities
		retry_policy = RetryPolicy(
			initial_interval=timedelta(seconds=1),
			maximum_interval=timedelta(seconds=60),
			backoff_coefficient=2.0,
			maximum_attempts=5,
		)
		
		# Activity execution options
		activity_options = {
			'start_to_close_timeout': timedelta(hours=2),
			'heartbeat_timeout': timedelta(seconds=90),
			'retry_policy': retry_policy,
		}
		
		result = KnowledgeExtractionResultV2(
			job_id=input.job_id,
			status='completed',
		)
		
		try:
			# ================================================================
			# Phase 1: Ingestion
			# ================================================================
			
			self._progress.phase = WorkflowPhase.INGESTION
			self._progress.current_activity = "ingest_source_v2"
			await self._check_pause_or_cancel()
			
			workflow.logger.info("📥 Phase 1: Ingesting source...")
			
			ingest_result: IngestSourceResult = await workflow.execute_activity(
				ingest_source_activity,
				IngestSourceInput(
					source_url=input.source_url,
					source_type=input.source_type,
					job_id=input.job_id,
					options=input.options,
				),
				**activity_options,
			)
			
			if not ingest_result.success:
				raise Exception(f"Ingestion failed: {ingest_result.errors}")
			
			result.sources_ingested = 1
			self._progress.sources_ingested = 1
			
			workflow.logger.info(
				f"✅ Ingestion completed: {ingest_result.content_chunks} chunks"
			)
			
			# ================================================================
			# Phase 2: Extraction
			# ================================================================
			
			self._progress.phase = WorkflowPhase.EXTRACTION
			await self._check_pause_or_cancel()
			
			workflow.logger.info("🔍 Phase 2: Extracting knowledge...")
			
			# Extract screens
			self._progress.current_activity = "extract_screens_v2"
			screens_result: ExtractScreensResult = await workflow.execute_activity(
				extract_screens_activity,
				ExtractScreensInput(
					ingestion_id=ingest_result.ingestion_id,
					job_id=input.job_id,
				),
				**activity_options,
			)
			
			result.screens_extracted = screens_result.screens_extracted
			self._progress.screens_extracted = screens_result.screens_extracted
			
			# Extract tasks
			self._progress.current_activity = "extract_tasks_v2"
			tasks_result: ExtractTasksResult = await workflow.execute_activity(
				extract_tasks_activity,
				ExtractTasksInput(
					ingestion_id=ingest_result.ingestion_id,
					job_id=input.job_id,
				),
				**activity_options,
			)
			
			result.tasks_extracted = tasks_result.tasks_extracted
			self._progress.tasks_extracted = tasks_result.tasks_extracted
			
			# Extract actions
			self._progress.current_activity = "extract_actions_v2"
			actions_result: ExtractActionsResult = await workflow.execute_activity(
				extract_actions_activity,
				ExtractActionsInput(
					ingestion_id=ingest_result.ingestion_id,
					job_id=input.job_id,
				),
				**activity_options,
			)
			
			result.actions_extracted = actions_result.actions_extracted
			self._progress.actions_extracted = actions_result.actions_extracted
			
			# Extract transitions
			self._progress.current_activity = "extract_transitions_v2"
			transitions_result: ExtractTransitionsResult = await workflow.execute_activity(
				extract_transitions_activity,
				ExtractTransitionsInput(
					ingestion_id=ingest_result.ingestion_id,
					job_id=input.job_id,
				),
				**activity_options,
			)
			
			result.transitions_extracted = transitions_result.transitions_extracted
			
			workflow.logger.info(
				f"✅ Extraction completed: "
				f"{result.screens_extracted} screens, "
				f"{result.tasks_extracted} tasks, "
				f"{result.actions_extracted} actions, "
				f"{result.transitions_extracted} transitions"
			)
			
			# ================================================================
			# Phase 3: Graph Construction
			# ================================================================
			
			self._progress.phase = WorkflowPhase.GRAPH_CONSTRUCTION
			self._progress.current_activity = "build_graph_v2"
			await self._check_pause_or_cancel()
			
			workflow.logger.info("🔗 Phase 3: Building knowledge graph...")
			
			graph_result: BuildGraphResult = await workflow.execute_activity(
				build_graph_activity,
				BuildGraphInput(
					job_id=input.job_id,
					screen_ids=screens_result.screen_ids,
					task_ids=tasks_result.task_ids,
					action_ids=actions_result.action_ids,
					transition_ids=transitions_result.transition_ids,
				),
				**activity_options,
			)
			
			result.graph_nodes = graph_result.graph_nodes
			result.graph_edges = graph_result.graph_edges
			
			workflow.logger.info(
				f"✅ Graph constructed: "
				f"{result.graph_nodes} nodes, "
				f"{result.graph_edges} edges"
			)
			
			# ================================================================
			# Phase 4: Verification
			# ================================================================
			
			self._progress.phase = WorkflowPhase.VERIFICATION
			self._progress.current_activity = "verify_extraction_v2"
			await self._check_pause_or_cancel()
			
			workflow.logger.info("🔬 Phase 4: Verifying extraction...")
			
			verify_result: VerifyExtractionResult = await workflow.execute_activity(
				verify_extraction_activity,
				VerifyExtractionInput(
					job_id=input.job_id,
					screen_ids=screens_result.screen_ids,
					task_ids=tasks_result.task_ids,
				),
				**activity_options,
			)
			
			result.screens_verified = verify_result.screens_verified
			result.discrepancies_found = verify_result.discrepancies_found
			
			workflow.logger.info(
				f"✅ Verification completed: "
				f"{result.screens_verified} screens verified, "
				f"{result.discrepancies_found} discrepancies found"
			)
			
			# ================================================================
			# Phase 5: Enrichment
			# ================================================================
			
			self._progress.phase = WorkflowPhase.ENRICHMENT
			self._progress.current_activity = "enrich_knowledge_v2"
			await self._check_pause_or_cancel()
			
			workflow.logger.info("✨ Phase 5: Enriching knowledge...")
			
			enrich_result: EnrichKnowledgeResult = await workflow.execute_activity(
				enrich_knowledge_activity,
				EnrichKnowledgeInput(
					job_id=input.job_id,
					discrepancy_ids=verify_result.discrepancy_ids,
				),
				**activity_options,
			)
			
			result.enrichments_applied = enrich_result.enrichments_applied
			
			workflow.logger.info(
				f"✅ Enrichment completed: "
				f"{result.enrichments_applied} enrichments applied"
			)
			
			# ================================================================
			# Completion
			# ================================================================
			
			self._progress.phase = WorkflowPhase.COMPLETED
			result.processing_time = time.time() - self._start_time
			result.status = 'completed'
			
			workflow.logger.info(
				f"🎉 Workflow completed in {result.processing_time:.2f}s"
			)
			
			return result
			
		except Exception as e:
			workflow.logger.error(f"❌ Workflow failed: {e}", exc_info=True)
			result.status = 'failed'
			result.error = str(e)
			result.processing_time = time.time() - self._start_time
			return result
	
	# ========================================================================
	# Signals (Workflow Control)
	# ========================================================================
	
	@workflow.signal
	def pause(self):
		"""Pause workflow execution."""
		workflow.logger.info("⏸️  Pause signal received")
		self._paused = True
	
	@workflow.signal
	def resume(self):
		"""Resume paused workflow."""
		workflow.logger.info("▶️  Resume signal received")
		self._paused = False
	
	@workflow.signal
	def cancel(self):
		"""Cancel workflow execution."""
		workflow.logger.info("⏹️  Cancel signal received")
		self._cancelled = True
	
	# ========================================================================
	# Queries (Workflow State)
	# ========================================================================
	
	@workflow.query
	def get_progress(self) -> dict:
		"""
		Get current workflow progress.
		
		Returns:
			Progress information including phase, activity, and statistics
		"""
		return {
			'phase': self._progress.phase.value,
			'current_activity': self._progress.current_activity,
			'items_processed': self._progress.items_processed,
			'total_items': self._progress.total_items,
			'sources_ingested': self._progress.sources_ingested,
			'screens_extracted': self._progress.screens_extracted,
			'tasks_extracted': self._progress.tasks_extracted,
			'actions_extracted': self._progress.actions_extracted,
			'errors': self._progress.errors,
			'elapsed_time': time.time() - self._start_time,
		}
	
	@workflow.query
	def is_paused(self) -> bool:
		"""Check if workflow is paused."""
		return self._paused
	
	@workflow.query
	def is_cancelled(self) -> bool:
		"""Check if workflow is cancelled."""
		return self._cancelled
	
	# ========================================================================
	# Private Methods
	# ========================================================================
	
	async def _check_pause_or_cancel(self):
		"""
		Check for pause/cancel signals and wait if needed.
		
		Raises:
			Exception: If workflow is cancelled
		"""
		# Check cancel first
		if self._cancelled:
			workflow.logger.info("⏹️  Workflow cancelled")
			raise Exception("Workflow cancelled by user")
		
		# Check pause and wait until resumed
		while self._paused:
			workflow.logger.info("⏸️  Workflow paused, waiting for resume...")
			await workflow.wait_condition(lambda: not self._paused or self._cancelled)
			
			if self._cancelled:
				workflow.logger.info("⏹️  Workflow cancelled during pause")
				raise Exception("Workflow cancelled by user during pause")

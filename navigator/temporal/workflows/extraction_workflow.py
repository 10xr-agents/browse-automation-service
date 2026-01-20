"""
Knowledge Extraction Workflow V2 - Main Orchestrator.

This workflow orchestrates the complete knowledge extraction pipeline:
ingestion → extraction → graph construction → verification → enrichment.

All phases are implemented in separate phase modules for maintainability.
"""

from datetime import timedelta
from urllib.parse import urlparse

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activities and schemas - wrap ALL imports including logging
with workflow.unsafe.imports_passed_through():
	import logging

	from navigator.schemas import (
		KnowledgeExtractionInputV2,
		KnowledgeExtractionProgressV2,
		KnowledgeExtractionResultV2,
		WorkflowPhase,
	)
	from navigator.temporal.workflows.helpers.workflow_control import WorkflowControl
	from navigator.temporal.workflows.phases.enrichment_phase import execute_enrichment_phase
	from navigator.temporal.workflows.phases.extraction_phase import execute_extraction_phase
	from navigator.temporal.workflows.phases.graph_construction_phase import execute_graph_construction_phase
	from navigator.temporal.workflows.phases.ingestion_phase import execute_ingestion_phase
	from navigator.temporal.workflows.phases.url_exploration_phase import execute_url_exploration_phase
	from navigator.temporal.workflows.phases.verification_phase import execute_verification_phase
	from navigator.temporal.workflows.utils.continue_as_new import safe_continue_as_new, should_continue_as_new

	logger = logging.getLogger(__name__)


@workflow.defn(name="knowledge-extraction-workflow-v2")
class KnowledgeExtractionWorkflowV2:
	"""
	Knowledge Extraction Workflow V2.
	
	Features:
	- **Smart Multi-Asset Processing**: Handles multiple files, videos, and websites in one workflow
	- **Auto-Type Detection**: Automatically detects asset type (video, documentation, website) per asset
	- **Mixed Asset Support**: Can process any combination of files, videos, and websites
	- **Knowledge Merging**: Aggregates knowledge from all assets and deduplicates across sources
	- **Empty Case Handling**: Gracefully handles cases where some asset types are missing
	- Multi-source ingestion (docs, website, video)
	- Semantic extraction and normalization
	- Graph validation (MongoDB-based)
	- Browser-based verification
	- Automated enrichment
	- Pause/resume/cancel support
	- Progress tracking via queries
	- Long-running execution (24 hour timeout)
	- Checkpoint-based recovery
	
	**Knowledge Deduplication**:
	- Screens, tasks, actions, and workflows are automatically deduplicated during extraction
	- Duplicate information across different asset types (e.g., same screen in video and docs) is merged
	- Final knowledge base contains unique, comprehensive knowledge from all sources
	"""

	def __init__(self):
		"""Initialize workflow state."""
		# Workflow control
		self._control = WorkflowControl()

		# Progress tracking
		self._progress = KnowledgeExtractionProgressV2()

		# Timing (using workflow time for determinism)
		self._start_time = workflow.time()

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
		3. Graph Construction - Build knowledge graph
		4. URL Exploration - DOM-level analysis (optional)
		5. Verification - Browser-based verification
		6. Enrichment - Update definitions based on verification
		
		Args:
			input: Workflow input parameters
		
		Returns:
			Workflow result with statistics
		"""
		# 🐛 DEBUG: Log workflow start
		workflow.logger.debug("=" * 80)
		workflow.logger.debug("🐛 DEBUG: Workflow run() method called - FIRST STEP")
		workflow.logger.debug(f"   Workflow ID: {workflow.info().workflow_id}")
		workflow.logger.debug(f"   Run ID: {workflow.info().run_id}")
		workflow.logger.debug("   Input received:")
		workflow.logger.debug(f"     - job_id: {input.job_id}")
		workflow.logger.debug(f"     - source_type: {input.source_type}")
		workflow.logger.debug(f"     - source_url: {input.source_url}")
		workflow.logger.debug(f"     - source_urls: {input.source_urls}")
		workflow.logger.debug(f"     - source_name: {input.source_name}")
		workflow.logger.debug(f"     - source_names: {input.source_names}")
		workflow.logger.debug(f"     - knowledge_id: {input.knowledge_id}")
		workflow.logger.debug(f"     - options: {input.options}")
		workflow.logger.debug("=" * 80)

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
		# Video ingestion can take 30-60+ minutes (transcription + frame analysis)
		# Use longer timeouts to handle legitimate long-running operations
		activity_options = {
			'start_to_close_timeout': timedelta(hours=2),  # Total activity execution time
			'heartbeat_timeout': timedelta(minutes=15),  # Allow 15 minutes between heartbeats
			'schedule_to_close_timeout': timedelta(hours=2),  # Total time from schedule to close
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

			ingest_results = await execute_ingestion_phase(
				input=input,
				result=result,
				progress=self._progress,
				activity_options=activity_options,
				check_pause_or_cancel=self._control.check_pause_or_cancel,
			)

			# Validate ingestion results
			if not ingest_results or len(ingest_results) == 0:
				error_msg = "❌ No ingestion results - all sources failed to ingest"
				workflow.logger.error(error_msg)
				raise Exception(error_msg)

			# Primary ingestion result for backward compatibility
			ingest_result = ingest_results[0]

			# Check if we should continue as new after Phase 1
			if should_continue_as_new():
				workflow.logger.info(
					"🔄 History size approaching limit after Phase 1 (Ingestion). "
					"Continuing as new to reset history..."
				)
				return await safe_continue_as_new(input)

			# ================================================================
			# Phase 2: Extraction
			# ================================================================

			screens_result, tasks_result, actions_result, transitions_result = await execute_extraction_phase(
				input=input,
				result=result,
				progress=self._progress,
				ingest_results=ingest_results,
				ingest_result=ingest_result,
				activity_options=activity_options,
				check_pause_or_cancel=self._control.check_pause_or_cancel,
			)

			# Check if we should continue as new after Phase 2
			if should_continue_as_new():
				workflow.logger.info(
					"🔄 History size approaching limit after Phase 2 (Extraction). "
					"Continuing as new to reset history..."
				)
				return await safe_continue_as_new(input)

			# ================================================================
			# Phase 3: Graph Construction
			# ================================================================

			await execute_graph_construction_phase(
				result=result,
				progress=self._progress,
				screens_result=screens_result,
				tasks_result=tasks_result,
				actions_result=actions_result,
				transitions_result=transitions_result,
				input_job_id=input.job_id,
				activity_options=activity_options,
				check_pause_or_cancel=self._control.check_pause_or_cancel,
			)

			# Check if we should continue as new after Phase 3
			if should_continue_as_new():
				workflow.logger.info(
					"🔄 History size approaching limit after Phase 3 (Graph Construction). "
					"Continuing as new to reset history..."
				)
				return await safe_continue_as_new(input)

			# ================================================================
			# Phase 3.5: URL Exploration (Optional)
			# ================================================================

			# Extract website_id for URL exploration
			if input.source_url:
				website_id = urlparse(input.source_url).netloc
			elif input.source_urls and len(input.source_urls) > 0:
				first_url = input.source_urls[0]
				# Validate first_url is not empty
				if not first_url:
					workflow.logger.warning("⚠️ First source URL is empty, using 'unknown' for website_id")
					website_id = "unknown"
				else:
					website_id = urlparse(first_url).netloc if first_url.startswith('http') else "mixed-assets"
			else:
				website_id = "unknown"

			await execute_url_exploration_phase(
				input=input,
				result=result,
				progress=self._progress,
				screens_result=screens_result,
				tasks_result=tasks_result,
				actions_result=actions_result,
				website_id=website_id,
				activity_options=activity_options,
				check_pause_or_cancel=self._control.check_pause_or_cancel,
			)

			# ================================================================
			# Phase 4: Verification
			# ================================================================

			verify_result = await execute_verification_phase(
				result=result,
				progress=self._progress,
				screens_result=screens_result,
				tasks_result=tasks_result,
				input_job_id=input.job_id,
				activity_options=activity_options,
				check_pause_or_cancel=self._control.check_pause_or_cancel,
			)

			# Check if we should continue as new after Phase 4
			if should_continue_as_new():
				workflow.logger.info(
					"🔄 History size approaching limit after Phase 4 (Verification). "
					"Continuing as new to reset history..."
				)
				return await safe_continue_as_new(input)

			# ================================================================
			# Phase 5: Enrichment
			# ================================================================

			await execute_enrichment_phase(
				result=result,
				progress=self._progress,
				verify_result=verify_result,
				input_job_id=input.job_id,
				activity_options=activity_options,
				check_pause_or_cancel=self._control.check_pause_or_cancel,
			)

			# ================================================================
			# Completion
			# ================================================================

			self._progress.phase = WorkflowPhase.COMPLETED
			result.processing_time = workflow.time() - self._start_time
			result.status = 'completed'

			workflow.logger.info(
				f"🎉 Workflow completed in {result.processing_time:.2f}s"
			)

			return result

		except Exception as e:
			workflow.logger.error(f"❌ Workflow failed: {e}", exc_info=True)
			result.status = 'failed'
			result.error = str(e)
			result.processing_time = workflow.time() - self._start_time
			return result

	# ========================================================================
	# Signals (Workflow Control)
	# ========================================================================

	@workflow.signal
	def pause(self):
		"""Pause workflow execution."""
		self._control.pause()

	@workflow.signal
	def resume(self):
		"""Resume paused workflow."""
		self._control.resume()

	@workflow.signal
	def cancel(self):
		"""Cancel workflow execution."""
		self._control.cancel()

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
			'tasks_extracted': self._progress.actions_extracted,
			'errors': self._progress.errors,
			'elapsed_time': workflow.time() - self._start_time,
		}

	@workflow.query
	def is_paused(self) -> bool:
		"""Check if workflow is paused."""
		return self._control.is_paused()

	@workflow.query
	def is_cancelled(self) -> bool:
		"""Check if workflow is cancelled."""
		return self._control.is_cancelled()

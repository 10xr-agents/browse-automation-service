"""
Ingestion activity for knowledge extraction workflow.

Handles ingestion of source content (documentation, website, or video).
"""

import logging
import time

from temporalio import activity

from navigator.schemas import IngestSourceInput, IngestSourceResult
from navigator.temporal.activities.shared import get_idempotency_manager

logger = logging.getLogger(__name__)


@activity.defn(name="ingest_source")
async def ingest_source_activity(input: IngestSourceInput) -> IngestSourceResult:
	"""
	Ingest source content (documentation, website, or video).
	
	This activity:
	1. Detects source type if not provided
	2. Routes to appropriate ingester
	3. Chunks content if needed
	4. Stores raw content in MongoDB
	5. Returns ingestion metadata
	
	Args:
		input: Ingestion parameters
	
	Returns:
		Ingestion result with metadata
	"""
	start_time = time.time()
	workflow_id = activity.info().workflow_id
	activity_id = activity.info().activity_id
	_idempotency_manager = get_idempotency_manager()

	# 🚨 AGGRESSIVE LOGGING: Activity start
	logger.info(f"{'='*80}")
	logger.info("🔵 ACTIVITY START: ingest_source")
	logger.info(f"   Workflow ID: {workflow_id}")
	logger.info(f"   Activity ID: {activity_id}")
	logger.info(f"   Source URL: {input.source_url}")
	logger.info(f"   Source Type: {input.source_type}")
	logger.info(f"{'='*80}")

	# Check idempotency
	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "ingest_source", input
		)
		if cached:
			logger.info("♻️  Using cached result from previous execution")
			return IngestSourceResult(**cached)

	# Send heartbeat
	activity.heartbeat({"status": "starting", "source": input.source_url})

	try:
		# Get ingestion router
		from navigator.knowledge.ingest import get_ingestion_router

		router = get_ingestion_router()

		# Send heartbeat
		activity.heartbeat({"status": "ingesting", "source": input.source_url})

		# Ingest content using router
		ingestion_result = await router.ingest(
			source_url=input.source_url,
			source_type=input.source_type,
			options=input.options
		)

		# Send heartbeat with results
		activity.heartbeat({
			"status": "completed",
			"chunks": ingestion_result.total_chunks,
			"tokens": ingestion_result.total_tokens
		})

		# Convert to activity result
		result = IngestSourceResult.from_ingestion_result(ingestion_result)

		# 🚨 CRITICAL FIX: Persist ingestion result to MongoDB
		from navigator.knowledge.persist.ingestion import save_ingestion_result

		logger.info(f"💾 Persisting ingestion result: {result.ingestion_id}")
		persist_success = await save_ingestion_result(ingestion_result)

		if not persist_success:
			error_msg = f"❌ CRITICAL: Failed to persist ingestion result: {result.ingestion_id}"
			logger.error(error_msg)
			raise RuntimeError(error_msg)  # Fixed: raise explicit exception instead of bare raise

		# Record execution
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"ingest_source",
				input,
				result.__dict__,
				success=True,
			)

		return result

	except Exception as e:
		logger.error(f"❌ Ingestion failed: {e}", exc_info=True)

		# Record failure
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"ingest_source",
				input,
				{},
				success=False,
				error=str(e),
			)

		raise

"""
Extract screens activity for knowledge extraction workflow.

Extracts screen definitions from ingested content.
"""

import logging
import time

from temporalio import activity

from navigator.schemas import ExtractScreensInput, ExtractScreensResult
from navigator.temporal.activities.shared import get_idempotency_manager

logger = logging.getLogger(__name__)


@activity.defn(name="extract_screens")
async def extract_screens_activity(input: ExtractScreensInput) -> ExtractScreensResult:
	"""
	Extract screen definitions from ingested content.
	
	This activity:
	1. Analyzes content to identify screen descriptions
	2. Extracts screen elements (name, URL patterns, state signatures)
	3. Normalizes to schema format
	4. Stores in staging collection
	
	Args:
		input: Extraction parameters
	
	Returns:
		Extraction result with screen IDs
	"""
	start_time = time.time()
	workflow_id = activity.info().workflow_id
	activity_id = activity.info().activity_id
	_idempotency_manager = get_idempotency_manager()

	# 🚨 AGGRESSIVE LOGGING: Activity start
	logger.info(f"{'='*80}")
	logger.info("🔵 ACTIVITY START: extract_screens")
	logger.info(f"   Workflow ID: {workflow_id}")
	logger.info(f"   Activity ID: {activity_id}")
	logger.info(f"   Ingestion ID: {input.ingestion_id}")
	logger.info(f"   Website ID: {input.website_id}")
	logger.info(f"{'='*80}")

	# Check idempotency
	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "extract_screens", input
		)
		if cached:
			logger.info("♻️  Using cached result from previous execution")
			return ExtractScreensResult(**cached)

	activity.heartbeat({"status": "extracting", "ingestion_id": input.ingestion_id})

	try:
		# 🚨 CRITICAL FIX: Load REAL ingestion result from MongoDB (NOT MOCK DATA!)
		from navigator.knowledge.extract import ScreenExtractor
		from navigator.knowledge.persist.ingestion import get_ingestion_chunks

		# Determine which ingestion IDs to load from
		ingestion_ids_to_load = input.ingestion_ids if input.ingestion_ids else [input.ingestion_id]

		logger.info(f"📥 Loading chunks from {len(ingestion_ids_to_load)} ingestion(s): {ingestion_ids_to_load}")

		# Load chunks from all ingestion results
		all_chunks = []
		for ingestion_id in ingestion_ids_to_load:
			chunks = await get_ingestion_chunks(ingestion_id)
			if chunks:
				all_chunks.extend(chunks)
				logger.info(f"✅ Loaded {len(chunks)} chunks from ingestion: {ingestion_id}")
			else:
				logger.warning(f"⚠️ No chunks found for ingestion: {ingestion_id}")

		content_chunks = all_chunks

		# Validate chunks exist
		if not content_chunks:
			error_msg = (
				f"❌ CRITICAL: No content chunks found for any ingestion: {ingestion_ids_to_load}. "
				f"This indicates ingestion results were not persisted correctly. "
				f"Extraction cannot proceed without source content."
			)
			logger.error(error_msg)
			raise ValueError(error_msg)

		# Extract screens from chunks
		# website_id is required for ScreenExtractor, use input value or default
		website_id = input.website_id or "unknown"
		screen_extractor = ScreenExtractor(website_id=website_id)
		screens_result = screen_extractor.extract_screens(content_chunks)

		# Persist screens to MongoDB with knowledge_id and job_id
		if screens_result.screens:
			from navigator.knowledge.persist.documents import save_screens
			await save_screens(screens_result.screens, knowledge_id=input.knowledge_id, job_id=input.job_id)
			logger.info(f"💾 Saved {len(screens_result.screens)} screen(s) to MongoDB with knowledge_id={input.knowledge_id}, job_id={input.job_id}")

		# Convert ScreenExtractionResult (Pydantic) to ExtractScreensResult (dataclass) for Temporal
		extract_result = ExtractScreensResult(
			screens_extracted=len(screens_result.screens),
			screen_ids=[s.screen_id for s in screens_result.screens],
			errors=[str(err.get("message", err)) for err in screens_result.errors] if screens_result.errors else [],
			success=screens_result.success,
		)

		# Record execution
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"extract_screens",
				input,
				{
					"screens_extracted": extract_result.screens_extracted,
					"screen_ids": extract_result.screen_ids,
					"errors": extract_result.errors,
					"success": extract_result.success,
				},
				success=True,
			)

		return extract_result

	except Exception as e:
		logger.error(f"❌ Screen extraction failed: {e}", exc_info=True)

		# Record failure
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"extract_screens",
				input,
				{},
				success=False,
				error=str(e),
			)

		raise

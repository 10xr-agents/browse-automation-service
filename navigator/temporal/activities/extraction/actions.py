"""
Extract actions activity for knowledge extraction workflow.

Extracts action definitions from ingested content.
"""

import logging

from temporalio import activity

from navigator.schemas import ExtractActionsInput, ExtractActionsResult
from navigator.temporal.activities.shared import get_idempotency_manager

logger = logging.getLogger(__name__)


@activity.defn(name="extract_actions")
async def extract_actions_activity(input: ExtractActionsInput) -> ExtractActionsResult:
	"""
	Extract action definitions from ingested content.
	
	This activity:
	1. Loads content chunks from ingestion results
	2. Extracts action definitions with preconditions, postconditions
	3. Persists actions to MongoDB
	4. Returns action IDs for graph construction
	"""
	workflow_id = activity.info().workflow_id
	_idempotency_manager = get_idempotency_manager()

	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "extract_actions", input
		)
		if cached:
			return ExtractActionsResult(**cached)

	activity.heartbeat({"status": "extracting", "ingestion_id": input.ingestion_id})

	try:
		from navigator.knowledge.extract import ActionExtractor
		from navigator.knowledge.persist.documents import save_actions
		from navigator.knowledge.persist.ingestion import get_ingestion_chunks

		# Determine which ingestion IDs to load from
		ingestion_ids_to_load = input.ingestion_ids if input.ingestion_ids else [input.ingestion_id]

		logger.info(f"📥 Loading chunks from {len(ingestion_ids_to_load)} ingestion(s) for action extraction")

		# Load chunks from all ingestion results
		all_chunks = []
		for ingestion_id in ingestion_ids_to_load:
			chunks = await get_ingestion_chunks(ingestion_id)
			if chunks:
				all_chunks.extend(chunks)
				logger.info(f"✅ Loaded {len(chunks)} chunks from ingestion: {ingestion_id}")
			else:
				logger.warning(f"⚠️ No chunks found for ingestion: {ingestion_id}")

		if not all_chunks:
			error_msg = (
				f"❌ CRITICAL: No content chunks found for any ingestion: {ingestion_ids_to_load}. "
				f"Action extraction cannot proceed without source content."
			)
			logger.error(error_msg)
			raise ValueError(error_msg)

		# Extract actions from chunks
		# website_id is required for ActionExtractor, use input value or default
		website_id = input.website_id or "unknown"
		action_extractor = ActionExtractor(website_id=website_id)
		extraction_result = action_extractor.extract_actions(all_chunks)

		# Persist actions
		if extraction_result.actions:
			await save_actions(extraction_result.actions, knowledge_id=input.knowledge_id, job_id=input.job_id)
			logger.info(f"💾 Saved {len(extraction_result.actions)} action(s) to MongoDB with knowledge_id={input.knowledge_id}, job_id={input.job_id}")

		# Convert to ExtractActionsResult (dataclass) for return
		# Extract action IDs from ActionDefinition objects
		action_ids = [action.action_id for action in extraction_result.actions]
		actions_result = ExtractActionsResult(
			actions_extracted=len(extraction_result.actions),
			action_ids=action_ids,
			errors=[err.get('message', str(err)) for err in extraction_result.errors] if extraction_result.errors else [],
			success=extraction_result.success,
		)

		# Record execution (serialization helper will handle Pydantic models in extraction_result)
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"extract_actions",
				input,
				actions_result.__dict__,  # Now this is a dataclass dict, safe for MongoDB
				success=True,
			)

		return actions_result

	except Exception as e:
		logger.error(f"❌ Action extraction failed: {e}", exc_info=True)

		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"extract_actions",
				input,
				{},
				success=False,
				error=str(e),
			)

		raise

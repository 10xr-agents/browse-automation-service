"""
Extract transitions activity for knowledge extraction workflow.

Extracts transition definitions from ingested content.
"""

import logging

from temporalio import activity

from navigator.schemas import ExtractTransitionsInput, ExtractTransitionsResult
from navigator.temporal.activities.shared import get_idempotency_manager

logger = logging.getLogger(__name__)


@activity.defn(name="extract_transitions")
async def extract_transitions_activity(input: ExtractTransitionsInput) -> ExtractTransitionsResult:
	"""
	Extract transition definitions from ingested content.
	
	This activity:
	1. Loads content chunks from ingestion results
	2. Extracts screen transitions with triggers, conditions, effects
	3. Persists transitions to MongoDB
	4. Returns transition IDs for graph construction
	"""
	workflow_id = activity.info().workflow_id
	_idempotency_manager = get_idempotency_manager()

	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "extract_transitions", input
		)
		if cached:
			return ExtractTransitionsResult(**cached)

	activity.heartbeat({"status": "extracting", "ingestion_id": input.ingestion_id})

	try:
		from navigator.knowledge.extract import TransitionExtractor
		from navigator.knowledge.persist.documents import save_transitions
		from navigator.knowledge.persist.ingestion import get_ingestion_chunks

		# Determine which ingestion IDs to load from
		ingestion_ids_to_load = input.ingestion_ids if input.ingestion_ids else [input.ingestion_id]

		logger.info(f"📥 Loading chunks from {len(ingestion_ids_to_load)} ingestion(s) for transition extraction")

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
				f"Transition extraction cannot proceed without source content."
			)
			logger.error(error_msg)
			raise ValueError(error_msg)

		# Extract transitions from chunks
		# website_id is required for TransitionExtractor, use input value or default
		website_id = input.website_id or "unknown"
		transition_extractor = TransitionExtractor(website_id=website_id)
		transitions_result = transition_extractor.extract_transitions(all_chunks)

		# Persist transitions
		transition_ids = []
		if transitions_result.transitions:
			await save_transitions(transitions_result.transitions, knowledge_id=input.knowledge_id, job_id=input.job_id)
			transition_ids = [t.transition_id for t in transitions_result.transitions]
			logger.info(f"💾 Saved {len(transitions_result.transitions)} transition(s) to MongoDB with knowledge_id={input.knowledge_id}, job_id={input.job_id}")

		# Convert TransitionExtractionResult (Pydantic) to ExtractTransitionsResult (dataclass)
		# ExtractTransitionsResult is required for Temporal workflow decoding
		extract_result = ExtractTransitionsResult(
			transitions_extracted=len(transitions_result.transitions),
			transition_ids=transition_ids,
			errors=[str(e) for e in transitions_result.errors] if transitions_result.errors else [],
			success=transitions_result.success,
		)

		# Record execution
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"extract_transitions",
				input,
				extract_result.__dict__,
				success=True,
			)

		return extract_result

	except Exception as e:
		logger.error(f"❌ Transition extraction failed: {e}", exc_info=True)

		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"extract_transitions",
				input,
				{},
				success=False,
				error=str(e),
			)

		raise

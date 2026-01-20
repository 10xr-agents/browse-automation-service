"""
Extract business functions activity for knowledge extraction workflow.

Extracts business functions from ingested content (video, documentation, website).
"""

import logging

from temporalio import activity

from navigator.schemas import ExtractBusinessFunctionsInput, ExtractBusinessFunctionsResult
from navigator.temporal.activities.shared import get_idempotency_manager

logger = logging.getLogger(__name__)


@activity.defn(name="extract_business_functions")
async def extract_business_functions_activity(
	input: ExtractBusinessFunctionsInput,
) -> ExtractBusinessFunctionsResult:
	"""
	Extract business functions from ingested content (video, documentation, website).
	
	This activity:
	1. Loads content chunks from all ingestion results
	2. Extracts business functions using LLM analysis
	3. Persists business functions (if persistence is implemented)
	4. Returns business function IDs
	
	Supports:
	- Video content (transcription, frame analysis, action sequences)
	- Documentation (markdown, PDF, DOCX, HTML, text)
	- Website content (crawled pages, exploration results)
	"""
	workflow_id = activity.info().workflow_id
	_idempotency_manager = get_idempotency_manager()

	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "extract_business_functions", input
		)
		if cached:
			return ExtractBusinessFunctionsResult(**cached)

	activity.heartbeat({"status": "extracting", "ingestion_id": input.ingestion_id})

	try:
		from navigator.knowledge.extract import BusinessFunctionExtractor
		from navigator.knowledge.persist.ingestion import get_ingestion_chunks

		# Determine which ingestion IDs to load from
		ingestion_ids_to_load = input.ingestion_ids if input.ingestion_ids else [input.ingestion_id]

		logger.info(
			f"📥 Loading chunks from {len(ingestion_ids_to_load)} ingestion(s) "
			f"for business function extraction"
		)

		# Load chunks from all ingestion results (supports mixed asset types)
		all_chunks = []
		for ingestion_id in ingestion_ids_to_load:
			chunks = await get_ingestion_chunks(ingestion_id)
			if chunks:
				all_chunks.extend(chunks)
				logger.info(f"✅ Loaded {len(chunks)} chunks from ingestion: {ingestion_id}")
			else:
				logger.warning(f"⚠️ No chunks found for ingestion: {ingestion_id}")

		if not all_chunks:
			logger.warning(
				"⚠️ No content chunks found for business function extraction. "
				"Returning empty result."
			)
			return ExtractBusinessFunctionsResult(
				business_functions_extracted=0,
				business_function_ids=[],
				success=True,
			)

		# Extract business functions from all chunks (supports video, docs, website)
		# website_id is required for BusinessFunctionExtractor, use input value or default
		website_id = input.website_id or "unknown"
		business_function_extractor = BusinessFunctionExtractor(website_id=website_id)
		bf_result = business_function_extractor.extract_business_functions(all_chunks)

		# Extract business function IDs
		business_function_ids = [
			bf.business_function_id for bf in bf_result.business_functions
		]

		# Persist business functions to MongoDB
		if bf_result.business_functions:
			from navigator.knowledge.persist.documents import save_business_functions

			persist_result = await save_business_functions(
				bf_result.business_functions,
				knowledge_id=input.knowledge_id,
				job_id=input.job_id
			)

			logger.info(
				f"✅ Extracted {len(bf_result.business_functions)} business function(s): "
				f"{', '.join([bf.name for bf in bf_result.business_functions[:5]])}"
				f"{'...' if len(bf_result.business_functions) > 5 else ''}"
			)
			logger.info(
				f"💾 Persisted {persist_result['saved']}/{persist_result['total']} "
				f"business function(s) to MongoDB"
			)

		result = ExtractBusinessFunctionsResult(
			business_functions_extracted=len(bf_result.business_functions),
			business_function_ids=business_function_ids,
			success=True,
		)

		# Record execution
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"extract_business_functions",
				input,
				result.__dict__,
				success=True,
			)

		return result

	except Exception as e:
		logger.error(f"❌ Business function extraction failed: {e}", exc_info=True)

		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"extract_business_functions",
				input,
				{},
				success=False,
				error=str(e),
			)

		raise

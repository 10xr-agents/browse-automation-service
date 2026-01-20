"""
Extract workflows activity for knowledge extraction workflow.

Extracts operational workflows from ingested content (video, documentation, website).
"""

import logging

from temporalio import activity

from navigator.schemas import ExtractWorkflowsInput, ExtractWorkflowsResult
from navigator.temporal.activities.shared import get_idempotency_manager

logger = logging.getLogger(__name__)


@activity.defn(name="extract_workflows")
async def extract_workflows_activity(
	input: ExtractWorkflowsInput,
) -> ExtractWorkflowsResult:
	"""
	Extract operational workflows from ingested content (video, documentation, website).
	
	This activity:
	1. Loads content chunks from all ingestion results
	2. Extracts operational workflows using LLM analysis
	3. Persists workflows (if persistence is implemented)
	4. Returns workflow IDs
	
	Supports:
	- Video content (transcription, frame analysis, action sequences)
	- Documentation (markdown, PDF, DOCX, HTML, text)
	- Website content (crawled pages, exploration results)
	"""
	workflow_id = activity.info().workflow_id
	_idempotency_manager = get_idempotency_manager()

	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "extract_workflows", input
		)
		if cached:
			return ExtractWorkflowsResult(**cached)

	activity.heartbeat({"status": "extracting", "ingestion_id": input.ingestion_id})

	try:
		from navigator.knowledge.extract import WorkflowExtractor
		from navigator.knowledge.persist.ingestion import get_ingestion_chunks

		# Determine which ingestion IDs to load from
		ingestion_ids_to_load = input.ingestion_ids if input.ingestion_ids else [input.ingestion_id]

		logger.info(
			f"📥 Loading chunks from {len(ingestion_ids_to_load)} ingestion(s) "
			f"for workflow extraction"
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
				"⚠️ No content chunks found for workflow extraction. "
				"Returning empty result."
			)
			return ExtractWorkflowsResult(
				workflows_extracted=0,
				workflow_ids=[],
				success=True,
			)

		# Extract workflows from all chunks (supports video, docs, website)
		# website_id is required for WorkflowExtractor, use input value or default
		website_id = input.website_id or "unknown"
		workflow_extractor = WorkflowExtractor(website_id=website_id)
		wf_result = workflow_extractor.extract_workflows(
			all_chunks,
			business_function=input.business_function,
		)

		# Extract workflow IDs
		workflow_ids = [wf.workflow_id for wf in wf_result.workflows]

		# Persist workflows to MongoDB
		if wf_result.workflows:
			from navigator.knowledge.persist.documents import save_workflows

			persist_result = await save_workflows(
				wf_result.workflows,
				knowledge_id=input.knowledge_id,
				job_id=input.job_id
			)

			logger.info(
				f"✅ Extracted {len(wf_result.workflows)} operational workflow(s): "
				f"{', '.join([wf.name for wf in wf_result.workflows[:5]])}"
				f"{'...' if len(wf_result.workflows) > 5 else ''}"
			)
			logger.info(
				f"💾 Persisted {persist_result['saved']}/{persist_result['total']} "
				f"workflow(s) to MongoDB"
			)

		result = ExtractWorkflowsResult(
			workflows_extracted=len(wf_result.workflows),
			workflow_ids=workflow_ids,
			success=True,
		)

		# Record execution
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"extract_workflows",
				input,
				result.__dict__,
				success=True,
			)

		return result

	except Exception as e:
		logger.error(f"❌ Workflow extraction failed: {e}", exc_info=True)

		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"extract_workflows",
				input,
				{},
				success=False,
				error=str(e),
			)

		raise

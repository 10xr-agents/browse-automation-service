"""
Extract tasks activity for knowledge extraction workflow.

Extracts task definitions from ingested content.
"""

import logging

from temporalio import activity

from navigator.schemas import ExtractTasksInput, ExtractTasksResult
from navigator.temporal.activities.shared import get_idempotency_manager

logger = logging.getLogger(__name__)


@activity.defn(name="extract_tasks")
async def extract_tasks_activity(input: ExtractTasksInput) -> ExtractTasksResult:
	"""
	Extract task definitions from ingested content.
	
	This activity:
	1. Loads content chunks from ingestion results
	2. Extracts task definitions with steps, IO specs, iterator specs
	3. Persists tasks to MongoDB
	4. Returns task IDs for graph construction
	"""
	workflow_id = activity.info().workflow_id
	_idempotency_manager = get_idempotency_manager()

	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "extract_tasks", input
		)
		if cached:
			return ExtractTasksResult(**cached)

	activity.heartbeat({"status": "extracting", "ingestion_id": input.ingestion_id})

	try:
		from navigator.knowledge.extract import TaskExtractor
		from navigator.knowledge.persist.documents import save_tasks
		from navigator.knowledge.persist.ingestion import get_ingestion_chunks

		# Determine which ingestion IDs to load from
		ingestion_ids_to_load = input.ingestion_ids if input.ingestion_ids else [input.ingestion_id]

		logger.info(f"📥 Loading chunks from {len(ingestion_ids_to_load)} ingestion(s) for task extraction")

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
				f"Task extraction cannot proceed without source content."
			)
			logger.error(error_msg)
			raise ValueError(error_msg)

		# Extract tasks from chunks
		# website_id is required for TaskExtractor, use input value or default
		website_id = input.website_id or "unknown"
		task_extractor = TaskExtractor(website_id=website_id)
		tasks_result = task_extractor.extract_tasks(all_chunks)

		# Persist tasks
		if tasks_result.tasks:
			await save_tasks(tasks_result.tasks, knowledge_id=input.knowledge_id, job_id=input.job_id)
			logger.info(f"💾 Saved {len(tasks_result.tasks)} task(s) to MongoDB with knowledge_id={input.knowledge_id}, job_id={input.job_id}")

		# Convert TaskExtractionResult (Pydantic) to ExtractTasksResult (dataclass) for Temporal
		extract_result = ExtractTasksResult(
			tasks_extracted=len(tasks_result.tasks),
			task_ids=[t.task_id for t in tasks_result.tasks],
			errors=[str(err.get("message", err)) for err in tasks_result.errors] if tasks_result.errors else [],
			success=tasks_result.success,
		)

		# Record execution
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"extract_tasks",
				input,
				{
					"tasks_extracted": extract_result.tasks_extracted,
					"task_ids": extract_result.task_ids,
					"errors": extract_result.errors,
					"success": extract_result.success,
				},
				success=True,
			)

		return extract_result

	except Exception as e:
		logger.error(f"❌ Task extraction failed: {e}", exc_info=True)

		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"extract_tasks",
				input,
				{},
				success=False,
				error=str(e),
			)

		raise

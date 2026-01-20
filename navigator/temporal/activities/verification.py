"""
Verification, enrichment, and deletion activities for knowledge extraction workflow.

Includes:
- verify_extraction_activity: Verify extracted knowledge
- enrich_knowledge_activity: Enrich knowledge based on verification
- delete_knowledge_activity: Delete existing knowledge by knowledge_id
"""

import logging

from temporalio import activity

from navigator.schemas import (
	DeleteKnowledgeInput,
	DeleteKnowledgeResult,
	EnrichKnowledgeInput,
	EnrichKnowledgeResult,
	VerifyExtractionInput,
	VerifyExtractionResult,
)
from navigator.temporal.activities.shared import get_idempotency_manager

logger = logging.getLogger(__name__)


@activity.defn(name="verify_extraction")
async def verify_extraction_activity(input: VerifyExtractionInput) -> VerifyExtractionResult:
	"""
	Verify extracted knowledge by checking screens and tasks.
	
	This activity:
	1. Loads screen and task definitions
	2. Validates they are queryable
	3. Checks for basic consistency
	4. Returns verification results
	"""
	workflow_id = activity.info().workflow_id
	_idempotency_manager = get_idempotency_manager()

	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "verify_extraction", input
		)
		if cached:
			return VerifyExtractionResult(**cached)

	activity.heartbeat({"status": "verifying", "job_id": input.job_id})

	try:
		from navigator.knowledge.persist.documents import get_screen, get_task

		screens_verified = 0
		discrepancies = []

		# Verify screens are queryable
		for screen_id in input.screen_ids:
			screen = await get_screen(screen_id)
			if screen:
				screens_verified += 1
			else:
				discrepancies.append(f"Screen {screen_id} not found in database")

		# Verify tasks are queryable
		for task_id in input.task_ids:
			task = await get_task(task_id)
			if not task:
				discrepancies.append(f"Task {task_id} not found in database")

		result = VerifyExtractionResult(
			screens_verified=screens_verified,
			discrepancies_found=len(discrepancies),
			discrepancy_ids=[],
			success=True,
		)

		# Record execution
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"verify_extraction",
				input,
				result.__dict__,
				success=True,
			)

		return result

	except Exception as e:
		logger.error(f"❌ Verification failed: {e}", exc_info=True)

		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"verify_extraction",
				input,
				{},
				success=False,
				error=str(e),
			)

		raise


@activity.defn(name="enrich_knowledge")
async def enrich_knowledge_activity(input: EnrichKnowledgeInput) -> EnrichKnowledgeResult:
	"""
	Enrich knowledge based on verification discrepancies.
	
	This activity:
	1. Loads discrepancies from verification
	2. Applies enrichments to knowledge entities
	3. Updates MongoDB with enriched data
	4. Returns enrichment statistics
	"""
	workflow_id = activity.info().workflow_id
	_idempotency_manager = get_idempotency_manager()

	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "enrich_knowledge", input
		)
		if cached:
			return EnrichKnowledgeResult(**cached)

	activity.heartbeat({"status": "enriching", "job_id": input.job_id})

	try:
		# For now, enrichment is a placeholder
		# In the future, this would:
		# 1. Load discrepancies
		# 2. Update screens/tasks/actions with corrections
		# 3. Persist enriched entities

		result = EnrichKnowledgeResult(
			enrichments_applied=0,
			updated_screen_ids=[],
			updated_task_ids=[],
			success=True,
		)

		# Record execution
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"enrich_knowledge",
				input,
				result.__dict__,
				success=True,
			)

		return result

	except Exception as e:
		logger.error(f"❌ Enrichment failed: {e}", exc_info=True)

		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"enrich_knowledge",
				input,
				{},
				success=False,
				error=str(e),
			)

		raise


@activity.defn(name="delete_knowledge")
async def delete_knowledge_activity(input: DeleteKnowledgeInput) -> DeleteKnowledgeResult:
	"""
	Delete existing knowledge by knowledge_id.
	
	This activity deletes all knowledge entities (screens, tasks, actions, transitions,
	business functions, workflows) associated with a given knowledge_id.
	
	Used for resyncing/re-extracting knowledge - deletes old knowledge before
	extracting new knowledge with the same knowledge_id.
	"""
	workflow_id = activity.info().workflow_id
	_idempotency_manager = get_idempotency_manager()

	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "delete_knowledge", input
		)
		if cached:
			return DeleteKnowledgeResult(**cached)

	activity.heartbeat({"status": "deleting", "knowledge_id": input.knowledge_id})

	try:
		from navigator.knowledge.persist.documents import delete_knowledge_by_knowledge_id

		deletion_counts = await delete_knowledge_by_knowledge_id(input.knowledge_id)
		total_deleted = sum(deletion_counts.values())

		result = DeleteKnowledgeResult(
			deletion_counts=deletion_counts,
			total_deleted=total_deleted,
			success=True,
		)

		# Record execution
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"delete_knowledge",
				input,
				result.__dict__,
				success=True,
			)

		return result

	except Exception as e:
		logger.error(f"❌ Delete knowledge failed: {e}", exc_info=True)

		result = DeleteKnowledgeResult(
			deletion_counts={},
			total_deleted=0,
			success=False,
			errors=[str(e)],
		)

		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"delete_knowledge",
				input,
				result.__dict__,
				success=False,
				error=str(e),
			)

		return result

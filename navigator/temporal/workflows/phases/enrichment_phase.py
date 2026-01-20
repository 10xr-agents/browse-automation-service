"""
Phase 5: Enrichment

Enriches knowledge based on verification results, updating definitions
based on discrepancies found during verification.
"""

from temporalio import workflow

# Import activities and schemas - wrap ALL imports
with workflow.unsafe.imports_passed_through():
	from navigator.schemas import (
		EnrichKnowledgeInput,
		EnrichKnowledgeResult,
		KnowledgeExtractionProgressV2,
		KnowledgeExtractionResultV2,
		VerifyExtractionResult,
		WorkflowPhase,
	)
	from navigator.temporal.activities import enrich_knowledge_activity


async def execute_enrichment_phase(
	result: KnowledgeExtractionResultV2,
	progress: KnowledgeExtractionProgressV2,
	verify_result: VerifyExtractionResult,
	input_job_id: str,
	activity_options: dict,
	check_pause_or_cancel,
) -> None:
	"""
	Execute Phase 5: Enrichment.
	
	Enriches knowledge based on verification discrepancies.
	
	Args:
		result: Workflow result object to update
		progress: Progress tracking object
		verify_result: Verification results with discrepancy IDs
		input_job_id: Job ID
		activity_options: Activity execution options
		check_pause_or_cancel: Function to check for pause/cancel
	"""
	progress.phase = WorkflowPhase.ENRICHMENT
	progress.current_activity = "enrich_knowledge"
	await check_pause_or_cancel()

	workflow.logger.info("✨ Phase 5: Enriching knowledge...")

	enrich_result: EnrichKnowledgeResult = await workflow.execute_activity(
		enrich_knowledge_activity,
		EnrichKnowledgeInput(
			job_id=input_job_id,
			discrepancy_ids=verify_result.discrepancy_ids,
		),
		**activity_options,
	)

	result.enrichments_applied = enrich_result.enrichments_applied

	workflow.logger.info(
		f"✅ Enrichment completed: "
		f"{result.enrichments_applied} enrichments applied"
	)

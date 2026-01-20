"""
Phase 4: Verification

Verifies extracted knowledge by checking screens and tasks against the actual website.
"""

from temporalio import workflow

# Import activities and schemas - wrap ALL imports
with workflow.unsafe.imports_passed_through():
	from navigator.schemas import (
		ExtractScreensResult,
		ExtractTasksResult,
		KnowledgeExtractionProgressV2,
		KnowledgeExtractionResultV2,
		VerifyExtractionInput,
		VerifyExtractionResult,
		WorkflowPhase,
	)
	from navigator.temporal.activities import verify_extraction_activity


async def execute_verification_phase(
	result: KnowledgeExtractionResultV2,
	progress: KnowledgeExtractionProgressV2,
	screens_result: ExtractScreensResult,
	tasks_result: ExtractTasksResult,
	input_job_id: str,
	activity_options: dict,
	check_pause_or_cancel,
) -> VerifyExtractionResult:
	"""
	Execute Phase 4: Verification.
	
	Verifies extracted knowledge by checking screens and tasks.
	
	Args:
		result: Workflow result object to update
		progress: Progress tracking object
		screens_result: Screen extraction results
		tasks_result: Task extraction results
		input_job_id: Job ID
		activity_options: Activity execution options
		check_pause_or_cancel: Function to check for pause/cancel
	
	Returns:
		Verification result with discrepancy IDs
	"""
	progress.phase = WorkflowPhase.VERIFICATION
	progress.current_activity = "verify_extraction"
	await check_pause_or_cancel()

	workflow.logger.info("🔬 Phase 4: Verifying extraction...")

	verify_result: VerifyExtractionResult = await workflow.execute_activity(
		verify_extraction_activity,
		VerifyExtractionInput(
			job_id=input_job_id,
			screen_ids=screens_result.screen_ids,
			task_ids=tasks_result.task_ids,
		),
		**activity_options,
	)

	result.screens_verified = verify_result.screens_verified
	result.discrepancies_found = verify_result.discrepancies_found

	workflow.logger.info(
		f"✅ Verification completed: "
		f"{result.screens_verified} screens verified, "
		f"{result.discrepancies_found} discrepancies found"
	)

	return verify_result

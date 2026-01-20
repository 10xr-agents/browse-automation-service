"""
Knowledge Verification Workflow

Phase 7: Browser-Based Verification & Enrichment

Temporal workflow for verifying extracted knowledge by replaying actions
in a real browser and detecting discrepancies.
"""

import logging
from datetime import timedelta

from temporalio import workflow

logger = logging.getLogger(__name__)

# Import activity functions
with workflow.unsafe.imports_passed_through():
	from navigator.schemas.verification import (
		VerificationWorkflowInput,
		VerificationWorkflowOutput,
	)


@workflow.defn
class KnowledgeVerificationWorkflow:
	"""
	Workflow for verifying extracted knowledge.
	
	Phases:
	1. Load knowledge definitions
	2. Launch browser session
	3. Navigate to target screen
	4. Replay actions
	5. Detect discrepancies
	6. Apply enrichments (if enabled)
	7. Generate report
	8. Cleanup
	"""

	@workflow.run
	async def run(self, input: VerificationWorkflowInput) -> VerificationWorkflowOutput:
		"""
		Run verification workflow.
		
		Args:
			input: Verification workflow input
		
		Returns:
			Verification workflow output with results
		"""
		workflow_logger = workflow.logger
		workflow_logger.info(
			f"Starting verification workflow: job_id={input.verification_job_id}, "
			f"target={input.target_type}:{input.target_id}"
		)

		try:
			# Phase 1: Load knowledge definitions
			workflow_logger.info("Phase 1: Loading knowledge definitions")
			definitions = await workflow.execute_activity(
				"load_knowledge_definitions_activity",
				input,
				start_to_close_timeout=timedelta(seconds=30),
				retry_policy={
					'maximum_attempts': 3,
					'initial_interval': timedelta(seconds=1),
				},
			)

			if not definitions.get('screens'):
				workflow_logger.warning("No screens found to verify")
				return VerificationWorkflowOutput(
					verification_job_id=input.verification_job_id,
					success=True,
					screens_verified=0,
					actions_replayed=0,
					discrepancies_found=0,
					changes_made=0,
					duration_seconds=0.0,
					report_id="",
				)

			# Phase 2: Launch browser session
			workflow_logger.info("Phase 2: Launching browser session")
			browser_session = await workflow.execute_activity(
				"launch_browser_session_activity",
				input,
				start_to_close_timeout=timedelta(seconds=60),
				retry_policy={
					'maximum_attempts': 2,
					'initial_interval': timedelta(seconds=5),
				},
			)

			# Phase 3-5: Verify screens and replay actions
			workflow_logger.info(f"Phase 3-5: Verifying {len(definitions['screens'])} screens")
			verification_results = await workflow.execute_activity(
				"verify_screens_activity",
				{
					'browser_session': browser_session,
					'definitions': definitions,
					'verification_job_id': input.verification_job_id,
					'options': input.verification_options,
				},
				start_to_close_timeout=timedelta(minutes=30),
				heartbeat_timeout=timedelta(seconds=30),
				retry_policy={
					'maximum_attempts': 1,  # Don't retry verification
				},
			)

			# Phase 6: Apply enrichments (if enabled and discrepancies found)
			changes_made = 0
			if verification_results.get('discrepancies') and input.verification_options.get('enable_enrichment', False):
				workflow_logger.info("Phase 6: Applying knowledge enrichments")
				enrichment_results = await workflow.execute_activity(
					"apply_enrichments_activity",
					{
						'discrepancies': verification_results['discrepancies'],
						'verification_job_id': input.verification_job_id,
					},
					start_to_close_timeout=timedelta(minutes=10),
					retry_policy={
						'maximum_attempts': 3,
					},
				)
				changes_made = enrichment_results.get('changes_made', 0)

			# Phase 7: Generate verification report
			workflow_logger.info("Phase 7: Generating verification report")
			report = await workflow.execute_activity(
				"generate_verification_report_activity",
				{
					'verification_job_id': input.verification_job_id,
					'verification_results': verification_results,
					'changes_made': changes_made,
					'input': input,
				},
				start_to_close_timeout=timedelta(seconds=60),
			)

			# Phase 8: Cleanup browser session
			workflow_logger.info("Phase 8: Cleaning up browser session")
			await workflow.execute_activity(
				"cleanup_browser_session_activity",
				browser_session,
				start_to_close_timeout=timedelta(seconds=30),
			)

			workflow_logger.info(
				f"Verification complete: screens={verification_results['screens_verified']}, "
				f"actions={verification_results['actions_replayed']}, "
				f"discrepancies={verification_results['discrepancies_found']}, "
				f"changes={changes_made}"
			)

			return VerificationWorkflowOutput(
				verification_job_id=input.verification_job_id,
				success=True,
				screens_verified=verification_results['screens_verified'],
				actions_replayed=verification_results['actions_replayed'],
				discrepancies_found=verification_results['discrepancies_found'],
				changes_made=changes_made,
				duration_seconds=report.get('duration_seconds', 0.0),
				report_id=report.get('report_id', ''),
			)

		except Exception as e:
			workflow_logger.error(f"Verification workflow failed: {e}", exc_info=True)

			# Try to cleanup browser if it was launched
			try:
				if 'browser_session' in locals():
					await workflow.execute_activity(
						"cleanup_browser_session_activity",
						browser_session,
						start_to_close_timeout=timedelta(seconds=10),
					)
			except:
				pass  # Best effort cleanup

			raise

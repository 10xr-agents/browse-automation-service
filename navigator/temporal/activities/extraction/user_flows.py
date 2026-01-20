"""
Extract user flows activity for knowledge extraction workflow.

Phase 4: User Flow Extraction & Synthesis.

Synthesizes user flows from screens, workflows, business functions, and transitions
to create complete navigation flows that show how users accomplish goals.
"""

import logging
import time

from temporalio import activity

from navigator.schemas import ExtractUserFlowsInput, ExtractUserFlowsResult
from navigator.temporal.activities.shared import get_idempotency_manager

logger = logging.getLogger(__name__)


@activity.defn(name="extract_user_flows")
async def extract_user_flows_activity(
	input: ExtractUserFlowsInput
) -> ExtractUserFlowsResult:
	"""
	Extract and synthesize user flows from all knowledge entities.
	
	This activity:
	1. Loads screens, workflows, business functions, and transitions from MongoDB
	2. Uses UserFlowExtractor to synthesize user flows
	3. Persists user flows to MongoDB with cross-references
	4. Updates cross-references in related entities
	
	Args:
		input: Extraction parameters
	
	Returns:
		Extraction result with user flow IDs
	"""
	start_time = time.time()
	workflow_id = activity.info().workflow_id
	activity_id = activity.info().activity_id
	_idempotency_manager = get_idempotency_manager()

	logger.info(f"{'='*80}")
	logger.info("🔵 ACTIVITY START: extract_user_flows (Phase 4)")
	logger.info(f"   Workflow ID: {workflow_id}")
	logger.info(f"   Activity ID: {activity_id}")
	logger.info(f"   Knowledge ID: {input.knowledge_id}")
	logger.info(f"   Website ID: {input.website_id}")
	logger.info(f"{'='*80}")

	# Check idempotency
	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "extract_user_flows", input
		)
		if cached:
			logger.info("♻️  Using cached result from previous execution")
			return ExtractUserFlowsResult(**cached)

	try:
		from navigator.knowledge.extract.user_flows import UserFlowExtractor
		from navigator.knowledge.persist.documents import (
			query_actions_by_knowledge_id,
			query_business_functions_by_knowledge_id,
			query_screens_by_knowledge_id,
			query_tasks_by_knowledge_id,
			query_transitions_by_knowledge_id,
			query_workflows_by_knowledge_id,
			save_user_flows,
		)

		# Load all knowledge entities for this knowledge_id
		logger.info(f"📥 Loading knowledge entities for knowledge_id={input.knowledge_id}")

		screens = await query_screens_by_knowledge_id(input.knowledge_id)
		workflows = await query_workflows_by_knowledge_id(input.knowledge_id)
		business_functions = await query_business_functions_by_knowledge_id(input.knowledge_id)
		transitions = await query_transitions_by_knowledge_id(input.knowledge_id)
		tasks = await query_tasks_by_knowledge_id(input.knowledge_id)
		actions = await query_actions_by_knowledge_id(input.knowledge_id)

		logger.info(
			f"✅ Loaded knowledge entities: "
			f"{len(screens)} screens, {len(workflows)} workflows, "
			f"{len(business_functions)} business functions, "
			f"{len(transitions)} transitions, {len(tasks)} tasks, "
			f"{len(actions)} actions"
		)

		if not screens and not workflows:
			logger.warning("⚠️ No screens or workflows found, cannot extract user flows")
			return ExtractUserFlowsResult(
				user_flows_extracted=0,
				user_flow_ids=[],
				errors=["No screens or workflows found for user flow extraction"],
				success=False
			)

		# Extract user flows using UserFlowExtractor
		website_id = input.website_id or "unknown"
		user_flow_extractor = UserFlowExtractor(website_id=website_id)

		# Convert to Any type for extractor (it expects Any for flexibility)
		user_flows_result = await user_flow_extractor.extract_user_flows(
			screens=screens,
			workflows=workflows,
			business_functions=business_functions,
			transitions=transitions
		)

		# Persist user flows to MongoDB
		user_flow_ids = []
		if user_flows_result.user_flows:
			persist_result = await save_user_flows(
				user_flows_result.user_flows,
				knowledge_id=input.knowledge_id,
				job_id=input.job_id
			)

			user_flow_ids = [flow.user_flow_id for flow in user_flows_result.user_flows]

			logger.info(
				f"✅ Extracted {len(user_flows_result.user_flows)} user flow(s): "
				f"{', '.join([flow.name for flow in user_flows_result.user_flows[:5]])}"
				f"{'...' if len(user_flows_result.user_flows) > 5 else ''}"
			)
			logger.info(
				f"💾 Persisted {persist_result['saved']}/{persist_result['total']} "
				f"user flow(s) to MongoDB"
			)

		# Build result
		result = ExtractUserFlowsResult(
			user_flows_extracted=len(user_flows_result.user_flows),
			user_flow_ids=user_flow_ids,
			errors=user_flows_result.errors if hasattr(user_flows_result, 'errors') else [],
			success=user_flows_result.success if hasattr(user_flows_result, 'success') else True,
		)

		# Record execution
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"extract_user_flows",
				input,
				result.__dict__,
				success=True,
			)

		duration = time.time() - start_time
		logger.info(f"✅ User flow extraction completed in {duration:.2f}s")

		return result

	except Exception as e:
		logger.error(f"❌ User flow extraction failed: {e}", exc_info=True)

		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"extract_user_flows",
				input,
				{},
				success=False,
				error=str(e),
			)

		raise

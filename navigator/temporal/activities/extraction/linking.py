"""
Post-extraction entity linking activity.

Links entities together after extraction phase completes.
Priority 2: Implement Post-Extraction Entity Linking Phase
"""

import logging

from temporalio import activity

from navigator.knowledge.persist.post_extraction_linking import PostExtractionLinker
from navigator.schemas.temporal import LinkEntitiesInput, LinkEntitiesResult
from navigator.temporal.activities.shared import get_idempotency_manager

logger = logging.getLogger(__name__)


@activity.defn(name="link_entities")
async def link_entities_activity(input: LinkEntitiesInput) -> LinkEntitiesResult:
	"""
	Link entities together after extraction phase completes.
	
	This activity:
	1. Loads all extracted entities (screens, tasks, actions, transitions, workflows, business functions)
	2. Links tasks to screens by matching page_url → screen URL patterns
	3. Links actions to screens by context (video actions → video screens, navigation → URL patterns)
	4. Links business functions to screens by screens_mentioned with fuzzy matching
	5. Links workflows to entities by parsing workflow steps
	6. Links transitions to screens and actions
	
	Args:
		input: LinkEntitiesInput with knowledge_id and optional job_id
	
	Returns:
		LinkEntitiesResult with linking statistics
	"""
	workflow_id = activity.info().workflow_id
	_idempotency_manager = get_idempotency_manager()

	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "link_entities", input
		)
		if cached:
			logger.info("♻️  Using cached result from previous execution")
			return LinkEntitiesResult(**cached)

	activity.heartbeat({"status": "linking", "knowledge_id": input.knowledge_id})

	try:
		logger.info(
			f"🔗 Starting entity linking for knowledge_id={input.knowledge_id}, "
			f"job_id={input.job_id}"
		)

		# Create linker and link all entities
		linker = PostExtractionLinker(
			knowledge_id=input.knowledge_id,
			job_id=input.job_id
		)
		
		stats = await linker.link_all_entities()

		result = LinkEntitiesResult(
			tasks_linked=stats['tasks_linked'],
			actions_linked=stats['actions_linked'],
			business_functions_linked=stats['business_functions_linked'],
			workflows_linked=stats['workflows_linked'],
			transitions_linked=stats['transitions_linked'],
			errors=stats['errors'],
			success=len(stats['errors']) == 0
		)

		logger.info(
			f"✅ Entity linking complete: "
			f"{result.tasks_linked} tasks, {result.actions_linked} actions, "
			f"{result.business_functions_linked} business functions, "
			f"{result.workflows_linked} workflows, {result.transitions_linked} transitions linked"
		)

		# Record execution for idempotency
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"link_entities",
				input,
				result.__dict__,
				success=True,
			)

		return result

	except Exception as e:
		logger.error(f"Failed to link entities: {e}", exc_info=True)
		return LinkEntitiesResult(
			tasks_linked=0,
			actions_linked=0,
			business_functions_linked=0,
			workflows_linked=0,
			transitions_linked=0,
			errors=[str(e)],
			success=False
		)

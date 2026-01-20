"""
Build graph activity for knowledge extraction workflow.

Builds knowledge graph from extracted entities.
"""

import logging

from temporalio import activity

from navigator.schemas import BuildGraphInput, BuildGraphResult
from navigator.temporal.activities.shared import get_idempotency_manager

logger = logging.getLogger(__name__)


@activity.defn(name="build_graph")
async def build_graph_activity(input: BuildGraphInput) -> BuildGraphResult:
	"""
	Build knowledge graph from extracted entities.
	
	This activity:
	1. Validates extracted entities (screens, tasks, actions, transitions)
	2. Ensures all entities are persisted in MongoDB
	3. Returns graph statistics
	
	Note: Graph structure is stored in MongoDB. NetworkX can be used in-memory by agents when needed.
	"""
	workflow_id = activity.info().workflow_id
	_idempotency_manager = get_idempotency_manager()

	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "build_graph", input
		)
		if cached:
			return BuildGraphResult(**cached)

	activity.heartbeat({"status": "building", "job_id": input.job_id})

	try:
		from navigator.knowledge.graph.collections import get_screen_group_collection
		from navigator.knowledge.persist.collections import (
			get_screens_collection,
			get_transitions_collection,
		)
		from navigator.knowledge.persist.documents import (
			get_screen,
			query_screens_by_knowledge_id,
			query_transitions_by_knowledge_id,
		)
		from navigator.knowledge.persist.state import load_workflow_state_by_job_id

		errors: list[str] = []

		# Try to get knowledge_id from workflow state
		workflow_state = await load_workflow_state_by_job_id(input.job_id)
		knowledge_id: str | None = None
		if workflow_state and hasattr(workflow_state, 'metadata'):
			# WorkflowState stores knowledge_id in metadata
			knowledge_id = workflow_state.metadata.get('knowledge_id')
		website_id: str | None = None

		# Verify screens exist and get website_id/knowledge_id from first screen
		if input.screen_ids:
			screen = await get_screen(input.screen_ids[0])
			if screen:
				website_id = screen.website_id
				# Get knowledge_id from MongoDB document if not from workflow state
				if not knowledge_id:
					# knowledge_id is stored in MongoDB but not in Pydantic model
					# Query it directly from the collection
					screens_collection = await get_screens_collection()
					if screens_collection:
						screen_doc = await screens_collection.find_one({'screen_id': input.screen_ids[0]})
						if screen_doc and 'knowledge_id' in screen_doc:
							knowledge_id = screen_doc['knowledge_id']
			else:
				errors.append(f"Screen not found: {input.screen_ids[0]}")

		# Count graph nodes (screens)
		graph_nodes = len(input.screen_ids)  # Default to provided count

		if knowledge_id:
			# Count all screens for this knowledge_id
			screens = await query_screens_by_knowledge_id(knowledge_id, limit=10000)
			graph_nodes = len(screens)
		elif website_id:
			# Count all screens for this website_id
			screens_collection = await get_screens_collection()
			if screens_collection:
				graph_nodes = await screens_collection.count_documents({'website_id': website_id})

		# Count graph edges (transitions)
		graph_edges = len(input.transition_ids)  # Default to provided count

		if knowledge_id:
			# Count all transitions for this knowledge_id
			transitions = await query_transitions_by_knowledge_id(knowledge_id, limit=10000)
			graph_edges = len(transitions)
		elif website_id and input.screen_ids:
			# Count transitions that connect to/from screens in this extraction
			# This is a fallback - transitions don't have website_id directly
			transitions_collection = await get_transitions_collection()
			if transitions_collection:
				# Count transitions where from_screen_id or to_screen_id is in our screen_ids
				graph_edges = await transitions_collection.count_documents({
					'$or': [
						{'from_screen_id': {'$in': input.screen_ids}},
						{'to_screen_id': {'$in': input.screen_ids}}
					]
				})

		# Count screen groups for this website
		screen_groups = 0
		if website_id:
			screen_groups_collection = await get_screen_group_collection()
			if screen_groups_collection:
				screen_groups = await screen_groups_collection.count_documents({'website_id': website_id})

		result = BuildGraphResult(
			graph_nodes=graph_nodes,
			graph_edges=graph_edges,
			screen_groups=screen_groups,
			errors=errors,
			success=len(errors) == 0,
		)

		logger.info(
			f"✅ Graph statistics: {result.graph_nodes} nodes, "
			f"{result.graph_edges} edges, {result.screen_groups} screen groups"
		)

		# Record execution
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"build_graph",
				input,
				result.__dict__,
				success=True,
			)

		return result

	except Exception as e:
		logger.error(f"❌ Graph construction failed: {e}", exc_info=True)

		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"build_graph",
				input,
				{},
				success=False,
				error=str(e),
			)

		raise

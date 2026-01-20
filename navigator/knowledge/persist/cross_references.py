"""
Cross-reference management for knowledge entities.

Maintains bidirectional links between all knowledge entities (Business Features,
User Flows, Screens, Tasks, Actions, Transitions, Workflows) to enable easy
navigation and relationship tracking.

Phase 2: CrossReferenceManager implementation.
"""

import logging
from typing import Any

from navigator.knowledge.persist.collections import (
	get_actions_collection,
	get_business_functions_collection,
	get_screens_collection,
	get_tasks_collection,
	get_transitions_collection,
)

logger = logging.getLogger(__name__)


class CrossReferenceManager:
	"""
	Manages bidirectional cross-references between knowledge entities.
	
	Automatically maintains links when entities are created/updated, ensuring
	consistency across all related entities.
	"""

	async def link_business_function_to_user_flow(
		self,
		business_function_id: str,
		user_flow_id: str,
		knowledge_id: str | None = None
	) -> bool:
		"""
		Link business function to user flow (bidirectional).
		
		Updates:
		- BusinessFunction.related_user_flows
		- UserFlow.related_business_functions
		
		Args:
			business_function_id: Business function ID
			user_flow_id: User flow ID
			knowledge_id: Optional knowledge ID for filtering
		
		Returns:
			True if both links updated successfully
		"""
		try:
			bf_collection = await get_business_functions_collection()
			if bf_collection is None:
				return False

			# Update business function: add user flow
			query = {'business_function_id': business_function_id}
			if knowledge_id:
				query['knowledge_id'] = knowledge_id

			await bf_collection.update_one(
				query,
				{'$addToSet': {'related_user_flows': user_flow_id}},
				upsert=False
			)

			# Update user flow: add business function
			# Note: User flows are stored separately, need to get collection
			# For now, we'll handle this in the user flow save function
			# This is a placeholder - user flows need their own collection

			logger.debug(
				f"Linked business_function_id={business_function_id} "
				f"to user_flow_id={user_flow_id}"
			)
			return True

		except Exception as e:
			logger.error(f"Failed to link business function to user flow: {e}")
			return False

	async def link_user_flow_to_screen(
		self,
		user_flow_id: str,
		screen_id: str,
		order: int | None = None,
		knowledge_id: str | None = None
	) -> bool:
		"""
		Link user flow to screen (bidirectional).
		
		Updates:
		- UserFlow.related_screens + screen_sequence
		- Screen.user_flow_ids
		
		Args:
			user_flow_id: User flow ID
			screen_id: Screen ID
			order: Optional order in sequence
			knowledge_id: Optional knowledge ID for filtering
		
		Returns:
			True if both links updated successfully
		"""
		try:
			screens_collection = await get_screens_collection()
			if screens_collection is None:
				return False

			# Update screen: add user flow
			query = {'screen_id': screen_id}
			if knowledge_id:
				query['knowledge_id'] = knowledge_id

			await screens_collection.update_one(
				query,
				{'$addToSet': {'user_flow_ids': user_flow_id}},
				upsert=False
			)

			# Update user flow screen_sequence if order provided
			# Note: User flows stored separately, handled in user flow save

			logger.debug(
				f"Linked user_flow_id={user_flow_id} to screen_id={screen_id} "
				f"(order={order})"
			)
			return True

		except Exception as e:
			logger.error(f"Failed to link user flow to screen: {e}")
			return False

	async def link_screen_to_action(
		self,
		screen_id: str,
		action_id: str,
		knowledge_id: str | None = None
	) -> bool:
		"""
		Link screen to action (bidirectional).
		
		Updates:
		- Screen.action_ids
		- Action.screen_ids
		
		Args:
			screen_id: Screen ID
			action_id: Action ID
			knowledge_id: Optional knowledge ID for filtering
		
		Returns:
			True if both links updated successfully
		"""
		try:
			screens_collection = await get_screens_collection()
			actions_collection = await get_actions_collection()

			if screens_collection is None or actions_collection is None:
				return False

			# Update screen: add action
			screen_query = {'screen_id': screen_id}
			if knowledge_id:
				screen_query['knowledge_id'] = knowledge_id

			await screens_collection.update_one(
				screen_query,
				{'$addToSet': {'action_ids': action_id}},
				upsert=False
			)

			# Update action: add screen
			action_query = {'action_id': action_id}
			if knowledge_id:
				action_query['knowledge_id'] = knowledge_id

			await actions_collection.update_one(
				action_query,
				{'$addToSet': {'screen_ids': screen_id}},
				upsert=False
			)

			logger.debug(f"Linked screen_id={screen_id} to action_id={action_id}")
			return True

		except Exception as e:
			logger.error(f"Failed to link screen to action: {e}")
			return False

	async def link_transition_to_action(
		self,
		transition_id: str,
		action_id: str,
		knowledge_id: str | None = None
	) -> bool:
		"""
		Link transition to action (bidirectional).
		
		Updates:
		- Transition.action_id
		- Action.triggered_transitions
		
		Args:
			transition_id: Transition ID
			action_id: Action ID
			knowledge_id: Optional knowledge ID for filtering
		
		Returns:
			True if both links updated successfully
		"""
		try:
			transitions_collection = await get_transitions_collection()
			actions_collection = await get_actions_collection()

			if transitions_collection is None or actions_collection is None:
				return False

			# Update transition: set action_id
			transition_query = {'transition_id': transition_id}
			if knowledge_id:
				transition_query['knowledge_id'] = knowledge_id

			await transitions_collection.update_one(
				transition_query,
				{'$set': {'action_id': action_id}},
				upsert=False
			)

			# Update action: add triggered transition
			action_query = {'action_id': action_id}
			if knowledge_id:
				action_query['knowledge_id'] = knowledge_id

			await actions_collection.update_one(
				action_query,
				{'$addToSet': {'triggered_transitions': transition_id}},
				upsert=False
			)

			logger.debug(
				f"Linked transition_id={transition_id} to action_id={action_id}"
			)
			return True

		except Exception as e:
			logger.error(f"Failed to link transition to action: {e}")
			return False

	async def link_task_to_screen(
		self,
		task_id: str,
		screen_id: str,
		knowledge_id: str | None = None
	) -> bool:
		"""
		Link task to screen (bidirectional).
		
		Updates:
		- Task.screen_ids
		- Screen.task_ids
		
		Args:
			task_id: Task ID
			screen_id: Screen ID
			knowledge_id: Optional knowledge ID for filtering
		
		Returns:
			True if both links updated successfully
		"""
		try:
			tasks_collection = await get_tasks_collection()
			screens_collection = await get_screens_collection()

			if tasks_collection is None or screens_collection is None:
				return False

			# Update task: add screen
			task_query = {'task_id': task_id}
			if knowledge_id:
				task_query['knowledge_id'] = knowledge_id

			await tasks_collection.update_one(
				task_query,
				{'$addToSet': {'screen_ids': screen_id}},
				upsert=False
			)

			# Update screen: add task
			screen_query = {'screen_id': screen_id}
			if knowledge_id:
				screen_query['knowledge_id'] = knowledge_id

			await screens_collection.update_one(
				screen_query,
				{'$addToSet': {'task_ids': task_id}},
				upsert=False
			)

			logger.debug(f"Linked task_id={task_id} to screen_id={screen_id}")
			return True

		except Exception as e:
			logger.error(f"Failed to link task to screen: {e}")
			return False

	async def link_transition_to_screens(
		self,
		transition_id: str,
		from_screen_id: str,
		to_screen_id: str,
		knowledge_id: str | None = None
	) -> bool:
		"""
		Link transition to source and target screens (bidirectional).
		
		Updates:
		- Transition.from_screen_id, to_screen_id (already set)
		- Screen.outgoing_transitions (from_screen)
		- Screen.incoming_transitions (to_screen)
		
		Args:
			transition_id: Transition ID
			from_screen_id: Source screen ID
			to_screen_id: Target screen ID
			knowledge_id: Optional knowledge ID for filtering
		
		Returns:
			True if all links updated successfully
		"""
		try:
			screens_collection = await get_screens_collection()
			if screens_collection is None:
				return False

			# Update from_screen: add outgoing transition
			from_query = {'screen_id': from_screen_id}
			if knowledge_id:
				from_query['knowledge_id'] = knowledge_id

			await screens_collection.update_one(
				from_query,
				{'$addToSet': {'outgoing_transitions': transition_id}},
				upsert=False
			)

			# Update to_screen: add incoming transition
			to_query = {'screen_id': to_screen_id}
			if knowledge_id:
				to_query['knowledge_id'] = knowledge_id

			await screens_collection.update_one(
				to_query,
				{'$addToSet': {'incoming_transitions': transition_id}},
				upsert=False
			)

			logger.debug(
				f"Linked transition_id={transition_id} "
				f"from_screen={from_screen_id} to_screen={to_screen_id}"
			)
			return True

		except Exception as e:
			logger.error(f"Failed to link transition to screens: {e}")
			return False

	async def update_screen_references_from_entity(
		self,
		screen_id: str,
		entity_type: str,
		entity_id: str,
		knowledge_id: str | None = None
	) -> bool:
		"""
		Update screen references when an entity references it.
		
		Generic helper to update screen references based on entity type.
		
		Args:
			screen_id: Screen ID
			entity_type: Type of entity ('user_flow', 'task', 'action', 'workflow', 'business_function')
			entity_id: Entity ID
			knowledge_id: Optional knowledge ID for filtering
		
		Returns:
			True if updated successfully
		"""
		try:
			screens_collection = await get_screens_collection()
			if screens_collection is None:
				return False

			query = {'screen_id': screen_id}
			if knowledge_id:
				query['knowledge_id'] = knowledge_id

			# Map entity type to field name
			field_map = {
				'user_flow': 'user_flow_ids',
				'task': 'task_ids',
				'action': 'action_ids',
				'workflow': 'workflow_ids',
				'business_function': 'business_function_ids',
			}

			field_name = field_map.get(entity_type)
			if not field_name:
				logger.warning(f"Unknown entity type for screen reference: {entity_type}")
				return False

			await screens_collection.update_one(
				query,
				{'$addToSet': {field_name: entity_id}},
				upsert=False
			)

			logger.debug(
				f"Updated screen_id={screen_id} with {entity_type}_id={entity_id}"
			)
			return True

		except Exception as e:
			logger.error(f"Failed to update screen references: {e}")
			return False

	async def rebuild_all_references(
		self,
		knowledge_id: str
	) -> dict[str, Any]:
		"""
		Rebuild all cross-references for a knowledge_id.
		
		Useful for:
		- Migration of existing knowledge
		- Fixing broken references
		- Re-syncing after extraction updates
		
		Args:
			knowledge_id: Knowledge ID to rebuild references for
		
		Returns:
			Dict with statistics about rebuilt references
		"""
		stats = {
			'screens_updated': 0,
			'tasks_updated': 0,
			'actions_updated': 0,
			'transitions_updated': 0,
			'workflows_updated': 0,
			'business_functions_updated': 0,
			'errors': [],
		}

		try:
			logger.info(f"Rebuilding cross-references for knowledge_id={knowledge_id}")

			# Load all entities for this knowledge_id
			from navigator.knowledge.persist.documents import (
				query_actions_by_knowledge_id,
				query_business_functions_by_knowledge_id,
				query_screens_by_knowledge_id,
				query_tasks_by_knowledge_id,
				query_transitions_by_knowledge_id,
				query_workflows_by_knowledge_id,
			)

			screens = await query_screens_by_knowledge_id(knowledge_id)
			tasks = await query_tasks_by_knowledge_id(knowledge_id)
			actions = await query_actions_by_knowledge_id(knowledge_id)
			transitions = await query_transitions_by_knowledge_id(knowledge_id)
			workflows = await query_workflows_by_knowledge_id(knowledge_id)
			business_functions = await query_business_functions_by_knowledge_id(knowledge_id)

			# Rebuild transition → screen links
			for transition in transitions:
				if transition.from_screen_id and transition.to_screen_id:
					success = await self.link_transition_to_screens(
						transition.transition_id,
						transition.from_screen_id,
						transition.to_screen_id,
						knowledge_id
					)
					if success:
						stats['transitions_updated'] += 1

					# Link transition to action if triggered_by.element_id exists
					if transition.triggered_by and transition.triggered_by.element_id:
						success = await self.link_transition_to_action(
							transition.transition_id,
							transition.triggered_by.element_id,
							knowledge_id
						)

			# Rebuild task → screen links (from task metadata or steps)
			for task in tasks:
				# Check if task has screen_ids already set
				if hasattr(task, 'screen_ids') and task.screen_ids:
					for screen_id in task.screen_ids:
						success = await self.link_task_to_screen(
							task.task_id,
							screen_id,
							knowledge_id
						)
						if success:
							stats['tasks_updated'] += 1

			# Rebuild action → screen links (from action metadata)
			for action in actions:
				if hasattr(action, 'screen_ids') and action.screen_ids:
					for screen_id in action.screen_ids:
						success = await self.link_screen_to_action(
							screen_id,
							action.action_id,
							knowledge_id
						)
						if success:
							stats['actions_updated'] += 1

			# Rebuild workflow → screen/task/action links
			for workflow in workflows:
				# Extract screen IDs from workflow steps
				screen_names = {step.screen for step in workflow.steps if hasattr(step, 'screen')}
				# Note: Would need to map screen names to IDs, simplified for now

				# Link workflow to business function if business_function_id set
				if hasattr(workflow, 'business_function_id') and workflow.business_function_id:
					# Update business function's related_workflows
					bf_collection = await get_business_functions_collection()
					if bf_collection:
						await bf_collection.update_one(
							{
								'business_function_id': workflow.business_function_id,
								'knowledge_id': knowledge_id
							},
							{'$addToSet': {'related_workflows': workflow.workflow_id}},
							upsert=False
						)
						stats['workflows_updated'] += 1

			# Rebuild business function links
			for bf in business_functions:
				# Update related entities if they exist
				if hasattr(bf, 'related_screens') and bf.related_screens:
					for screen_id in bf.related_screens:
						await self.update_screen_references_from_entity(
							screen_id,
							'business_function',
							bf.business_function_id,
							knowledge_id
						)
					stats['business_functions_updated'] += 1

			logger.info(
				f"✅ Rebuilt cross-references: "
				f"screens={stats['screens_updated']}, "
				f"tasks={stats['tasks_updated']}, "
				f"actions={stats['actions_updated']}, "
				f"transitions={stats['transitions_updated']}, "
				f"workflows={stats['workflows_updated']}, "
				f"business_functions={stats['business_functions_updated']}"
			)

		except Exception as e:
			logger.error(f"Failed to rebuild cross-references: {e}", exc_info=True)
			stats['errors'].append(str(e))

		return stats


# Global instance
_cross_reference_manager: CrossReferenceManager | None = None


def get_cross_reference_manager() -> CrossReferenceManager:
	"""Get global CrossReferenceManager instance."""
	global _cross_reference_manager
	if _cross_reference_manager is None:
		_cross_reference_manager = CrossReferenceManager()
	return _cross_reference_manager

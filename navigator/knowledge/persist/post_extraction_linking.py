"""
Post-Extraction Entity Linking

Links entities together after extraction phase completes.
Establishes relationships between screens, tasks, actions, transitions, workflows, and business functions.

Priority 2: Implement Post-Extraction Entity Linking Phase
"""

import logging
import re
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlparse

from navigator.knowledge.extract.actions import ActionDefinition
from navigator.knowledge.extract.business_functions import BusinessFunction
from navigator.knowledge.extract.screens import ScreenDefinition
from navigator.knowledge.extract.tasks import TaskDefinition
from navigator.knowledge.extract.transitions import TransitionDefinition
from navigator.knowledge.extract.workflows import OperationalWorkflow
from navigator.knowledge.persist.cross_references import get_cross_reference_manager
from navigator.knowledge.persist.linking_helpers import (
	find_actions_by_name,
	find_screens_by_name,
	find_screens_by_url,
	find_tasks_by_name,
)
from navigator.knowledge.persist.documents import (
	get_action,
	get_business_function,
	get_screen,
	get_task,
	get_transition,
	get_workflow,
	query_actions_by_knowledge_id,
	query_business_functions_by_knowledge_id,
	query_screens_by_knowledge_id,
	query_tasks_by_knowledge_id,
	query_transitions_by_knowledge_id,
	query_workflows_by_knowledge_id,
)

logger = logging.getLogger(__name__)


class PostExtractionLinker:
	"""
	Links entities together after extraction phase completes.
	
	Establishes relationships by:
	- Matching tasks to screens by page_url → screen URL patterns
	- Matching actions to screens by context (video actions → video screens, navigation → URL patterns)
	- Matching business functions to screens by screens_mentioned with fuzzy matching
	- Parsing workflow steps for screen/task/action references
	- Linking transitions to screens and actions
	"""

	def __init__(self, knowledge_id: str, job_id: str | None = None):
		"""
		Initialize the linker.
		
		Args:
			knowledge_id: Knowledge ID to link entities for
			job_id: Optional job ID to filter by
		"""
		self.knowledge_id = knowledge_id
		self.job_id = job_id
		self.cross_ref_manager = get_cross_reference_manager()
		
		# Cache entities for efficient lookup
		self._screens: list[ScreenDefinition] | None = None
		self._tasks: list[TaskDefinition] | None = None
		self._actions: list[ActionDefinition] | None = None
		self._transitions: list[TransitionDefinition] | None = None
		self._workflows: list[OperationalWorkflow] | None = None
		self._business_functions: list[BusinessFunction] | None = None

	async def link_all_entities(self) -> dict[str, Any]:
		"""
		Link all entities together.
		
		Returns:
			Dict with linking statistics
		"""
		stats = {
			'tasks_linked': 0,
			'actions_linked': 0,
			'business_functions_linked': 0,
			'workflows_linked': 0,
			'transitions_linked': 0,
			'errors': [],
		}

		try:
			logger.info(f"🔗 Starting post-extraction entity linking for knowledge_id={self.knowledge_id}")

			# Load all entities
			await self._load_entities()

			# Link tasks to screens
			tasks_linked = await self.link_tasks_to_screens()
			stats['tasks_linked'] = tasks_linked

			# Link actions to screens
			actions_linked = await self.link_actions_to_screens()
			stats['actions_linked'] = actions_linked

			# Link business functions to screens
			bf_linked = await self.link_business_functions_to_screens()
			stats['business_functions_linked'] = bf_linked

			# Link workflows to entities
			workflows_linked = await self.link_workflows_to_entities()
			stats['workflows_linked'] = workflows_linked

			# Link transitions to entities
			transitions_linked = await self.link_transitions_to_entities()
			stats['transitions_linked'] = transitions_linked

			logger.info(
				f"✅ Entity linking complete: "
				f"{tasks_linked} tasks, {actions_linked} actions, "
				f"{bf_linked} business functions, {workflows_linked} workflows, "
				f"{transitions_linked} transitions linked"
			)

		except Exception as e:
			logger.error(f"Failed to link entities: {e}", exc_info=True)
			stats['errors'].append(str(e))

		return stats

	async def _load_entities(self) -> None:
		"""Load all entities for this knowledge_id."""
		if self._screens is None:
			self._screens = await query_screens_by_knowledge_id(
				self.knowledge_id,
				job_id=self.job_id,
				limit=10000
			)
			logger.debug(f"Loaded {len(self._screens)} screens")

		if self._tasks is None:
			self._tasks = await query_tasks_by_knowledge_id(
				self.knowledge_id,
				job_id=self.job_id,
				limit=10000
			)
			logger.debug(f"Loaded {len(self._tasks)} tasks")

		if self._actions is None:
			self._actions = await query_actions_by_knowledge_id(
				self.knowledge_id,
				job_id=self.job_id,
				limit=10000
			)
			logger.debug(f"Loaded {len(self._actions)} actions")

		if self._transitions is None:
			self._transitions = await query_transitions_by_knowledge_id(
				self.knowledge_id,
				job_id=self.job_id,
				limit=10000
			)
			logger.debug(f"Loaded {len(self._transitions)} transitions")

		if self._workflows is None:
			self._workflows = await query_workflows_by_knowledge_id(
				self.knowledge_id,
				job_id=self.job_id,
				limit=10000
			)
			logger.debug(f"Loaded {len(self._workflows)} workflows")

		if self._business_functions is None:
			self._business_functions = await query_business_functions_by_knowledge_id(
				self.knowledge_id,
				job_id=self.job_id,
				limit=10000
			)
			logger.debug(f"Loaded {len(self._business_functions)} business functions")

	async def link_tasks_to_screens(self) -> int:
		"""
		Link tasks to screens by matching page_url in task metadata → screen URL patterns.
		
		Returns:
			Number of tasks linked
		"""
		if not self._tasks or not self._screens:
			await self._load_entities()

		if not self._tasks or not self._screens:
			return 0

		linked_count = 0

		for task in self._tasks:
			# Get page_url from task metadata
			task_metadata = task.metadata if hasattr(task, 'metadata') and task.metadata else {}
			page_url = task_metadata.get('page_url')
			
			# If no page_url, try screen_context for name-based matching
			if not page_url:
				screen_context = task_metadata.get('screen_context')
				if screen_context:
					# Try to match by screen name (fuzzy matching)
					matched_screens = find_screens_by_name(screen_context, self._screens, fuzzy=True)
					for screen in matched_screens:
						success = await self.cross_ref_manager.link_task_to_screen(
							task.task_id,
							screen.screen_id,
							self.knowledge_id
						)
						if success:
							linked_count += 1
							logger.debug(
								f"Linked task '{task.name}' (screen_context={screen_context}) "
								f"to screen '{screen.name}' (screen_id={screen.screen_id})"
							)
				continue

			# Find screens that match this URL
			matched_screens = find_screens_by_url(page_url, self._screens)
			
			for screen in matched_screens:
				# Link task to screen (bidirectional)
				success = await self.cross_ref_manager.link_task_to_screen(
					task.task_id,
					screen.screen_id,
					self.knowledge_id
				)
				if success:
					linked_count += 1
					logger.debug(
						f"Linked task '{task.name}' (page_url={page_url}) "
						f"to screen '{screen.name}' (screen_id={screen.screen_id})"
					)

		return linked_count

	async def link_actions_to_screens(self) -> int:
		"""
		Link actions to screens by matching context.
		
		- Video actions → video screens (by screen name or context)
		- Navigation actions → URL patterns
		
		Returns:
			Number of actions linked
		"""
		if not self._actions or not self._screens:
			await self._load_entities()

		if not self._actions or not self._screens:
			return 0

		linked_count = 0

		for action in self._actions:
			# Check if action has screen_ids already (from extraction)
			if hasattr(action, 'screen_ids') and action.screen_ids:
				# Already linked, skip
				continue

			# Try to match by metadata context
			action_metadata = action.metadata if hasattr(action, 'metadata') and action.metadata else {}
			
			# Check for video actions (from video extraction)
			if action_metadata.get('source') == 'video':
				# Match by screen name mentioned in action context
				screen_name = action_metadata.get('screen_name')
				if screen_name:
					matched_screens = find_screens_by_name(screen_name, self._screens, fuzzy=True)
					for screen in matched_screens:
						success = await self.cross_ref_manager.link_screen_to_action(
							screen.screen_id,
							action.action_id,
							self.knowledge_id
						)
						if success:
							linked_count += 1
							logger.debug(
								f"Linked video action '{action.name}' to screen '{screen.name}' "
								f"(matched by name: {screen_name})"
							)

			# Check for navigation actions
			if action.action_type == 'navigate':
				# Try to get URL from parameters
				target_url = action.parameters.get('url') if action.parameters else None
				
				# If no URL in parameters, try to infer from browser_use_action
				if not target_url and hasattr(action, 'browser_use_action') and action.browser_use_action:
					target_url = action.browser_use_action.get('parameters', {}).get('url')
				
				# If we have a URL, match by URL patterns
				if target_url and (target_url.startswith('http://') or target_url.startswith('https://')):
					matched_screens = find_screens_by_url(target_url, self._screens)
					for screen in matched_screens:
						success = await self.cross_ref_manager.link_screen_to_action(
							screen.screen_id,
							action.action_id,
							self.knowledge_id
						)
						if success:
							linked_count += 1
							logger.debug(
								f"Linked navigation action '{action.name}' (url={target_url}) "
								f"to screen '{screen.name}'"
							)
				# If no URL but action name suggests a screen (e.g., "Navigate Dashboard")
				# try name-based matching
				elif action.name and 'navigate' in action.name.lower():
					# Extract screen name from action (e.g., "Navigate Dashboard" -> "Dashboard")
					action_name_lower = action.name.lower()
					for screen in self._screens:
						screen_name_lower = screen.name.lower()
						# Check if screen name appears in action name
						if screen_name_lower in action_name_lower or action_name_lower in screen_name_lower:
							# Additional check: screen should be actionable (web_ui)
							if screen.is_actionable and screen.content_type == 'web_ui':
								success = await self.cross_ref_manager.link_screen_to_action(
									screen.screen_id,
									action.action_id,
									self.knowledge_id
								)
								if success:
									linked_count += 1
									logger.debug(
										f"Linked navigation action '{action.name}' "
										f"to screen '{screen.name}' (matched by name)"
									)

		return linked_count

	async def link_business_functions_to_screens(self) -> int:
		"""
		Link business functions to screens by matching screens_mentioned with fuzzy matching.
		
		Supports both web_ui and documentation screens.
		
		Returns:
			Number of business functions linked
		"""
		if not self._business_functions or not self._screens:
			await self._load_entities()

		if not self._business_functions or not self._screens:
			return 0

		linked_count = 0

		for bf in self._business_functions:
			# Get screens_mentioned from metadata
			bf_metadata = bf.metadata if hasattr(bf, 'metadata') and bf.metadata else {}
			screens_mentioned = bf_metadata.get('screens_mentioned', [])
			
			if not screens_mentioned:
				continue

			# Match each mentioned screen name to actual screens
			for screen_name in screens_mentioned:
				# Use fuzzy matching to find screens
				matched_screens = find_screens_by_name(screen_name, self._screens, fuzzy=True)
				
				for screen in matched_screens:
					# Link business function to screen (bidirectional)
					success = await self.cross_ref_manager.link_entity_to_business_function(
						'screen',
						screen.screen_id,
						bf.business_function_id,
						self.knowledge_id
					)
					if success:
						linked_count += 1
						logger.debug(
							f"Linked business function '{bf.name}' (screens_mentioned: {screen_name}) "
							f"to screen '{screen.name}' (screen_id={screen.screen_id})"
						)

		return linked_count

	async def link_workflows_to_entities(self) -> int:
		"""
		Link workflows to entities by parsing workflow steps for screen/task/action references.
		
		Returns:
			Number of workflows linked
		"""
		if not self._workflows:
			await self._load_entities()

		if not self._workflows:
			return 0

		linked_count = 0

		for workflow in self._workflows:
			# Parse workflow steps for screen/task/action references
			screen_names = set()
			action_names = set()
			task_names = set()

			for step in workflow.steps:
				# Extract screen name from step
				if hasattr(step, 'screen') and step.screen:
					screen_names.add(step.screen)
				
				# Extract action name from step
				if hasattr(step, 'action') and step.action:
					action_names.add(step.action)
				
				# Extract task name from step (if mentioned)
				if hasattr(step, 'task') and step.task:
					task_names.add(step.task)

			# Link screens
			for screen_name in screen_names:
				matched_screens = find_screens_by_name(screen_name, self._screens or [], fuzzy=True)
				for screen in matched_screens:
					success = await self.cross_ref_manager.update_screen_references_from_entity(
						screen.screen_id,
						'workflow',
						workflow.workflow_id,
						self.knowledge_id
					)
					if success:
						linked_count += 1
						logger.debug(
							f"Linked workflow '{workflow.name}' to screen '{screen.name}' "
							f"(from step screen: {screen_name})"
						)

			# Link actions (by name matching)
			for action_name in action_names:
				matched_actions = find_actions_by_name(action_name, self._actions or [])
				for action in matched_actions:
					# Update workflow's action_ids
					from navigator.knowledge.persist.collections import get_workflows_collection
					workflows_collection = await get_workflows_collection()
					if workflows_collection:
						await workflows_collection.update_one(
							{'workflow_id': workflow.workflow_id, 'knowledge_id': self.knowledge_id},
							{'$addToSet': {'action_ids': action.action_id}},
							upsert=False
						)
						linked_count += 1
						logger.debug(
							f"Linked workflow '{workflow.name}' to action '{action.name}' "
							f"(from step action: {action_name})"
						)

			# Link tasks (by name matching)
			for task_name in task_names:
				matched_tasks = find_tasks_by_name(task_name, self._tasks or [])
				for task in matched_tasks:
					# Update workflow's task_ids
					from navigator.knowledge.persist.collections import get_workflows_collection
					workflows_collection = await get_workflows_collection()
					if workflows_collection:
						await workflows_collection.update_one(
							{'workflow_id': workflow.workflow_id, 'knowledge_id': self.knowledge_id},
							{'$addToSet': {'task_ids': task.task_id}},
							upsert=False
						)
						linked_count += 1
						logger.debug(
							f"Linked workflow '{workflow.name}' to task '{task.name}' "
							f"(from step task: {task_name})"
						)

		return linked_count

	async def link_transitions_to_entities(self) -> int:
		"""
		Link transitions to screens and actions.
		
		- Transitions already have from_screen_id and to_screen_id, but we need to ensure
		  bidirectional links are established
		- Link transitions to actions by triggered_by.element_id
		
		Returns:
			Number of transitions linked
		"""
		if not self._transitions:
			await self._load_entities()

		if not self._transitions:
			return 0

		linked_count = 0

		for transition in self._transitions:
			# Link transition to screens (from_screen_id and to_screen_id)
			if transition.from_screen_id and transition.to_screen_id:
				success = await self.cross_ref_manager.link_transition_to_screens(
					transition.transition_id,
					transition.from_screen_id,
					transition.to_screen_id,
					self.knowledge_id
				)
				if success:
					linked_count += 1
					logger.debug(
						f"Linked transition '{transition.transition_id}' to screens "
						f"(from={transition.from_screen_id}, to={transition.to_screen_id})"
					)

			# Link transition to action if triggered_by.element_id exists
			if transition.triggered_by and transition.triggered_by.element_id:
				# element_id might be an action_id
				action_id = transition.triggered_by.element_id
				success = await self.cross_ref_manager.link_transition_to_action(
					transition.transition_id,
					action_id,
					self.knowledge_id
				)
				if success:
					linked_count += 1
					logger.debug(
						f"Linked transition '{transition.transition_id}' to action '{action_id}'"
					)

		return linked_count

"""
Full Knowledge Definition Storage

Implements Phase 5.5: Full-Definition Storage in MongoDB

Stores complete definitions (not just graph references):
- Screens: Full screen definitions with UI elements, state signatures, affordances
- Tasks: Full task definitions with steps, IO specs, iterator specs
- Actions: Full action definitions with preconditions, postconditions, parameters
- Transitions: Full transition definitions with triggers, conditions, effects

Complements ArangoDB graph (which stores lightweight node/edge references).
"""

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection

from navigator.knowledge.persist.collections import (
	get_screens_collection,
	get_tasks_collection,
	get_actions_collection,
	get_transitions_collection,
)
from navigator.knowledge.extract.screens import ScreenDefinition
from navigator.knowledge.extract.tasks import TaskDefinition
from navigator.knowledge.extract.actions import ActionDefinition
from navigator.knowledge.extract.transitions import TransitionDefinition

logger = logging.getLogger(__name__)


# ============================================================================
# Screen Storage
# ============================================================================

async def save_screen(screen: ScreenDefinition) -> bool:
	"""
	Save full screen definition to MongoDB.
	
	Args:
		screen: ScreenDefinition to save
	
	Returns:
		True if saved successfully, False otherwise
	"""
	try:
		collection = await get_screens_collection()
		if not collection:
			logger.warning("MongoDB unavailable, screen not persisted")
			return False
		
		# Convert to dict for MongoDB storage
		screen_dict = screen.dict(exclude_none=True)
		
		# Upsert by screen_id
		await collection.update_one(
			{'screen_id': screen.screen_id},
			{'$set': screen_dict},
			upsert=True
		)
		
		logger.info(f"Saved screen: screen_id={screen.screen_id}, name={screen.name}")
		return True
	
	except Exception as e:
		logger.error(f"Failed to save screen: {e}")
		return False


async def save_screens(screens: list[ScreenDefinition]) -> dict[str, Any]:
	"""
	Save multiple screen definitions (batch operation).
	
	Args:
		screens: List of ScreenDefinition objects
	
	Returns:
		Dict with 'saved', 'failed', 'total' counts
	"""
	results = {'saved': 0, 'failed': 0, 'total': len(screens)}
	
	for screen in screens:
		success = await save_screen(screen)
		if success:
			results['saved'] += 1
		else:
			results['failed'] += 1
	
	logger.info(f"Batch saved screens: {results['saved']}/{results['total']} succeeded, {results['failed']} failed")
	return results


async def get_screen(screen_id: str) -> ScreenDefinition | None:
	"""
	Get screen definition by screen_id.
	
	Args:
		screen_id: Screen identifier
	
	Returns:
		ScreenDefinition if found, None otherwise
	"""
	try:
		collection = await get_screens_collection()
		if not collection:
			logger.warning("MongoDB unavailable, cannot get screen")
			return None
		
		screen_dict = await collection.find_one({'screen_id': screen_id})
		if not screen_dict:
			logger.debug(f"Screen not found: screen_id={screen_id}")
			return None
		
		# Remove MongoDB _id field
		screen_dict.pop('_id', None)
		
		screen = ScreenDefinition(**screen_dict)
		logger.debug(f"Retrieved screen: screen_id={screen_id}, name={screen.name}")
		return screen
	
	except Exception as e:
		logger.error(f"Failed to get screen: {e}")
		return None


async def query_screens_by_website(website_id: str, limit: int = 100) -> list[ScreenDefinition]:
	"""
	Query screens by website_id.
	
	Args:
		website_id: Website identifier
		limit: Maximum number of results (default: 100)
	
	Returns:
		List of ScreenDefinition objects
	"""
	try:
		collection = await get_screens_collection()
		if not collection:
			logger.warning("MongoDB unavailable, cannot query screens")
			return []
		
		cursor = collection.find({'website_id': website_id}).limit(limit)
		
		screens = []
		async for screen_dict in cursor:
			screen_dict.pop('_id', None)
			screens.append(ScreenDefinition(**screen_dict))
		
		logger.debug(f"Queried {len(screens)} screens for website_id={website_id}")
		return screens
	
	except Exception as e:
		logger.error(f"Failed to query screens by website: {e}")
		return []


async def delete_screen(screen_id: str) -> bool:
	"""
	Delete screen definition.
	
	Args:
		screen_id: Screen identifier
	
	Returns:
		True if deleted successfully, False otherwise
	"""
	try:
		collection = await get_screens_collection()
		if not collection:
			logger.warning("MongoDB unavailable, cannot delete screen")
			return False
		
		result = await collection.delete_one({'screen_id': screen_id})
		
		if result.deleted_count > 0:
			logger.info(f"Deleted screen: screen_id={screen_id}")
			return True
		else:
			logger.warning(f"Screen not found for deletion: screen_id={screen_id}")
			return False
	
	except Exception as e:
		logger.error(f"Failed to delete screen: {e}")
		return False


# ============================================================================
# Task Storage
# ============================================================================

async def save_task(task: TaskDefinition) -> bool:
	"""
	Save full task definition to MongoDB.
	
	Args:
		task: TaskDefinition to save
	
	Returns:
		True if saved successfully, False otherwise
	"""
	try:
		collection = await get_tasks_collection()
		if not collection:
			logger.warning("MongoDB unavailable, task not persisted")
			return False
		
		# Convert to dict for MongoDB storage
		task_dict = task.dict(exclude_none=True)
		
		# Upsert by task_id
		await collection.update_one(
			{'task_id': task.task_id},
			{'$set': task_dict},
			upsert=True
		)
		
		logger.info(f"Saved task: task_id={task.task_id}, name={task.name}")
		return True
	
	except Exception as e:
		logger.error(f"Failed to save task: {e}")
		return False


async def save_tasks(tasks: list[TaskDefinition]) -> dict[str, Any]:
	"""
	Save multiple task definitions (batch operation).
	
	Args:
		tasks: List of TaskDefinition objects
	
	Returns:
		Dict with 'saved', 'failed', 'total' counts
	"""
	results = {'saved': 0, 'failed': 0, 'total': len(tasks)}
	
	for task in tasks:
		success = await save_task(task)
		if success:
			results['saved'] += 1
		else:
			results['failed'] += 1
	
	logger.info(f"Batch saved tasks: {results['saved']}/{results['total']} succeeded, {results['failed']} failed")
	return results


async def get_task(task_id: str) -> TaskDefinition | None:
	"""
	Get task definition by task_id.
	
	Args:
		task_id: Task identifier
	
	Returns:
		TaskDefinition if found, None otherwise
	"""
	try:
		collection = await get_tasks_collection()
		if not collection:
			logger.warning("MongoDB unavailable, cannot get task")
			return None
		
		task_dict = await collection.find_one({'task_id': task_id})
		if not task_dict:
			logger.debug(f"Task not found: task_id={task_id}")
			return None
		
		# Remove MongoDB _id field
		task_dict.pop('_id', None)
		
		task = TaskDefinition(**task_dict)
		logger.debug(f"Retrieved task: task_id={task_id}, name={task.name}")
		return task
	
	except Exception as e:
		logger.error(f"Failed to get task: {e}")
		return None


async def query_tasks_by_website(website_id: str, limit: int = 100) -> list[TaskDefinition]:
	"""
	Query tasks by website_id.
	
	Args:
		website_id: Website identifier
		limit: Maximum number of results (default: 100)
	
	Returns:
		List of TaskDefinition objects
	"""
	try:
		collection = await get_tasks_collection()
		if not collection:
			logger.warning("MongoDB unavailable, cannot query tasks")
			return []
		
		cursor = collection.find({'website_id': website_id}).limit(limit)
		
		tasks = []
		async for task_dict in cursor:
			task_dict.pop('_id', None)
			tasks.append(TaskDefinition(**task_dict))
		
		logger.debug(f"Queried {len(tasks)} tasks for website_id={website_id}")
		return tasks
	
	except Exception as e:
		logger.error(f"Failed to query tasks by website: {e}")
		return []


# ============================================================================
# Action Storage
# ============================================================================

async def save_action(action: ActionDefinition) -> bool:
	"""
	Save full action definition to MongoDB.
	
	Args:
		action: ActionDefinition to save
	
	Returns:
		True if saved successfully, False otherwise
	"""
	try:
		collection = await get_actions_collection()
		if not collection:
			logger.warning("MongoDB unavailable, action not persisted")
			return False
		
		# Convert to dict for MongoDB storage
		action_dict = action.dict(exclude_none=True)
		
		# Upsert by action_id
		await collection.update_one(
			{'action_id': action.action_id},
			{'$set': action_dict},
			upsert=True
		)
		
		logger.info(f"Saved action: action_id={action.action_id}, type={action.action_type}")
		return True
	
	except Exception as e:
		logger.error(f"Failed to save action: {e}")
		return False


async def save_actions(actions: list[ActionDefinition]) -> dict[str, Any]:
	"""
	Save multiple action definitions (batch operation).
	
	Args:
		actions: List of ActionDefinition objects
	
	Returns:
		Dict with 'saved', 'failed', 'total' counts
	"""
	results = {'saved': 0, 'failed': 0, 'total': len(actions)}
	
	for action in actions:
		success = await save_action(action)
		if success:
			results['saved'] += 1
		else:
			results['failed'] += 1
	
	logger.info(f"Batch saved actions: {results['saved']}/{results['total']} succeeded, {results['failed']} failed")
	return results


async def get_action(action_id: str) -> ActionDefinition | None:
	"""
	Get action definition by action_id.
	
	Args:
		action_id: Action identifier
	
	Returns:
		ActionDefinition if found, None otherwise
	"""
	try:
		collection = await get_actions_collection()
		if not collection:
			logger.warning("MongoDB unavailable, cannot get action")
			return None
		
		action_dict = await collection.find_one({'action_id': action_id})
		if not action_dict:
			logger.debug(f"Action not found: action_id={action_id}")
			return None
		
		# Remove MongoDB _id field
		action_dict.pop('_id', None)
		
		action = ActionDefinition(**action_dict)
		logger.debug(f"Retrieved action: action_id={action_id}, type={action.action_type}")
		return action
	
	except Exception as e:
		logger.error(f"Failed to get action: {e}")
		return None


# ============================================================================
# Transition Storage
# ============================================================================

async def save_transition(transition: TransitionDefinition) -> bool:
	"""
	Save full transition definition to MongoDB.
	
	Args:
		transition: TransitionDefinition to save
	
	Returns:
		True if saved successfully, False otherwise
	"""
	try:
		collection = await get_transitions_collection()
		if not collection:
			logger.warning("MongoDB unavailable, transition not persisted")
			return False
		
		# Convert to dict for MongoDB storage
		transition_dict = transition.dict(exclude_none=True)
		
		# Upsert by transition_id
		await collection.update_one(
			{'transition_id': transition.transition_id},
			{'$set': transition_dict},
			upsert=True
		)
		
		logger.info(
			f"Saved transition: transition_id={transition.transition_id}, "
			f"from={transition.source_screen_id} to={transition.target_screen_id}"
		)
		return True
	
	except Exception as e:
		logger.error(f"Failed to save transition: {e}")
		return False


async def save_transitions(transitions: list[TransitionDefinition]) -> dict[str, Any]:
	"""
	Save multiple transition definitions (batch operation).
	
	Args:
		transitions: List of TransitionDefinition objects
	
	Returns:
		Dict with 'saved', 'failed', 'total' counts
	"""
	results = {'saved': 0, 'failed': 0, 'total': len(transitions)}
	
	for transition in transitions:
		success = await save_transition(transition)
		if success:
			results['saved'] += 1
		else:
			results['failed'] += 1
	
	logger.info(f"Batch saved transitions: {results['saved']}/{results['total']} succeeded, {results['failed']} failed")
	return results


async def get_transition(transition_id: str) -> TransitionDefinition | None:
	"""
	Get transition definition by transition_id.
	
	Args:
		transition_id: Transition identifier
	
	Returns:
		TransitionDefinition if found, None otherwise
	"""
	try:
		collection = await get_transitions_collection()
		if not collection:
			logger.warning("MongoDB unavailable, cannot get transition")
			return None
		
		transition_dict = await collection.find_one({'transition_id': transition_id})
		if not transition_dict:
			logger.debug(f"Transition not found: transition_id={transition_id}")
			return None
		
		# Remove MongoDB _id field
		transition_dict.pop('_id', None)
		
		transition = TransitionDefinition(**transition_dict)
		logger.debug(f"Retrieved transition: transition_id={transition_id}")
		return transition
	
	except Exception as e:
		logger.error(f"Failed to get transition: {e}")
		return None


async def query_transitions_by_source(source_screen_id: str, limit: int = 100) -> list[TransitionDefinition]:
	"""
	Query transitions by source screen.
	
	Args:
		source_screen_id: Source screen identifier
		limit: Maximum number of results (default: 100)
	
	Returns:
		List of TransitionDefinition objects
	"""
	try:
		collection = await get_transitions_collection()
		if not collection:
			logger.warning("MongoDB unavailable, cannot query transitions")
			return []
		
		cursor = collection.find({'source_screen_id': source_screen_id}).limit(limit)
		
		transitions = []
		async for transition_dict in cursor:
			transition_dict.pop('_id', None)
			transitions.append(TransitionDefinition(**transition_dict))
		
		logger.debug(f"Queried {len(transitions)} transitions from source_screen_id={source_screen_id}")
		return transitions
	
	except Exception as e:
		logger.error(f"Failed to query transitions by source: {e}")
		return []


async def query_transitions_by_target(target_screen_id: str, limit: int = 100) -> list[TransitionDefinition]:
	"""
	Query transitions by target screen.
	
	Args:
		target_screen_id: Target screen identifier
		limit: Maximum number of results (default: 100)
	
	Returns:
		List of TransitionDefinition objects
	"""
	try:
		collection = await get_transitions_collection()
		if not collection:
			logger.warning("MongoDB unavailable, cannot query transitions")
			return []
		
		cursor = collection.find({'target_screen_id': target_screen_id}).limit(limit)
		
		transitions = []
		async for transition_dict in cursor:
			transition_dict.pop('_id', None)
			transitions.append(TransitionDefinition(**transition_dict))
		
		logger.debug(f"Queried {len(transitions)} transitions to target_screen_id={target_screen_id}")
		return transitions
	
	except Exception as e:
		logger.error(f"Failed to query transitions by target: {e}")
		return []

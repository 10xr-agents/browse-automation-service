"""
Task storage functions.

Handles persistence of TaskDefinition objects in MongoDB.
"""

import logging
from typing import Any

from navigator.knowledge.extract.tasks import TaskDefinition
from navigator.knowledge.persist.collections import (
	get_actions_collection,
	get_tasks_collection,
)

logger = logging.getLogger(__name__)


async def save_task(
	task: TaskDefinition,
	knowledge_id: str | None = None,
	job_id: str | None = None
) -> bool:
	"""
	Save full task definition to MongoDB.
	
	Args:
		task: TaskDefinition to save
		knowledge_id: Optional knowledge ID for persistence and querying
		job_id: Optional job ID for historical tracking
	
	Returns:
		True if saved successfully, False otherwise
	"""
	try:
		collection = await get_tasks_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, task not persisted")
			return False

		# Convert to dict for MongoDB storage
		task_dict = task.model_dump(exclude_none=True)

		# Add knowledge_id if provided
		if knowledge_id:
			task_dict['knowledge_id'] = knowledge_id

		# Add job_id if provided (for historical tracking)
		if job_id:
			task_dict['job_id'] = job_id

		# Upsert by task_id
		await collection.update_one(
			{'task_id': task.task_id},
			{'$set': task_dict},
			upsert=True
		)

		# Update cross-references (Phase 2: CrossReferenceManager)
		from navigator.knowledge.persist.cross_references import get_cross_reference_manager
		cross_ref_manager = get_cross_reference_manager()

		# Link task to screens if screen_ids are set
		if hasattr(task, 'screen_ids') and task.screen_ids:
			for screen_id in task.screen_ids:
				await cross_ref_manager.link_task_to_screen(
					task.task_id,
					screen_id,
					knowledge_id
				)

		# Link task to actions if action_ids are set
		if hasattr(task, 'action_ids') and task.action_ids:
			actions_collection = await get_actions_collection()
			if actions_collection:
				for action_id in task.action_ids:
					# Update action: add task
					action_query = {'action_id': action_id}
					if knowledge_id:
						action_query['knowledge_id'] = knowledge_id
					await actions_collection.update_one(
						action_query,
						{'$addToSet': {'task_ids': task.task_id}},
						upsert=False
					)

		# Phase 3.1: Link task to business functions
		if hasattr(task, 'business_function_ids') and task.business_function_ids:
			for bf_id in task.business_function_ids:
				await cross_ref_manager.link_entity_to_business_function(
					'task',
					task.task_id,
					bf_id,
					knowledge_id
				)

		logger.info(f"Saved task: task_id={task.task_id}, name={task.name}, knowledge_id={knowledge_id}, job_id={job_id}")
		return True

	except Exception as e:
		logger.error(f"Failed to save task: {e}")
		return False


async def save_tasks(
	tasks: list[TaskDefinition],
	knowledge_id: str | None = None,
	job_id: str | None = None
) -> dict[str, Any]:
	"""
	Save multiple task definitions (batch operation).
	
	Args:
		tasks: List of TaskDefinition objects
		knowledge_id: Optional knowledge ID for persistence and querying
		job_id: Optional job ID for historical tracking
	
	Returns:
		Dict with 'saved', 'failed', 'total' counts
	"""
	results = {'saved': 0, 'failed': 0, 'total': len(tasks)}

	for task in tasks:
		success = await save_task(task, knowledge_id=knowledge_id, job_id=job_id)
		if success:
			results['saved'] += 1
		else:
			results['failed'] += 1

	logger.info(f"Saved {results['saved']}/{results['total']} tasks")
	return results


async def get_task(task_id: str) -> TaskDefinition | None:
	"""
	Retrieve task definition by task_id.
	
	Args:
		task_id: Task ID to retrieve
	
	Returns:
		TaskDefinition if found, None otherwise
	"""
	try:
		collection = await get_tasks_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot retrieve task")
			return None

		doc = await collection.find_one({'task_id': task_id})
		if doc is None:
			return None

		# Remove MongoDB _id field
		doc.pop('_id', None)

		# Reconstruct TaskDefinition from dict
		return TaskDefinition(**doc)

	except Exception as e:
		logger.error(f"Failed to get task: {e}")
		return None


async def query_tasks_by_website(website_id: str, limit: int = 100) -> list[TaskDefinition]:
	"""
	Query tasks by website_id.
	
	Args:
		website_id: Website ID to query
		limit: Maximum number of results
	
	Returns:
		List of TaskDefinition objects
	"""
	try:
		collection = await get_tasks_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot query tasks")
			return []

		cursor = collection.find({'website_id': website_id}).limit(limit)
		tasks = []

		async for doc in cursor:
			doc.pop('_id', None)
			try:
				tasks.append(TaskDefinition(**doc))
			except Exception as e:
				logger.warning(f"Failed to parse task document: {e}")
				continue

		return tasks

	except Exception as e:
		logger.error(f"Failed to query tasks by website: {e}")
		return []


async def query_tasks_by_knowledge_id(
	knowledge_id: str,
	job_id: str | None = None,
	limit: int = 100
) -> list[TaskDefinition]:
	"""
	Query tasks by knowledge_id, optionally filtered by job_id.
	
	If job_id is provided, returns tasks for that specific job.
	If job_id is None, returns latest tasks (most recent job) for the knowledge_id.
	
	Args:
		knowledge_id: Knowledge ID to query
		job_id: Optional job ID to filter by (if None, gets latest)
		limit: Maximum number of results
	
	Returns:
		List of TaskDefinition objects
	"""
	try:
		collection = await get_tasks_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot query tasks")
			return []

		# Build query
		query: dict[str, Any] = {'knowledge_id': knowledge_id}

		if job_id:
			# Query specific job
			query['job_id'] = job_id
			cursor = collection.find(query).limit(limit)
		else:
			# Get latest (most recent job_id) - sort by MongoDB _id descending
			# Filter out None job_ids (backward compatibility)
			pipeline = [
				{'$match': {'knowledge_id': knowledge_id, 'job_id': {'$exists': True, '$ne': None}}},
				{'$sort': {'_id': -1}},
				{'$group': {'_id': '$job_id', 'first_doc': {'$first': '$$ROOT'}}},
				{'$sort': {'first_doc._id': -1}},
				{'$limit': 1}
			]

			latest_job = None
			async for result in collection.aggregate(pipeline):
				latest_job = result.get('_id')
				break

			if latest_job:
				query['job_id'] = latest_job
			# If no job_id found, query all documents for this knowledge_id (backward compatibility)

			cursor = collection.find(query).limit(limit)

		tasks = []

		async for doc in cursor:
			doc.pop('_id', None)
			try:
				tasks.append(TaskDefinition(**doc))
			except Exception as e:
				logger.warning(f"Failed to parse task document: {e}")
				continue

		return tasks

	except Exception as e:
		logger.error(f"Failed to query tasks by knowledge_id: {e}")
		return []

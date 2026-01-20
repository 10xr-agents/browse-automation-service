"""
Base storage utilities for document persistence.

Shared utilities and common patterns used across all entity storage modules.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def get_latest_job_id_for_knowledge_id(knowledge_id: str) -> str | None:
	"""
	Get the latest (most recent) job_id for a given knowledge_id.
	
	Queries all knowledge collections to find the most recent job_id.
	
	Args:
		knowledge_id: Knowledge ID to query
	
	Returns:
		Latest job_id if found, None otherwise
	"""
	try:
		from navigator.knowledge.persist.collections import (
			get_actions_collection,
			get_screens_collection,
			get_tasks_collection,
		)

		# Try screens collection first (most likely to have data)
		collection = await get_screens_collection()
		if collection is not None:
			pipeline = [
				{'$match': {'knowledge_id': knowledge_id, 'job_id': {'$exists': True, '$ne': None}}},
				{'$sort': {'_id': -1}},
				{'$group': {'_id': '$job_id', 'first_doc': {'$first': '$$ROOT'}}},
				{'$sort': {'first_doc._id': -1}},
				{'$limit': 1}
			]

			async for result in collection.aggregate(pipeline):
				job_id = result.get('_id')
				if job_id:
					return job_id

		# Fallback to tasks collection
		collection = await get_tasks_collection()
		if collection is not None:
			pipeline = [
				{'$match': {'knowledge_id': knowledge_id, 'job_id': {'$exists': True, '$ne': None}}},
				{'$sort': {'_id': -1}},
				{'$group': {'_id': '$job_id', 'first_doc': {'$first': '$$ROOT'}}},
				{'$sort': {'first_doc._id': -1}},
				{'$limit': 1}
			]

			async for result in collection.aggregate(pipeline):
				job_id = result.get('_id')
				if job_id:
					return job_id

		# Fallback to actions collection
		collection = await get_actions_collection()
		if collection is not None:
			pipeline = [
				{'$match': {'knowledge_id': knowledge_id, 'job_id': {'$exists': True, '$ne': None}}},
				{'$sort': {'_id': -1}},
				{'$group': {'_id': '$job_id', 'first_doc': {'$first': '$$ROOT'}}},
				{'$sort': {'first_doc._id': -1}},
				{'$limit': 1}
			]

			async for result in collection.aggregate(pipeline):
				job_id = result.get('_id')
				if job_id:
					return job_id

		return None

	except Exception as e:
		logger.error(f"Failed to get latest job_id for knowledge_id: {e}")
		return None


async def delete_knowledge_by_knowledge_id(knowledge_id: str) -> dict[str, Any]:
	"""
	Delete all knowledge entities associated with a knowledge_id.
	
	This is a utility function that deletes screens, tasks, actions, transitions,
	business functions, and workflows for a given knowledge_id.
	
	Args:
		knowledge_id: Knowledge ID to delete all entities for
	
	Returns:
		Dict with deletion results for each entity type
	"""
	results = {
		'screens_deleted': 0,
		'tasks_deleted': 0,
		'actions_deleted': 0,
		'transitions_deleted': 0,
		'business_functions_deleted': 0,
		'workflows_deleted': 0,
		'total_deleted': 0,
	}

	try:
		from navigator.knowledge.persist.collections import (
			get_actions_collection,
			get_business_functions_collection,
			get_screens_collection,
			get_tasks_collection,
			get_transitions_collection,
			get_workflows_collection,
		)

		# Delete screens
		screens_collection = await get_screens_collection()
		if screens_collection is not None:
			screens_result = await screens_collection.delete_many({'knowledge_id': knowledge_id})
			results['screens_deleted'] = screens_result.deleted_count

		# Delete tasks
		tasks_collection = await get_tasks_collection()
		if tasks_collection is not None:
			tasks_result = await tasks_collection.delete_many({'knowledge_id': knowledge_id})
			results['tasks_deleted'] = tasks_result.deleted_count

		# Delete actions
		actions_collection = await get_actions_collection()
		if actions_collection is not None:
			actions_result = await actions_collection.delete_many({'knowledge_id': knowledge_id})
			results['actions_deleted'] = actions_result.deleted_count

		# Delete transitions
		transitions_collection = await get_transitions_collection()
		if transitions_collection is not None:
			transitions_result = await transitions_collection.delete_many({'knowledge_id': knowledge_id})
			results['transitions_deleted'] = transitions_result.deleted_count

		# Delete business functions
		business_functions_collection = await get_business_functions_collection()
		if business_functions_collection is not None:
			bf_result = await business_functions_collection.delete_many({'knowledge_id': knowledge_id})
			results['business_functions_deleted'] = bf_result.deleted_count

		# Delete workflows
		workflows_collection = await get_workflows_collection()
		if workflows_collection is not None:
			workflows_result = await workflows_collection.delete_many({'knowledge_id': knowledge_id})
			results['workflows_deleted'] = workflows_result.deleted_count

		results['total_deleted'] = (
			results['screens_deleted'] +
			results['tasks_deleted'] +
			results['actions_deleted'] +
			results['transitions_deleted'] +
			results['business_functions_deleted'] +
			results['workflows_deleted']
		)

		logger.info(
			f"Deleted knowledge_id={knowledge_id}: "
			f"{results['total_deleted']} total entities "
			f"(screens={results['screens_deleted']}, "
			f"tasks={results['tasks_deleted']}, "
			f"actions={results['actions_deleted']}, "
			f"transitions={results['transitions_deleted']}, "
			f"business_functions={results['business_functions_deleted']}, "
			f"workflows={results['workflows_deleted']})"
		)

		return results

	except Exception as e:
		logger.error(f"Failed to delete knowledge by knowledge_id: {e}")
		return results

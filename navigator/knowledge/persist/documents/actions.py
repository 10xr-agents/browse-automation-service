"""
Action storage functions.

Handles persistence of ActionDefinition objects in MongoDB.
"""

import logging
from typing import Any

from navigator.knowledge.extract.actions import ActionDefinition
from navigator.knowledge.persist.collections import get_actions_collection

logger = logging.getLogger(__name__)


async def save_action(
	action: ActionDefinition,
	knowledge_id: str | None = None,
	job_id: str | None = None
) -> bool:
	"""
	Save full action definition to MongoDB.
	
	Args:
		action: ActionDefinition to save
		knowledge_id: Optional knowledge ID for persistence and querying
		job_id: Optional job ID for historical tracking
	
	Returns:
		True if saved successfully, False otherwise
	"""
	try:
		collection = await get_actions_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, action not persisted")
			return False

		# Convert to dict for MongoDB storage
		action_dict = action.dict(exclude_none=True)

		# Add knowledge_id if provided
		if knowledge_id:
			action_dict['knowledge_id'] = knowledge_id

		# Add job_id if provided (for historical tracking)
		if job_id:
			action_dict['job_id'] = job_id

		# Upsert by action_id
		await collection.update_one(
			{'action_id': action.action_id},
			{'$set': action_dict},
			upsert=True
		)

		# Update cross-references (Phase 2: CrossReferenceManager)
		from navigator.knowledge.persist.cross_references import get_cross_reference_manager
		cross_ref_manager = get_cross_reference_manager()

		# Link action to screens if screen_ids are set
		if hasattr(action, 'screen_ids') and action.screen_ids:
			for screen_id in action.screen_ids:
				await cross_ref_manager.link_screen_to_action(
					screen_id,
					action.action_id,
					knowledge_id
				)

		logger.info(f"Saved action: action_id={action.action_id}, name={action.name}, knowledge_id={knowledge_id}, job_id={job_id}")
		return True

	except Exception as e:
		logger.error(f"Failed to save action: {e}")
		return False


async def save_actions(
	actions: list[ActionDefinition],
	knowledge_id: str | None = None,
	job_id: str | None = None
) -> dict[str, Any]:
	"""
	Save multiple action definitions (batch operation).
	
	Args:
		actions: List of ActionDefinition objects
		knowledge_id: Optional knowledge ID for persistence and querying
		job_id: Optional job ID for historical tracking
	
	Returns:
		Dict with 'saved', 'failed', 'total' counts
	"""
	results = {'saved': 0, 'failed': 0, 'total': len(actions)}

	for action in actions:
		success = await save_action(action, knowledge_id=knowledge_id, job_id=job_id)
		if success:
			results['saved'] += 1
		else:
			results['failed'] += 1

	logger.info(f"Saved {results['saved']}/{results['total']} actions")
	return results


async def get_action(action_id: str) -> ActionDefinition | None:
	"""
	Retrieve action definition by action_id.
	
	Args:
		action_id: Action ID to retrieve
	
	Returns:
		ActionDefinition if found, None otherwise
	"""
	try:
		collection = await get_actions_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot retrieve action")
			return None

		doc = await collection.find_one({'action_id': action_id})
		if doc is None:
			return None

		# Remove MongoDB _id field
		doc.pop('_id', None)

		# Reconstruct ActionDefinition from dict
		return ActionDefinition(**doc)

	except Exception as e:
		logger.error(f"Failed to get action: {e}")
		return None


async def query_actions_by_knowledge_id(
	knowledge_id: str,
	job_id: str | None = None,
	limit: int = 100
) -> list[ActionDefinition]:
	"""
	Query actions by knowledge_id, optionally filtered by job_id.
	
	If job_id is provided, returns actions for that specific job.
	If job_id is None, returns latest actions (most recent job) for the knowledge_id.
	
	Args:
		knowledge_id: Knowledge ID to query
		job_id: Optional job ID to filter by (if None, gets latest)
		limit: Maximum number of results
	
	Returns:
		List of ActionDefinition objects
	"""
	try:
		collection = await get_actions_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot query actions")
			return []

		# Build query
		query: dict[str, Any] = {'knowledge_id': knowledge_id}

		if job_id:
			# Query specific job
			query['job_id'] = job_id
			cursor = collection.find(query).limit(limit)
		else:
			# Get latest (most recent job_id) - filter out None job_ids
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

		actions = []

		async for doc in cursor:
			doc.pop('_id', None)
			try:
				actions.append(ActionDefinition(**doc))
			except Exception as e:
				logger.warning(f"Failed to parse action document: {e}")
				continue

		return actions

	except Exception as e:
		logger.error(f"Failed to query actions by knowledge_id: {e}")
		return []

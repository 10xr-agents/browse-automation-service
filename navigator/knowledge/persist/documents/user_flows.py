"""
User flow storage functions.

Handles persistence of UserFlow objects in MongoDB.
"""

import logging
from typing import Any

from navigator.knowledge.extract.user_flows import UserFlow
from navigator.knowledge.persist.collections import get_user_flows_collection

logger = logging.getLogger(__name__)


async def save_user_flow(
	user_flow: UserFlow,
	knowledge_id: str | None = None,
	job_id: str | None = None
) -> bool:
	"""
	Save full user flow definition to MongoDB.
	
	Args:
		user_flow: UserFlow to save
		knowledge_id: Optional knowledge ID for persistence and querying
		job_id: Optional job ID for historical tracking
	
	Returns:
		True if saved successfully, False otherwise
	"""
	try:
		collection = await get_user_flows_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, user flow not persisted")
			return False

		# Convert to dict for MongoDB storage
		flow_dict = user_flow.dict(exclude_none=True)

		# Add knowledge_id if provided
		if knowledge_id:
			flow_dict['knowledge_id'] = knowledge_id

		# Add job_id if provided (for historical tracking)
		if job_id:
			flow_dict['job_id'] = job_id

		# Upsert by user_flow_id
		await collection.update_one(
			{'user_flow_id': user_flow.user_flow_id},
			{'$set': flow_dict},
			upsert=True
		)

		# Update cross-references (Phase 2: CrossReferenceManager)
		from navigator.knowledge.persist.cross_references import get_cross_reference_manager
		cross_ref_manager = get_cross_reference_manager()

		# Link user flow to screens
		if hasattr(user_flow, 'related_screens') and user_flow.related_screens:
			for screen_id in user_flow.related_screens:
				await cross_ref_manager.link_user_flow_to_screen(
					user_flow.user_flow_id,
					screen_id,
					knowledge_id=knowledge_id
				)

		# Link user flow to business functions
		if hasattr(user_flow, 'related_business_functions') and user_flow.related_business_functions:
			for bf_id in user_flow.related_business_functions:
				await cross_ref_manager.link_business_function_to_user_flow(
					bf_id,
					user_flow.user_flow_id,
					knowledge_id
				)

		# Link user flow to actions
		if hasattr(user_flow, 'related_actions') and user_flow.related_actions:
			from navigator.knowledge.persist.collections import get_actions_collection
			actions_collection = await get_actions_collection()
			if actions_collection:
				for action_id in user_flow.related_actions:
					action_query = {'action_id': action_id}
					if knowledge_id:
						action_query['knowledge_id'] = knowledge_id
					await actions_collection.update_one(
						action_query,
						{'$addToSet': {'user_flow_ids': user_flow.user_flow_id}},
						upsert=False
					)

		# Link user flow to tasks
		if hasattr(user_flow, 'related_tasks') and user_flow.related_tasks:
			from navigator.knowledge.persist.collections import get_tasks_collection
			tasks_collection = await get_tasks_collection()
			if tasks_collection:
				for task_id in user_flow.related_tasks:
					task_query = {'task_id': task_id}
					if knowledge_id:
						task_query['knowledge_id'] = knowledge_id
					await tasks_collection.update_one(
						task_query,
						{'$addToSet': {'user_flow_ids': user_flow.user_flow_id}},
						upsert=False
					)

		logger.info(
			f"Saved user flow: user_flow_id={user_flow.user_flow_id}, "
			f"name={user_flow.name}, knowledge_id={knowledge_id}, job_id={job_id}"
		)
		return True

	except Exception as e:
		logger.error(f"Failed to save user flow: {e}")
		return False


async def save_user_flows(
	user_flows: list[UserFlow],
	knowledge_id: str | None = None,
	job_id: str | None = None
) -> dict[str, Any]:
	"""
	Save multiple user flow definitions (batch operation).
	
	Args:
		user_flows: List of UserFlow objects
		knowledge_id: Optional knowledge ID for persistence and querying
		job_id: Optional job ID for historical tracking
	
	Returns:
		Dict with 'saved', 'failed', 'total' counts
	"""
	results = {'saved': 0, 'failed': 0, 'total': len(user_flows)}

	for user_flow in user_flows:
		success = await save_user_flow(user_flow, knowledge_id=knowledge_id, job_id=job_id)
		if success:
			results['saved'] += 1
		else:
			results['failed'] += 1

	logger.info(f"Saved {results['saved']}/{results['total']} user flows")
	return results


async def get_user_flow(user_flow_id: str) -> UserFlow | None:
	"""
	Retrieve user flow definition by user_flow_id.
	
	Args:
		user_flow_id: User flow ID to retrieve
	
	Returns:
		UserFlow if found, None otherwise
	"""
	try:
		collection = await get_user_flows_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot retrieve user flow")
			return None

		doc = await collection.find_one({'user_flow_id': user_flow_id})
		if doc is None:
			return None

		# Remove MongoDB _id field
		doc.pop('_id', None)

		# Reconstruct UserFlow from dict
		return UserFlow(**doc)

	except Exception as e:
		logger.error(f"Failed to get user flow: {e}")
		return None


async def query_user_flows_by_knowledge_id(
	knowledge_id: str,
	job_id: str | None = None,
	limit: int = 1000
) -> list[UserFlow]:
	"""
	Query user flows by knowledge_id, optionally filtered by job_id.
	
	If job_id is provided, returns user flows for that specific job.
	If job_id is None, returns latest user flows (most recent job) for the knowledge_id.
	
	Args:
		knowledge_id: Knowledge ID to query
		job_id: Optional job ID to filter by (if None, gets latest)
		limit: Maximum number of results
	
	Returns:
		List of UserFlow objects
	"""
	try:
		collection = await get_user_flows_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot query user flows")
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

		user_flows = []

		async for doc in cursor:
			doc.pop('_id', None)
			try:
				user_flows.append(UserFlow(**doc))
			except Exception as e:
				logger.warning(f"Failed to parse user flow document: {e}")
				continue

		return user_flows

	except Exception as e:
		logger.error(f"Failed to query user flows by knowledge_id: {e}")
		return []


async def query_user_flows_by_business_function(
	business_function_id: str,
	knowledge_id: str | None = None,
	limit: int = 100
) -> list[UserFlow]:
	"""
	Query user flows by business function ID.
	
	Args:
		business_function_id: Business function ID to query
		knowledge_id: Optional knowledge ID filter
		limit: Maximum number of results
	
	Returns:
		List of UserFlow objects
	"""
	try:
		collection = await get_user_flows_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot query user flows")
			return []

		query: dict[str, Any] = {'related_business_functions': business_function_id}
		if knowledge_id:
			query['knowledge_id'] = knowledge_id

		cursor = collection.find(query).limit(limit)
		user_flows = []

		async for doc in cursor:
			doc.pop('_id', None)
			try:
				user_flows.append(UserFlow(**doc))
			except Exception as e:
				logger.warning(f"Failed to parse user flow document: {e}")
				continue

		return user_flows

	except Exception as e:
		logger.error(f"Failed to query user flows by business function: {e}")
		return []


async def query_user_flows_by_category(
	category: str,
	knowledge_id: str | None = None,
	limit: int = 100
) -> list[UserFlow]:
	"""
	Query user flows by category.
	
	Args:
		category: Flow category (authentication, purchase, content_creation, etc.)
		knowledge_id: Optional knowledge ID filter
		limit: Maximum number of results
	
	Returns:
		List of UserFlow objects
	"""
	try:
		collection = await get_user_flows_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot query user flows")
			return []

		query: dict[str, Any] = {'category': category}
		if knowledge_id:
			query['knowledge_id'] = knowledge_id

		cursor = collection.find(query).limit(limit)
		user_flows = []

		async for doc in cursor:
			doc.pop('_id', None)
			try:
				user_flows.append(UserFlow(**doc))
			except Exception as e:
				logger.warning(f"Failed to parse user flow document: {e}")
				continue

		return user_flows

	except Exception as e:
		logger.error(f"Failed to query user flows by category: {e}")
		return []

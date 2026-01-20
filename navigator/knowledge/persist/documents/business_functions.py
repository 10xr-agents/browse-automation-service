"""
Business function storage functions.

Handles persistence of BusinessFunction objects in MongoDB.
"""

import logging
from typing import Any

from navigator.knowledge.extract.business_functions import BusinessFunction
from navigator.knowledge.persist.collections import get_business_functions_collection

logger = logging.getLogger(__name__)


async def save_business_function(
	business_function: BusinessFunction,
	knowledge_id: str | None = None,
	job_id: str | None = None
) -> bool:
	"""
	Save full business function definition to MongoDB.
	
	Args:
		business_function: BusinessFunction to save
		knowledge_id: Optional knowledge ID for persistence and querying
		job_id: Optional job ID for historical tracking
	
	Returns:
		True if saved successfully, False otherwise
	"""
	try:
		collection = await get_business_functions_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, business function not persisted")
			return False

		# Convert to dict for MongoDB storage
		bf_dict = business_function.dict(exclude_none=True)

		# Add knowledge_id if provided
		if knowledge_id:
			bf_dict['knowledge_id'] = knowledge_id

		# Add job_id if provided (for historical tracking)
		if job_id:
			bf_dict['job_id'] = job_id

		# Upsert by business_function_id
		await collection.update_one(
			{'business_function_id': business_function.business_function_id},
			{'$set': bf_dict},
			upsert=True
		)

		# Update cross-references (Phase 2: CrossReferenceManager)
		from navigator.knowledge.persist.cross_references import get_cross_reference_manager
		cross_ref_manager = get_cross_reference_manager()

		# Link business function to screens if related_screens are set
		if hasattr(business_function, 'related_screens') and business_function.related_screens:
			for screen_id in business_function.related_screens:
				await cross_ref_manager.update_screen_references_from_entity(
					screen_id,
					'business_function',
					business_function.business_function_id,
					knowledge_id
				)

		logger.info(
			f"Saved business function: "
			f"business_function_id={business_function.business_function_id}, "
			f"name={business_function.name}, "
			f"knowledge_id={knowledge_id}, job_id={job_id}"
		)
		return True

	except Exception as e:
		logger.error(f"Failed to save business function: {e}")
		return False


async def save_business_functions(
	business_functions: list[BusinessFunction],
	knowledge_id: str | None = None,
	job_id: str | None = None
) -> dict[str, Any]:
	"""
	Save multiple business function definitions (batch operation).
	
	Args:
		business_functions: List of BusinessFunction objects
		knowledge_id: Optional knowledge ID for persistence and querying
		job_id: Optional job ID for historical tracking
	
	Returns:
		Dict with 'saved', 'failed', 'total' counts
	"""
	results = {'saved': 0, 'failed': 0, 'total': len(business_functions)}

	for business_function in business_functions:
		success = await save_business_function(business_function, knowledge_id=knowledge_id, job_id=job_id)
		if success:
			results['saved'] += 1
		else:
			results['failed'] += 1

	logger.info(f"Saved {results['saved']}/{results['total']} business functions")
	return results


async def get_business_function(business_function_id: str) -> BusinessFunction | None:
	"""
	Retrieve business function definition by business_function_id.
	
	Args:
		business_function_id: Business function ID to retrieve
	
	Returns:
		BusinessFunction if found, None otherwise
	"""
	try:
		collection = await get_business_functions_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot retrieve business function")
			return None

		doc = await collection.find_one({'business_function_id': business_function_id})
		if doc is None:
			return None

		# Remove MongoDB _id field
		doc.pop('_id', None)

		# Reconstruct BusinessFunction from dict
		return BusinessFunction(**doc)

	except Exception as e:
		logger.error(f"Failed to get business function: {e}")
		return None


async def query_business_functions_by_website(website_id: str, limit: int = 100) -> list[BusinessFunction]:
	"""
	Query business functions by website_id.
	
	Args:
		website_id: Website ID to query
		limit: Maximum number of results
	
	Returns:
		List of BusinessFunction objects
	"""
	try:
		collection = await get_business_functions_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot query business functions")
			return []

		cursor = collection.find({'website_id': website_id}).limit(limit)
		business_functions = []

		async for doc in cursor:
			doc.pop('_id', None)
			try:
				business_functions.append(BusinessFunction(**doc))
			except Exception as e:
				logger.warning(f"Failed to parse business function document: {e}")
				continue

		return business_functions

	except Exception as e:
		logger.error(f"Failed to query business functions by website: {e}")
		return []


async def query_business_functions_by_knowledge_id(
	knowledge_id: str,
	job_id: str | None = None,
	limit: int = 100
) -> list[BusinessFunction]:
	"""
	Query business functions by knowledge_id, optionally filtered by job_id.
	
	If job_id is provided, returns business functions for that specific job.
	If job_id is None, returns latest business functions (most recent job) for the knowledge_id.
	
	Args:
		knowledge_id: Knowledge ID to query
		job_id: Optional job ID to filter by (if None, gets latest)
		limit: Maximum number of results
	
	Returns:
		List of BusinessFunction objects
	"""
	try:
		collection = await get_business_functions_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot query business functions")
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

		business_functions = []

		async for doc in cursor:
			doc.pop('_id', None)
			try:
				business_functions.append(BusinessFunction(**doc))
			except Exception as e:
				logger.warning(f"Failed to parse business function document: {e}")
				continue

		return business_functions

	except Exception as e:
		logger.error(f"Failed to query business functions by knowledge_id: {e}")
		return []


async def query_business_functions_by_category(category: str, limit: int = 100) -> list[BusinessFunction]:
	"""
	Query business functions by category.
	
	Args:
		category: Category to query
		limit: Maximum number of results
	
	Returns:
		List of BusinessFunction objects
	"""
	try:
		collection = await get_business_functions_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot query business functions")
			return []

		cursor = collection.find({'category': category}).limit(limit)
		business_functions = []

		async for doc in cursor:
			doc.pop('_id', None)
			try:
				business_functions.append(BusinessFunction(**doc))
			except Exception as e:
				logger.warning(f"Failed to parse business function document: {e}")
				continue

		return business_functions

	except Exception as e:
		logger.error(f"Failed to query business functions by category: {e}")
		return []

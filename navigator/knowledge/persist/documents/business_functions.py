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

		# Phase 3.4: Update cross-references (enhanced to link to all entity types)
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

		# Phase 3.4: Link business function to actions if related_actions are set
		if hasattr(business_function, 'related_actions') and business_function.related_actions:
			for action_id in business_function.related_actions:
				await cross_ref_manager.link_entity_to_business_function(
					'action',
					action_id,
					business_function.business_function_id,
					knowledge_id
				)

		# Phase 3.4: Link business function to tasks if related_tasks are set
		if hasattr(business_function, 'related_tasks') and business_function.related_tasks:
			for task_id in business_function.related_tasks:
				await cross_ref_manager.link_entity_to_business_function(
					'task',
					task_id,
					business_function.business_function_id,
					knowledge_id
				)

		# Phase 3.4: Link business function to workflows if related_workflows are set
		if hasattr(business_function, 'related_workflows') and business_function.related_workflows:
			for workflow_id in business_function.related_workflows:
				await cross_ref_manager.link_entity_to_business_function(
					'workflow',
					workflow_id,
					business_function.business_function_id,
					knowledge_id
				)

		# Phase 3.4: Link business function to user flows if related_user_flows are set
		if hasattr(business_function, 'related_user_flows') and business_function.related_user_flows:
			for user_flow_id in business_function.related_user_flows:
				await cross_ref_manager.link_business_function_to_user_flow(
					business_function.business_function_id,
					user_flow_id,
					knowledge_id
				)
		
		# Priority 6: Link business function to screens mentioned in documentation
		# Enhanced with fuzzy matching and support for both web_ui and documentation screens
		if hasattr(business_function, 'metadata') and business_function.metadata:
			screens_mentioned = business_function.metadata.get('screens_mentioned', [])
			if screens_mentioned:
				# Priority 6: Query all screens (both web_ui and documentation) for matching
				from navigator.knowledge.persist.documents.screens import query_screens_by_knowledge_id
				from navigator.knowledge.persist.linking_helpers import find_screens_by_name
				
				# Get all screens (web_ui and documentation) for matching
				all_screens = await query_screens_by_knowledge_id(
					knowledge_id=knowledge_id,
					job_id=job_id,
					limit=1000,  # Get all screens for matching
					content_type=None,  # Priority 6: Get all content types (web_ui and documentation)
					actionable_only=False  # Priority 6: Include non-actionable documentation screens
				)
				
				# Priority 6: Match screens by name using fuzzy matching
				matched_screen_ids = []
				unmatched_screen_names = []
				
				for screen_name in screens_mentioned:
					# Priority 6: Use fuzzy matching to find screens
					matched_screens = find_screens_by_name(
						screen_name,
						all_screens,
						fuzzy=True,  # Priority 6: Enable fuzzy matching
						threshold=0.6  # Priority 6: Similarity threshold (60% match required)
					)
					
					if matched_screens:
						# Link all matched screens to business function
						for screen in matched_screens:
							if screen.screen_id not in matched_screen_ids:
								matched_screen_ids.append(screen.screen_id)
								# Link screen to business function (bidirectional)
								await cross_ref_manager.link_entity_to_business_function(
									'screen',
									screen.screen_id,
									business_function.business_function_id,
									knowledge_id
								)
								logger.debug(
									f"Priority 6: Linked screen '{screen.name}' (content_type={screen.content_type}) "
									f"to business function '{business_function.name}' "
									f"via screens_mentioned '{screen_name}' (fuzzy match)"
								)
					else:
						# Priority 6: Track unmatched screens for potential placeholder links
						unmatched_screen_names.append(screen_name)
						logger.debug(
							f"Priority 6: No match found for screens_mentioned '{screen_name}' "
							f"in business function '{business_function.name}'"
						)
				
				if matched_screen_ids:
					logger.info(
						f"Priority 6: Linked {len(matched_screen_ids)} screens (fuzzy matching) "
						f"to business function '{business_function.name}' "
						f"from {len(screens_mentioned)} screens_mentioned"
					)
				
				# Priority 6: Log unmatched screens (for potential placeholder links in future)
				if unmatched_screen_names:
					logger.debug(
						f"Priority 6: {len(unmatched_screen_names)} unmatched screens_mentioned "
						f"for business function '{business_function.name}': {unmatched_screen_names}"
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

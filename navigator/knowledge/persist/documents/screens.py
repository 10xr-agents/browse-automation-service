"""
Screen storage functions.

Handles persistence of ScreenDefinition objects in MongoDB.
"""

import logging
from typing import Any

from navigator.knowledge.extract.screens import ScreenDefinition
from navigator.knowledge.persist.collections import get_screens_collection

logger = logging.getLogger(__name__)


async def save_screen(
	screen: ScreenDefinition,
	knowledge_id: str | None = None,
	job_id: str | None = None
) -> bool:
	"""
	Save full screen definition to MongoDB.
	
	Args:
		screen: ScreenDefinition to save
		knowledge_id: Optional knowledge ID for persistence and querying
		job_id: Optional job ID for historical tracking
	
	Returns:
		True if saved successfully, False otherwise
	"""
	try:
		collection = await get_screens_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, screen not persisted")
			return False

		# Convert to dict for MongoDB storage
		screen_dict = screen.dict(exclude_none=True)

		# Add knowledge_id if provided
		if knowledge_id:
			screen_dict['knowledge_id'] = knowledge_id

		# Add job_id if provided (for historical tracking)
		if job_id:
			screen_dict['job_id'] = job_id

		# Upsert by screen_id
		await collection.update_one(
			{'screen_id': screen.screen_id},
			{'$set': screen_dict},
			upsert=True
		)

		logger.info(f"Saved screen: screen_id={screen.screen_id}, name={screen.name}, knowledge_id={knowledge_id}, job_id={job_id}")
		return True

	except Exception as e:
		logger.error(f"Failed to save screen: {e}")
		return False


async def save_screens(
	screens: list[ScreenDefinition],
	knowledge_id: str | None = None,
	job_id: str | None = None
) -> dict[str, Any]:
	"""
	Save multiple screen definitions (batch operation).
	
	Args:
		screens: List of ScreenDefinition objects
		knowledge_id: Optional knowledge ID for persistence and querying
		job_id: Optional job ID for historical tracking
	
	Returns:
		Dict with 'saved', 'failed', 'total' counts
	"""
	results = {'saved': 0, 'failed': 0, 'total': len(screens)}

	for screen in screens:
		success = await save_screen(screen, knowledge_id=knowledge_id, job_id=job_id)
		if success:
			results['saved'] += 1
		else:
			results['failed'] += 1

	logger.info(f"Saved {results['saved']}/{results['total']} screens")
	return results


async def get_screen(screen_id: str) -> ScreenDefinition | None:
	"""
	Retrieve screen definition by screen_id.
	
	Args:
		screen_id: Screen ID to retrieve
	
	Returns:
		ScreenDefinition if found, None otherwise
	"""
	try:
		collection = await get_screens_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot retrieve screen")
			return None

		doc = await collection.find_one({'screen_id': screen_id})
		if doc is None:
			return None

		# Remove MongoDB _id field
		doc.pop('_id', None)

		# Reconstruct ScreenDefinition from dict
		return ScreenDefinition(**doc)

	except Exception as e:
		logger.error(f"Failed to get screen: {e}")
		return None


async def query_screens_by_website(
	website_id: str,
	limit: int = 100,
	content_type: str | None = None,
	actionable_only: bool = False
) -> list[ScreenDefinition]:
	"""
	Query screens by website_id.
	
	Args:
		website_id: Website ID to query
		limit: Maximum number of results
		content_type: Optional content type filter ('web_ui', 'documentation', etc.)
		actionable_only: If True, only return screens with is_actionable=True
	
	Returns:
		List of ScreenDefinition objects
	"""
	try:
		collection = await get_screens_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot query screens")
			return []

		# Build query
		query: dict[str, Any] = {'website_id': website_id}
		
		# Add content type filter (Phase 1)
		if content_type:
			query['content_type'] = content_type
		
		# Add actionable filter (Phase 1)
		if actionable_only:
			query['is_actionable'] = True

		cursor = collection.find(query).limit(limit)
		screens = []

		async for doc in cursor:
			doc.pop('_id', None)
			try:
				screens.append(ScreenDefinition(**doc))
			except Exception as e:
				logger.warning(f"Failed to parse screen document: {e}")
				continue

		return screens

	except Exception as e:
		logger.error(f"Failed to query screens by website: {e}")
		return []


async def query_screens_by_knowledge_id(
	knowledge_id: str,
	job_id: str | None = None,
	limit: int = 100,
	content_type: str | None = None,
	actionable_only: bool = False
) -> list[ScreenDefinition]:
	"""
	Query screens by knowledge_id, optionally filtered by job_id.
	
	If job_id is provided, returns screens for that specific job.
	If job_id is None, returns latest screens (most recent job) for the knowledge_id.
	
	Args:
		knowledge_id: Knowledge ID to query
		job_id: Optional job ID to filter by (if None, gets latest)
		limit: Maximum number of results
		content_type: Optional content type filter ('web_ui', 'documentation', etc.)
		actionable_only: If True, only return screens with is_actionable=True
	
	Returns:
		List of ScreenDefinition objects
	"""
	try:
		collection = await get_screens_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot query screens")
			return []

		# Build query
		query: dict[str, Any] = {'knowledge_id': knowledge_id}
		
		# Add content type filter (Phase 1)
		if content_type:
			query['content_type'] = content_type
		
		# Add actionable filter (Phase 1)
		if actionable_only:
			query['is_actionable'] = True

		# Track which job_id we're querying (for return value)
		actual_job_id = job_id

		if job_id:
			# Query specific job
			query['job_id'] = job_id
			cursor = collection.find(query).limit(limit)
		else:
			# Get latest (most recent job_id) - sort by MongoDB _id descending
			# First try to find documents with job_id
			pipeline = [
				{'$match': {'knowledge_id': knowledge_id, 'job_id': {'$exists': True, '$ne': None}}},
				{'$sort': {'_id': -1}},  # Sort by MongoDB _id (creation time) descending
				{'$group': {'_id': '$job_id', 'first_doc': {'$first': '$$ROOT'}}},
				{'$sort': {'first_doc._id': -1}},
				{'$limit': 1}
			]

			latest_job = None
			async for result in collection.aggregate(pipeline):
				latest_job = result.get('_id')
				break

			if latest_job:
				# Filter by latest job_id
				query['job_id'] = latest_job
			# If no job_id found, query all documents for this knowledge_id (backward compatibility)
			# This handles old data that doesn't have job_id

			cursor = collection.find(query).limit(limit)

		screens = []

		async for doc in cursor:
			doc.pop('_id', None)
			try:
				screens.append(ScreenDefinition(**doc))
			except Exception as e:
				logger.warning(f"Failed to parse screen document: {e}")
				continue

		return screens

	except Exception as e:
		logger.error(f"Failed to query screens by knowledge_id: {e}")
		return []


async def query_screens_by_name_pattern(
	screen_name: str,
	website_id: str | None = None,
	limit: int = 100
) -> list[ScreenDefinition]:
	"""
	Query screens by name pattern (partial match, case-insensitive).
	
	Args:
		screen_name: Screen name pattern to search (partial match)
		website_id: Optional website identifier filter
		limit: Maximum number of results (default: 100)
	
	Returns:
		List of ScreenDefinition objects
	"""
	try:
		collection = await get_screens_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot query screens")
			return []

		# Build query
		query = {}
		if website_id:
			query['website_id'] = website_id

		# Use regex for case-insensitive partial match
		import re
		query['name'] = {'$regex': re.escape(screen_name), '$options': 'i'}

		cursor = collection.find(query).limit(limit)
		screens = []

		async for doc in cursor:
			doc.pop('_id', None)
			try:
				screens.append(ScreenDefinition(**doc))
			except Exception as e:
				logger.warning(f"Failed to parse screen document: {e}")
				continue

		return screens

	except Exception as e:
		logger.error(f"Failed to query screens by name pattern: {e}")
		return []


async def delete_screen(screen_id: str) -> bool:
	"""
	Delete screen by screen_id.
	
	Args:
		screen_id: Screen ID to delete
	
	Returns:
		True if deleted successfully, False otherwise
	"""
	try:
		collection = await get_screens_collection()
		if collection is None:
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

"""
Transition storage functions.

Handles persistence of TransitionDefinition objects in MongoDB.
"""

import logging
from typing import Any

from navigator.knowledge.extract.transitions import TransitionDefinition
from navigator.knowledge.persist.collections import get_transitions_collection

logger = logging.getLogger(__name__)


async def save_transition(
	transition: TransitionDefinition,
	knowledge_id: str | None = None,
	job_id: str | None = None
) -> bool:
	"""
	Save full transition definition to MongoDB.
	
	Args:
		transition: TransitionDefinition to save
		knowledge_id: Optional knowledge ID for persistence and querying
		job_id: Optional job ID for historical tracking
	
	Returns:
		True if saved successfully, False otherwise
	"""
	try:
		collection = await get_transitions_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, transition not persisted")
			return False

		# Convert to dict for MongoDB storage
		transition_dict = transition.dict(exclude_none=True)

		# Add knowledge_id if provided
		if knowledge_id:
			transition_dict['knowledge_id'] = knowledge_id

		# Add job_id if provided (for historical tracking)
		if job_id:
			transition_dict['job_id'] = job_id

		# Sync delay intelligence if available (from DelayTracker) - do this BEFORE saving
		if transition.delay_intelligence is None:
			try:
				from navigator.knowledge.delay_intelligence_sync import get_delay_intelligence_for_transition
				# Get delay intelligence directly (non-blocking, won't fail if not available)
				delay_intel = get_delay_intelligence_for_transition(transition.transition_id, min_samples=1)
				if delay_intel:
					transition.delay_intelligence = delay_intel
					transition_dict['delay_intelligence'] = delay_intel
					# Update cost.estimated_ms with actual delay
					transition.cost['estimated_ms'] = delay_intel['recommended_wait_time_ms']
					transition.cost['actual_avg_ms'] = delay_intel['average_delay_ms']
					transition.cost['confidence'] = delay_intel['confidence']
					transition_dict['cost'] = transition.cost
			except Exception as e:
				logger.debug(f"Could not get delay intelligence for transition {transition.transition_id}: {e}")
		
		# Upsert by transition_id
		await collection.update_one(
			{'transition_id': transition.transition_id},
			{'$set': transition_dict},
			upsert=True
		)

		# Update cross-references (Phase 2: CrossReferenceManager)
		from navigator.knowledge.persist.cross_references import get_cross_reference_manager
		cross_ref_manager = get_cross_reference_manager()

		# Link transition to source and target screens
		if transition.from_screen_id and transition.to_screen_id:
			await cross_ref_manager.link_transition_to_screens(
				transition.transition_id,
				transition.from_screen_id,
				transition.to_screen_id,
				knowledge_id
			)

		# Link transition to action if triggered_by.element_id exists
		if transition.triggered_by and transition.triggered_by.element_id:
			await cross_ref_manager.link_transition_to_action(
				transition.transition_id,
				transition.triggered_by.element_id,
				knowledge_id
			)

		logger.info(f"Saved transition: transition_id={transition.transition_id}, knowledge_id={knowledge_id}, job_id={job_id}")
		return True

	except Exception as e:
		logger.error(f"Failed to save transition: {e}")
		return False


async def save_transitions(
	transitions: list[TransitionDefinition],
	knowledge_id: str | None = None,
	job_id: str | None = None
) -> dict[str, Any]:
	"""
	Save multiple transition definitions (batch operation).
	
	Args:
		transitions: List of TransitionDefinition objects
		knowledge_id: Optional knowledge ID for persistence and querying
		job_id: Optional job ID for historical tracking
	
	Returns:
		Dict with 'saved', 'failed', 'total' counts
	"""
	results = {'saved': 0, 'failed': 0, 'total': len(transitions)}

	for transition in transitions:
		success = await save_transition(transition, knowledge_id=knowledge_id, job_id=job_id)
		if success:
			results['saved'] += 1
		else:
			results['failed'] += 1

	logger.info(f"Saved {results['saved']}/{results['total']} transitions")
	return results


async def get_transition(transition_id: str) -> TransitionDefinition | None:
	"""
	Retrieve transition definition by transition_id.
	
	Args:
		transition_id: Transition ID to retrieve
	
	Returns:
		TransitionDefinition if found, None otherwise
	"""
	try:
		collection = await get_transitions_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot retrieve transition")
			return None

		doc = await collection.find_one({'transition_id': transition_id})
		if doc is None:
			return None

		# Remove MongoDB _id field
		doc.pop('_id', None)

		# Reconstruct TransitionDefinition from dict
		return TransitionDefinition(**doc)

	except Exception as e:
		logger.error(f"Failed to get transition: {e}")
		return None


async def query_transitions_by_source(source_screen_id: str, limit: int = 100) -> list[TransitionDefinition]:
	"""
	Query transitions by source screen_id.
	
	Args:
		source_screen_id: Source screen ID to query
		limit: Maximum number of results
	
	Returns:
		List of TransitionDefinition objects
	"""
	try:
		collection = await get_transitions_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot query transitions")
			return []

		cursor = collection.find({'from_screen_id': source_screen_id}).limit(limit)
		transitions = []

		async for doc in cursor:
			doc.pop('_id', None)
			try:
				transitions.append(TransitionDefinition(**doc))
			except Exception as e:
				logger.warning(f"Failed to parse transition document: {e}")
				continue

		return transitions

	except Exception as e:
		logger.error(f"Failed to query transitions by source: {e}")
		return []


async def query_transitions_by_target(target_screen_id: str, limit: int = 100) -> list[TransitionDefinition]:
	"""
	Query transitions by target screen_id.
	
	Args:
		target_screen_id: Target screen ID to query
		limit: Maximum number of results
	
	Returns:
		List of TransitionDefinition objects
	"""
	try:
		collection = await get_transitions_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot query transitions")
			return []

		cursor = collection.find({'to_screen_id': target_screen_id}).limit(limit)
		transitions = []

		async for doc in cursor:
			doc.pop('_id', None)
			try:
				transitions.append(TransitionDefinition(**doc))
			except Exception as e:
				logger.warning(f"Failed to parse transition document: {e}")
				continue

		return transitions

	except Exception as e:
		logger.error(f"Failed to query transitions by target: {e}")
		return []


async def query_transitions_by_website(website_id: str, limit: int = 1000) -> list[TransitionDefinition]:
	"""
	Query transitions by website_id.
	
	Args:
		website_id: Website ID to query
		limit: Maximum number of results
	
	Returns:
		List of TransitionDefinition objects
	"""
	try:
		collection = await get_transitions_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot query transitions")
			return []

		cursor = collection.find({'website_id': website_id}).limit(limit)
		transitions = []

		async for doc in cursor:
			doc.pop('_id', None)
			try:
				transitions.append(TransitionDefinition(**doc))
			except Exception as e:
				logger.warning(f"Failed to parse transition document: {e}")
				continue

		return transitions

	except Exception as e:
		logger.error(f"Failed to query transitions by website: {e}")
		return []


async def query_transitions_by_knowledge_id(
	knowledge_id: str,
	job_id: str | None = None,
	limit: int = 1000
) -> list[TransitionDefinition]:
	"""
	Query transitions by knowledge_id, optionally filtered by job_id.
	
	If job_id is provided, returns transitions for that specific job.
	If job_id is None, returns latest transitions (most recent job) for the knowledge_id.
	
	Args:
		knowledge_id: Knowledge ID to query
		job_id: Optional job ID to filter by (if None, gets latest)
		limit: Maximum number of results
	
	Returns:
		List of TransitionDefinition objects
	"""
	try:
		collection = await get_transitions_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot query transitions")
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

		transitions = []

		async for doc in cursor:
			doc.pop('_id', None)
			try:
				transitions.append(TransitionDefinition(**doc))
			except Exception as e:
				logger.warning(f"Failed to parse transition document: {e}")
				continue

		return transitions

	except Exception as e:
		logger.error(f"Failed to query transitions by knowledge_id: {e}")
		return []

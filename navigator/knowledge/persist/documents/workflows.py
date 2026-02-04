"""
Workflow storage functions.

Handles persistence of OperationalWorkflow objects in MongoDB.
"""

import logging
from typing import Any

from navigator.knowledge.extract.workflows import OperationalWorkflow
from navigator.knowledge.persist.collections import (
	get_business_functions_collection,
	get_screens_collection,
	get_workflows_collection,
)

logger = logging.getLogger(__name__)


async def save_workflow(
	workflow: OperationalWorkflow,
	knowledge_id: str | None = None,
	job_id: str | None = None
) -> bool:
	"""
	Save full operational workflow definition to MongoDB.
	
	Args:
		workflow: OperationalWorkflow to save
		knowledge_id: Optional knowledge ID for persistence and querying
		job_id: Optional job ID for historical tracking
	
	Returns:
		True if saved successfully, False otherwise
	"""
	try:
		collection = await get_workflows_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, workflow not persisted")
			return False

		# Convert to dict for MongoDB storage
		wf_dict = workflow.dict(exclude_none=True)

		# Add knowledge_id if provided
		if knowledge_id:
			wf_dict['knowledge_id'] = knowledge_id

		# Add job_id if provided (for historical tracking)
		if job_id:
			wf_dict['job_id'] = job_id

		# Upsert by workflow_id
		await collection.update_one(
			{'workflow_id': workflow.workflow_id},
			{'$set': wf_dict},
			upsert=True
		)

		# Update cross-references (Phase 2: CrossReferenceManager)
		from navigator.knowledge.persist.cross_references import get_cross_reference_manager
		cross_ref_manager = get_cross_reference_manager()

		# Phase 3.1: Link workflow to business function if business_function_id is set (bidirectional)
		if hasattr(workflow, 'business_function_id') and workflow.business_function_id:
			await cross_ref_manager.link_entity_to_business_function(
				'workflow',
				workflow.workflow_id,
				workflow.business_function_id,
				knowledge_id
			)

		# Link workflow to screens if screen_ids are set
		if hasattr(workflow, 'screen_ids') and workflow.screen_ids:
			screens_collection = await get_screens_collection()
			if screens_collection:
				for screen_id in workflow.screen_ids:
					await cross_ref_manager.update_screen_references_from_entity(
						screen_id,
						'workflow',
						workflow.workflow_id,
						knowledge_id
					)

		logger.info(
			f"Saved workflow: workflow_id={workflow.workflow_id}, "
			f"name={workflow.name}, business_function={workflow.business_function}, "
			f"knowledge_id={knowledge_id}, job_id={job_id}"
		)
		return True

	except Exception as e:
		logger.error(f"Failed to save workflow: {e}")
		return False


async def save_workflows(
	workflows: list[OperationalWorkflow],
	knowledge_id: str | None = None,
	job_id: str | None = None
) -> dict[str, Any]:
	"""
	Save multiple workflow definitions (batch operation).
	
	Args:
		workflows: List of OperationalWorkflow objects
		knowledge_id: Optional knowledge ID for persistence and querying
		job_id: Optional job ID for historical tracking
	
	Returns:
		Dict with 'saved', 'failed', 'total' counts
	"""
	results = {'saved': 0, 'failed': 0, 'total': len(workflows)}

	for workflow in workflows:
		success = await save_workflow(workflow, knowledge_id=knowledge_id, job_id=job_id)
		if success:
			results['saved'] += 1
		else:
			results['failed'] += 1

	logger.info(f"Saved {results['saved']}/{results['total']} workflows")
	return results


async def get_workflow(workflow_id: str) -> OperationalWorkflow | None:
	"""
	Retrieve workflow definition by workflow_id.
	
	Args:
		workflow_id: Workflow ID to retrieve
	
	Returns:
		OperationalWorkflow if found, None otherwise
	"""
	try:
		collection = await get_workflows_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot retrieve workflow")
			return None

		doc = await collection.find_one({'workflow_id': workflow_id})
		if doc is None:
			return None

		# Remove MongoDB _id field
		doc.pop('_id', None)

		# Reconstruct OperationalWorkflow from dict
		return OperationalWorkflow(**doc)

	except Exception as e:
		logger.error(f"Failed to get workflow: {e}")
		return None


async def query_workflows_by_website(website_id: str, limit: int = 100) -> list[OperationalWorkflow]:
	"""
	Query workflows by website_id.
	
	Args:
		website_id: Website ID to query
		limit: Maximum number of results
	
	Returns:
		List of OperationalWorkflow objects
	"""
	try:
		collection = await get_workflows_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot query workflows")
			return []

		cursor = collection.find({'website_id': website_id}).limit(limit)
		workflows = []

		async for doc in cursor:
			doc.pop('_id', None)
			try:
				workflows.append(OperationalWorkflow(**doc))
			except Exception as e:
				logger.warning(f"Failed to parse workflow document: {e}")
				continue

		return workflows

	except Exception as e:
		logger.error(f"Failed to query workflows by website: {e}")
		return []


async def query_workflows_by_knowledge_id(
	knowledge_id: str,
	job_id: str | None = None,
	limit: int = 100
) -> list[OperationalWorkflow]:
	"""
	Query workflows by knowledge_id, optionally filtered by job_id.
	
	If job_id is provided, returns workflows for that specific job.
	If job_id is None, returns latest workflows (most recent job) for the knowledge_id.
	
	Args:
		knowledge_id: Knowledge ID to query
		job_id: Optional job ID to filter by (if None, gets latest)
		limit: Maximum number of results
	
	Returns:
		List of OperationalWorkflow objects
	"""
	try:
		collection = await get_workflows_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot query workflows")
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

		workflows = []

		async for doc in cursor:
			doc.pop('_id', None)
			try:
				workflows.append(OperationalWorkflow(**doc))
			except Exception as e:
				logger.warning(f"Failed to parse workflow document: {e}")
				continue

		return workflows

	except Exception as e:
		logger.error(f"Failed to query workflows by knowledge_id: {e}")
		return []


async def query_workflows_by_business_function(
	business_function_id: str,
	limit: int = 100
) -> list[OperationalWorkflow]:
	"""
	Query workflows by business_function_id.
	
	Args:
		business_function_id: Business function ID to query
		limit: Maximum number of results
	
	Returns:
		List of OperationalWorkflow objects
	"""
	try:
		collection = await get_workflows_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot query workflows")
			return []

		cursor = collection.find({'business_function_id': business_function_id}).limit(limit)
		workflows = []

		async for doc in cursor:
			doc.pop('_id', None)
			try:
				workflows.append(OperationalWorkflow(**doc))
			except Exception as e:
				logger.warning(f"Failed to parse workflow document: {e}")
				continue

		return workflows

	except Exception as e:
		logger.error(f"Failed to query workflows by business function: {e}")
		return []

"""
Workflow State Persistence

Implements Phase 5.2: Workflow State Persistence

Provides functions to:
- Save/load workflow state
- Update progress during execution
- Record errors and warnings
- Query workflow status

Integrates with Temporal workflows for state management.
"""

import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from navigator.knowledge.persist.collections import (
	WorkflowStatus,
	get_workflow_state_collection,
)

logger = logging.getLogger(__name__)


class WorkflowState(BaseModel):
	"""
	Workflow state model for persistence.
	
	Maps to WorkflowStateCollection schema.
	"""
	workflow_id: str = Field(..., description="Temporal workflow execution ID")
	job_id: str = Field(default_factory=lambda: f"job-{uuid4()}", description="User-facing job ID")
	status: WorkflowStatus = Field(WorkflowStatus.QUEUED, description="Current workflow status")
	phase: str | None = Field(None, description="Current phase name")
	progress: float = Field(0.0, description="Progress percentage (0-100)")
	errors: list[str] = Field(default_factory=list, description="List of error messages")
	warnings: list[str] = Field(default_factory=list, description="List of warning messages")
	metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
	created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
	updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")

	model_config = ConfigDict(
		json_encoders={
			datetime: lambda v: v.isoformat(),
		}
	)


async def save_workflow_state(state: WorkflowState) -> bool:
	"""
	Save workflow state to MongoDB.
	
	Creates or updates workflow state document.
	
	Args:
		state: Workflow state to save
	
	Returns:
		True if saved successfully, False otherwise
	"""
	try:
		collection = await get_workflow_state_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, workflow state not persisted")
			return False

		# Update timestamp
		state.updated_at = datetime.utcnow()

		# Upsert by workflow_id
		state_dict = state.dict()
		await collection.update_one(
			{'workflow_id': state.workflow_id},
			{'$set': state_dict},
			upsert=True
		)

		logger.info(f"Saved workflow state: workflow_id={state.workflow_id}, status={state.status}, progress={state.progress}%")
		return True

	except Exception as e:
		logger.error(f"Failed to save workflow state: {e}")
		return False


async def load_workflow_state(workflow_id: str) -> WorkflowState | None:
	"""
	Load workflow state from MongoDB.
	
	Args:
		workflow_id: Temporal workflow execution ID
	
	Returns:
		WorkflowState if found, None otherwise
	"""
	try:
		collection = await get_workflow_state_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot load workflow state")
			return None

		state_dict = await collection.find_one({'workflow_id': workflow_id})
		if not state_dict:
			logger.debug(f"Workflow state not found: workflow_id={workflow_id}")
			return None

		# Remove MongoDB _id field
		state_dict.pop('_id', None)

		state = WorkflowState(**state_dict)
		logger.debug(f"Loaded workflow state: workflow_id={workflow_id}, status={state.status}")
		return state

	except Exception as e:
		logger.error(f"Failed to load workflow state: {e}")
		return None


async def load_workflow_state_by_job_id(job_id: str) -> WorkflowState | None:
	"""
	Load workflow state by user-facing job ID.
	
	Args:
		job_id: User-facing job ID
	
	Returns:
		WorkflowState if found, None otherwise
	"""
	try:
		collection = await get_workflow_state_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot load workflow state")
			return None

		state_dict = await collection.find_one({'job_id': job_id})
		if not state_dict:
			logger.debug(f"Workflow state not found: job_id={job_id}")
			return None

		# Remove MongoDB _id field
		state_dict.pop('_id', None)

		state = WorkflowState(**state_dict)
		logger.debug(f"Loaded workflow state: job_id={job_id}, status={state.status}")
		return state

	except Exception as e:
		logger.error(f"Failed to load workflow state by job_id: {e}")
		return None


async def update_workflow_progress(
	workflow_id: str,
	phase: str,
	progress: float,
	status: WorkflowStatus | None = None
) -> bool:
	"""
	Update workflow progress.
	
	Args:
		workflow_id: Temporal workflow execution ID
		phase: Current phase name (e.g., 'ingestion', 'extraction')
		progress: Progress percentage (0-100)
		status: Optional status update
	
	Returns:
		True if updated successfully, False otherwise
	"""
	try:
		collection = await get_workflow_state_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, progress not updated")
			return False

		# Build update document
		update_doc = {
			'phase': phase,
			'progress': min(100.0, max(0.0, progress)),  # Clamp to [0, 100]
			'updated_at': datetime.utcnow(),
		}

		if status:
			update_doc['status'] = status.value

		# Update workflow state
		result = await collection.update_one(
			{'workflow_id': workflow_id},
			{'$set': update_doc}
		)

		if result.matched_count > 0:
			logger.info(f"Updated workflow progress: workflow_id={workflow_id}, phase={phase}, progress={progress}%")
			return True
		else:
			logger.warning(f"Workflow state not found for progress update: workflow_id={workflow_id}")
			return False

	except Exception as e:
		logger.error(f"Failed to update workflow progress: {e}")
		return False


async def record_workflow_error(workflow_id: str, error: str) -> bool:
	"""
	Record a workflow error.
	
	Args:
		workflow_id: Temporal workflow execution ID
		error: Error message
	
	Returns:
		True if recorded successfully, False otherwise
	"""
	try:
		collection = await get_workflow_state_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, error not recorded")
			return False

		# Append error to errors array
		result = await collection.update_one(
			{'workflow_id': workflow_id},
			{
				'$push': {'errors': error},
				'$set': {
					'status': WorkflowStatus.FAILED.value,
					'updated_at': datetime.utcnow()
				}
			}
		)

		if result.matched_count > 0:
			logger.error(f"Recorded workflow error: workflow_id={workflow_id}, error={error}")
			return True
		else:
			logger.warning(f"Workflow state not found for error recording: workflow_id={workflow_id}")
			return False

	except Exception as e:
		logger.error(f"Failed to record workflow error: {e}")
		return False


async def record_workflow_warning(workflow_id: str, warning: str) -> bool:
	"""
	Record a workflow warning.
	
	Args:
		workflow_id: Temporal workflow execution ID
		warning: Warning message
	
	Returns:
		True if recorded successfully, False otherwise
	"""
	try:
		collection = await get_workflow_state_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, warning not recorded")
			return False

		# Append warning to warnings array
		result = await collection.update_one(
			{'workflow_id': workflow_id},
			{
				'$push': {'warnings': warning},
				'$set': {'updated_at': datetime.utcnow()}
			}
		)

		if result.matched_count > 0:
			logger.warning(f"Recorded workflow warning: workflow_id={workflow_id}, warning={warning}")
			return True
		else:
			logger.warning(f"Workflow state not found for warning recording: workflow_id={workflow_id}")
			return False

	except Exception as e:
		logger.error(f"Failed to record workflow warning: {e}")
		return False


async def mark_workflow_completed(workflow_id: str) -> bool:
	"""
	Mark workflow as completed.
	
	Args:
		workflow_id: Temporal workflow execution ID
	
	Returns:
		True if marked successfully, False otherwise
	"""
	try:
		collection = await get_workflow_state_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, completion not recorded")
			return False

		result = await collection.update_one(
			{'workflow_id': workflow_id},
			{
				'$set': {
					'status': WorkflowStatus.COMPLETED.value,
					'progress': 100.0,
					'updated_at': datetime.utcnow()
				}
			}
		)

		if result.matched_count > 0:
			logger.info(f"✅ Marked workflow as completed: workflow_id={workflow_id}")
			return True
		else:
			logger.warning(f"Workflow state not found for completion: workflow_id={workflow_id}")
			return False

	except Exception as e:
		logger.error(f"Failed to mark workflow as completed: {e}")
		return False


async def mark_workflow_failed(workflow_id: str, error: str) -> bool:
	"""
	Mark workflow as failed with error.
	
	Combines status update and error recording.
	
	Args:
		workflow_id: Temporal workflow execution ID
		error: Final error message
	
	Returns:
		True if marked successfully, False otherwise
	"""
	return await record_workflow_error(workflow_id, error)


async def query_workflows_by_status(status: WorkflowStatus, limit: int = 100) -> list[WorkflowState]:
	"""
	Query workflows by status.
	
	Args:
		status: Workflow status to filter by
		limit: Maximum number of results (default: 100)
	
	Returns:
		List of WorkflowState objects
	"""
	try:
		collection = await get_workflow_state_collection()
		if collection is None:
			logger.warning("MongoDB unavailable, cannot query workflows")
			return []

		cursor = collection.find({'status': status.value}).sort('created_at', -1).limit(limit)

		workflows = []
		async for state_dict in cursor:
			state_dict.pop('_id', None)
			workflows.append(WorkflowState(**state_dict))

		logger.debug(f"Queried {len(workflows)} workflows with status={status}")
		return workflows

	except Exception as e:
		logger.error(f"Failed to query workflows by status: {e}")
		return []

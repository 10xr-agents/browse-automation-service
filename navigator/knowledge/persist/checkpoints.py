"""
Checkpoint-Based Recovery

Implements Phase 5.3: Checkpoint-Based Recovery

Provides functions to:
- Save processing checkpoints every N items
- Load last checkpoint on workflow resume
- Skip already-processed items
- Enable incremental processing

Integrates with Temporal activities for long-running operations.
"""

import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from navigator.knowledge.persist.collections import (
	ProcessingCheckpointCollection,
	get_checkpoint_collection,
)

logger = logging.getLogger(__name__)


class ProcessingCheckpoint(BaseModel):
	"""
	Processing checkpoint model for persistence.
	
	Maps to ProcessingCheckpointCollection schema.
	"""
	workflow_id: str = Field(..., description="Workflow execution ID")
	activity_name: str = Field(..., description="Activity name")
	checkpoint_id: int = Field(..., description="Sequential checkpoint ID")
	items_processed: int = Field(0, description="Number of items processed")
	total_items: int = Field(..., description="Total items to process")
	last_item_id: str | None = Field(None, description="ID of last processed item")
	checkpoint_data: dict[str, Any] = Field(default_factory=dict, description="Activity-specific data")
	created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
	
	@property
	def progress_percentage(self) -> float:
		"""Calculate progress percentage."""
		if self.total_items == 0:
			return 0.0
		return (self.items_processed / self.total_items) * 100.0
	
	class Config:
		json_encoders = {
			datetime: lambda v: v.isoformat(),
		}


async def save_checkpoint(checkpoint: ProcessingCheckpoint) -> bool:
	"""
	Save processing checkpoint to MongoDB.
	
	Creates or updates checkpoint document.
	
	Args:
		checkpoint: Checkpoint to save
	
	Returns:
		True if saved successfully, False otherwise
	"""
	try:
		collection = await get_checkpoint_collection()
		if not collection:
			logger.warning("MongoDB unavailable, checkpoint not persisted")
			return False
		
		# Upsert by workflow_id + activity_name + checkpoint_id
		checkpoint_dict = checkpoint.dict()
		await collection.update_one(
			{
				'workflow_id': checkpoint.workflow_id,
				'activity_name': checkpoint.activity_name,
				'checkpoint_id': checkpoint.checkpoint_id,
			},
			{'$set': checkpoint_dict},
			upsert=True
		)
		
		logger.info(
			f"Saved checkpoint: workflow_id={checkpoint.workflow_id}, "
			f"activity={checkpoint.activity_name}, checkpoint_id={checkpoint.checkpoint_id}, "
			f"progress={checkpoint.items_processed}/{checkpoint.total_items} "
			f"({checkpoint.progress_percentage:.1f}%)"
		)
		return True
	
	except Exception as e:
		logger.error(f"Failed to save checkpoint: {e}")
		return False


async def load_checkpoint(
	workflow_id: str,
	activity_name: str,
	checkpoint_id: int
) -> ProcessingCheckpoint | None:
	"""
	Load specific checkpoint from MongoDB.
	
	Args:
		workflow_id: Workflow execution ID
		activity_name: Activity name
		checkpoint_id: Checkpoint ID
	
	Returns:
		ProcessingCheckpoint if found, None otherwise
	"""
	try:
		collection = await get_checkpoint_collection()
		if not collection:
			logger.warning("MongoDB unavailable, cannot load checkpoint")
			return None
		
		checkpoint_dict = await collection.find_one({
			'workflow_id': workflow_id,
			'activity_name': activity_name,
			'checkpoint_id': checkpoint_id,
		})
		
		if not checkpoint_dict:
			logger.debug(
				f"Checkpoint not found: workflow_id={workflow_id}, "
				f"activity={activity_name}, checkpoint_id={checkpoint_id}"
			)
			return None
		
		# Remove MongoDB _id field
		checkpoint_dict.pop('_id', None)
		
		checkpoint = ProcessingCheckpoint(**checkpoint_dict)
		logger.debug(f"Loaded checkpoint: checkpoint_id={checkpoint_id}, progress={checkpoint.progress_percentage:.1f}%")
		return checkpoint
	
	except Exception as e:
		logger.error(f"Failed to load checkpoint: {e}")
		return None


async def get_resume_point(
	workflow_id: str,
	activity_name: str
) -> ProcessingCheckpoint | None:
	"""
	Get the last checkpoint for an activity (resume point).
	
	Args:
		workflow_id: Workflow execution ID
		activity_name: Activity name
	
	Returns:
		Last ProcessingCheckpoint if found, None otherwise
	"""
	try:
		collection = await get_checkpoint_collection()
		if not collection:
			logger.warning("MongoDB unavailable, cannot get resume point")
			return None
		
		# Find the most recent checkpoint for this workflow + activity
		checkpoint_dict = await collection.find_one(
			{
				'workflow_id': workflow_id,
				'activity_name': activity_name,
			},
			sort=[('checkpoint_id', -1)]  # Sort by checkpoint_id descending
		)
		
		if not checkpoint_dict:
			logger.debug(f"No checkpoints found for workflow_id={workflow_id}, activity={activity_name}")
			return None
		
		# Remove MongoDB _id field
		checkpoint_dict.pop('_id', None)
		
		checkpoint = ProcessingCheckpoint(**checkpoint_dict)
		logger.info(
			f"Found resume point: workflow_id={workflow_id}, activity={activity_name}, "
			f"checkpoint_id={checkpoint.checkpoint_id}, "
			f"items_processed={checkpoint.items_processed}/{checkpoint.total_items}"
		)
		return checkpoint
	
	except Exception as e:
		logger.error(f"Failed to get resume point: {e}")
		return None


async def list_checkpoints(
	workflow_id: str,
	activity_name: str | None = None
) -> list[ProcessingCheckpoint]:
	"""
	List all checkpoints for a workflow (optionally filtered by activity).
	
	Args:
		workflow_id: Workflow execution ID
		activity_name: Optional activity name filter
	
	Returns:
		List of ProcessingCheckpoint objects (sorted by checkpoint_id)
	"""
	try:
		collection = await get_checkpoint_collection()
		if not collection:
			logger.warning("MongoDB unavailable, cannot list checkpoints")
			return []
		
		# Build query
		query = {'workflow_id': workflow_id}
		if activity_name:
			query['activity_name'] = activity_name
		
		# Find and sort checkpoints
		cursor = collection.find(query).sort('checkpoint_id', 1)
		
		checkpoints = []
		async for checkpoint_dict in cursor:
			checkpoint_dict.pop('_id', None)
			checkpoints.append(ProcessingCheckpoint(**checkpoint_dict))
		
		logger.debug(f"Listed {len(checkpoints)} checkpoints for workflow_id={workflow_id}")
		return checkpoints
	
	except Exception as e:
		logger.error(f"Failed to list checkpoints: {e}")
		return []


async def clear_checkpoints(
	workflow_id: str,
	activity_name: str | None = None
) -> bool:
	"""
	Clear checkpoints for a workflow (optionally filtered by activity).
	
	Useful for cleanup after successful workflow completion.
	
	Args:
		workflow_id: Workflow execution ID
		activity_name: Optional activity name filter
	
	Returns:
		True if cleared successfully, False otherwise
	"""
	try:
		collection = await get_checkpoint_collection()
		if not collection:
			logger.warning("MongoDB unavailable, cannot clear checkpoints")
			return False
		
		# Build query
		query = {'workflow_id': workflow_id}
		if activity_name:
			query['activity_name'] = activity_name
		
		# Delete checkpoints
		result = await collection.delete_many(query)
		
		logger.info(
			f"Cleared {result.deleted_count} checkpoints: workflow_id={workflow_id}, "
			f"activity={activity_name or 'all'}"
		)
		return True
	
	except Exception as e:
		logger.error(f"Failed to clear checkpoints: {e}")
		return False


async def should_skip_item(
	workflow_id: str,
	activity_name: str,
	item_id: str
) -> bool:
	"""
	Check if an item should be skipped (already processed).
	
	Compares item_id with last_item_id from the most recent checkpoint.
	This is a simple string comparison - activities should use IDs that
	can be compared (e.g., sequential integers, timestamps).
	
	Args:
		workflow_id: Workflow execution ID
		activity_name: Activity name
		item_id: ID of item to check
	
	Returns:
		True if item should be skipped (already processed), False otherwise
	"""
	try:
		checkpoint = await get_resume_point(workflow_id, activity_name)
		if not checkpoint:
			# No checkpoint found, don't skip
			return False
		
		if not checkpoint.last_item_id:
			# Checkpoint exists but no last_item_id, don't skip
			return False
		
		# Compare IDs (assumes IDs are comparable strings/integers)
		# For integer IDs: item_id <= last_item_id means already processed
		try:
			return int(item_id) <= int(checkpoint.last_item_id)
		except ValueError:
			# If not integers, do string comparison
			return item_id <= checkpoint.last_item_id
	
	except Exception as e:
		logger.error(f"Failed to check if item should be skipped: {e}")
		# In case of error, don't skip (safer to re-process than miss items)
		return False


async def create_checkpoint_from_progress(
	workflow_id: str,
	activity_name: str,
	items_processed: int,
	total_items: int,
	last_item_id: str | None = None,
	checkpoint_data: dict[str, Any] | None = None
) -> ProcessingCheckpoint | None:
	"""
	Create and save a checkpoint from progress information.
	
	Convenience function that auto-generates checkpoint_id.
	
	Args:
		workflow_id: Workflow execution ID
		activity_name: Activity name
		items_processed: Number of items processed
		total_items: Total items to process
		last_item_id: ID of last processed item
		checkpoint_data: Activity-specific checkpoint data
	
	Returns:
		Created ProcessingCheckpoint if successful, None otherwise
	"""
	try:
		# Get next checkpoint_id (last checkpoint_id + 1)
		last_checkpoint = await get_resume_point(workflow_id, activity_name)
		checkpoint_id = (last_checkpoint.checkpoint_id + 1) if last_checkpoint else 0
		
		# Create checkpoint
		checkpoint = ProcessingCheckpoint(
			workflow_id=workflow_id,
			activity_name=activity_name,
			checkpoint_id=checkpoint_id,
			items_processed=items_processed,
			total_items=total_items,
			last_item_id=last_item_id,
			checkpoint_data=checkpoint_data or {},
		)
		
		# Save checkpoint
		success = await save_checkpoint(checkpoint)
		if success:
			return checkpoint
		else:
			return None
	
	except Exception as e:
		logger.error(f"Failed to create checkpoint from progress: {e}")
		return None

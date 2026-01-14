"""
MongoDB Collections for Knowledge Persistence

Implements Phase 5.1: Define MongoDB Collections for Workflow State

Collections:
1. workflow_state: Workflow execution tracking
2. ingestion_metadata: Source ingestion tracking (with deduplication)
3. processing_checkpoints: Incremental progress tracking
4. screens: Full screen definitions
5. tasks: Full task definitions
6. actions: Full action definitions
7. transitions: Full transition definitions

All collections use 'brwsr_auto_svc_' prefix for namespace safety.
"""

import logging
from enum import Enum
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import BaseModel, Field
from datetime import datetime

from navigator.storage.mongodb import get_collection

logger = logging.getLogger(__name__)

# Collection names (base names, will be prefixed automatically)
WORKFLOW_STATE_COLLECTION = 'knowledge_workflow_state'
INGESTION_METADATA_COLLECTION = 'knowledge_ingestion_metadata'
PROCESSING_CHECKPOINT_COLLECTION = 'knowledge_processing_checkpoints'
SCREENS_COLLECTION = 'knowledge_screens'
TASKS_COLLECTION = 'knowledge_tasks'
ACTIONS_COLLECTION = 'knowledge_actions'
TRANSITIONS_COLLECTION = 'knowledge_transitions'


class WorkflowStatus(str, Enum):
	"""Workflow execution status."""
	QUEUED = 'queued'
	RUNNING = 'running'
	PAUSED = 'paused'
	COMPLETED = 'completed'
	FAILED = 'failed'
	CANCELLED = 'cancelled'


class SourceType(str, Enum):
	"""Source type for ingestion."""
	DOCUMENTATION = 'documentation'
	WEBSITE = 'website'
	VIDEO = 'video'


class WorkflowStateCollection(BaseModel):
	"""
	Workflow state document schema.
	
	Tracks workflow execution state for Temporal workflows.
	"""
	workflow_id: str = Field(..., description="Temporal workflow execution ID")
	job_id: str = Field(..., description="User-facing job ID")
	status: WorkflowStatus = Field(..., description="Current workflow status")
	phase: str | None = Field(None, description="Current phase name (e.g., 'ingestion', 'extraction')")
	progress: float = Field(0.0, description="Progress percentage (0-100)")
	errors: list[str] = Field(default_factory=list, description="List of error messages")
	warnings: list[str] = Field(default_factory=list, description="List of warning messages")
	metadata: dict[str, Any] = Field(default_factory=dict, description="Additional workflow metadata")
	created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
	updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
	
	class Config:
		json_encoders = {
			datetime: lambda v: v.isoformat(),
		}


class IngestionMetadataCollection(BaseModel):
	"""
	Ingestion metadata document schema.
	
	Tracks ingested sources for deduplication.
	"""
	source_id: str = Field(..., description="Unique source identifier (UUID)")
	source_type: SourceType = Field(..., description="Source type (documentation, website, video)")
	source_url: str | None = Field(None, description="Original URL (if applicable)")
	source_path: str | None = Field(None, description="File path (if applicable)")
	content_hash: str = Field(..., description="SHA-256 hash of content for deduplication")
	ingested_at: datetime = Field(default_factory=datetime.utcnow, description="Ingestion timestamp")
	last_updated: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
	metadata: dict[str, Any] = Field(default_factory=dict, description="Source-specific metadata")
	
	class Config:
		json_encoders = {
			datetime: lambda v: v.isoformat(),
		}


class ProcessingCheckpointCollection(BaseModel):
	"""
	Processing checkpoint document schema.
	
	Enables incremental processing and recovery.
	"""
	workflow_id: str = Field(..., description="Workflow execution ID")
	activity_name: str = Field(..., description="Activity name (e.g., 'ingest_source', 'extract_screens')")
	checkpoint_id: int = Field(..., description="Sequential checkpoint ID within activity")
	items_processed: int = Field(0, description="Number of items processed so far")
	total_items: int = Field(..., description="Total items to process")
	last_item_id: str | None = Field(None, description="ID of last processed item (for resumption)")
	checkpoint_data: dict[str, Any] = Field(default_factory=dict, description="Activity-specific checkpoint data")
	created_at: datetime = Field(default_factory=datetime.utcnow, description="Checkpoint creation timestamp")
	
	class Config:
		json_encoders = {
			datetime: lambda v: v.isoformat(),
		}


async def get_workflow_state_collection() -> AsyncIOMotorCollection | None:
	"""
	Get workflow_state collection.
	
	Returns:
		Motor collection instance or None if MongoDB unavailable
	"""
	return await get_collection(WORKFLOW_STATE_COLLECTION)


async def get_ingestion_metadata_collection() -> AsyncIOMotorCollection | None:
	"""
	Get ingestion_metadata collection.
	
	Returns:
		Motor collection instance or None if MongoDB unavailable
	"""
	return await get_collection(INGESTION_METADATA_COLLECTION)


async def get_checkpoint_collection() -> AsyncIOMotorCollection | None:
	"""
	Get processing_checkpoints collection.
	
	Returns:
		Motor collection instance or None if MongoDB unavailable
	"""
	return await get_collection(PROCESSING_CHECKPOINT_COLLECTION)


async def get_screens_collection() -> AsyncIOMotorCollection | None:
	"""
	Get screens collection (full definitions).
	
	Returns:
		Motor collection instance or None if MongoDB unavailable
	"""
	return await get_collection(SCREENS_COLLECTION)


async def get_tasks_collection() -> AsyncIOMotorCollection | None:
	"""
	Get tasks collection (full definitions).
	
	Returns:
		Motor collection instance or None if MongoDB unavailable
	"""
	return await get_collection(TASKS_COLLECTION)


async def get_actions_collection() -> AsyncIOMotorCollection | None:
	"""
	Get actions collection (full definitions).
	
	Returns:
		Motor collection instance or None if MongoDB unavailable
	"""
	return await get_collection(ACTIONS_COLLECTION)


async def get_transitions_collection() -> AsyncIOMotorCollection | None:
	"""
	Get transitions collection (full definitions).
	
	Returns:
		Motor collection instance or None if MongoDB unavailable
	"""
	return await get_collection(TRANSITIONS_COLLECTION)


async def ensure_indexes() -> None:
	"""
	Create indexes for all knowledge persistence collections.
	
	Indexes:
	- workflow_state: workflow_id (unique), job_id (unique), status, created_at
	- ingestion_metadata: source_id (unique), content_hash, source_url
	- processing_checkpoints: workflow_id + activity_name + checkpoint_id (compound unique)
	- screens: screen_id (unique), website_id
	- tasks: task_id (unique), website_id
	- actions: action_id (unique), website_id
	- transitions: transition_id (unique), source_screen_id, target_screen_id
	"""
	try:
		# Workflow state indexes
		workflow_state_col = await get_workflow_state_collection()
		if workflow_state_col:
			await workflow_state_col.create_index('workflow_id', unique=True)
			await workflow_state_col.create_index('job_id', unique=True)
			await workflow_state_col.create_index('status')
			await workflow_state_col.create_index('created_at')
			logger.info(f"Created indexes for {WORKFLOW_STATE_COLLECTION}")
		
		# Ingestion metadata indexes
		ingestion_col = await get_ingestion_metadata_collection()
		if ingestion_col:
			await ingestion_col.create_index('source_id', unique=True)
			await ingestion_col.create_index('content_hash')
			await ingestion_col.create_index('source_url')
			logger.info(f"Created indexes for {INGESTION_METADATA_COLLECTION}")
		
		# Processing checkpoint indexes
		checkpoint_col = await get_checkpoint_collection()
		if checkpoint_col:
			await checkpoint_col.create_index([
				('workflow_id', 1),
				('activity_name', 1),
				('checkpoint_id', 1)
			], unique=True)
			await checkpoint_col.create_index('workflow_id')
			logger.info(f"Created indexes for {PROCESSING_CHECKPOINT_COLLECTION}")
		
		# Screens collection indexes
		screens_col = await get_screens_collection()
		if screens_col:
			await screens_col.create_index('screen_id', unique=True)
			await screens_col.create_index('website_id')
			logger.info(f"Created indexes for {SCREENS_COLLECTION}")
		
		# Tasks collection indexes
		tasks_col = await get_tasks_collection()
		if tasks_col:
			await tasks_col.create_index('task_id', unique=True)
			await tasks_col.create_index('website_id')
			logger.info(f"Created indexes for {TASKS_COLLECTION}")
		
		# Actions collection indexes
		actions_col = await get_actions_collection()
		if actions_col:
			await actions_col.create_index('action_id', unique=True)
			await actions_col.create_index('website_id')
			logger.info(f"Created indexes for {ACTIONS_COLLECTION}")
		
		# Transitions collection indexes
		transitions_col = await get_transitions_collection()
		if transitions_col:
			await transitions_col.create_index('transition_id', unique=True)
			await transitions_col.create_index('source_screen_id')
			await transitions_col.create_index('target_screen_id')
			logger.info(f"Created indexes for {TRANSITIONS_COLLECTION}")
		
		logger.info("✅ All knowledge persistence indexes created successfully")
		
	except Exception as e:
		logger.error(f"Failed to create indexes: {e}")
		raise


async def clear_all_collections() -> None:
	"""
	Clear all knowledge persistence collections (for testing).
	
	WARNING: This deletes all data!
	"""
	try:
		collections = [
			await get_workflow_state_collection(),
			await get_ingestion_metadata_collection(),
			await get_checkpoint_collection(),
			await get_screens_collection(),
			await get_tasks_collection(),
			await get_actions_collection(),
			await get_transitions_collection(),
		]
		
		for col in collections:
			if col:
				await col.delete_many({})
		
		logger.info("✅ Cleared all knowledge persistence collections")
	
	except Exception as e:
		logger.error(f"Failed to clear collections: {e}")
		raise

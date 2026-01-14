"""
Knowledge Persistence Layer

MongoDB-based persistence for the knowledge extraction workflow.
Separate from legacy storage.py (V1 system).

This module implements Phase 5 of the Knowledge Extraction Implementation Checklist:
- Workflow state management
- Checkpoint-based recovery
- Ingestion deduplication
- Full knowledge definition storage (screens, tasks, actions, transitions)

Collections:
- workflow_state: Workflow execution tracking
- ingestion_metadata: Source ingestion tracking
- processing_checkpoints: Incremental progress tracking
- screens: Full screen definitions
- tasks: Full task definitions
- actions: Full action definitions
- transitions: Full transition definitions
"""

from navigator.knowledge.persist.collections import (
	WorkflowStateCollection,
	IngestionMetadataCollection,
	ProcessingCheckpointCollection,
	get_workflow_state_collection,
	get_ingestion_metadata_collection,
	get_checkpoint_collection,
)
from navigator.knowledge.persist.state import (
	WorkflowState,
	WorkflowStatus,
	save_workflow_state,
	load_workflow_state,
	update_workflow_progress,
	record_workflow_error,
)
from navigator.knowledge.persist.checkpoints import (
	ProcessingCheckpoint,
	save_checkpoint,
	load_checkpoint,
	get_resume_point,
	clear_checkpoints,
)
from navigator.knowledge.persist.deduplication import (
	IngestionMetadata,
	check_already_ingested,
	compute_content_hash,
	update_ingestion_metadata,
)
from navigator.knowledge.persist.documents import (
	save_screen,
	save_task,
	save_action,
	save_transition,
	get_screen,
	get_task,
	get_action,
	get_transition,
	query_screens_by_website,
	query_tasks_by_website,
)

__all__ = [
	# Collections
	'WorkflowStateCollection',
	'IngestionMetadataCollection',
	'ProcessingCheckpointCollection',
	'get_workflow_state_collection',
	'get_ingestion_metadata_collection',
	'get_checkpoint_collection',
	# State management
	'WorkflowState',
	'WorkflowStatus',
	'save_workflow_state',
	'load_workflow_state',
	'update_workflow_progress',
	'record_workflow_error',
	# Checkpoints
	'ProcessingCheckpoint',
	'save_checkpoint',
	'load_checkpoint',
	'get_resume_point',
	'clear_checkpoints',
	# Deduplication
	'IngestionMetadata',
	'check_already_ingested',
	'compute_content_hash',
	'update_ingestion_metadata',
	# Document storage
	'save_screen',
	'save_task',
	'save_action',
	'save_transition',
	'get_screen',
	'get_task',
	'get_action',
	'get_transition',
	'query_screens_by_website',
	'query_tasks_by_website',
]

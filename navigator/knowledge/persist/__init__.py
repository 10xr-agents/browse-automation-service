"""
Knowledge Persistence Layer

MongoDB-based persistence for the knowledge extraction workflow.
Separate from legacy storage.py (V1 system).

This module implements Phase 5 of the Knowledge Extraction Implementation Checklist:
- Workflow state management
- Checkpoint-based recovery
- Ingestion deduplication
- Full knowledge definition storage (screens, tasks, actions, transitions, business functions, workflows)

Collections:
- workflow_state: Workflow execution tracking
- ingestion_metadata: Source ingestion tracking
- processing_checkpoints: Incremental progress tracking
- screens: Full screen definitions
- tasks: Full task definitions
- actions: Full action definitions
- transitions: Full transition definitions
- business_functions: Full business function definitions
- workflows: Full operational workflow definitions
"""

from navigator.knowledge.persist.checkpoints import (
	ProcessingCheckpoint,
	clear_checkpoints,
	get_resume_point,
	load_checkpoint,
	save_checkpoint,
)
from navigator.knowledge.persist.collections import (
	IngestionMetadataCollection,
	ProcessingCheckpointCollection,
	WorkflowStateCollection,
	get_checkpoint_collection,
	get_ingestion_metadata_collection,
	get_workflow_state_collection,
)
from navigator.knowledge.persist.cross_references import (
	CrossReferenceManager,
	get_cross_reference_manager,
)
from navigator.knowledge.persist.deduplication import (
	IngestionMetadata,
	check_already_ingested,
	compute_content_hash,
	update_ingestion_metadata,
)
from navigator.knowledge.persist.documents import (
	get_action,
	get_business_function,
	get_screen,
	get_task,
	get_transition,
	get_user_flow,
	get_workflow,
	query_business_functions_by_category,
	query_business_functions_by_website,
	query_screens_by_website,
	query_tasks_by_website,
	query_user_flows_by_business_function,
	query_user_flows_by_category,
	query_user_flows_by_knowledge_id,
	query_workflows_by_business_function,
	query_workflows_by_website,
	save_action,
	save_actions,
	save_business_function,
	save_business_functions,
	save_screen,
	save_screens,
	save_task,
	save_tasks,
	save_transition,
	save_transitions,
	save_user_flow,
	save_user_flows,
	save_workflow,
	save_workflows,
)
from navigator.knowledge.persist.ingestion import (
	delete_ingestion_result,
	get_ingestion_chunks,
	get_ingestion_result,
	save_ingestion_result,
)
from navigator.knowledge.persist.navigation import (
	get_business_feature_flows,
	get_flow_navigation,
	get_navigation_path,
	get_screen_context,
)
from navigator.knowledge.persist.state import (
	WorkflowState,
	WorkflowStatus,
	load_workflow_state,
	record_workflow_error,
	save_workflow_state,
	update_workflow_progress,
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
	'save_screens',
	'save_task',
	'save_tasks',
	'save_action',
	'save_actions',
	'save_transition',
	'save_transitions',
	'save_business_function',
	'save_business_functions',
	'save_user_flow',
	'save_user_flows',
	'save_workflow',
	'save_workflows',
	'get_screen',
	'get_task',
	'get_action',
	'get_transition',
	'get_business_function',
	'get_user_flow',
	'get_workflow',
	'query_screens_by_website',
	'query_tasks_by_website',
	'query_business_functions_by_website',
	'query_business_functions_by_category',
	'query_user_flows_by_knowledge_id',
	'query_user_flows_by_business_function',
	'query_user_flows_by_category',
	'query_workflows_by_website',
	'query_workflows_by_business_function',
	# Ingestion storage
	'save_ingestion_result',
	'get_ingestion_result',
	'get_ingestion_chunks',
	'delete_ingestion_result',
	# Cross-reference management (Phase 2)
	'CrossReferenceManager',
	'get_cross_reference_manager',
	# Navigation helpers (Phase 3)
	'get_navigation_path',
	'get_flow_navigation',
	'get_business_feature_flows',
	'get_screen_context',
]

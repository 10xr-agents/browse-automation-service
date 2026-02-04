"""
Temporal activities for knowledge extraction workflow.

This module re-exports all activities and provides the initialization function.
"""

# Import shared dependencies
# Import exploration activity
from navigator.temporal.activities.exploration import explore_primary_url_activity

# Import extraction activities
from navigator.temporal.activities.extraction.actions import extract_actions_activity
from navigator.temporal.activities.extraction.business_functions import extract_business_functions_activity
from navigator.temporal.activities.extraction.linking import link_entities_activity
from navigator.temporal.activities.extraction.screens import extract_screens_activity
from navigator.temporal.activities.extraction.tasks import extract_tasks_activity
from navigator.temporal.activities.extraction.transitions import extract_transitions_activity
from navigator.temporal.activities.extraction.user_flows import extract_user_flows_activity
from navigator.temporal.activities.extraction.workflows import extract_workflows_activity

# Import graph activity
from navigator.temporal.activities.graph import build_graph_activity

# Import ingestion activity
from navigator.temporal.activities.ingestion import ingest_source_activity
from navigator.temporal.activities.shared import (
	get_idempotency_manager,
	init_activity_dependencies,
)

# Import verification activities
from navigator.temporal.activities.verification import (
	delete_knowledge_activity,
	enrich_knowledge_activity,
	verify_extraction_activity,
)

# Import video activities from separate module (already split)
# Video activities are now in activities/video/ submodule
from navigator.temporal.activities.video import (
	analyze_frames_batch_activity,
	assemble_video_ingestion_activity,
	filter_frames_activity,
	transcribe_video_activity,
)

__all__ = [
	# Initialization
	'init_activity_dependencies',
	'get_idempotency_manager',
	# Ingestion
	'ingest_source_activity',
	# Extraction
	'extract_screens_activity',
	'extract_tasks_activity',
	'extract_actions_activity',
	'extract_transitions_activity',
	'extract_business_functions_activity',
	'extract_workflows_activity',
	'extract_user_flows_activity',  # Phase 4
	'link_entities_activity',  # Priority 2: Post-Extraction Entity Linking
	# Graph
	'build_graph_activity',
	# Verification
	'verify_extraction_activity',
	'enrich_knowledge_activity',
	'delete_knowledge_activity',
	# Exploration
	'explore_primary_url_activity',
	# Video (from separate module)
	'transcribe_video_activity',
	'filter_frames_activity',
	'analyze_frames_batch_activity',
	'assemble_video_ingestion_activity',
]

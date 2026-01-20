"""
Document storage module.

Re-exports all document storage functions organized by entity type.
"""

# Base utilities
# Action storage
from navigator.knowledge.persist.documents.actions import (
	get_action,
	query_actions_by_knowledge_id,
	save_action,
	save_actions,
)
from navigator.knowledge.persist.documents.base import (
	delete_knowledge_by_knowledge_id,
	get_latest_job_id_for_knowledge_id,
)

# Business function storage
from navigator.knowledge.persist.documents.business_functions import (
	get_business_function,
	query_business_functions_by_category,
	query_business_functions_by_knowledge_id,
	query_business_functions_by_website,
	save_business_function,
	save_business_functions,
)

# Screen storage
from navigator.knowledge.persist.documents.screens import (
	delete_screen,
	get_screen,
	query_screens_by_knowledge_id,
	query_screens_by_name_pattern,
	query_screens_by_website,
	save_screen,
	save_screens,
)

# Task storage
from navigator.knowledge.persist.documents.tasks import (
	get_task,
	query_tasks_by_knowledge_id,
	query_tasks_by_website,
	save_task,
	save_tasks,
)

# Transition storage
from navigator.knowledge.persist.documents.transitions import (
	get_transition,
	query_transitions_by_knowledge_id,
	query_transitions_by_source,
	query_transitions_by_target,
	query_transitions_by_website,
	save_transition,
	save_transitions,
)

# User flow storage (Phase 4)
from navigator.knowledge.persist.documents.user_flows import (
	get_user_flow,
	query_user_flows_by_business_function,
	query_user_flows_by_category,
	query_user_flows_by_knowledge_id,
	save_user_flow,
	save_user_flows,
)

# Workflow storage
from navigator.knowledge.persist.documents.workflows import (
	get_workflow,
	query_workflows_by_business_function,
	query_workflows_by_knowledge_id,
	query_workflows_by_website,
	save_workflow,
	save_workflows,
)

__all__ = [
	# Base utilities
	'delete_knowledge_by_knowledge_id',
	'get_latest_job_id_for_knowledge_id',
	# Screen storage
	'save_screen',
	'save_screens',
	'get_screen',
	'query_screens_by_website',
	'query_screens_by_knowledge_id',
	'query_screens_by_name_pattern',
	'delete_screen',
	# Task storage
	'save_task',
	'save_tasks',
	'get_task',
	'query_tasks_by_website',
	'query_tasks_by_knowledge_id',
	# Action storage
	'save_action',
	'save_actions',
	'get_action',
	'query_actions_by_knowledge_id',
	# Transition storage
	'save_transition',
	'save_transitions',
	'get_transition',
	'query_transitions_by_source',
	'query_transitions_by_target',
	'query_transitions_by_website',
	'query_transitions_by_knowledge_id',
	# Business function storage
	'save_business_function',
	'save_business_functions',
	'get_business_function',
	'query_business_functions_by_website',
	'query_business_functions_by_knowledge_id',
	'query_business_functions_by_category',
	# Workflow storage
	'save_workflow',
	'save_workflows',
	'get_workflow',
	'query_workflows_by_website',
	'query_workflows_by_knowledge_id',
	'query_workflows_by_business_function',
	# User flow storage (Phase 4)
	'save_user_flow',
	'save_user_flows',
	'get_user_flow',
	'query_user_flows_by_knowledge_id',
	'query_user_flows_by_business_function',
	'query_user_flows_by_category',
]

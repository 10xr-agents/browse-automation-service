"""
Knowledge Graph Construction Module.

Implements ArangoDB graph construction for navigation and recovery.
"""

from navigator.knowledge.graph.collections import (
	create_all_collections,
	get_screen_collection,
	get_screen_group_collection,
	get_transition_collection,
	get_group_membership_collection,
	get_global_recovery_collection,
)
from navigator.knowledge.graph.config import (
	get_graph_database,
	verify_graph_connection,
)
from navigator.knowledge.graph.edges import create_transition_edges, create_membership_edges, create_recovery_edges
from navigator.knowledge.graph.graphs import create_all_graphs, get_navigation_graph, get_recovery_graph
from navigator.knowledge.graph.groups import create_screen_groups, group_screens_by_pattern
from navigator.knowledge.graph.nodes import create_screen_nodes, upsert_screen_node
from navigator.knowledge.graph.validation import validate_graph_structure
from navigator.knowledge.graph.queries import (
	find_shortest_path,
	get_adjacent_screens,
	search_screens_by_name,
	search_screens_by_url_pattern,
	get_transitions_from_screen,
	get_transitions_to_screen,
	get_screen_statistics,
)

__all__ = [
	# Configuration
	'get_graph_database',
	'verify_graph_connection',
	# Collections
	'create_all_collections',
	'get_screen_collection',
	'get_screen_group_collection',
	'get_transition_collection',
	'get_group_membership_collection',
	'get_global_recovery_collection',
	# Graphs
	'create_all_graphs',
	'get_navigation_graph',
	'get_recovery_graph',
	# Nodes
	'create_screen_nodes',
	'upsert_screen_node',
	# Edges
	'create_transition_edges',
	'create_membership_edges',
	'create_recovery_edges',
	# Groups
	'create_screen_groups',
	'group_screens_by_pattern',
	# Validation
	'validate_graph_structure',
	# Queries (Phase 6.2)
	'find_shortest_path',
	'get_adjacent_screens',
	'search_screens_by_name',
	'search_screens_by_url_pattern',
	'get_transitions_from_screen',
	'get_transitions_to_screen',
	'get_screen_statistics',
]

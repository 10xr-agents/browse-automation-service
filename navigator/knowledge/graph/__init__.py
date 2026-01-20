"""
Knowledge Graph Query Module.

Provides graph query functions using MongoDB as the single source of truth.
NetworkX can be used in-memory by agents when needed for graph operations.
"""

# Note: Graph query functions use MongoDB as the single source of truth.
# All knowledge is now stored in MongoDB. NetworkX can be used in-memory by agents when needed.
from navigator.knowledge.graph.collections import create_all_collections
from navigator.knowledge.graph.config import get_graph_database, verify_graph_connection
from navigator.knowledge.graph.edges import create_transition_edges
from navigator.knowledge.graph.graphs import create_all_graphs
from navigator.knowledge.graph.groups import create_screen_groups
from navigator.knowledge.graph.nodes import create_screen_nodes
from navigator.knowledge.graph.queries import (
	find_shortest_path,
	get_adjacent_screens,
	get_screen_statistics,
	get_transitions_from_screen,
	get_transitions_to_screen,
	search_screens_by_name,
	search_screens_by_url_pattern,
)
from navigator.knowledge.graph.validation import validate_graph_structure

__all__ = [
	# Collections (for tests)
	'create_all_collections',
	# Graph operations
	'create_all_graphs',
	'create_screen_groups',
	'create_screen_nodes',
	'create_transition_edges',
	'get_graph_database',
	'validate_graph_structure',
	'verify_graph_connection',
	# Queries (MongoDB-based)
	'find_shortest_path',
	'get_adjacent_screens',
	'search_screens_by_name',
	'search_screens_by_url_pattern',
	'get_transitions_from_screen',
	'get_transitions_to_screen',
	'get_screen_statistics',
]

"""
Phase 4.3: ArangoDB Graph Definitions.

Creates named graphs for navigation and recovery traversal.
"""

import logging
from typing import Any

from navigator.knowledge.graph.collections import (
	GLOBAL_RECOVERY_COLLECTION,
	GROUP_MEMBERSHIP_COLLECTION,
	SCREENS_COLLECTION,
	SCREEN_GROUPS_COLLECTION,
	TRANSITIONS_COLLECTION,
)
from navigator.knowledge.graph.config import get_graph_database

logger = logging.getLogger(__name__)


# Graph names
NAVIGATION_GRAPH = "navigation"
RECOVERY_GRAPH = "global_recovery"


async def create_all_graphs() -> bool:
	"""
	Create all required named graphs for the knowledge graph.
	
	Graphs:
	- navigation: Screen transitions (screens → transitions → screens)
	- global_recovery: Recovery paths (screen_groups → global_recovery → screens)
	
	Returns:
		True if all graphs created/exist, False on error
	"""
	try:
		logger.info("Creating ArangoDB graphs for knowledge graph...")
		
		db = await get_graph_database()
		if db is None:
			return False
		
		# Create navigation graph
		if not db.has_graph(NAVIGATION_GRAPH):
			edge_definitions = [
				{
					'edge_collection': TRANSITIONS_COLLECTION,
					'from_vertex_collections': [SCREENS_COLLECTION],
					'to_vertex_collections': [SCREENS_COLLECTION],
				}
			]
			db.create_graph(NAVIGATION_GRAPH, edge_definitions=edge_definitions)
			logger.info(f"✅ Created navigation graph: {NAVIGATION_GRAPH}")
		else:
			logger.info(f"   Navigation graph exists: {NAVIGATION_GRAPH}")
		
		# Create recovery graph
		if not db.has_graph(RECOVERY_GRAPH):
			edge_definitions = [
				{
					'edge_collection': GROUP_MEMBERSHIP_COLLECTION,
					'from_vertex_collections': [SCREENS_COLLECTION],
					'to_vertex_collections': [SCREEN_GROUPS_COLLECTION],
				},
				{
					'edge_collection': GLOBAL_RECOVERY_COLLECTION,
					'from_vertex_collections': [SCREEN_GROUPS_COLLECTION],
					'to_vertex_collections': [SCREENS_COLLECTION],
				},
			]
			db.create_graph(RECOVERY_GRAPH, edge_definitions=edge_definitions)
			logger.info(f"✅ Created recovery graph: {RECOVERY_GRAPH}")
		else:
			logger.info(f"   Recovery graph exists: {RECOVERY_GRAPH}")
		
		logger.info("🎉 All graphs created successfully!")
		return True
		
	except Exception as e:
		logger.error(f"❌ Failed to create graphs: {e}", exc_info=True)
		return False


async def get_navigation_graph() -> Any | None:
	"""
	Get the navigation graph for screen transitions.
	
	Returns:
		ArangoDB graph instance or None
	"""
	try:
		db = await get_graph_database()
		if db is None:
			return None
		
		return db.graph(NAVIGATION_GRAPH)
		
	except Exception as e:
		logger.error(f"Failed to get navigation graph: {e}")
		return None


async def get_recovery_graph() -> Any | None:
	"""
	Get the recovery graph for fallback paths.
	
	Returns:
		ArangoDB graph instance or None
	"""
	try:
		db = await get_graph_database()
		if db is None:
			return None
		
		return db.graph(RECOVERY_GRAPH)
		
	except Exception as e:
		logger.error(f"Failed to get recovery graph: {e}")
		return None


async def traverse_navigation_graph(
	start_screen_id: str,
	direction: str = "outbound",
	min_depth: int = 1,
	max_depth: int = 5
) -> list[dict]:
	"""
	Traverse the navigation graph from a start screen.
	
	Args:
		start_screen_id: Starting screen ID (key)
		direction: Traversal direction ('outbound', 'inbound', 'any')
		min_depth: Minimum traversal depth
		max_depth: Maximum traversal depth
	
	Returns:
		List of traversal results with paths and vertices
	"""
	try:
		graph = await get_navigation_graph()
		if graph is None:
			return []
		
		# Build start vertex ID
		start_vertex = f"{SCREENS_COLLECTION}/{start_screen_id}"
		
		# Perform traversal
		results = graph.traverse(
			start_vertex=start_vertex,
			direction=direction,
			min_depth=min_depth,
			max_depth=max_depth,
		)
		
		return results.get('vertices', [])
		
	except Exception as e:
		logger.error(f"Failed to traverse navigation graph: {e}")
		return []


async def find_recovery_paths(screen_id: str) -> list[dict]:
	"""
	Find recovery paths for a screen using the recovery graph.
	
	Args:
		screen_id: Screen ID (key) to find recovery paths for
	
	Returns:
		List of recovery screens with priorities
	"""
	try:
		db = await get_graph_database()
		if db is None:
			return []
		
		# Query: screen → group → recovery screens
		aql = """
		FOR screen IN screens
		    FILTER screen._key == @screen_id
		    FOR group IN 1..1 OUTBOUND screen group_membership
		        FOR recovery IN 1..1 OUTBOUND group global_recovery
		            RETURN {
		                screen_id: recovery._key,
		                screen_name: recovery.name,
		                priority: recovery.priority,
		                reliability: recovery.reliability
		            }
		"""
		
		cursor = db.aql.execute(aql, bind_vars={'screen_id': screen_id})
		return list(cursor)
		
	except Exception as e:
		logger.error(f"Failed to find recovery paths: {e}")
		return []

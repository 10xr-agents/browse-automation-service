"""
Graph Query Functions

Helper functions for querying the knowledge graph in ArangoDB.
Used by Phase 6.2: Graph Query API.

Query types:
- find_path: Find shortest path between two screens
- get_neighbors: Get adjacent nodes
- search_screens: Search screens by name or URL pattern
- get_transitions: Get transitions from a screen
"""

import logging
from typing import Any

from navigator.knowledge.graph.config import get_graph_database
from navigator.knowledge.graph.collections import (
	SCREENS_COLLECTION,
	TRANSITIONS_COLLECTION,
)

logger = logging.getLogger(__name__)


async def find_shortest_path(
	source_screen_id: str,
	target_screen_id: str,
	max_depth: int = 10
) -> dict[str, Any]:
	"""
	Find shortest path between two screens using AQL traversal.
	
	Args:
		source_screen_id: Source screen ID
		target_screen_id: Target screen ID
		max_depth: Maximum traversal depth (default: 10)
	
	Returns:
		Dict with 'path' (list of vertices) and 'edges' (list of edges)
	"""
	try:
		db = await get_graph_database()
		if not db:
			logger.warning("ArangoDB unavailable, cannot find path")
			return {'path': [], 'edges': []}
		
		# AQL query for shortest path
		aql = """
		FOR v, e IN 1..@max_depth OUTBOUND @start_vertex
		GRAPH 'navigation'
		PRUNE v._key == @target_key
		FILTER v._key == @target_key
		LIMIT 1
		RETURN {path: [v], edges: [e]}
		"""
		
		bind_vars = {
			'start_vertex': f"{SCREENS_COLLECTION}/{source_screen_id}",
			'target_key': target_screen_id,
			'max_depth': max_depth,
		}
		
		cursor = await db.aql.execute(aql, bind_vars=bind_vars)
		results = [doc async for doc in cursor]
		
		if results:
			return results[0]
		else:
			logger.debug(f"No path found from {source_screen_id} to {target_screen_id}")
			return {'path': [], 'edges': []}
	
	except Exception as e:
		logger.error(f"Failed to find shortest path: {e}")
		return {'path': [], 'edges': []}


async def get_adjacent_screens(
	screen_id: str,
	direction: str = "outbound",
	limit: int = 10
) -> list[dict[str, Any]]:
	"""
	Get adjacent screens (neighbors).
	
	Args:
		screen_id: Screen ID
		direction: Direction ('outbound', 'inbound', or 'any')
		limit: Maximum number of results
	
	Returns:
		List of adjacent screen documents
	"""
	try:
		db = await get_graph_database()
		if not db:
			logger.warning("ArangoDB unavailable, cannot get adjacent screens")
			return []
		
		# Map direction to AQL keyword
		direction_keyword = direction.upper()
		
		# AQL query for adjacent screens
		aql = f"""
		FOR v, e IN 1..1 {direction_keyword} @start_vertex
		GRAPH 'navigation'
		LIMIT @limit
		RETURN {{
			screen: v,
			edge: e
		}}
		"""
		
		bind_vars = {
			'start_vertex': f"{SCREENS_COLLECTION}/{screen_id}",
			'limit': limit,
		}
		
		cursor = await db.aql.execute(aql, bind_vars=bind_vars)
		results = [doc async for doc in cursor]
		
		logger.debug(f"Found {len(results)} adjacent screens for {screen_id}")
		return results
	
	except Exception as e:
		logger.error(f"Failed to get adjacent screens: {e}")
		return []


async def search_screens_by_name(
	screen_name: str,
	website_id: str | None = None,
	limit: int = 10
) -> list[dict[str, Any]]:
	"""
	Search screens by name (fuzzy match).
	
	Args:
		screen_name: Screen name to search (partial match)
		website_id: Optional website ID filter
		limit: Maximum number of results
	
	Returns:
		List of matching screen documents
	"""
	try:
		db = await get_graph_database()
		if not db:
			logger.warning("ArangoDB unavailable, cannot search screens")
			return []
		
		# Build AQL query
		if website_id:
			aql = """
			FOR screen IN @@collection
			FILTER screen.website_id == @website_id
			FILTER CONTAINS(LOWER(screen.name), LOWER(@screen_name))
			LIMIT @limit
			RETURN screen
			"""
			bind_vars = {
				'@collection': SCREENS_COLLECTION,
				'website_id': website_id,
				'screen_name': screen_name,
				'limit': limit,
			}
		else:
			aql = """
			FOR screen IN @@collection
			FILTER CONTAINS(LOWER(screen.name), LOWER(@screen_name))
			LIMIT @limit
			RETURN screen
			"""
			bind_vars = {
				'@collection': SCREENS_COLLECTION,
				'screen_name': screen_name,
				'limit': limit,
			}
		
		cursor = await db.aql.execute(aql, bind_vars=bind_vars)
		results = [doc async for doc in cursor]
		
		logger.debug(f"Found {len(results)} screens matching '{screen_name}'")
		return results
	
	except Exception as e:
		logger.error(f"Failed to search screens: {e}")
		return []


async def search_screens_by_url_pattern(
	url_pattern: str,
	website_id: str | None = None,
	limit: int = 10
) -> list[dict[str, Any]]:
	"""
	Search screens by URL pattern.
	
	Args:
		url_pattern: URL pattern to match (regex or substring)
		website_id: Optional website ID filter
		limit: Maximum number of results
	
	Returns:
		List of matching screen documents
	"""
	try:
		db = await get_graph_database()
		if not db:
			logger.warning("ArangoDB unavailable, cannot search screens by URL")
			return []
		
		# Build AQL query
		if website_id:
			aql = """
			FOR screen IN @@collection
			FILTER screen.website_id == @website_id
			FILTER LENGTH(
				FOR pattern IN screen.url_patterns
				FILTER REGEX_TEST(pattern, @url_pattern, true)
				RETURN pattern
			) > 0
			LIMIT @limit
			RETURN screen
			"""
			bind_vars = {
				'@collection': SCREENS_COLLECTION,
				'website_id': website_id,
				'url_pattern': url_pattern,
				'limit': limit,
			}
		else:
			aql = """
			FOR screen IN @@collection
			FILTER LENGTH(
				FOR pattern IN screen.url_patterns
				FILTER REGEX_TEST(pattern, @url_pattern, true)
				RETURN pattern
			) > 0
			LIMIT @limit
			RETURN screen
			"""
			bind_vars = {
				'@collection': SCREENS_COLLECTION,
				'url_pattern': url_pattern,
				'limit': limit,
			}
		
		cursor = await db.aql.execute(aql, bind_vars=bind_vars)
		results = [doc async for doc in cursor]
		
		logger.debug(f"Found {len(results)} screens matching URL pattern '{url_pattern}'")
		return results
	
	except Exception as e:
		logger.error(f"Failed to search screens by URL pattern: {e}")
		return []


async def get_transitions_from_screen(
	screen_id: str,
	limit: int = 10
) -> list[dict[str, Any]]:
	"""
	Get all transitions originating from a screen.
	
	Args:
		screen_id: Source screen ID
		limit: Maximum number of results
	
	Returns:
		List of transition edge documents
	"""
	try:
		db = await get_graph_database()
		if not db:
			logger.warning("ArangoDB unavailable, cannot get transitions")
			return []
		
		# AQL query for outbound transitions
		aql = """
		FOR transition IN @@collection
		FILTER transition._from == @from_vertex
		LIMIT @limit
		RETURN transition
		"""
		
		bind_vars = {
			'@collection': TRANSITIONS_COLLECTION,
			'from_vertex': f"{SCREENS_COLLECTION}/{screen_id}",
			'limit': limit,
		}
		
		cursor = await db.aql.execute(aql, bind_vars=bind_vars)
		results = [doc async for doc in cursor]
		
		logger.debug(f"Found {len(results)} transitions from screen {screen_id}")
		return results
	
	except Exception as e:
		logger.error(f"Failed to get transitions from screen: {e}")
		return []


async def get_transitions_to_screen(
	screen_id: str,
	limit: int = 10
) -> list[dict[str, Any]]:
	"""
	Get all transitions leading to a screen.
	
	Args:
		screen_id: Target screen ID
		limit: Maximum number of results
	
	Returns:
		List of transition edge documents
	"""
	try:
		db = await get_graph_database()
		if not db:
			logger.warning("ArangoDB unavailable, cannot get transitions")
			return []
		
		# AQL query for inbound transitions
		aql = """
		FOR transition IN @@collection
		FILTER transition._to == @to_vertex
		LIMIT @limit
		RETURN transition
		"""
		
		bind_vars = {
			'@collection': TRANSITIONS_COLLECTION,
			'to_vertex': f"{SCREENS_COLLECTION}/{screen_id}",
			'limit': limit,
		}
		
		cursor = await db.aql.execute(aql, bind_vars=bind_vars)
		results = [doc async for doc in cursor]
		
		logger.debug(f"Found {len(results)} transitions to screen {screen_id}")
		return results
	
	except Exception as e:
		logger.error(f"Failed to get transitions to screen: {e}")
		return []


async def get_screen_statistics(website_id: str | None = None) -> dict[str, Any]:
	"""
	Get statistics about screens in the graph.
	
	Args:
		website_id: Optional website ID filter
	
	Returns:
		Dict with screen count, UI element count, etc.
	"""
	try:
		db = await get_graph_database()
		if not db:
			logger.warning("ArangoDB unavailable, cannot get statistics")
			return {'total_screens': 0, 'total_ui_elements': 0}
		
		# Build AQL query
		if website_id:
			aql = """
			FOR screen IN @@collection
			FILTER screen.website_id == @website_id
			COLLECT AGGREGATE
				total = COUNT(1),
				total_ui_elements = SUM(screen.metadata.ui_elements_count OR 0)
			RETURN {
				total_screens: total,
				total_ui_elements: total_ui_elements
			}
			"""
			bind_vars = {
				'@collection': SCREENS_COLLECTION,
				'website_id': website_id,
			}
		else:
			aql = """
			FOR screen IN @@collection
			COLLECT AGGREGATE
				total = COUNT(1),
				total_ui_elements = SUM(screen.metadata.ui_elements_count OR 0)
			RETURN {
				total_screens: total,
				total_ui_elements: total_ui_elements
			}
			"""
			bind_vars = {
				'@collection': SCREENS_COLLECTION,
			}
		
		cursor = await db.aql.execute(aql, bind_vars=bind_vars)
		results = [doc async for doc in cursor]
		
		if results:
			return results[0]
		else:
			return {'total_screens': 0, 'total_ui_elements': 0}
	
	except Exception as e:
		logger.error(f"Failed to get screen statistics: {e}")
		return {'total_screens': 0, 'total_ui_elements': 0}

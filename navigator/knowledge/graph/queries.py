"""
Graph Query Functions

Helper functions for querying the knowledge graph from MongoDB.
Uses MongoDB as the single source of truth for all knowledge.

Used by Phase 6.2: Graph Query API.

Query types:
- find_path: Find shortest path between two screens (uses NetworkX cache when available)
- get_neighbors: Get adjacent nodes (uses MongoDB queries)
- search_screens: Search screens by name or URL pattern (uses MongoDB queries)
- get_transitions: Get transitions from a screen (uses MongoDB queries)

Architecture:
- All knowledge stored in MongoDB
- NetworkX cache can be built in-memory by agents when needed for path finding
- For now, simple MongoDB queries are used for most operations
"""

import logging
from typing import Any

from navigator.knowledge.persist.documents import (
	get_screen,
	query_screens_by_name_pattern,
	query_screens_by_website,
	query_transitions_by_source,
	query_transitions_by_target,
)

logger = logging.getLogger(__name__)


async def find_shortest_path(
	source_screen_id: str,
	target_screen_id: str,
	max_depth: int = 10,
	website_id: str | None = None,
	use_networkx: bool = True  # Use NetworkX cache if available
) -> dict[str, Any]:
	"""
	Find shortest path between two screens.
	
	Uses NetworkX cache (built from MongoDB) if website_id provided and use_networkx=True.
	Otherwise, performs simple breadth-first search using MongoDB queries.
	
	Args:
		source_screen_id: Source screen ID
		target_screen_id: Target screen ID
		max_depth: Maximum traversal depth (default: 10)
		website_id: Optional website identifier (required for NetworkX cache)
		use_networkx: Whether to use NetworkX cache if available (default: True)
	
	Returns:
		Dict with 'path' (list of screen IDs) and 'edges' (list of edge data)
	"""
	# Try NetworkX cache if available
	if use_networkx and website_id:
		try:
			from navigator.knowledge.graph.cache import get_graph_cache

			cache = get_graph_cache()
			graph = await cache.get_navigation_graph(website_id)
			if graph:
				path_list = await cache.find_shortest_path(
					website_id, source_screen_id, target_screen_id
				)
				if path_list:
					# Get edge data for path
					edges = []
					for i in range(len(path_list) - 1):
						transitions = await cache.get_transitions_from_screen(website_id, path_list[i])
					for trans in transitions:
						if trans.get('to_screen_id') == path_list[i + 1]:
							edges.append(trans)
							break

					return {
						'path': path_list,
						'edges': edges,
						'backend': 'networkx'
					}
		except Exception as e:
			logger.debug(f"NetworkX cache unavailable, using MongoDB BFS: {e}")

	# Fallback: Simple BFS using MongoDB queries
	try:
		# Breadth-first search
		visited = {source_screen_id}
		queue = [(source_screen_id, [source_screen_id])]

		while queue and len(queue[0][1]) <= max_depth:
			current_id, path = queue.pop(0)

			if current_id == target_screen_id:
				# Found path, get edge data
				edges = []
				for i in range(len(path) - 1):
					transitions = await query_transitions_by_source(path[i], limit=100)
					for trans in transitions:
						if trans.to_screen_id == path[i + 1]:
							edges.append(trans.dict())
							break

				return {
					'path': path,
					'edges': edges,
					'backend': 'mongodb_bfs'
				}

			# Get neighbors
			transitions = await query_transitions_by_source(current_id, limit=100)
			for transition in transitions:
				next_id = transition.to_screen_id
				if next_id not in visited:
					visited.add(next_id)
					queue.append((next_id, path + [next_id]))

		logger.debug(f"No path found from {source_screen_id} to {target_screen_id}")
		return {'path': [], 'edges': [], 'backend': 'mongodb_bfs'}

	except Exception as e:
		logger.error(f"Failed to find shortest path: {e}")
		return {'path': [], 'edges': [], 'backend': 'error'}


async def get_adjacent_screens(
	screen_id: str,
	direction: str = "outbound",
	limit: int = 10,
	website_id: str | None = None,
	use_networkx: bool = True
) -> list[dict[str, Any]]:
	"""
	Get adjacent screens (neighbors).
	
	Uses NetworkX cache if available, otherwise MongoDB queries.
	
	Args:
		screen_id: Screen ID
		direction: Direction ('outbound', 'inbound', or 'any')
		limit: Maximum number of results
		website_id: Optional website identifier (required for NetworkX cache)
		use_networkx: Whether to use NetworkX cache if available (default: True)
	
	Returns:
		List of adjacent screen documents with edge data
	"""
	# Try NetworkX cache if available
	if use_networkx and website_id:
		try:
			from navigator.knowledge.graph.cache import get_graph_cache

			cache = get_graph_cache()
			graph = await cache.get_navigation_graph(website_id)
			if graph:
				adjacent_ids = await cache.get_adjacent_screens(website_id, screen_id, direction)
				adjacent_ids = adjacent_ids[:limit]

				# Get screen details from MongoDB
				results = []
				transitions = await cache.get_transitions_from_screen(website_id, screen_id)
				for adj_id in adjacent_ids:
					screen = await get_screen(adj_id)
					if screen:
						edge_data = next(
							(t for t in transitions if t.get('to_screen_id') == adj_id),
							{}
						)
						results.append({
							'screen': screen.dict(),
							'edge': edge_data
						})

				return results
		except Exception as e:
			logger.debug(f"NetworkX cache unavailable, using MongoDB: {e}")

	# Fallback: MongoDB queries
	try:
		results = []

		if direction in ("outbound", "any"):
			transitions = await query_transitions_by_source(screen_id, limit=limit)
			for transition in transitions:
				screen = await get_screen(transition.to_screen_id)
				if screen:
					results.append({
						'screen': screen.dict(),
						'edge': transition.dict()
					})

		if direction in ("inbound", "any") and len(results) < limit:
			transitions = await query_transitions_by_target(screen_id, limit=limit - len(results))
			for transition in transitions:
				screen = await get_screen(transition.from_screen_id)
				if screen:
					results.append({
						'screen': screen.dict(),
						'edge': transition.dict()
					})

		logger.debug(f"Found {len(results)} adjacent screens for {screen_id}")
		return results[:limit]

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
	
	Uses MongoDB queries.
	
	Args:
		screen_name: Screen name to search (partial match)
		website_id: Optional website ID filter
		limit: Maximum number of results
	
	Returns:
		List of matching screen documents
	"""
	try:
		screens = await query_screens_by_name_pattern(screen_name, website_id, limit)
		results = [screen.dict() for screen in screens]

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
	
	Uses MongoDB queries.
	
	Args:
		url_pattern: URL pattern to match (regex or substring)
		website_id: Optional website ID filter
		limit: Maximum number of results
	
	Returns:
		List of matching screen documents
	"""
	try:
		# Query screens by website
		if website_id:
			screens = await query_screens_by_website(website_id, limit=limit * 2)
		else:
			# Would need a function to query all screens - for now, use website_id
			logger.warning("search_screens_by_url_pattern requires website_id when not filtering by website")
			return []

		# Filter by URL pattern
		import re
		pattern_re = re.compile(url_pattern, re.IGNORECASE)
		results = []
		for screen in screens:
			if screen.url_pattern and pattern_re.search(screen.url_pattern):
				results.append(screen.dict())
				if len(results) >= limit:
					break

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
	
	Uses MongoDB queries.
	
	Args:
		screen_id: Source screen ID
		limit: Maximum number of results
	
	Returns:
		List of transition documents
	"""
	try:
		transitions = await query_transitions_by_source(screen_id, limit=limit)
		results = [transition.dict() for transition in transitions]

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
	
	Uses MongoDB queries.
	
	Args:
		screen_id: Target screen ID
		limit: Maximum number of results
	
	Returns:
		List of transition documents
	"""
	try:
		transitions = await query_transitions_by_target(screen_id, limit=limit)
		results = [transition.dict() for transition in transitions]

		logger.debug(f"Found {len(results)} transitions to screen {screen_id}")
		return results

	except Exception as e:
		logger.error(f"Failed to get transitions to screen: {e}")
		return []


async def get_screen_statistics(website_id: str | None = None) -> dict[str, Any]:
	"""
	Get statistics about screens.
	
	Uses MongoDB queries.
	
	Args:
		website_id: Optional website ID filter
	
	Returns:
		Dict with screen count, UI element count, etc.
	"""
	try:
		if website_id:
			screens = await query_screens_by_website(website_id, limit=10000)
		else:
			# Would need a function to query all screens - for now, require website_id
			logger.warning("get_screen_statistics requires website_id when not filtering by website")
			return {'total_screens': 0, 'total_ui_elements': 0}

		total_screens = len(screens)
		total_ui_elements = sum(
			len(screen.ui_elements) if screen.ui_elements else 0
			for screen in screens
		)

		return {
			'total_screens': total_screens,
			'total_ui_elements': total_ui_elements
		}

	except Exception as e:
		logger.error(f"Failed to get screen statistics: {e}")
		return {'total_screens': 0, 'total_ui_elements': 0}

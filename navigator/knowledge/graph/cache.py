"""
In-Memory Graph Cache for Knowledge Graph

Loads graph structure from MongoDB into memory (NetworkX) for fast path finding.
Can be used by agents when needed for graph operations.

Use Cases:
- Fast path finding in agents
- Graph traversal operations
- On-demand graph analysis

Note: This is an optional in-memory cache. All knowledge is stored in MongoDB.
Agents can build this cache when needed for graph operations.
"""

import logging
from typing import Any

try:
	import networkx as nx
	NETWORKX_AVAILABLE = True
except ImportError:
	NETWORKX_AVAILABLE = False
	logging.warning("NetworkX not available - install with: pip install networkx")

from navigator.knowledge.persist.documents import (
	query_screens_by_website,
)

logger = logging.getLogger(__name__)


class GraphCache:
	"""
	In-memory graph cache for navigation and recovery paths.
	
	Loads graph structure from MongoDB and provides fast path finding
	using NetworkX.
	"""

	def __init__(self):
		"""Initialize graph cache."""
		if not NETWORKX_AVAILABLE:
			raise ImportError(
				"NetworkX is required for graph cache. Install with: pip install networkx"
			)

		self._navigation_graphs: dict[str, nx.DiGraph] = {}  # website_id -> graph
		self._recovery_graphs: dict[str, nx.DiGraph] = {}  # website_id -> recovery graph
		logger.info("GraphCache initialized")

	async def get_navigation_graph(self, website_id: str) -> nx.DiGraph | None:
		"""
		Get or build navigation graph for website.
		
		Args:
			website_id: Website identifier
		
		Returns:
			NetworkX DiGraph or None if build fails
		"""
		if website_id in self._navigation_graphs:
			return self._navigation_graphs[website_id]

		# Build graph from MongoDB
		graph = await self._build_navigation_graph(website_id)
		if graph:
			self._navigation_graphs[website_id] = graph

		return graph

	async def _build_navigation_graph(self, website_id: str) -> nx.DiGraph | None:
		"""
		Build navigation graph from MongoDB.
		
		Args:
			website_id: Website identifier
		
		Returns:
			NetworkX DiGraph or None
		"""
		try:
			logger.info(f"Building navigation graph cache for website: {website_id}")

			# Load screens and transitions from MongoDB
			screens = await query_screens_by_website(website_id, limit=10000)

			if not screens:
				logger.warning(f"No screens found for website: {website_id}")
				return None

			# Build graph
			G = nx.DiGraph()

			# Add screen nodes
			for screen in screens:
				G.add_node(
					screen.screen_id,
					name=screen.name,
					url_pattern=screen.url_pattern,
					website_id=screen.website_id,
					**screen.dict(exclude={'screen_id', 'name', 'url_pattern', 'website_id'})
				)

			# Add transition edges (load all transitions for website)
			from navigator.knowledge.persist.documents import query_transitions_by_website
			transitions = await query_transitions_by_website(website_id, limit=10000)

			edges_added = 0
			for transition in transitions:
				# Only add edge if both source and target screens exist in graph
				if (transition.from_screen_id in G and
				    transition.to_screen_id in G):
					# Get cost and reliability from transition
					cost = transition.cost.get('estimated_ms', 1000) if transition.cost else 1000
					reliability = transition.reliability_score if transition.reliability_score else 0.5

					G.add_edge(
						transition.from_screen_id,
						transition.to_screen_id,
						transition_id=transition.transition_id,
						cost=cost,
						reliability=reliability,
						trigger_action=transition.triggered_by,
						conditions=transition.conditions,
						**transition.dict(exclude={
							'transition_id', 'from_screen_id', 'to_screen_id',
							'cost', 'reliability_score', 'triggered_by', 'conditions'
						})
					)
					edges_added += 1

			logger.debug(f"Added {edges_added} transition edges to graph")

			logger.info(
				f"✅ Built navigation graph: {len(G.nodes)} nodes, {len(G.edges)} edges"
			)
			return G

		except Exception as e:
			logger.error(f"Failed to build navigation graph: {e}", exc_info=True)
			return None

	async def find_shortest_path(
		self,
		website_id: str,
		source_screen_id: str,
		target_screen_id: str,
		weight: str = 'cost'
	) -> list[str] | None:
		"""
		Find shortest path between two screens.
		
		Args:
			website_id: Website identifier
			source_screen_id: Source screen ID
			target_screen_id: Target screen ID
			weight: Edge weight attribute ('cost' or 'reliability')
		
		Returns:
			List of screen IDs in path, or None if no path found
		"""
		try:
			# Ensure graph is loaded
			graph = await self.get_navigation_graph(website_id)
			if not graph:
				logger.warning(f"Graph not available for website: {website_id}")
				return None

			if source_screen_id not in graph or target_screen_id not in graph:
				logger.debug(
					f"Screen not in graph: source={source_screen_id}, target={target_screen_id}"
				)
				return None

			try:
				path = nx.shortest_path(
					graph,
					source_screen_id,
					target_screen_id,
					weight=weight
				)
				logger.debug(
					f"Found path: {len(path)} hops from {source_screen_id} to {target_screen_id}"
				)
				return path
			except nx.NetworkXNoPath:
				logger.debug(f"No path found from {source_screen_id} to {target_screen_id}")
				return None

		except Exception as e:
			logger.error(f"Failed to find shortest path: {e}")
			return None

	async def get_adjacent_screens(
		self,
		website_id: str,
		screen_id: str,
		direction: str = "outbound"
	) -> list[str]:
		"""
		Get adjacent screens (neighbors).
		
		Args:
			website_id: Website identifier
			screen_id: Screen ID
			direction: 'outbound' (successors), 'inbound' (predecessors), or 'any'
		
		Returns:
			List of adjacent screen IDs
		"""
		try:
			# Ensure graph is loaded
			graph = await self.get_navigation_graph(website_id)
			if not graph:
				logger.warning(f"Graph not available for website: {website_id}")
				return []

			if screen_id not in graph:
				logger.debug(f"Screen not in graph: {screen_id}")
				return []

			if direction == "outbound":
				return list(graph.successors(screen_id))
			elif direction == "inbound":
				return list(graph.predecessors(screen_id))
			else:  # any
				return list(graph.neighbors(screen_id))

		except Exception as e:
			logger.error(f"Failed to get adjacent screens: {e}")
			return []

	async def get_transitions_from_screen(
		self,
		website_id: str,
		screen_id: str
	) -> list[dict[str, Any]]:
		"""
		Get all transitions from a screen.
		
		Args:
			website_id: Website identifier
			screen_id: Source screen ID
		
		Returns:
			List of transition edge data
		"""
		try:
			# Ensure graph is loaded
			graph = await self.get_navigation_graph(website_id)
			if not graph:
				return []

			if screen_id not in graph:
				return []

			transitions = []
			for target_id in graph.successors(screen_id):
				edge_data = graph.get_edge_data(screen_id, target_id)
				if edge_data:
					transitions.append({
						'from_screen_id': screen_id,
						'to_screen_id': target_id,
						**edge_data
					})

			return transitions

		except Exception as e:
			logger.error(f"Failed to get transitions from screen: {e}")
			return []

	def invalidate(self, website_id: str):
		"""
		Invalidate graph cache for website.
		
		Args:
			website_id: Website identifier
		"""
		if website_id in self._navigation_graphs:
			del self._navigation_graphs[website_id]
			logger.info(f"Invalidated graph cache for website: {website_id}")

		if website_id in self._recovery_graphs:
			del self._recovery_graphs[website_id]

	def get_graph_stats(self, website_id: str) -> dict[str, Any]:
		"""
		Get graph statistics.
		
		Args:
			website_id: Website identifier
		
		Returns:
			Dict with graph statistics
		"""
		graph = self._navigation_graphs.get(website_id)
		if not graph:
			return {'nodes': 0, 'edges': 0, 'cached': False}

		return {
			'nodes': len(graph.nodes),
			'edges': len(graph.edges),
			'cached': True,
			'memory_mb': self._estimate_memory_usage(graph)
		}

	def _estimate_memory_usage(self, graph: nx.DiGraph) -> float:
		"""Estimate memory usage of graph in MB."""
		# Rough estimate: ~100 bytes per node, ~200 bytes per edge
		node_bytes = len(graph.nodes) * 100
		edge_bytes = len(graph.edges) * 200
		total_bytes = node_bytes + edge_bytes
		return total_bytes / (1024 * 1024)  # Convert to MB


# Global cache instance
_graph_cache: GraphCache | None = None


def get_graph_cache() -> GraphCache:
	"""
	Get global graph cache instance.
	
	Returns:
		GraphCache instance
	"""
	global _graph_cache
	if _graph_cache is None:
		_graph_cache = GraphCache()
	return _graph_cache


async def initialize_graph_cache(website_id: str) -> bool:
	"""
	Initialize graph cache for website.
	
	Args:
		website_id: Website identifier
	
	Returns:
		True if initialized successfully
	"""
	try:
		cache = get_graph_cache()
		graph = await cache.get_navigation_graph(website_id)
		return graph is not None
	except Exception as e:
		logger.error(f"Failed to initialize graph cache: {e}")
		return False

"""
REST API: Graph Query Endpoints (Phase 6.2)

Endpoints for querying knowledge graphs.
"""

import logging
import time

try:
	from fastapi import APIRouter, HTTPException
	FASTAPI_AVAILABLE = True
except ImportError:
	FASTAPI_AVAILABLE = False
	logging.warning('FastAPI not installed. Install with: pip install fastapi')

from navigator.knowledge.graph.queries import (
	find_shortest_path,
	get_adjacent_screens,
	get_screen_statistics,
	get_transitions_from_screen,
	search_screens_by_name,
)
from navigator.knowledge.rest_api_models import GraphQueryRequest, GraphQueryResponse

logger = logging.getLogger(__name__)


def register_graph_routes(router: APIRouter) -> None:
	"""
	Register graph query API routes (Phase 6.2).
	
	Args:
		router: FastAPI router to register routes on
	"""
	
	@router.post("/graph/query", response_model=GraphQueryResponse)
	async def graph_query(request: GraphQueryRequest) -> GraphQueryResponse:
		"""
		Execute graph query (Phase 6.2).
		
		Supported query types:
		- find_shortest_path: Find shortest path between two screens
		- get_adjacent_screens: Get screens adjacent to a given screen
		- search_screens: Search screens by name pattern
		- get_transitions: Get transitions from a source screen
		
		Returns query results with execution time.
		"""
		start_time = time.time()
		
		try:
			results = []
			
			if request.query_type == "find_shortest_path":
				if not request.source_screen_id or not request.target_screen_id:
					raise HTTPException(status_code=400, detail="source_screen_id and target_screen_id required for find_shortest_path")
				
				# Find shortest path using graph queries
				path_result = await find_shortest_path(
					source_screen_id=request.source_screen_id,
					target_screen_id=request.target_screen_id,
					website_id=request.website_id
				)
				results = [path_result] if path_result else []
				
			elif request.query_type == "get_adjacent_screens":
				if not request.source_screen_id:
					raise HTTPException(status_code=400, detail="source_screen_id required for get_adjacent_screens")
				
				# Get adjacent screens from MongoDB
				adjacent = await get_adjacent_screens(
					screen_id=request.source_screen_id,
					limit=request.limit
				)
				results = adjacent
				
			elif request.query_type == "search_screens":
				if not request.screen_name and not request.website_id:
					raise HTTPException(status_code=400, detail="screen_name or website_id required for search_screens")
				
				# Search screens in MongoDB
				if request.screen_name:
					results = await search_screens_by_name(
						screen_name=request.screen_name,
						website_id=request.website_id,
						limit=request.limit
					)
				else:
					# Return statistics if only website_id provided
					stats = await get_screen_statistics(website_id=request.website_id)
					results = [stats]
				
			elif request.query_type == "get_transitions":
				if not request.source_screen_id:
					raise HTTPException(status_code=400, detail="source_screen_id required for get_transitions")
				
				# Get transitions from MongoDB
				results = await get_transitions_from_screen(
					screen_id=request.source_screen_id,
					limit=request.limit
				)
				
			else:
				raise HTTPException(status_code=400, detail=f"Unknown query type: {request.query_type}")
			
			execution_time_ms = (time.time() - start_time) * 1000
			
			return GraphQueryResponse(
				query_type=request.query_type,
				results=results,
				count=len(results),
				execution_time_ms=execution_time_ms
			)
			
		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Graph query failed: {e}")
			raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

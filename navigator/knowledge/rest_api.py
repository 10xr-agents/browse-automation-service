"""
Knowledge Extraction REST API

Production API for knowledge extraction and retrieval.

Implements Phase 6: REST API Upgrades

Provides HTTP endpoints for:
- Starting knowledge extraction workflows (6.1)
- Querying knowledge graphs (6.2)
- Retrieving knowledge definitions (6.3)
- Getting workflow status (6.4)
- Triggering verification workflows (6.5)
"""

import logging

try:
	from fastapi import APIRouter
	FASTAPI_AVAILABLE = True
except ImportError:
	FASTAPI_AVAILABLE = False
	logging.warning('FastAPI not installed. Install with: pip install fastapi')

from temporalio.client import Client

from navigator.knowledge.rest_api_graph import register_graph_routes
from navigator.knowledge.rest_api_ingestion import register_ingestion_routes
from navigator.knowledge.rest_api_knowledge import register_knowledge_routes
from navigator.knowledge.rest_api_verification import register_verification_routes
from navigator.knowledge.rest_api_workflows import register_workflow_routes
from navigator.temporal.config import get_temporal_client

logger = logging.getLogger(__name__)


def create_knowledge_api_router() -> APIRouter | None:
	"""
	Create FastAPI router for knowledge extraction REST API.
	
	Production API implementing Phase 6: REST API Upgrades
	
	Returns:
		APIRouter instance or None if FastAPI not available
	"""
	if not FASTAPI_AVAILABLE:
		logger.error("FastAPI not available, cannot create router")
		return None

	router = APIRouter(
		prefix="/api/knowledge",
		tags=["Knowledge Extraction"],
	)

	# Store Temporal client
	_temporal_client: Client | None = None

	async def _get_temporal_client() -> Client | None:
		"""Get or create Temporal client. Returns None if Temporal is not available."""
		nonlocal _temporal_client
		if _temporal_client is None:
			try:
				_temporal_client = await get_temporal_client()
			except Exception as e:
				# Temporal is not available - this is expected if Temporal server is not running
				logger.debug(f"Temporal client not available (server may not be running): {type(e).__name__}")
				return None
		return _temporal_client

	# Register all route groups
	register_ingestion_routes(router, _get_temporal_client)
	register_graph_routes(router)
	register_knowledge_routes(router)
	register_workflow_routes(router, _get_temporal_client)
	register_verification_routes(router, _get_temporal_client)

	# ========================================================================
	# Health Check
	# ========================================================================

	@router.get("/health")
	async def health_check() -> dict:
		"""Health check endpoint."""
		return {
			"status": "healthy",
			"service": "knowledge-extraction-api",
			"version": "1.0.0"
		}

	return router

"""
Knowledge Retrieval & Storage Flow

Components for comprehensive website exploration and knowledge extraction.

Includes Phase 6 REST API v2 for knowledge extraction.
"""

from navigator.knowledge.api import KnowledgeAPI
from navigator.knowledge.exploration_engine import ExplorationEngine, ExplorationStrategy
from navigator.knowledge.flow_mapper import FunctionalFlowMapper
from navigator.knowledge.pipeline import KnowledgePipeline
from navigator.knowledge.semantic_analyzer import SemanticAnalyzer
from navigator.knowledge.sitemap_generator import SiteMapGenerator
from navigator.knowledge.storage import KnowledgeStorage
from navigator.knowledge.vector_store import VectorStore

# Phase 6: Production REST API
try:
	from navigator.knowledge.rest_api import create_knowledge_api_router
	_API_AVAILABLE = True
except ImportError:
	_API_AVAILABLE = False
	create_knowledge_api_router = None

__all__ = [
	'ExplorationEngine',
	'ExplorationStrategy',
	'SemanticAnalyzer',
	'FunctionalFlowMapper',
	'KnowledgeStorage',
	'VectorStore',
	'KnowledgePipeline',
	'SiteMapGenerator',
	'KnowledgeAPI',
	'create_knowledge_api_router',
]

"""
Knowledge Retrieval API

Provides API endpoints for accessing stored knowledge.
"""

import logging
from typing import Any

from navigator.knowledge.pipeline import KnowledgePipeline
from navigator.knowledge.sitemap_generator import SiteMapGenerator
from navigator.knowledge.storage import KnowledgeStorage
from navigator.knowledge.vector_store import VectorStore

logger = logging.getLogger(__name__)


class KnowledgeAPI:
	"""
	Knowledge retrieval API for accessing stored knowledge.
	
	Supports:
	- Page retrieval
	- Semantic search
	- Site map generation
	- Knowledge queries
	"""

	def __init__(
		self,
		storage: KnowledgeStorage,
		vector_store: VectorStore | None = None,
		pipeline: KnowledgePipeline | None = None,
		sitemap_generator: SiteMapGenerator | None = None,
	):
		"""
		Initialize the knowledge API.
		
		Args:
			storage: Knowledge storage instance
			vector_store: Vector store instance (optional)
			pipeline: Knowledge pipeline instance (optional)
			sitemap_generator: Site map generator instance (optional)
		"""
		self.storage = storage
		self.vector_store = vector_store
		self.pipeline = pipeline
		self.sitemap_generator = sitemap_generator or SiteMapGenerator(
			storage=storage,
			vector_store=vector_store,
		)

		logger.debug("KnowledgeAPI initialized")

	async def get_page(self, url: str) -> dict[str, Any]:
		"""
		Get a page by URL.
		
		Args:
			url: Page URL
		
		Returns:
			Page data dictionary
		"""
		try:
			page = await self.storage.get_page(url)
			if page:
				return {
					'success': True,
					'page': page,
				}
			else:
				return {
					'success': False,
					'error': 'Page not found',
				}
		except Exception as e:
			logger.error(f"Failed to get page {url}: {e}")
			return {
				'success': False,
				'error': str(e),
			}

	async def search(self, query: str, top_k: int = 5) -> dict[str, Any]:
		"""
		Search for pages using semantic search.
		
		Args:
			query: Search query text
			top_k: Number of results to return
		
		Returns:
			Search results dictionary
		"""
		try:
			if not self.pipeline:
				return {
					'success': False,
					'error': 'Pipeline not available for semantic search',
				}

			results = await self.pipeline.search_similar(query, top_k=top_k)

			return {
				'success': True,
				'query': query,
				'results': results,
				'count': len(results),
			}
		except Exception as e:
			logger.error(f"Failed to search: {e}")
			return {
				'success': False,
				'error': str(e),
			}

	async def get_links(self, url: str, direction: str = 'from') -> dict[str, Any]:
		"""
		Get links for a page.
		
		Args:
			url: Page URL
			direction: 'from' or 'to' (default: 'from')
		
		Returns:
			Links dictionary
		"""
		try:
			if direction == 'from':
				links = await self.storage.get_links_from(url)
			elif direction == 'to':
				links = await self.storage.get_links_to(url)
			else:
				return {
					'success': False,
					'error': f"Invalid direction: {direction} (must be 'from' or 'to')",
				}

			return {
				'success': True,
				'url': url,
				'direction': direction,
				'links': links,
				'count': len(links),
			}
		except Exception as e:
			logger.error(f"Failed to get links for {url}: {e}")
			return {
				'success': False,
				'error': str(e),
			}

	async def get_semantic_sitemap(self) -> dict[str, Any]:
		"""
		Get semantic site map.
		
		Returns:
			Semantic site map dictionary
		"""
		try:
			sitemap = await self.sitemap_generator.generate_semantic_sitemap()
			return {
				'success': True,
				'sitemap': sitemap,
			}
		except Exception as e:
			logger.error(f"Failed to get semantic site map: {e}")
			return {
				'success': False,
				'error': str(e),
			}

	async def get_functional_sitemap(self) -> dict[str, Any]:
		"""
		Get functional site map.
		
		Returns:
			Functional site map dictionary
		"""
		try:
			sitemap = await self.sitemap_generator.generate_functional_sitemap()
			return {
				'success': True,
				'sitemap': sitemap,
			}
		except Exception as e:
			logger.error(f"Failed to get functional site map: {e}")
			return {
				'success': False,
				'error': str(e),
			}

	async def query(self, query_type: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
		"""
		Generic query interface for knowledge retrieval.
		
		Args:
			query_type: Type of query ('page', 'search', 'links', 'sitemap_semantic', 'sitemap_functional')
			params: Query parameters
		
		Returns:
			Query results dictionary
		"""
		params = params or {}

		try:
			if query_type == 'page':
				url = params.get('url', '')
				if not url:
					return {'success': False, 'error': 'url parameter required'}
				return await self.get_page(url)

			elif query_type == 'search':
				query = params.get('query', '')
				top_k = params.get('top_k', 5)
				if not query:
					return {'success': False, 'error': 'query parameter required'}
				return await self.search(query, top_k=top_k)

			elif query_type == 'links':
				url = params.get('url', '')
				direction = params.get('direction', 'from')
				if not url:
					return {'success': False, 'error': 'url parameter required'}
				return await self.get_links(url, direction=direction)

			elif query_type == 'sitemap_semantic':
				return await self.get_semantic_sitemap()

			elif query_type == 'sitemap_functional':
				return await self.get_functional_sitemap()

			else:
				return {
					'success': False,
					'error': f"Unknown query type: {query_type}",
					'available_types': ['page', 'search', 'links', 'sitemap_semantic', 'sitemap_functional'],
				}
		except Exception as e:
			logger.error(f"Failed to execute query {query_type}: {e}")
			return {
				'success': False,
				'error': str(e),
			}

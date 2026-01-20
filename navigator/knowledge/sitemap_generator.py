"""
Site Map Generator for Knowledge Retrieval

Generates semantic and functional site maps from stored knowledge.
"""

import logging
from typing import Any

from navigator.knowledge.flow_mapper import FunctionalFlowMapper
from navigator.knowledge.storage import KnowledgeStorage
from navigator.knowledge.vector_store import VectorStore

logger = logging.getLogger(__name__)


class SiteMapGenerator:
	"""
	Site map generator for creating semantic and functional site maps.
	
	Supports:
	- Semantic site maps (hierarchical structure, topics, categories)
	- Functional site maps (navigation flows, user journeys, action sequences)
	- Export to JSON/XML/GraphML/Mermaid formats
	"""

	def __init__(
		self,
		storage: KnowledgeStorage,
		flow_mapper: FunctionalFlowMapper | None = None,
		vector_store: VectorStore | None = None,
	):
		"""
		Initialize the site map generator.
		
		Args:
			storage: Knowledge storage instance
			flow_mapper: Flow mapper instance (optional)
			vector_store: Vector store instance (optional)
		"""
		self.storage = storage
		self.flow_mapper = flow_mapper or FunctionalFlowMapper()
		self.vector_store = vector_store

		logger.debug("SiteMapGenerator initialized")

	async def generate_semantic_sitemap(self) -> dict[str, Any]:
		"""
		Generate semantic site map (hierarchical structure based on content).
		
		Returns:
			Dictionary with semantic site map structure
		"""
		try:
			# Get all pages from storage (in-memory for now)
			if hasattr(self.storage, 'pages'):
				pages = list(self.storage.pages.values())
			else:
				# Query all pages from MongoDB
				try:
					from navigator.knowledge.persist.documents.screens import query_screens_by_knowledge_id
					from navigator.knowledge.persist.collections import get_screens_collection
					
					# Get all screens from MongoDB (screens represent pages)
					collection = await get_screens_collection()
					if collection:
						cursor = collection.find({})
						screen_docs = await cursor.to_list(length=None)
						
						# Convert screens to page format
						pages = []
						for screen_doc in screen_docs:
							pages.append({
								'url': screen_doc.get('url', ''),
								'title': screen_doc.get('name', screen_doc.get('screen_id', '')),
								'description': screen_doc.get('description', ''),
								'topics': {
									'categories': screen_doc.get('categories', []),
									'main_topics': screen_doc.get('topics', []),
									'keywords': screen_doc.get('keywords', []),
								}
							})
						logger.info(f"✅ Loaded {len(pages)} pages from MongoDB for sitemap generation")
					else:
						logger.warning("⚠️ MongoDB screens collection unavailable, using empty structure")
						pages = []
				except Exception as e:
					logger.warning(f"⚠️ Failed to load pages from MongoDB: {e}, using empty structure")
					pages = []

			# Group by topics/categories
			topics: dict[str, list[dict[str, Any]]] = {}
			hierarchy: list[dict[str, Any]] = []

			for page in pages:
				page_topics = page.get('topics', {})
				page_categories = page_topics.get('categories', [])

				# Group by first category (or "Uncategorized")
				category = page_categories[0] if page_categories else "Uncategorized"

				if category not in topics:
					topics[category] = []

				topics[category].append({
					'url': page.get('url', ''),
					'title': page.get('title', ''),
					'description': page.get('description', ''),
					'main_topics': page_topics.get('main_topics', []),
					'keywords': page_topics.get('keywords', [])[:10],  # Top 10 keywords
				})

			# Build hierarchy
			for category, category_pages in topics.items():
				hierarchy.append({
					'category': category,
					'pages': category_pages,
					'count': len(category_pages),
				})

			return {
				'hierarchy': hierarchy,
				'topics': list(topics.keys()),
				'total_pages': len(pages),
				'categories': len(topics),
			}
		except Exception as e:
			logger.error(f"Failed to generate semantic site map: {e}")
			return {
				'hierarchy': [],
				'topics': [],
				'total_pages': 0,
				'categories': 0,
				'error': str(e),
			}

	async def generate_functional_sitemap(self) -> dict[str, Any]:
		"""
		Generate functional site map (navigation flows, user journeys).
		
		Returns:
			Dictionary with functional site map structure
		"""
		try:
			# Analyze flows
			flow_analysis = self.flow_mapper.analyze_flows()

			# Get navigation structure
			navigation: list[dict[str, Any]] = []

			# Build navigation from flow mapper
			entry_points = flow_analysis.get('entry_points', [])
			popular_paths = flow_analysis.get('popular_paths', [])

			# Create navigation structure
			for entry_point in entry_points:
				navigation.append({
					'entry_point': entry_point,
					'type': 'entry',
				})

			# Get user journeys (popular paths)
			user_journeys: list[dict[str, Any]] = []
			for path in popular_paths:
				user_journeys.append({
					'path': path,
					'steps': len(path),
				})

			return {
				'navigation': navigation,
				'user_journeys': user_journeys,
				'entry_points': entry_points,
				'exit_points': flow_analysis.get('exit_points', []),
				'popular_pages': flow_analysis.get('popular_pages', []),
				'avg_path_length': flow_analysis.get('avg_path_length', 0.0),
			}
		except Exception as e:
			logger.error(f"Failed to generate functional site map: {e}")
			return {
				'navigation': [],
				'user_journeys': [],
				'entry_points': [],
				'exit_points': [],
				'popular_pages': [],
				'avg_path_length': 0.0,
				'error': str(e),
			}

	async def export_to_json(self, sitemap: dict[str, Any], output_path: str | None = None) -> str:
		"""
		Export site map to JSON format.
		
		Args:
			sitemap: Site map dictionary
			output_path: Optional output file path
		
		Returns:
			JSON string representation
		"""
		import json

		json_str = json.dumps(sitemap, indent=2)

		if output_path:
			with open(output_path, 'w') as f:
				f.write(json_str)
			logger.debug(f"Exported site map to {output_path}")

		return json_str

	async def export_to_xml(self, sitemap: dict[str, Any], output_path: str | None = None) -> str:
		"""
		Export site map to XML format (sitemap.xml compatible).
		
		Args:
			sitemap: Site map dictionary
			output_path: Optional output file path
		
		Returns:
			XML string representation
		"""
		xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
		xml_lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

		# Extract URLs from hierarchy (semantic) or navigation (functional)
		urls = set()

		if 'hierarchy' in sitemap:
			for category_data in sitemap['hierarchy']:
				for page in category_data.get('pages', []):
					url = page.get('url', '')
					if url:
						urls.add(url)
		elif 'navigation' in sitemap:
			# Extract URLs from navigation structure
			for nav_item in sitemap['navigation']:
				entry_point = nav_item.get('entry_point', '')
				if entry_point:
					urls.add(entry_point)

		# Generate XML entries
		for url in urls:
			xml_lines.append('  <url>')
			xml_lines.append(f'    <loc>{url}</loc>')
			xml_lines.append('  </url>')

		xml_lines.append('</urlset>')
		xml_str = '\n'.join(xml_lines)

		if output_path:
			with open(output_path, 'w') as f:
				f.write(xml_str)
			logger.debug(f"Exported site map to {output_path}")

		return xml_str

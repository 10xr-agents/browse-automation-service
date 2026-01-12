"""
Tests for Site Map Generator (Steps 2.18-2.19).

Tests cover:
- Semantic Site Map (Step 2.18)
- Functional Site Map (Step 2.19)
"""

import pytest

from navigator.knowledge.flow_mapper import FunctionalFlowMapper
from navigator.knowledge.sitemap_generator import SiteMapGenerator
from navigator.knowledge.storage import KnowledgeStorage
from navigator.knowledge.vector_store import VectorStore


class TestSitemapGeneratorInitialization:
	"""Tests for site map generator initialization (Steps 2.18-2.19)."""

	def test_sitemap_generator_init(self):
		"""Test site map generator initialization."""
		storage = KnowledgeStorage(use_arangodb=False)
		flow_mapper = FunctionalFlowMapper()
		vector_store = VectorStore(use_vector_db=False)
		
		generator = SiteMapGenerator(
			storage=storage,
			flow_mapper=flow_mapper,
			vector_store=vector_store,
		)
		
		assert generator.storage == storage
		assert generator.flow_mapper == flow_mapper
		assert generator.vector_store == vector_store


class TestSemanticSitemap:
	"""Tests for semantic site map generation (Step 2.18)."""

	@pytest.mark.asyncio
	async def test_generate_semantic_sitemap(self):
		"""Test generating semantic site map."""
		storage = KnowledgeStorage(use_arangodb=False)
		generator = SiteMapGenerator(storage=storage)
		
		# Store some pages with topics
		await storage.store_page("https://example.com/page1", {
			"title": "Page 1",
			"topics": {
				"categories": ["Technology"],
				"keywords": ["python", "programming"],
				"main_topics": ["Python Tutorial"],
			},
		})
		
		await storage.store_page("https://example.com/page2", {
			"title": "Page 2",
			"topics": {
				"categories": ["Technology"],
				"keywords": ["javascript", "web"],
				"main_topics": ["JavaScript Guide"],
			},
		})
		
		sitemap = await generator.generate_semantic_sitemap()
		
		assert "hierarchy" in sitemap
		assert "topics" in sitemap
		assert "total_pages" in sitemap
		assert "categories" in sitemap
		assert sitemap["total_pages"] >= 2

	@pytest.mark.asyncio
	async def test_export_semantic_sitemap_to_json(self):
		"""Test exporting semantic site map to JSON."""
		storage = KnowledgeStorage(use_arangodb=False)
		generator = SiteMapGenerator(storage=storage)
		
		# Store a page
		await storage.store_page("https://example.com/page1", {
			"title": "Page 1",
			"topics": {"categories": ["Technology"]},
		})
		
		sitemap = await generator.generate_semantic_sitemap()
		json_str = await generator.export_to_json(sitemap)
		
		assert isinstance(json_str, str)
		assert "hierarchy" in json_str or '"hierarchy"' in json_str

	@pytest.mark.asyncio
	async def test_export_semantic_sitemap_to_xml(self):
		"""Test exporting semantic site map to XML."""
		storage = KnowledgeStorage(use_arangodb=False)
		generator = SiteMapGenerator(storage=storage)
		
		# Store a page
		await storage.store_page("https://example.com/page1", {
			"title": "Page 1",
			"url": "https://example.com/page1",
			"topics": {"categories": ["Technology"]},
		})
		
		sitemap = await generator.generate_semantic_sitemap()
		xml_str = await generator.export_to_xml(sitemap)
		
		assert isinstance(xml_str, str)
		assert "<?xml" in xml_str
		assert "<urlset" in xml_str


class TestFunctionalSitemap:
	"""Tests for functional site map generation (Step 2.19)."""

	@pytest.mark.asyncio
	async def test_generate_functional_sitemap(self):
		"""Test generating functional site map."""
		storage = KnowledgeStorage(use_arangodb=False)
		flow_mapper = FunctionalFlowMapper()
		generator = SiteMapGenerator(storage=storage, flow_mapper=flow_mapper)
		
		# Add some navigation data
		flow_mapper.track_navigation("https://example.com/home")
		flow_mapper.track_navigation("https://example.com/about", referrer="https://example.com/home")
		flow_mapper.start_click_path("https://example.com/home")
		flow_mapper.add_to_click_path("https://example.com/about")
		flow_mapper.end_click_path()
		
		sitemap = await generator.generate_functional_sitemap()
		
		assert "navigation" in sitemap
		assert "user_journeys" in sitemap
		assert "entry_points" in sitemap
		assert "exit_points" in sitemap
		assert "popular_pages" in sitemap
		assert "avg_path_length" in sitemap

	@pytest.mark.asyncio
	async def test_export_functional_sitemap_to_json(self):
		"""Test exporting functional site map to JSON."""
		storage = KnowledgeStorage(use_arangodb=False)
		flow_mapper = FunctionalFlowMapper()
		generator = SiteMapGenerator(storage=storage, flow_mapper=flow_mapper)
		
		flow_mapper.track_navigation("https://example.com/home")
		
		sitemap = await generator.generate_functional_sitemap()
		json_str = await generator.export_to_json(sitemap)
		
		assert isinstance(json_str, str)
		assert "navigation" in json_str or '"navigation"' in json_str

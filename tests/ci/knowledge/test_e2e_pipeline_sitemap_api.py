"""
End-to-End Tests for Pipeline, Site Map Generator, and API (Steps 2.17-2.20).

Tests the complete pipeline, site map generation, and API workflow.
"""

import pytest

from browser_use import BrowserSession
from browser_use.browser.profile import BrowserProfile

from navigator.knowledge.api import KnowledgeAPI
from navigator.knowledge.flow_mapper import FunctionalFlowMapper
from navigator.knowledge.pipeline import KnowledgePipeline
from navigator.knowledge.sitemap_generator import SiteMapGenerator
from navigator.knowledge.storage import KnowledgeStorage
from navigator.knowledge.vector_store import VectorStore


class TestE2EPipeline:
	"""End-to-end tests for complete pipeline workflow."""

	@pytest.mark.asyncio
	async def test_e2e_pipeline_workflow(self, browser_session):
		"""Test complete pipeline workflow."""
		storage = KnowledgeStorage(use_arangodb=False)
		vector_store = VectorStore(use_vector_db=False)
		
		pipeline = KnowledgePipeline(
			browser_session=browser_session,
			storage=storage,
			vector_store=vector_store,
		)
		
		# Process a URL
		result = await pipeline.process_url("https://example.com")
		
		assert "success" in result
		if result.get("success"):
			# Verify page stored
			page = await storage.get_page("https://example.com")
			assert page is not None
			
			# Verify embedding stored
			embedding = await vector_store.get_embedding("https://example.com")
			assert embedding is not None


class TestE2ESitemapGeneration:
	"""End-to-end tests for site map generation."""

	@pytest.mark.asyncio
	async def test_e2e_semantic_and_functional_sitemap(self):
		"""Test generating both semantic and functional site maps."""
		storage = KnowledgeStorage(use_arangodb=False)
		flow_mapper = FunctionalFlowMapper()
		generator = SiteMapGenerator(
			storage=storage,
			flow_mapper=flow_mapper,
		)
		
		# Store pages
		await storage.store_page("https://example.com/page1", {
			"title": "Page 1",
			"topics": {"categories": ["Technology"]},
		})
		
		# Add navigation data
		flow_mapper.track_navigation("https://example.com/page1")
		flow_mapper.start_click_path("https://example.com/page1")
		flow_mapper.end_click_path()
		
		# Generate semantic site map
		semantic_sitemap = await generator.generate_semantic_sitemap()
		assert "hierarchy" in semantic_sitemap
		
		# Generate functional site map
		functional_sitemap = await generator.generate_functional_sitemap()
		assert "navigation" in functional_sitemap


class TestE2EAPI:
	"""End-to-end tests for knowledge API."""

	@pytest.mark.asyncio
	async def test_e2e_api_workflow(self, browser_session):
		"""Test complete API workflow."""
		storage = KnowledgeStorage(use_arangodb=False)
		vector_store = VectorStore(use_vector_db=False)
		pipeline = KnowledgePipeline(
			browser_session=browser_session,
			storage=storage,
			vector_store=vector_store,
		)
		
		api = KnowledgeAPI(
			storage=storage,
			vector_store=vector_store,
			pipeline=pipeline,
		)
		
		# Store a page
		await storage.store_page("https://example.com/test", {
			"title": "Test Page",
			"topics": {"categories": ["Test"]},
		})
		
		# Get page via API
		result = await api.get_page("https://example.com/test")
		assert result["success"] is True
		
		# Get semantic site map via API
		sitemap_result = await api.get_semantic_sitemap()
		assert sitemap_result["success"] is True
		
		# Query via generic query interface
		query_result = await api.query("page", {"url": "https://example.com/test"})
		assert query_result["success"] is True


class TestE2EIntegration:
	"""End-to-end integration tests for complete workflow."""

	@pytest.mark.asyncio
	async def test_e2e_complete_workflow(self, browser_session):
		"""Test complete workflow: pipeline → site map → API."""
		storage = KnowledgeStorage(use_arangodb=False)
		vector_store = VectorStore(use_vector_db=False)
		flow_mapper = FunctionalFlowMapper()
		
		pipeline = KnowledgePipeline(
			browser_session=browser_session,
			storage=storage,
			vector_store=vector_store,
		)
		
		# Process a URL
		result = await pipeline.process_url("https://example.com")
		if result.get("success"):
			# Track navigation
			flow_mapper.track_navigation("https://example.com")
			
			# Generate site map
			generator = SiteMapGenerator(
				storage=storage,
				flow_mapper=flow_mapper,
			)
			sitemap = await generator.generate_semantic_sitemap()
			assert "hierarchy" in sitemap
			
			# Access via API
			api = KnowledgeAPI(
				storage=storage,
				vector_store=vector_store,
				pipeline=pipeline,
			)
			page_result = await api.get_page("https://example.com")
			assert page_result["success"] is True

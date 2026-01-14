"""
Complete Phase 2 Testing Script

Tests the entire knowledge retrieval flow from Steps 2.1-2.20.
"""

import asyncio
import logging
from typing import Any

import pytest

from browser_use import BrowserSession
from browser_use.browser.profile import BrowserProfile

from navigator.knowledge.api import KnowledgeAPI
from navigator.knowledge.exploration_engine import ExplorationEngine, ExplorationStrategy
from navigator.knowledge.flow_mapper import FunctionalFlowMapper
from navigator.knowledge.pipeline import KnowledgePipeline
from navigator.knowledge.semantic_analyzer import SemanticAnalyzer
from navigator.knowledge.sitemap_generator import SiteMapGenerator
from navigator.knowledge.storage import KnowledgeStorage
from navigator.knowledge.vector_store import VectorStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestPhase2Complete:
	"""Complete Phase 2 integration tests."""

	@pytest.mark.asyncio
	async def test_complete_phase2_workflow(self, browser_session, base_url):
		"""Test complete Phase 2 workflow: Exploration → Analysis → Storage → Retrieval."""
		logger.info("Starting complete Phase 2 workflow test")
		
		# Initialize all components
		storage = KnowledgeStorage(use_arangodb=False)
		vector_store = VectorStore(use_vector_db=False)
		flow_mapper = FunctionalFlowMapper()
		
		# Create pipeline
		pipeline = KnowledgePipeline(
			browser_session=browser_session,
			storage=storage,
			vector_store=vector_store,
			max_depth=2,
			strategy=ExplorationStrategy.BFS,
		)
		
		# Step 1: Explore and store (Steps 2.1-2.6, 2.17)
		logger.info("Step 1: Exploring and storing pages")
		start_url = f"{base_url}/"
		results = await pipeline.explore_and_store(start_url, max_pages=5)
		
		assert results["pages_processed"] > 0, "Should have processed at least one page"
		logger.info(f"Processed {results['pages_processed']} pages, stored {results['pages_stored']} pages")
		
		# Step 2: Verify storage (Steps 2.13-2.15)
		logger.info("Step 2: Verifying storage")
		for result in results["results"]:
			if result.get("success"):
				url = result["url"]
				page = await storage.get_page(url)
				assert page is not None, f"Page {url} should be stored"
				
				# Verify embedding stored
				embedding = await vector_store.get_embedding(url)
				assert embedding is not None, f"Embedding for {url} should be stored"
		
		# Step 3: Test semantic search (Step 2.16)
		logger.info("Step 3: Testing semantic search")
		if results["pages_stored"] > 0:
			search_results = await pipeline.search_similar("example content", top_k=3)
			assert isinstance(search_results, list), "Search results should be a list"
			logger.info(f"Found {len(search_results)} similar pages")
		
		# Step 4: Test site map generation (Steps 2.18-2.19)
		logger.info("Step 4: Testing site map generation")
		sitemap_generator = SiteMapGenerator(
			storage=storage,
			flow_mapper=flow_mapper,
			vector_store=vector_store,
		)
		
		# Add some navigation data for functional site map
		if results["pages_stored"] > 0:
			first_result = results["results"][0]
			if first_result.get("success"):
				flow_mapper.track_navigation(first_result["url"])
				flow_mapper.start_click_path(first_result["url"])
				flow_mapper.end_click_path()
		
		semantic_sitemap = await sitemap_generator.generate_semantic_sitemap()
		assert "hierarchy" in semantic_sitemap, "Semantic site map should have hierarchy"
		logger.info(f"Semantic site map: {semantic_sitemap['total_pages']} pages, {semantic_sitemap['categories']} categories")
		
		functional_sitemap = await sitemap_generator.generate_functional_sitemap()
		assert "navigation" in functional_sitemap, "Functional site map should have navigation"
		logger.info(f"Functional site map: {len(functional_sitemap['user_journeys'])} user journeys")
		
		# Step 5: Test API (Step 2.20)
		logger.info("Step 5: Testing Knowledge API")
		api = KnowledgeAPI(
			storage=storage,
			vector_store=vector_store,
			pipeline=pipeline,
			sitemap_generator=sitemap_generator,
		)
		
		# Test get_page
		if results["pages_stored"] > 0:
			first_result = results["results"][0]
			if first_result.get("success"):
				url = first_result["url"]
				page_result = await api.get_page(url)
				assert page_result["success"] is True, "Should be able to get page"
				logger.info(f"API get_page: Success for {url}")
		
		# Test semantic sitemap via API
		sitemap_result = await api.get_semantic_sitemap()
		assert sitemap_result["success"] is True, "Should be able to get semantic site map"
		logger.info("API get_semantic_sitemap: Success")
		
		# Test functional sitemap via API
		functional_result = await api.get_functional_sitemap()
		assert functional_result["success"] is True, "Should be able to get functional site map"
		logger.info("API get_functional_sitemap: Success")
		
		# Test query interface
		if results["pages_stored"] > 0:
			first_result = results["results"][0]
			if first_result.get("success"):
				url = first_result["url"]
				query_result = await api.query("page", {"url": url})
				assert query_result["success"] is True, "Query interface should work"
				logger.info(f"API query: Success for page query")
		
		logger.info("Complete Phase 2 workflow test: SUCCESS")
		
		return {
			"success": True,
			"pages_processed": results["pages_processed"],
			"pages_stored": results["pages_stored"],
			"semantic_sitemap_pages": semantic_sitemap["total_pages"],
			"functional_sitemap_journeys": len(functional_sitemap["user_journeys"]),
		}

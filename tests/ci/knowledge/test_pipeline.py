"""
Tests for Knowledge Pipeline (Step 2.17).

Tests cover:
- Integration Pipeline (Step 2.17)
"""

import pytest

from browser_use import BrowserSession
from browser_use.browser.profile import BrowserProfile

from navigator.knowledge.exploration_engine import ExplorationStrategy
from navigator.knowledge.pipeline import KnowledgePipeline
from navigator.knowledge.storage import KnowledgeStorage
from navigator.knowledge.vector_store import VectorStore


class TestPipelineInitialization:
	"""Tests for pipeline initialization (Step 2.17)."""

	@pytest.mark.asyncio
	async def test_pipeline_init(self):
		"""Test pipeline initialization."""
		browser_session = BrowserSession(browser_profile=BrowserProfile(headless=True, user_data_dir=None))
		await browser_session.start()
		try:
			storage = KnowledgeStorage(use_arangodb=False)
			vector_store = VectorStore(use_vector_db=False)
			
			pipeline = KnowledgePipeline(
				browser_session=browser_session,
				storage=storage,
				vector_store=vector_store,
			)
			
			assert pipeline.browser_session == browser_session
			assert pipeline.storage == storage
			assert pipeline.vector_store == vector_store
			assert pipeline.exploration_engine is not None
			assert pipeline.semantic_analyzer is not None
		finally:
			await browser_session.kill()


class TestPipelineOperations:
	"""Tests for pipeline operations (Step 2.17)."""

	@pytest.mark.asyncio
	async def test_process_url(self, browser_session):
		"""Test processing a single URL."""
		storage = KnowledgeStorage(use_arangodb=False)
		vector_store = VectorStore(use_vector_db=False)
		
		pipeline = KnowledgePipeline(
			browser_session=browser_session,
			storage=storage,
			vector_store=vector_store,
		)
		
		# Process a URL (using a simple test URL)
		result = await pipeline.process_url("https://example.com")
		
		assert "success" in result
		assert "url" in result
		if result.get("success"):
			assert "content" in result
			assert "entities" in result
			assert "topics" in result

	@pytest.mark.asyncio
	async def test_explore_and_store(self, browser_session, base_url, http_server):
		"""Test explore and store workflow."""
		storage = KnowledgeStorage(use_arangodb=False)
		vector_store = VectorStore(use_vector_db=False)
		
		pipeline = KnowledgePipeline(
			browser_session=browser_session,
			storage=storage,
			vector_store=vector_store,
		)
		
		# Set up test server with multiple pages
		url = f"{base_url}/page1"
		
		# Explore and store (with max_pages limit)
		results = await pipeline.explore_and_store(url, max_pages=3)
		
		assert "start_url" in results
		assert "pages_processed" in results
		assert "pages_stored" in results
		assert results["pages_processed"] > 0

	@pytest.mark.asyncio
	async def test_search_similar(self, browser_session):
		"""Test semantic search."""
		storage = KnowledgeStorage(use_arangodb=False)
		vector_store = VectorStore(use_vector_db=False)
		
		pipeline = KnowledgePipeline(
			browser_session=browser_session,
			storage=storage,
			vector_store=vector_store,
		)
		
		# Store some pages first
		await pipeline.process_url("https://example.com")
		
		# Search for similar pages
		results = await pipeline.search_similar("example content", top_k=3)
		
		assert isinstance(results, list)
		# Results may be empty if no matches, which is OK

"""
Tests for Knowledge API (Step 2.20).

Tests cover:
- Knowledge Retrieval API (Step 2.20)
"""

import pytest

from browser_use import BrowserSession
from browser_use.browser.profile import BrowserProfile

from navigator.knowledge.api import KnowledgeAPI
from navigator.knowledge.flow_mapper import FunctionalFlowMapper
from navigator.knowledge.pipeline import KnowledgePipeline
from navigator.knowledge.storage import KnowledgeStorage
from navigator.knowledge.vector_store import VectorStore


class TestKnowledgeAPIInitialization:
	"""Tests for knowledge API initialization (Step 2.20)."""

	def test_knowledge_api_init(self):
		"""Test knowledge API initialization."""
		storage = KnowledgeStorage(use_arangodb=False)
		vector_store = VectorStore(use_vector_db=False)
		
		api = KnowledgeAPI(
			storage=storage,
			vector_store=vector_store,
		)
		
		assert api.storage == storage
		assert api.vector_store == vector_store
		assert api.sitemap_generator is not None


class TestKnowledgeAPIOperations:
	"""Tests for knowledge API operations (Step 2.20)."""

	@pytest.mark.asyncio
	async def test_get_page(self):
		"""Test getting a page."""
		storage = KnowledgeStorage(use_arangodb=False)
		api = KnowledgeAPI(storage=storage)
		
		# Store a page
		await storage.store_page("https://example.com/page1", {
			"title": "Page 1",
			"content": "Content 1",
		})
		
		result = await api.get_page("https://example.com/page1")
		
		assert result["success"] is True
		assert "page" in result
		assert result["page"]["title"] == "Page 1"

	@pytest.mark.asyncio
	async def test_get_page_not_found(self):
		"""Test getting a non-existent page."""
		storage = KnowledgeStorage(use_arangodb=False)
		api = KnowledgeAPI(storage=storage)
		
		result = await api.get_page("https://example.com/notfound")
		
		assert result["success"] is False
		assert "error" in result

	@pytest.mark.asyncio
	async def test_search(self, browser_session):
		"""Test semantic search."""
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
		
		# Store a page first
		await pipeline.process_url("https://example.com")
		
		result = await api.search("example query", top_k=3)
		
		assert "success" in result
		if result.get("success"):
			assert "results" in result
			assert "query" in result
			assert "count" in result

	@pytest.mark.asyncio
	async def test_get_links(self):
		"""Test getting links."""
		storage = KnowledgeStorage(use_arangodb=False)
		api = KnowledgeAPI(storage=storage)
		
		# Store pages and links
		await storage.store_page("https://example.com/page1", {"title": "Page 1"})
		await storage.store_page("https://example.com/page2", {"title": "Page 2"})
		await storage.store_link("https://example.com/page1", "https://example.com/page2")
		
		result = await api.get_links("https://example.com/page1", direction="from")
		
		assert result["success"] is True
		assert "links" in result
		assert result["count"] >= 1

	@pytest.mark.asyncio
	async def test_get_semantic_sitemap(self):
		"""Test getting semantic site map."""
		storage = KnowledgeStorage(use_arangodb=False)
		api = KnowledgeAPI(storage=storage)
		
		# Store a page
		await storage.store_page("https://example.com/page1", {
			"title": "Page 1",
			"topics": {"categories": ["Technology"]},
		})
		
		result = await api.get_semantic_sitemap()
		
		assert result["success"] is True
		assert "sitemap" in result
		assert "hierarchy" in result["sitemap"]

	@pytest.mark.asyncio
	async def test_get_functional_sitemap(self):
		"""Test getting functional site map."""
		storage = KnowledgeStorage(use_arangodb=False)
		flow_mapper = FunctionalFlowMapper()
		api = KnowledgeAPI(storage=storage)
		api.sitemap_generator.flow_mapper = flow_mapper
		
		# Add navigation data
		flow_mapper.track_navigation("https://example.com/home")
		
		result = await api.get_functional_sitemap()
		
		assert result["success"] is True
		assert "sitemap" in result
		assert "navigation" in result["sitemap"]

	@pytest.mark.asyncio
	async def test_query_page(self):
		"""Test query interface - page query."""
		storage = KnowledgeStorage(use_arangodb=False)
		api = KnowledgeAPI(storage=storage)
		
		await storage.store_page("https://example.com/page1", {"title": "Page 1"})
		
		result = await api.query("page", {"url": "https://example.com/page1"})
		
		assert result["success"] is True
		assert "page" in result

	@pytest.mark.asyncio
	async def test_query_invalid_type(self):
		"""Test query interface - invalid query type."""
		storage = KnowledgeStorage(use_arangodb=False)
		api = KnowledgeAPI(storage=storage)
		
		result = await api.query("invalid_type", {})
		
		assert result["success"] is False
		assert "error" in result
		assert "available_types" in result

"""
Tests for Knowledge Storage (Steps 2.13-2.15).

Tests cover:
- ArangoDB Setup (Step 2.13)
- Page Storage (Step 2.14)
- Link Storage (Step 2.15)
"""

import pytest

from navigator.knowledge.storage import KnowledgeStorage


class TestStorageInitialization:
	"""Tests for storage initialization (Step 2.13)."""

	def test_in_memory_storage_init(self):
		"""Test in-memory storage initialization."""
		storage = KnowledgeStorage(use_arangodb=False)
		
		assert storage.use_arangodb is False
		assert hasattr(storage, 'pages')
		assert hasattr(storage, 'links')

	def test_arangodb_storage_init_without_arangodb(self):
		"""Test ArangoDB storage initialization falls back to in-memory if ArangoDB unavailable."""
		# This will fall back to in-memory since ArangoDB is not installed
		storage = KnowledgeStorage(use_arangodb=True)
		
		# Should fall back to in-memory
		assert storage.use_arangodb is False
		assert hasattr(storage, 'pages')
		assert hasattr(storage, 'links')


class TestPageStorage:
	"""Tests for page storage (Step 2.14)."""

	@pytest.mark.asyncio
	async def test_store_page(self):
		"""Test storing a page."""
		storage = KnowledgeStorage(use_arangodb=False)
		
		page_data = {
			"title": "Test Page",
			"content": "Test content",
			"headings": [{"level": 1, "text": "Heading"}],
			"paragraphs": ["Paragraph 1"],
		}
		
		await storage.store_page("https://example.com/page1", page_data)
		
		# Check stored page
		stored_page = await storage.get_page("https://example.com/page1")
		assert stored_page is not None
		assert stored_page["url"] == "https://example.com/page1"
		assert stored_page["title"] == "Test Page"

	@pytest.mark.asyncio
	async def test_get_page_not_found(self):
		"""Test getting a non-existent page."""
		storage = KnowledgeStorage(use_arangodb=False)
		
		page = await storage.get_page("https://example.com/notfound")
		assert page is None

	@pytest.mark.asyncio
	async def test_store_page_update(self):
		"""Test updating an existing page."""
		storage = KnowledgeStorage(use_arangodb=False)
		
		page_data1 = {"title": "Original Title", "content": "Original content"}
		await storage.store_page("https://example.com/page1", page_data1)
		
		page_data2 = {"title": "Updated Title", "content": "Updated content"}
		await storage.store_page("https://example.com/page1", page_data2)
		
		stored_page = await storage.get_page("https://example.com/page1")
		assert stored_page["title"] == "Updated Title"
		assert stored_page["content"] == "Updated content"

	@pytest.mark.asyncio
	async def test_store_multiple_pages(self):
		"""Test storing multiple pages."""
		storage = KnowledgeStorage(use_arangodb=False)
		
		await storage.store_page("https://example.com/page1", {"title": "Page 1"})
		await storage.store_page("https://example.com/page2", {"title": "Page 2"})
		await storage.store_page("https://example.com/page3", {"title": "Page 3"})
		
		page1 = await storage.get_page("https://example.com/page1")
		page2 = await storage.get_page("https://example.com/page2")
		page3 = await storage.get_page("https://example.com/page3")
		
		assert page1 is not None
		assert page2 is not None
		assert page3 is not None
		assert page1["title"] == "Page 1"
		assert page2["title"] == "Page 2"
		assert page3["title"] == "Page 3"


class TestLinkStorage:
	"""Tests for link storage (Step 2.15)."""

	@pytest.mark.asyncio
	async def test_store_link(self):
		"""Test storing a link."""
		storage = KnowledgeStorage(use_arangodb=False)
		
		# Store pages first
		await storage.store_page("https://example.com/page1", {"title": "Page 1"})
		await storage.store_page("https://example.com/page2", {"title": "Page 2"})
		
		# Store link
		await storage.store_link("https://example.com/page1", "https://example.com/page2")
		
		# Check links from page1
		links_from = await storage.get_links_from("https://example.com/page1")
		assert len(links_from) == 1
		assert links_from[0]["to_url"] == "https://example.com/page2" or links_from[0].get("_to", "").endswith("page2")

	@pytest.mark.asyncio
	async def test_store_link_with_data(self):
		"""Test storing a link with additional data."""
		storage = KnowledgeStorage(use_arangodb=False)
		
		await storage.store_page("https://example.com/page1", {"title": "Page 1"})
		await storage.store_page("https://example.com/page2", {"title": "Page 2"})
		
		link_data = {"anchor_text": "Click here", "link_type": "internal"}
		await storage.store_link("https://example.com/page1", "https://example.com/page2", link_data)
		
		links_from = await storage.get_links_from("https://example.com/page1")
		assert len(links_from) == 1
		link = links_from[0]
		assert link.get("anchor_text") == "Click here" or link.get("link_type") == "internal"

	@pytest.mark.asyncio
	async def test_get_links_from(self):
		"""Test getting links from a page."""
		storage = KnowledgeStorage(use_arangodb=False)
		
		await storage.store_page("https://example.com/page1", {"title": "Page 1"})
		await storage.store_page("https://example.com/page2", {"title": "Page 2"})
		await storage.store_page("https://example.com/page3", {"title": "Page 3"})
		
		await storage.store_link("https://example.com/page1", "https://example.com/page2")
		await storage.store_link("https://example.com/page1", "https://example.com/page3")
		
		links_from = await storage.get_links_from("https://example.com/page1")
		assert len(links_from) == 2

	@pytest.mark.asyncio
	async def test_get_links_to(self):
		"""Test getting links to a page."""
		storage = KnowledgeStorage(use_arangodb=False)
		
		await storage.store_page("https://example.com/page1", {"title": "Page 1"})
		await storage.store_page("https://example.com/page2", {"title": "Page 2"})
		await storage.store_page("https://example.com/target", {"title": "Target"})
		
		await storage.store_link("https://example.com/page1", "https://example.com/target")
		await storage.store_link("https://example.com/page2", "https://example.com/target")
		
		links_to = await storage.get_links_to("https://example.com/target")
		assert len(links_to) == 2

	@pytest.mark.asyncio
	async def test_get_links_from_empty(self):
		"""Test getting links from page with no links."""
		storage = KnowledgeStorage(use_arangodb=False)
		
		await storage.store_page("https://example.com/page1", {"title": "Page 1"})
		
		links_from = await storage.get_links_from("https://example.com/page1")
		assert len(links_from) == 0

	@pytest.mark.asyncio
	async def test_get_links_to_empty(self):
		"""Test getting links to page with no incoming links."""
		storage = KnowledgeStorage(use_arangodb=False)
		
		await storage.store_page("https://example.com/page1", {"title": "Page 1"})
		
		links_to = await storage.get_links_to("https://example.com/page1")
		assert len(links_to) == 0


class TestStorageUtilities:
	"""Tests for storage utility methods."""

	@pytest.mark.asyncio
	async def test_clear_storage(self):
		"""Test clearing storage."""
		storage = KnowledgeStorage(use_arangodb=False)
		
		await storage.store_page("https://example.com/page1", {"title": "Page 1"})
		await storage.store_link("https://example.com/page1", "https://example.com/page2")
		
		await storage.clear()
		
		page = await storage.get_page("https://example.com/page1")
		assert page is None
		
		links = await storage.get_links_from("https://example.com/page1")
		assert len(links) == 0

	def test_url_to_key(self):
		"""Test URL to key conversion."""
		storage = KnowledgeStorage(use_arangodb=False)
		
		key = storage._url_to_key("https://example.com/page1")
		assert isinstance(key, str)
		assert len(key) > 0
		
		# Should handle special characters
		key2 = storage._url_to_key("https://example.com/page?query=test&param=value")
		assert isinstance(key2, str)

"""
End-to-End Tests for Flow Mapper and Storage (Steps 2.11-2.15).

Tests the complete flow mapping and storage workflow.
"""

import pytest

from navigator.knowledge.flow_mapper import FunctionalFlowMapper
from navigator.knowledge.storage import KnowledgeStorage


class TestE2EFlowMapping:
	"""End-to-end tests for complete flow mapping workflow."""

	def test_e2e_navigation_and_path_tracking(self):
		"""Test complete navigation and path tracking workflow."""
		mapper = FunctionalFlowMapper()
		
		# Simulate navigation flow
		mapper.track_navigation("https://example.com/home")
		mapper.start_click_path("https://example.com/home")
		
		mapper.track_navigation("https://example.com/about", referrer="https://example.com/home")
		mapper.add_to_click_path("https://example.com/about")
		
		mapper.track_navigation("https://example.com/contact", referrer="https://example.com/about")
		mapper.add_to_click_path("https://example.com/contact")
		
		mapper.end_click_path()
		
		# Verify navigation tracking
		assert mapper.get_visit_count("https://example.com/home") == 1
		assert mapper.get_visit_count("https://example.com/about") == 1
		assert mapper.is_entry_point("https://example.com/home") is True
		
		# Verify click path
		paths = mapper.get_all_paths()
		assert len(paths) == 1
		assert len(paths[0]) == 3
		
		# Verify flow analysis
		analysis = mapper.analyze_flows()
		assert analysis["total_pages"] == 3
		assert analysis["total_paths"] == 1
		assert len(analysis["entry_points"]) == 1


class TestE2EStorage:
	"""End-to-end tests for complete storage workflow."""

	@pytest.mark.asyncio
	async def test_e2e_page_and_link_storage(self):
		"""Test complete page and link storage workflow."""
		storage = KnowledgeStorage(use_arangodb=False)
		
		# Store pages
		await storage.store_page("https://example.com/page1", {
			"title": "Page 1",
			"content": "Content 1",
			"headings": [{"level": 1, "text": "Heading 1"}],
		})
		
		await storage.store_page("https://example.com/page2", {
			"title": "Page 2",
			"content": "Content 2",
		})
		
		# Store links
		await storage.store_link("https://example.com/page1", "https://example.com/page2", {
			"anchor_text": "Link to Page 2",
		})
		
		# Retrieve and verify
		page1 = await storage.get_page("https://example.com/page1")
		assert page1 is not None
		assert page1["title"] == "Page 1"
		
		links_from_page1 = await storage.get_links_from("https://example.com/page1")
		assert len(links_from_page1) == 1
		
		links_to_page2 = await storage.get_links_to("https://example.com/page2")
		assert len(links_to_page2) == 1


class TestE2EIntegration:
	"""End-to-end integration tests for flow mapper and storage."""

	@pytest.mark.asyncio
	async def test_e2e_complete_workflow(self):
		"""Test complete workflow with flow mapper and storage."""
		mapper = FunctionalFlowMapper()
		storage = KnowledgeStorage(use_arangodb=False)
		
		# Simulate exploration flow
		urls = [
			"https://example.com/home",
			"https://example.com/about",
			"https://example.com/contact",
		]
		
		# Track navigation and store pages
		prev_url = None
		for url in urls:
			mapper.track_navigation(url, referrer=prev_url)
			await storage.store_page(url, {
				"title": f"Page {url.split('/')[-1]}",
				"url": url,
			})
			
			if prev_url:
				await storage.store_link(prev_url, url)
			
			prev_url = url
		
		# Track click path
		mapper.start_click_path(urls[0])
		for url in urls[1:]:
			mapper.add_to_click_path(url)
		mapper.end_click_path()
		
		# Verify navigation tracking
		assert mapper.get_visit_count(urls[0]) == 1
		assert mapper.is_entry_point(urls[0]) is True
		
		# Verify storage
		page1 = await storage.get_page(urls[0])
		assert page1 is not None
		
		links_from_home = await storage.get_links_from(urls[0])
		assert len(links_from_home) == 1
		
		# Verify flow analysis
		analysis = mapper.analyze_flows()
		assert analysis["total_pages"] == 3
		assert analysis["total_paths"] == 1

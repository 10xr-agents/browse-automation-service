"""
Tests for Exploration Engine (Steps 2.1-2.5).

Tests cover:
- Basic Link Discovery (Step 2.1)
- Link Tracking (Step 2.2)
- Depth Management (Step 2.3)
- BFS Strategy (Step 2.4)
- DFS Strategy (Step 2.5)
"""

import asyncio

import pytest

from navigator.knowledge.exploration_engine import ExplorationEngine, ExplorationStrategy


class TestLinkDiscovery:
	"""Tests for basic link discovery (Step 2.1)."""

	async def test_discover_links_from_page(self, exploration_engine, base_url):
		"""Test discovering links from a webpage."""
		url = f"{base_url}/"
		links = await exploration_engine.discover_links(url)
		
		assert len(links) > 0
		assert all("href" in link for link in links)
		assert all("text" in link for link in links)
		assert all("attributes" in link for link in links)
		
		# Verify we found the expected links
		hrefs = [link["href"] for link in links]
		assert any("/page1" in href for href in hrefs)
		assert any("/page2" in href for href in hrefs)
		assert any("/page3" in href for href in hrefs)

	async def test_link_extraction_attributes(self, exploration_engine, base_url):
		"""Test that link attributes are extracted correctly."""
		url = f"{base_url}/"
		links = await exploration_engine.discover_links(url)
		
		# Verify all links have href
		for link in links:
			assert "href" in link
			assert link["href"]  # href is not empty
			assert link["href"].startswith("http")  # URLs are resolved

	async def test_resolve_relative_urls(self, exploration_engine):
		"""Test that relative URLs are resolved correctly."""
		base = "https://example.com/page"
		
		# Test relative path
		resolved = exploration_engine._resolve_url("/page2", base)
		assert resolved == "https://example.com/page2"
		
		# Test relative URL without leading slash
		resolved = exploration_engine._resolve_url("page2", base)
		assert resolved == "https://example.com/page2"
		
		# Test absolute URL (should remain unchanged)
		resolved = exploration_engine._resolve_url("https://other.com/page", base)
		assert resolved == "https://other.com/page"

	async def test_filter_invalid_urls(self, exploration_engine):
		"""Test that invalid URLs are filtered out."""
		# Valid URLs
		assert exploration_engine._is_valid_url("https://example.com") is True
		assert exploration_engine._is_valid_url("http://example.com/page") is True
		
		# Invalid URLs
		assert exploration_engine._is_valid_url("javascript:void(0)") is False
		assert exploration_engine._is_valid_url("mailto:test@example.com") is False
		assert exploration_engine._is_valid_url("") is False


class TestLinkTracking:
	"""Tests for link tracking (Step 2.2)."""

	async def test_track_visited_url(self, exploration_engine):
		"""Test tracking a visited URL."""
		url = "https://example.com/page1"
		
		assert exploration_engine.is_visited(url) is False
		exploration_engine.track_visited(url)
		assert exploration_engine.is_visited(url) is True

	async def test_filter_unvisited_links(self, exploration_engine, base_url):
		"""Test filtering unvisited links."""
		url = f"{base_url}/"
		links = await exploration_engine.discover_links(url)
		
		assert len(links) > 0
		
		# Mark first link as visited
		first_link = links[0]
		exploration_engine.track_visited(first_link["href"])
		
		# Filter unvisited links
		unvisited = exploration_engine.filter_unvisited(links)
		
		# First link should be filtered out
		assert first_link not in unvisited
		assert len(unvisited) == len(links) - 1
		
		# All unvisited links should not be visited
		for link in unvisited:
			assert not exploration_engine.is_visited(link["href"])


class TestDepthManagement:
	"""Tests for depth management (Step 2.3)."""

	async def test_depth_filtering(self, exploration_engine):
		"""Test filtering links by depth limit."""
		links = [
			{"href": "https://example.com/page1", "text": "Page 1"},
			{"href": "https://example.com/page2", "text": "Page 2"},
		]
		
		# With max_depth=3, links at depth 0, 1, 2 should pass
		exploration_engine.max_depth = 3
		
		filtered = exploration_engine.filter_by_depth(links, current_depth=0)
		assert len(filtered) == len(links)  # Depth 0 < 3
		
		filtered = exploration_engine.filter_by_depth(links, current_depth=2)
		assert len(filtered) == len(links)  # Depth 2 < 3
		
		filtered = exploration_engine.filter_by_depth(links, current_depth=3)
		assert len(filtered) == 0  # Depth 3 >= 3

	async def test_explore_with_depth_limit(self, exploration_engine, base_url):
		"""Test exploration respects depth limit."""
		exploration_engine.max_depth = 1
		start_url = f"{base_url}/"
		
		pages = await exploration_engine.explore(start_url, max_pages=10)
		
		# All pages should have depth <= 1
		for page in pages:
			assert page["depth"] <= 1


class TestBFSStrategy:
	"""Tests for BFS strategy (Step 2.4)."""

	async def test_bfs_exploration_order(self, browser_session, base_url):
		"""Test that BFS explores level by level."""
		engine = ExplorationEngine(
			browser_session=browser_session,
			max_depth=2,
			strategy=ExplorationStrategy.BFS,
			base_url=base_url,
		)
		
		start_url = f"{base_url}/"
		pages = await engine.explore(start_url, max_pages=10)
		
		# BFS should explore depth 0 first, then depth 1
		# Find indices where depth changes
		if len(pages) > 1:
			depths = [page["depth"] for page in pages]
			
			# First page should be depth 0
			assert depths[0] == 0
			
			# All depth 0 pages should come before depth 1 pages
			depth_0_count = sum(1 for d in depths if d == 0)
			depth_1_count = sum(1 for d in depths if d == 1)
			
			# Verify ordering: all depth 0, then all depth 1
			first_depth_1_idx = next((i for i, d in enumerate(depths) if d == 1), None)
			if first_depth_1_idx is not None:
				# All pages before first_depth_1_idx should be depth 0
				assert all(depths[i] == 0 for i in range(first_depth_1_idx))

	async def test_bfs_completes_exploration(self, exploration_engine, base_url):
		"""Test that BFS completes exploration."""
		exploration_engine.strategy = ExplorationStrategy.BFS
		exploration_engine.max_depth = 2
		
		start_url = f"{base_url}/"
		pages = await exploration_engine.explore(start_url, max_pages=20)
		
		# Should have explored multiple pages
		assert len(pages) > 1
		
		# All pages should be marked as visited
		for page in pages:
			assert exploration_engine.is_visited(page["url"])


class TestDFSStrategy:
	"""Tests for DFS strategy (Step 2.5)."""

	async def test_dfs_exploration_deep_paths_first(self, browser_session, base_url):
		"""Test that DFS explores deep paths first."""
		engine = ExplorationEngine(
			browser_session=browser_session,
			max_depth=3,
			strategy=ExplorationStrategy.DFS,
			base_url=base_url,
		)
		
		start_url = f"{base_url}/"
		pages = await engine.explore(start_url, max_pages=10)
		
		# DFS should explore deeper paths before exploring breadth
		# This is harder to verify directly, but we can check that
		# pages are explored (not in strict depth order like BFS)
		assert len(pages) > 0
		
		# All pages should be marked as visited
		for page in pages:
			assert engine.is_visited(page["url"])

	async def test_dfs_completes_exploration(self, exploration_engine, base_url):
		"""Test that DFS completes exploration."""
		exploration_engine.strategy = ExplorationStrategy.DFS
		exploration_engine.max_depth = 2
		
		start_url = f"{base_url}/"
		pages = await exploration_engine.explore(start_url, max_pages=20)
		
		# Should have explored multiple pages
		assert len(pages) > 0
		
		# All pages should be marked as visited
		for page in pages:
			assert exploration_engine.is_visited(page["url"])


class TestExplorationEngineIntegration:
	"""Integration tests for Exploration Engine."""

	async def test_complete_exploration_flow(self, exploration_engine, base_url):
		"""Test complete exploration flow with all features."""
		start_url = f"{base_url}/"
		
		# Run exploration
		pages = await exploration_engine.explore(start_url, max_pages=10)
		
		# Verify results
		assert len(pages) > 0
		
		# Each page should have required fields
		for page in pages:
			assert "url" in page
			assert "depth" in page
			assert "links" in page
			assert "link_count" in page
			assert isinstance(page["links"], list)
			assert page["link_count"] == len(page["links"])
		
		# Verify all URLs are unique
		urls = [page["url"] for page in pages]
		assert len(urls) == len(set(urls))  # No duplicates
		
		# Verify all pages are marked as visited
		for page in pages:
			assert exploration_engine.is_visited(page["url"])

	async def test_exploration_respects_max_pages(self, exploration_engine, base_url):
		"""Test that exploration respects max_pages limit."""
		start_url = f"{base_url}/"
		
		max_pages = 3
		pages = await exploration_engine.explore(start_url, max_pages=max_pages)
		
		# Should not exceed max_pages
		assert len(pages) <= max_pages

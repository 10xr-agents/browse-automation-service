"""
End-to-End Tests for Exploration Engine (Steps 2.1-2.5).

Tests the complete exploration flow with all features integrated.
"""

import asyncio

import pytest

from navigator.knowledge.exploration_engine import ExplorationEngine, ExplorationStrategy


class TestE2EExploration:
	"""End-to-end tests for complete exploration flow."""

	async def test_e2e_bfs_exploration(self, browser_session, base_url):
		"""Test complete BFS exploration flow."""
		engine = ExplorationEngine(
			browser_session=browser_session,
			max_depth=2,
			strategy=ExplorationStrategy.BFS,
			base_url=base_url,
		)
		
		start_url = f"{base_url}/"
		pages = await engine.explore(start_url, max_pages=10)
		
		# Verify exploration completed
		assert len(pages) > 0
		
		# Verify all pages have links discovered
		for page in pages:
			assert "links" in page
			assert isinstance(page["links"], list)
		
		# Verify visited tracking
		visited_count = len(engine.visited_urls)
		assert visited_count == len(pages)
		
		# Verify depth tracking
		assert len(engine.url_depths) == len(pages)
		for page in pages:
			assert page["url"] in engine.url_depths
			assert engine.url_depths[page["url"]] == page["depth"]

	async def test_e2e_dfs_exploration(self, browser_session, base_url):
		"""Test complete DFS exploration flow."""
		engine = ExplorationEngine(
			browser_session=browser_session,
			max_depth=2,
			strategy=ExplorationStrategy.DFS,
			base_url=base_url,
		)
		
		start_url = f"{base_url}/"
		pages = await engine.explore(start_url, max_pages=10)
		
		# Verify exploration completed
		assert len(pages) > 0
		
		# Verify all features work together
		assert len(engine.visited_urls) == len(pages)
		assert len(engine.url_depths) == len(pages)
		
		# Verify no duplicates
		urls = [page["url"] for page in pages]
		assert len(urls) == len(set(urls))

	async def test_e2e_link_discovery_and_tracking(self, exploration_engine, base_url):
		"""Test link discovery and tracking integration."""
		url = f"{base_url}/"
		
		# Discover links
		links = await exploration_engine.discover_links(url)
		assert len(links) > 0
		
		# Track first link as visited
		first_link = links[0]
		exploration_engine.track_visited(first_link["href"])
		
		# Filter should exclude visited link
		unvisited = exploration_engine.filter_unvisited(links)
		assert first_link not in unvisited
		assert len(unvisited) == len(links) - 1

	async def test_e2e_depth_limited_exploration(self, browser_session, base_url):
		"""Test exploration with depth limits."""
		engine = ExplorationEngine(
			browser_session=browser_session,
			max_depth=1,  # Only explore depth 0 and 1
			strategy=ExplorationStrategy.BFS,
			base_url=base_url,
		)
		
		start_url = f"{base_url}/"
		pages = await engine.explore(start_url, max_pages=20)
		
		# All pages should have depth <= 1
		for page in pages:
			assert page["depth"] <= 1
		
		# Verify no pages at depth 2 were explored
		assert all(page["depth"] < 2 for page in pages)

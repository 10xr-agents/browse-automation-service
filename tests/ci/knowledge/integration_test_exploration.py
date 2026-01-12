#!/usr/bin/env python3
"""
Integration Test Script for Exploration Engine (Steps 2.1-2.5).

This script performs actual calls to test the complete exploration engine.
Run this script to verify all exploration functionality works end-to-end.

Usage:
    python tests/ci/knowledge/integration_test_exploration.py

Requirements:
    - Browser automation dependencies installed
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from browser_use.browser import BrowserSession
from browser_use.browser.profile import BrowserProfile

from navigator.knowledge.exploration_engine import ExplorationEngine, ExplorationStrategy

# Configure logging
logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_link_discovery():
	"""Test basic link discovery."""
	logger.info("=" * 80)
	logger.info("Test 1: Basic Link Discovery")
	logger.info("=" * 80)
	
	browser_session = BrowserSession(
		browser_profile=BrowserProfile(headless=True, user_data_dir=None)
	)
	await browser_session.start()
	logger.info("✅ Started browser session")
	
	try:
		engine = ExplorationEngine(browser_session=browser_session)
		test_url = "https://example.com"
		
		logger.info(f"📋 Discovering links from {test_url}")
		links = await engine.discover_links(test_url)
		
		logger.info(f"✅ Discovered {len(links)} links")
		assert len(links) > 0
		assert all("href" in link for link in links)
		
		# Print first few links
		for i, link in enumerate(links[:5]):
			logger.info(f"  Link {i+1}: {link['href'][:80]}... ({link.get('text', '')[:50]})")
		
		logger.info("✅ Test 1 PASSED: Basic Link Discovery")
		return True
	
	finally:
		await browser_session.kill()


async def test_link_tracking():
	"""Test link tracking functionality."""
	logger.info("=" * 80)
	logger.info("Test 2: Link Tracking")
	logger.info("=" * 80)
	
	browser_session = BrowserSession(
		browser_profile=BrowserProfile(headless=True, user_data_dir=None)
	)
	await browser_session.start()
	
	try:
		engine = ExplorationEngine(browser_session=browser_session)
		test_url = "https://example.com"
		
		links = await engine.discover_links(test_url)
		logger.info(f"✅ Discovered {len(links)} links")
		
		if len(links) > 0:
			first_link = links[0]
			test_url_to_track = first_link["href"]
			
			logger.info(f"📋 Tracking URL: {test_url_to_track[:80]}...")
			assert engine.is_visited(test_url_to_track) is False
			engine.track_visited(test_url_to_track)
			assert engine.is_visited(test_url_to_track) is True
			logger.info("✅ URL tracking works")
			
			logger.info("📋 Filtering unvisited links")
			unvisited = engine.filter_unvisited(links)
			logger.info(f"✅ {len(unvisited)} unvisited links (of {len(links)} total)")
			assert test_url_to_track not in [link["href"] for link in unvisited]
		
		logger.info("✅ Test 2 PASSED: Link Tracking")
		return True
	
	finally:
		await browser_session.kill()


async def test_bfs_exploration():
	"""Test BFS exploration strategy."""
	logger.info("=" * 80)
	logger.info("Test 3: BFS Exploration Strategy")
	logger.info("=" * 80)
	
	browser_session = BrowserSession(
		browser_profile=BrowserProfile(headless=True, user_data_dir=None)
	)
	await browser_session.start()
	
	try:
		engine = ExplorationEngine(
			browser_session=browser_session,
			max_depth=2,
			strategy=ExplorationStrategy.BFS,
		)
		
		test_url = "https://example.com"
		logger.info(f"📋 Exploring {test_url} with BFS (max_depth=2, max_pages=5)")
		
		pages = await engine.explore(test_url, max_pages=5)
		
		logger.info(f"✅ Explored {len(pages)} pages")
		assert len(pages) > 0
		
		for page in pages:
			logger.info(f"  Page: {page['url'][:80]}... (depth: {page['depth']}, links: {page['link_count']})")
		
		# Verify all pages are visited
		assert len(engine.visited_urls) == len(pages)
		
		logger.info("✅ Test 3 PASSED: BFS Exploration Strategy")
		return True
	
	finally:
		await browser_session.kill()


async def test_dfs_exploration():
	"""Test DFS exploration strategy."""
	logger.info("=" * 80)
	logger.info("Test 4: DFS Exploration Strategy")
	logger.info("=" * 80)
	
	browser_session = BrowserSession(
		browser_profile=BrowserProfile(headless=True, user_data_dir=None)
	)
	await browser_session.start()
	
	try:
		engine = ExplorationEngine(
			browser_session=browser_session,
			max_depth=2,
			strategy=ExplorationStrategy.DFS,
		)
		
		test_url = "https://example.com"
		logger.info(f"📋 Exploring {test_url} with DFS (max_depth=2, max_pages=5)")
		
		pages = await engine.explore(test_url, max_pages=5)
		
		logger.info(f"✅ Explored {len(pages)} pages")
		assert len(pages) > 0
		
		for page in pages:
			logger.info(f"  Page: {page['url'][:80]}... (depth: {page['depth']}, links: {page['link_count']})")
		
		# Verify all pages are visited
		assert len(engine.visited_urls) == len(pages)
		
		logger.info("✅ Test 4 PASSED: DFS Exploration Strategy")
		return True
	
	finally:
		await browser_session.kill()


async def test_complete_integration():
	"""Test complete integration of all features."""
	logger.info("=" * 80)
	logger.info("Test 5: Complete Integration")
	logger.info("=" * 80)
	
	browser_session = BrowserSession(
		browser_profile=BrowserProfile(headless=True, user_data_dir=None)
	)
	await browser_session.start()
	
	try:
		engine = ExplorationEngine(
			browser_session=browser_session,
			max_depth=2,
			strategy=ExplorationStrategy.BFS,
		)
		
		test_url = "https://example.com"
		
		logger.info("📋 Running complete exploration flow")
		pages = await engine.explore(test_url, max_pages=5)
		
		logger.info(f"✅ Explored {len(pages)} pages")
		
		# Verify all features integrated
		assert len(pages) > 0
		assert len(engine.visited_urls) == len(pages)
		assert len(engine.url_depths) == len(pages)
		
		# Verify no duplicates
		urls = [page["url"] for page in pages]
		assert len(urls) == len(set(urls))
		
		logger.info("✅ Test 5 PASSED: Complete Integration")
		return True
	
	finally:
		await browser_session.kill()


async def main():
	"""Run all integration tests."""
	logger.info("🚀 Starting Exploration Engine Integration Tests")
	logger.info("=" * 80)
	
	tests = [
		("Link Discovery", test_link_discovery),
		("Link Tracking", test_link_tracking),
		("BFS Exploration", test_bfs_exploration),
		("DFS Exploration", test_dfs_exploration),
		("Complete Integration", test_complete_integration),
	]
	
	passed = 0
	failed = 0
	
	for test_name, test_func in tests:
		try:
			result = await test_func()
			if result:
				passed += 1
			else:
				failed += 1
				logger.error(f"❌ {test_name} FAILED")
		except Exception as e:
			failed += 1
			logger.error(f"❌ {test_name} FAILED with exception: {e}", exc_info=True)
	
	logger.info("=" * 80)
	logger.info(f"📊 Test Results: {passed} passed, {failed} failed")
	logger.info("=" * 80)
	
	if failed > 0:
		logger.error("❌ Some tests failed!")
		sys.exit(1)
	else:
		logger.info("✅ All tests passed!")
		sys.exit(0)


if __name__ == "__main__":
	asyncio.run(main())

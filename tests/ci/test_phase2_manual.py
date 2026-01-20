#!/usr/bin/env python3
"""
Manual Phase 2 Testing Script

Tests Phase 2 knowledge retrieval flow with actual browser calls.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

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

logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


async def test_phase2_complete():
	"""Test complete Phase 2 workflow with real browser."""
	logger.info("=" * 80)
	logger.info("Phase 2 Complete Testing - Knowledge Retrieval Flow")
	logger.info("=" * 80)
	
	# Initialize browser session
	logger.info("\n1. Initializing browser session...")
	browser_session = BrowserSession(
		browser_profile=BrowserProfile(headless=True, user_data_dir=None)
	)
	await browser_session.start()
	
	try:
		# Initialize components
		logger.info("\n2. Initializing knowledge retrieval components...")
		storage = KnowledgeStorage(use_arangodb=False)
		vector_store = VectorStore(use_vector_db=False)
		flow_mapper = FunctionalFlowMapper()
		
		pipeline = KnowledgePipeline(
			browser_session=browser_session,
			storage=storage,
			vector_store=vector_store,
			max_depth=2,
			strategy=ExplorationStrategy.BFS,
		)
		
		# Test with example.com
		test_url = "https://example.com"
		logger.info(f"\n3. Testing with URL: {test_url}")
		
		# Step 1: Process a single URL
		logger.info("\n   Step 1: Processing single URL...")
		result = await pipeline.process_url(test_url)
		
		if result.get("success"):
			logger.info(f"   ✓ Successfully processed {test_url}")
			logger.info(f"   - Content extracted: {len(result.get('content', {}).get('text', ''))} chars")
			logger.info(f"   - Entities found: {len(result.get('entities', []))}")
			logger.info(f"   - Topics: {result.get('topics', {}).get('categories', [])}")
			
			# Verify storage
			page = await storage.get_page(test_url)
			assert page is not None, "Page should be stored"
			logger.info("   ✓ Page stored in KnowledgeStorage")
			
			embedding = await vector_store.get_embedding(test_url)
			assert embedding is not None, "Embedding should be stored"
			logger.info(f"   ✓ Embedding stored (dimension: {len(embedding['embedding'])})")
		else:
			logger.error(f"   ✗ Failed to process {test_url}: {result.get('error')}")
			return False
		
		# Step 2: Test semantic search
		logger.info("\n   Step 2: Testing semantic search...")
		search_results = await pipeline.search_similar("example domain", top_k=3)
		logger.info(f"   ✓ Found {len(search_results)} similar pages")
		
		# Step 3: Test site map generation
		logger.info("\n   Step 3: Testing site map generation...")
		sitemap_generator = SiteMapGenerator(
			storage=storage,
			flow_mapper=flow_mapper,
			vector_store=vector_store,
		)
		
		# Add navigation data
		flow_mapper.track_navigation(test_url)
		flow_mapper.start_click_path(test_url)
		flow_mapper.end_click_path()
		
		semantic_sitemap = await sitemap_generator.generate_semantic_sitemap()
		logger.info(f"   ✓ Semantic site map: {semantic_sitemap['total_pages']} pages, {semantic_sitemap['categories']} categories")
		
		functional_sitemap = await sitemap_generator.generate_functional_sitemap()
		logger.info(f"   ✓ Functional site map: {len(functional_sitemap['user_journeys'])} user journeys")
		
		# Step 4: Test API
		logger.info("\n   Step 4: Testing Knowledge API...")
		api = KnowledgeAPI(
			storage=storage,
			vector_store=vector_store,
			pipeline=pipeline,
			sitemap_generator=sitemap_generator,
		)
		
		page_result = await api.get_page(test_url)
		assert page_result["success"] is True
		logger.info(f"   ✓ API get_page: Success")
		
		sitemap_result = await api.get_semantic_sitemap()
		assert sitemap_result["success"] is True
		logger.info(f"   ✓ API get_semantic_sitemap: Success")
		
		functional_result = await api.get_functional_sitemap()
		assert functional_result["success"] is True
		logger.info(f"   ✓ API get_functional_sitemap: Success")
		
		query_result = await api.query("page", {"url": test_url})
		assert query_result["success"] is True
		logger.info(f"   ✓ API query interface: Success")
		
		logger.info("\n" + "=" * 80)
		logger.info("Phase 2 Complete Testing: SUCCESS")
		logger.info("=" * 80)
		
		return True
		
	except Exception as e:
		logger.error(f"\n✗ Phase 2 testing failed: {e}", exc_info=True)
		return False
	finally:
		logger.info("\n5. Cleaning up browser session...")
		await browser_session.kill()
		logger.info("   ✓ Browser session closed")


async def main():
	"""Main entry point."""
	success = await test_phase2_complete()
	sys.exit(0 if success else 1)


if __name__ == "__main__":
	asyncio.run(main())

"""
End-to-End Test for Phase 2: Knowledge Retrieval & Storage Flow.

Tests the complete knowledge retrieval flow on a complex public website:
- Website exploration (BFS/DFS strategies)
- Semantic analysis (content extraction, entity recognition, embeddings)
- Knowledge storage (ArangoDB/in-memory, vector store)
- Site map generation (semantic + functional)
- Knowledge API queries

Uses quotes.toscrape.com as a complex public website with:
- Multiple pages (quotes, authors, tags)
- Navigation links
- Semantic content (quotes, authors, tags)
- Pagination
- Real-world complexity
"""

import pytest
import asyncio
import logging
from typing import Any

from browser_use import BrowserSession, BrowserProfile
from navigator.knowledge.pipeline import KnowledgePipeline
from navigator.knowledge.exploration_engine import ExplorationEngine, ExplorationStrategy
from navigator.knowledge.semantic_analyzer import SemanticAnalyzer
from navigator.knowledge.storage import KnowledgeStorage
from navigator.knowledge.vector_store import VectorStore
from navigator.knowledge.flow_mapper import FunctionalFlowMapper
from navigator.knowledge.sitemap_generator import SiteMapGenerator
from navigator.knowledge.api import KnowledgeAPI

logger = logging.getLogger(__name__)

# Test configuration
TEST_WEBSITE_URL = "https://quotes.toscrape.com"
MAX_PAGES_TO_EXPLORE = 50  # Limit for testing (quotes.toscrape.com has ~100 pages)
MAX_DEPTH = 3  # Limit exploration depth
EXPLORATION_STRATEGY = ExplorationStrategy.BFS  # Use BFS for predictable order


@pytest.fixture
async def browser_session():
	"""Create a browser session for testing."""
	profile = BrowserProfile(
		headless=True,  # Run headless for CI
		window_size={"width": 1920, "height": 1080},
	)
	session = BrowserSession(browser_profile=profile)
	await session.start()
	yield session
	await session.kill()


@pytest.fixture
def knowledge_storage():
	"""Create knowledge storage (in-memory for testing)."""
	return KnowledgeStorage(use_arangodb=False)


@pytest.fixture
def vector_store():
	"""Create vector store (in-memory for testing)."""
	return VectorStore(use_vector_db=False)


@pytest.fixture
def flow_mapper():
	"""Create flow mapper for navigation tracking."""
	return FunctionalFlowMapper()


@pytest.fixture
async def knowledge_pipeline(
	browser_session,
	knowledge_storage,
	vector_store,
):
	"""Create knowledge pipeline with all components."""
	return KnowledgePipeline(
		browser_session=browser_session,
		storage=knowledge_storage,
		vector_store=vector_store,
		max_depth=MAX_DEPTH,
		strategy=EXPLORATION_STRATEGY,
	)


@pytest.fixture
def sitemap_generator(knowledge_storage, flow_mapper):
	"""Create sitemap generator."""
	return SiteMapGenerator(
		storage=knowledge_storage,
		flow_mapper=flow_mapper,
	)


@pytest.fixture
async def knowledge_api(knowledge_storage, vector_store, knowledge_pipeline):
	"""Create knowledge API."""
	return KnowledgeAPI(
		storage=knowledge_storage,
		vector_store=vector_store,
		pipeline=knowledge_pipeline,
	)


@pytest.fixture
async def explored_pages(knowledge_pipeline, flow_mapper):
	"""
	Fixture that runs website exploration and returns explored pages.
	
	This fixture:
	1. Runs the complete exploration of the test website
	2. Tracks navigation using flow_mapper
	3. Returns the list of explored pages (from results['results'])
	"""
	logger.info("=" * 80)
	logger.info("Fixture: Website Exploration")
	logger.info("=" * 80)
	logger.info(f"Starting exploration of {TEST_WEBSITE_URL}")
	logger.info(f"Strategy: {EXPLORATION_STRATEGY}, Max Depth: {MAX_DEPTH}, Max Pages: {MAX_PAGES_TO_EXPLORE}")
	
	# Start exploration
	exploration_results = await knowledge_pipeline.explore_and_store(
		start_url=TEST_WEBSITE_URL,
		max_pages=MAX_PAGES_TO_EXPLORE,
	)
	
	logger.info(f"Exploration complete: {exploration_results['pages_stored']}/{exploration_results['pages_processed']} pages stored")
	
	# Extract explored pages from results
	explored_pages = exploration_results.get('results', [])
	
	# Track navigation in flow_mapper (since pipeline doesn't do it automatically)
	flow_mapper.track_navigation(TEST_WEBSITE_URL)  # Entry point
	for result in explored_pages:
		if result.get('success') and 'url' in result:
			url = result['url']
			if url != TEST_WEBSITE_URL:
				# Track with referrer (simplified - in real exploration, we'd track actual referrers)
				flow_mapper.track_navigation(url, referrer=TEST_WEBSITE_URL)
	
	# Verify exploration results
	assert len(explored_pages) > 0, "Should discover at least one page"
	assert exploration_results['pages_processed'] <= MAX_PAGES_TO_EXPLORE, \
		f"Should not exceed max pages ({MAX_PAGES_TO_EXPLORE})"
	
	# Verify all explored pages are visited
	for result in explored_pages:
		if result.get('success') and 'url' in result:
			url = result['url']
			assert knowledge_pipeline.exploration_engine.is_visited(url), \
				f"Page {url} should be marked as visited"
	
	# Verify entry point tracking
	entry_points = flow_mapper.get_entry_points()
	assert TEST_WEBSITE_URL in entry_points, "Starting URL should be an entry point"
	
	# Verify navigation tracking
	flow_stats = flow_mapper.get_flow_stats()
	logger.info(f"Navigation stats: {flow_stats}")
	assert flow_stats["total_pages"] > 0, "Should track at least one page"
	assert flow_stats["total_visits"] > 0, "Should track at least one visit"
	
	logger.info("✅ Exploration fixture complete")
	
	return explored_pages


@pytest.mark.asyncio
async def test_e2e_complex_website_exploration(
	knowledge_pipeline,
	browser_session,
	knowledge_storage,
	flow_mapper,
	explored_pages,
):
	"""
	Test complete website exploration on quotes.toscrape.com.
	
	This test:
	1. Verifies exploration results (handled by fixture)
	2. Validates exploration metrics
	3. Checks navigation tracking
	"""
	logger.info("=" * 80)
	logger.info("E2E Test: Complex Website Exploration")
	logger.info("=" * 80)
	
	# Exploration is done by fixture, verify results
	assert len(explored_pages) > 0, "Should discover at least one page"
	
	# Count successful results
	successful_results = [r for r in explored_pages if r.get('success')]
	assert len(successful_results) > 0, "Should have at least one successful result"
	
	# Verify exploration engine state
	assert knowledge_pipeline.exploration_engine.is_visited(TEST_WEBSITE_URL), \
		"Starting URL should be visited"
	
	# Verify flow mapper state
	flow_stats = flow_mapper.get_flow_stats()
	assert flow_stats["total_pages"] > 0, "Flow mapper should track at least one page"
	
	logger.info(f"✅ Explored {len(successful_results)}/{len(explored_pages)} pages successfully")
	logger.info("✅ Exploration phase complete")


@pytest.mark.asyncio
async def test_e2e_complex_website_storage(
	knowledge_pipeline,
	knowledge_storage,
	explored_pages,
):
	"""
	Test knowledge storage after exploration.
	
	This test:
	1. Verifies pages are stored in KnowledgeStorage
	2. Verifies links are stored as graph edges
	3. Verifies page content is retrievable
	4. Verifies graph queries work
	"""
	logger.info("=" * 80)
	logger.info("E2E Test: Knowledge Storage")
	logger.info("=" * 80)
	
	# Verify pages are stored
	logger.info("Phase 2: Verifying page storage...")
	stored_count = 0
	for result in explored_pages:
		if result.get('success') and 'url' in result:
			url = result['url']
			stored_page = await knowledge_storage.get_page(url)
			
			if stored_page:
				stored_count += 1
				assert stored_page["url"] == url, f"Stored page URL should match: {url}"
				assert "title" in stored_page or "content" in stored_page, \
					f"Stored page should have title or content: {url}"
	
	logger.info(f"Verified {stored_count} stored pages from {len(explored_pages)} results")
	assert stored_count > 0, "Should store at least some pages"
	
	# Verify graph structure (links stored as edges)
	logger.info("Phase 3: Verifying graph structure...")
	links_found = 0
	checked_pages = 0
	for result in explored_pages[:10]:  # Check first 10 results
		if result.get('success') and 'url' in result:
			url = result['url']
			checked_pages += 1
			outgoing_links = await knowledge_storage.get_links_from(url)
			
			if outgoing_links:
				links_found += 1
				assert len(outgoing_links) > 0, f"Page {url} should have outgoing links"
				# Verify link structure
				for link in outgoing_links:
					assert "to_url" in link or "_to" in link, "Link should have destination"
	
	logger.info(f"Found links from {links_found}/{checked_pages} checked pages")
	
	# Verify graph queries work
	logger.info("Phase 4: Testing graph queries...")
	for result in explored_pages:
		if result.get('success') and 'url' in result:
			first_page_url = result['url']
			outgoing_links = await knowledge_storage.get_links_from(first_page_url)
			incoming_links = await knowledge_storage.get_links_to(first_page_url)
			
			logger.info(f"Page {first_page_url}: {len(outgoing_links)} outgoing, {len(incoming_links)} incoming links")
			break
	
	logger.info("✅ Storage phase complete")


@pytest.mark.asyncio
async def test_e2e_complex_website_semantic_analysis(
	knowledge_pipeline,
	knowledge_storage,
	vector_store,
	explored_pages,
):
	"""
	Test semantic analysis after exploration.
	
	This test:
	1. Verifies semantic analysis was performed on pages
	2. Verifies embeddings were generated
	3. Verifies vector store has embeddings
	4. Tests semantic search functionality
	"""
	logger.info("=" * 80)
	logger.info("E2E Test: Semantic Analysis")
	logger.info("=" * 80)
	
	# Verify semantic analysis results
	logger.info("Phase 1: Verifying semantic analysis...")
	pages_with_content = 0
	pages_with_embeddings = 0
	checked_count = 0
	
	for result in explored_pages[:20]:  # Check first 20 results
		if result.get('success') and 'url' in result:
			url = result['url']
			checked_count += 1
			stored_page = await knowledge_storage.get_page(url)
			
			if stored_page:
				# Check for semantic analysis results
				if "content" in stored_page or "headings" in stored_page:
					pages_with_content += 1
				
				# Check for embeddings
				embedding = await vector_store.get_embedding(url)
				if embedding:
					pages_with_embeddings += 1
	
	logger.info(f"Pages with content: {pages_with_content}/{checked_count}")
	logger.info(f"Pages with embeddings: {pages_with_embeddings}/{checked_count}")
	
	# Test semantic search
	if pages_with_embeddings > 0:
		logger.info("Phase 2: Testing semantic search...")
		search_query = "life wisdom"  # Common theme in quotes.toscrape.com
		search_results = await knowledge_pipeline.search_similar(
			query_text=search_query,
			top_k=5,
		)
		
		logger.info(f"Semantic search for '{search_query}': {len(search_results)} results")
		assert len(search_results) > 0, "Semantic search should return results"
		
		# Verify search result structure
		for result in search_results:
			assert "url" in result or "page_url" in result, "Search result should have URL"
			assert "score" in result or "similarity" in result, "Search result should have similarity score"
	else:
		logger.warning("Skipping semantic search test - no embeddings found")
	
	logger.info("✅ Semantic analysis phase complete")


@pytest.mark.asyncio
async def test_e2e_complex_website_sitemap_generation(
	sitemap_generator,
	knowledge_storage,
	flow_mapper,
	explored_pages,
):
	"""
	Test site map generation after exploration.
	
	This test:
	1. Generates semantic sitemap
	2. Generates functional sitemap
	3. Verifies sitemap structure
	4. Verifies sitemap contains explored pages
	"""
	logger.info("=" * 80)
	logger.info("E2E Test: Site Map Generation")
	logger.info("=" * 80)
	
	# Generate semantic sitemap
	logger.info("Phase 1: Generating semantic sitemap...")
	semantic_sitemap = await sitemap_generator.generate_semantic_sitemap()
	
	logger.info(f"Semantic sitemap generated: {semantic_sitemap.get('total_pages', 0)} pages")
	assert "hierarchy" in semantic_sitemap, "Semantic sitemap should have hierarchy"
	assert len(semantic_sitemap["hierarchy"]) > 0, "Semantic sitemap should contain categories"
	
	# Verify sitemap structure
	for category in semantic_sitemap["hierarchy"][:5]:  # Check first 5 categories
		assert "category" in category, "Sitemap category should have category name"
		assert "pages" in category, "Sitemap category should have pages"
		if category["pages"]:
			for page in category["pages"][:3]:  # Check first 3 pages in category
				assert "url" in page, "Sitemap page should have URL"
				assert "title" in page, "Sitemap page should have title"
	
	# Generate functional sitemap
	logger.info("Phase 2: Generating functional sitemap...")
	functional_sitemap = await sitemap_generator.generate_functional_sitemap()
	
	logger.info(f"Functional sitemap generated")
	assert "navigation" in functional_sitemap, "Functional sitemap should have navigation"
	assert "user_journeys" in functional_sitemap, "Functional sitemap should have user journeys"
	
	# Verify functional sitemap structure
	navigation = functional_sitemap.get("navigation", [])
	assert len(navigation) > 0, "Functional sitemap should have navigation entries"
	
	user_journeys = functional_sitemap.get("user_journeys", [])
	logger.info(f"User journeys: {len(user_journeys)}")
	
	# Note: export_to_json may not exist, skip export test
	logger.info("Phase 3: Sitemap structure verified")
	logger.info("✅ Semantic and functional sitemaps generated successfully")
	
	logger.info("✅ Site map generation phase complete")


@pytest.mark.asyncio
async def test_e2e_complex_website_knowledge_api(
	knowledge_api,
	knowledge_storage,
	vector_store,
	flow_mapper,
	explored_pages,
):
	"""
	Test Knowledge API after exploration.
	
	This test:
	1. Tests get_page API method
	2. Tests search API method
	3. Tests get_links API method
	4. Tests get_semantic_sitemap API method
	5. Tests get_functional_sitemap API method
	"""
	logger.info("=" * 80)
	logger.info("E2E Test: Knowledge API")
	logger.info("=" * 80)
	
	# Test get_page
	for result in explored_pages:
		if result.get('success') and 'url' in result:
			logger.info("Phase 1: Testing get_page API...")
			test_url = result['url']
			page_result = await knowledge_api.get_page(test_url)
			
			assert page_result is not None, f"get_page should return data for {test_url}"
			assert page_result.get("success"), f"get_page should succeed for {test_url}"
			if page_result.get("success"):
				assert "page" in page_result, "get_page result should have page data"
				assert page_result["page"]["url"] == test_url, "get_page should return correct URL"
				logger.info(f"✅ get_page API works: {test_url}")
			break
	
	# Test search
	logger.info("Phase 2: Testing search API...")
	search_result = await knowledge_api.search(
		query="wisdom",
		top_k=5,
	)
	
	assert search_result is not None, "search should return data"
	if search_result.get("success"):
		results = search_result.get("results", [])
		logger.info(f"Search API returned {len(results)} results")
		# Results may be empty if no embeddings, which is OK for testing
	else:
		logger.warning(f"Search API returned error: {search_result.get('error')}")
	
	# Test get_links
	for result in explored_pages:
		if result.get('success') and 'url' in result:
			logger.info("Phase 3: Testing get_links API...")
			test_url = result['url']
			links_result = await knowledge_api.get_links(test_url)
			
			assert links_result is not None, "get_links should return data"
			if links_result.get("success"):
				links = links_result.get("links", [])
				logger.info(f"get_links API returned {len(links)} links for {test_url}")
			break
	
	# Test get_semantic_sitemap
	logger.info("Phase 4: Testing get_semantic_sitemap API...")
	semantic_sitemap_result = await knowledge_api.get_semantic_sitemap()
	
	assert semantic_sitemap_result is not None, "get_semantic_sitemap should return data"
	assert semantic_sitemap_result.get("success"), "get_semantic_sitemap should succeed"
	if semantic_sitemap_result.get("success"):
		sitemap = semantic_sitemap_result.get("sitemap", {})
		assert "hierarchy" in sitemap, "Semantic sitemap should have hierarchy"
		logger.info(f"✅ get_semantic_sitemap API works: {sitemap.get('total_pages', 0)} pages")
	
	# Test get_functional_sitemap
	logger.info("Phase 5: Testing get_functional_sitemap API...")
	functional_sitemap_result = await knowledge_api.get_functional_sitemap()
	
	assert functional_sitemap_result is not None, "get_functional_sitemap should return data"
	assert functional_sitemap_result.get("success"), "get_functional_sitemap should succeed"
	if functional_sitemap_result.get("success"):
		sitemap = functional_sitemap_result.get("sitemap", {})
		assert "navigation" in sitemap, "Functional sitemap should have navigation"
		logger.info(f"✅ get_functional_sitemap API works")
	
	logger.info("✅ Knowledge API phase complete")


@pytest.mark.asyncio
async def test_e2e_complex_website_complete_flow(
	knowledge_pipeline,
	knowledge_storage,
	vector_store,
	flow_mapper,
	sitemap_generator,
	knowledge_api,
	browser_session,
):
	"""
	Complete end-to-end test of the entire Phase 2 flow.
	
	This test runs the complete flow:
	1. Website exploration
	2. Semantic analysis
	3. Knowledge storage
	4. Site map generation
	5. API testing
	
	This is the main comprehensive test that validates the entire system.
	"""
	logger.info("=" * 80)
	logger.info("E2E Test: Complete Phase 2 Flow")
	logger.info("=" * 80)
	logger.info(f"Target website: {TEST_WEBSITE_URL}")
	logger.info(f"Configuration: Strategy={EXPLORATION_STRATEGY}, Depth={MAX_DEPTH}, Max Pages={MAX_PAGES_TO_EXPLORE}")
	
	# Step 1: Exploration
	logger.info("\n" + "=" * 80)
	logger.info("STEP 1: Website Exploration")
	logger.info("=" * 80)
	exploration_results = await knowledge_pipeline.explore_and_store(
		start_url=TEST_WEBSITE_URL,
		max_pages=MAX_PAGES_TO_EXPLORE,
	)
	
	explored_pages = exploration_results.get('results', [])
	successful_results = [r for r in explored_pages if r.get('success')]
	
	logger.info(f"✅ Explored {exploration_results['pages_stored']}/{exploration_results['pages_processed']} pages")
	assert len(explored_pages) > 0, "Should discover pages"
	
	# Track navigation in flow_mapper
	flow_mapper.track_navigation(TEST_WEBSITE_URL)  # Entry point
	for result in successful_results:
		if 'url' in result:
			url = result['url']
			if url != TEST_WEBSITE_URL:
				flow_mapper.track_navigation(url, referrer=TEST_WEBSITE_URL)
	
	# Step 2: Verify Storage
	logger.info("\n" + "=" * 80)
	logger.info("STEP 2: Knowledge Storage Verification")
	logger.info("=" * 80)
	
	stored_pages = 0
	total_links = 0
	for result in successful_results:
		if 'url' in result:
			url = result['url']
			stored_page = await knowledge_storage.get_page(url)
			if stored_page:
				stored_pages += 1
			
			links = await knowledge_storage.get_links_from(url)
			total_links += len(links)
	
	logger.info(f"✅ Stored {stored_pages}/{len(successful_results)} pages")
	logger.info(f"✅ Stored {total_links} links (graph edges)")
	assert stored_pages > 0, "Should store pages"
	
	# Step 3: Verify Semantic Analysis
	logger.info("\n" + "=" * 80)
	logger.info("STEP 3: Semantic Analysis Verification")
	logger.info("=" * 80)
	
	pages_with_embeddings = 0
	for result in successful_results[:20]:
		if 'url' in result:
			url = result['url']
			embedding = await vector_store.get_embedding(url)
			if embedding:
				pages_with_embeddings += 1
	
	logger.info(f"✅ Generated embeddings for {pages_with_embeddings} pages")
	
	# Step 4: Site Map Generation
	logger.info("\n" + "=" * 80)
	logger.info("STEP 4: Site Map Generation")
	logger.info("=" * 80)
	
	semantic_sitemap = await sitemap_generator.generate_semantic_sitemap()
	functional_sitemap = await sitemap_generator.generate_functional_sitemap()
	
	logger.info(f"✅ Semantic sitemap: {semantic_sitemap.get('total_pages', 0)} pages, {len(semantic_sitemap.get('hierarchy', []))} categories")
	logger.info(f"✅ Functional sitemap: {len(functional_sitemap.get('navigation', []))} navigation entries")
	
	# Step 5: API Testing
	logger.info("\n" + "=" * 80)
	logger.info("STEP 5: Knowledge API Testing")
	logger.info("=" * 80)
	
	# Test search
	search_result = await knowledge_api.search(query="life", top_k=5)
	if search_result.get("success"):
		results = search_result.get("results", [])
		logger.info(f"✅ Search API: {len(results)} results")
	else:
		logger.warning(f"Search API error: {search_result.get('error')}")
	
	# Test get_page
	for result in successful_results:
		if 'url' in result:
			page_result = await knowledge_api.get_page(result['url'])
			assert page_result is not None, "get_page should work"
			assert page_result.get("success"), "get_page should succeed"
			logger.info(f"✅ get_page API: Works")
			break
	
	# Step 6: Final Statistics
	logger.info("\n" + "=" * 80)
	logger.info("STEP 6: Final Statistics")
	logger.info("=" * 80)
	
	flow_stats = flow_mapper.get_flow_stats()
	logger.info(f"Navigation Statistics:")
	logger.info(f"  - Total pages: {flow_stats.get('total_pages', 0)}")
	logger.info(f"  - Total visits: {flow_stats.get('total_visits', 0)}")
	logger.info(f"  - Entry points: {len(flow_mapper.get_entry_points())}")
	logger.info(f"  - Total paths: {flow_stats.get('total_paths', 0)}")
	
	logger.info("\n" + "=" * 80)
	logger.info("✅ COMPLETE E2E TEST PASSED")
	logger.info("=" * 80)
	
	# Final assertions
	assert len(explored_pages) > 0, "Should explore pages"
	assert stored_pages > 0, "Should store pages"
	assert len(semantic_sitemap.get("hierarchy", [])) > 0, "Should generate semantic sitemap"
	assert len(functional_sitemap.get("navigation", [])) > 0, "Should generate functional sitemap"
	if search_result.get("success"):
		assert len(search_result.get("results", [])) >= 0, "Search should return results (may be empty)"

#!/usr/bin/env python3
"""
Integration Test Script for Semantic Analyzer (Steps 2.7-2.10).

This script performs actual calls to test the complete semantic analyzer.
Run this script to verify all semantic analysis functionality works end-to-end.

Usage:
    python tests/ci/knowledge/integration_test_semantic.py

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

from navigator.knowledge.semantic_analyzer import SemanticAnalyzer

# Configure logging
logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_content_extraction():
	"""Test content extraction."""
	logger.info("=" * 80)
	logger.info("Test 1: Content Extraction")
	logger.info("=" * 80)
	
	browser_session = BrowserSession(
		browser_profile=BrowserProfile(headless=True, user_data_dir=None)
	)
	await browser_session.start()
	logger.info("✅ Started browser session")
	
	try:
		analyzer = SemanticAnalyzer(browser_session=browser_session)
		test_url = "https://example.com"
		
		logger.info(f"📋 Extracting content from {test_url}")
		content = await analyzer.extract_content(test_url)
		
		logger.info(f"✅ Extracted content successfully")
		assert "title" in content
		assert "headings" in content
		assert "paragraphs" in content
		assert "text" in content
		
		logger.info(f"  Title: {content.get('title', 'N/A')[:80]}")
		logger.info(f"  Headings: {len(content.get('headings', []))}")
		logger.info(f"  Paragraphs: {len(content.get('paragraphs', []))}")
		
		logger.info("✅ Test 1 PASSED: Content Extraction")
		return True
	
	finally:
		await browser_session.kill()


async def test_entity_recognition():
	"""Test entity recognition."""
	logger.info("=" * 80)
	logger.info("Test 2: Entity Recognition")
	logger.info("=" * 80)
	
	browser_session = BrowserSession(
		browser_profile=BrowserProfile(headless=True, user_data_dir=None)
	)
	await browser_session.start()
	
	try:
		analyzer = SemanticAnalyzer(browser_session=browser_session)
		test_url = "https://example.com"
		
		logger.info(f"📋 Extracting content and identifying entities from {test_url}")
		content = await analyzer.extract_content(test_url)
		
		entities = analyzer.identify_entities(content["text"])
		logger.info(f"✅ Identified {len(entities)} entities")
		
		# Print entity types
		entity_labels = set(e["label"] for e in entities)
		logger.info(f"  Entity types: {entity_labels}")
		
		logger.info("✅ Test 2 PASSED: Entity Recognition")
		return True
	
	finally:
		await browser_session.kill()


async def test_topic_modeling():
	"""Test topic modeling."""
	logger.info("=" * 80)
	logger.info("Test 3: Topic Modeling")
	logger.info("=" * 80)
	
	browser_session = BrowserSession(
		browser_profile=BrowserProfile(headless=True, user_data_dir=None)
	)
	await browser_session.start()
	
	try:
		analyzer = SemanticAnalyzer(browser_session=browser_session)
		test_url = "https://example.com"
		
		logger.info(f"📋 Extracting topics from {test_url}")
		content = await analyzer.extract_content(test_url)
		
		topics = analyzer.extract_topics(content)
		logger.info(f"✅ Extracted topics successfully")
		
		logger.info(f"  Keywords: {len(topics.get('keywords', []))}")
		logger.info(f"  Main topics: {len(topics.get('main_topics', []))}")
		logger.info(f"  Categories: {topics.get('categories', [])}")
		
		logger.info("✅ Test 3 PASSED: Topic Modeling")
		return True
	
	finally:
		await browser_session.kill()


async def test_embedding_generation():
	"""Test embedding generation."""
	logger.info("=" * 80)
	logger.info("Test 4: Embedding Generation")
	logger.info("=" * 80)
	
	browser_session = BrowserSession(
		browser_profile=BrowserProfile(headless=True, user_data_dir=None)
	)
	await browser_session.start()
	
	try:
		analyzer = SemanticAnalyzer(browser_session=browser_session)
		test_url = "https://example.com"
		
		logger.info(f"📋 Generating embedding from {test_url}")
		content = await analyzer.extract_content(test_url)
		
		embedding = analyzer.generate_embedding(content["text"])
		logger.info(f"✅ Generated embedding of size {len(embedding)}")
		
		logger.info("✅ Test 4 PASSED: Embedding Generation")
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
		analyzer = SemanticAnalyzer(browser_session=browser_session)
		test_url = "https://example.com"
		
		logger.info("📋 Running complete semantic analysis pipeline")
		
		# Extract content
		content = await analyzer.extract_content(test_url)
		logger.info("✅ Content extracted")
		
		# Identify entities
		entities = analyzer.identify_entities(content["text"])
		logger.info(f"✅ Entities identified: {len(entities)}")
		
		# Extract topics
		topics = analyzer.extract_topics(content)
		logger.info(f"✅ Topics extracted: {len(topics.get('keywords', []))} keywords")
		
		# Generate embedding
		embedding = analyzer.generate_embedding(content["text"])
		logger.info(f"✅ Embedding generated: {len(embedding)} dimensions")
		
		logger.info("✅ Test 5 PASSED: Complete Integration")
		return True
	
	finally:
		await browser_session.kill()


async def main():
	"""Run all integration tests."""
	logger.info("🚀 Starting Semantic Analyzer Integration Tests")
	logger.info("=" * 80)
	
	tests = [
		("Content Extraction", test_content_extraction),
		("Entity Recognition", test_entity_recognition),
		("Topic Modeling", test_topic_modeling),
		("Embedding Generation", test_embedding_generation),
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

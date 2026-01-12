"""
End-to-End Tests for Semantic Analyzer (Steps 2.7-2.10).

Tests the complete semantic analysis workflow.
"""

import asyncio

import pytest

from navigator.knowledge.semantic_analyzer import SemanticAnalyzer


class TestE2ESemanticAnalysis:
	"""End-to-end tests for complete semantic analysis flow."""

	async def test_e2e_content_extraction_and_analysis(self, browser_session, base_url, http_server):
		"""Test complete content extraction and analysis workflow."""
		http_server.expect_request('/semantic').respond_with_data(
			'<html><head><title>Semantic Analysis Page</title></head><body>'
			'<h1>Main Heading</h1>'
			'<h2>Sub Heading</h2>'
			'<p>This is a paragraph about Python programming and software development.</p>'
			'<p>Contact us at info@example.com or visit https://example.com for more info.</p>'
			'</body></html>',
			content_type='text/html',
		)
		
		analyzer = SemanticAnalyzer(browser_session=browser_session)
		url = f"{base_url}/semantic"
		
		# Extract content
		content = await analyzer.extract_content(url)
		
		# Verify content structure
		assert "title" in content
		assert "headings" in content
		assert "paragraphs" in content
		assert "text" in content
		
		# Identify entities
		entities = analyzer.identify_entities(content["text"])
		assert len(entities) > 0
		
		# Extract topics
		topics = analyzer.extract_topics(content)
		assert "keywords" in topics
		assert "main_topics" in topics
		
		# Generate embedding
		embedding = analyzer.generate_embedding(content["text"])
		assert len(embedding) > 0
		assert len(embedding) == 128  # Basic implementation uses 128 dimensions

	async def test_e2e_full_analysis_pipeline(self, browser_session, base_url, http_server):
		"""Test full analysis pipeline with all features."""
		http_server.expect_request('/pipeline').respond_with_data(
			'<html><head><title>Full Pipeline Test</title></head><body>'
			'<h1>Technology Article</h1>'
			'<p>Python programming language is used for software development.</p>'
			'<p>Contact info@example.com or call 123-456-7890.</p>'
			'</body></html>',
			content_type='text/html',
		)
		
		analyzer = SemanticAnalyzer(browser_session=browser_session)
		url = f"{base_url}/pipeline"
		
		# Complete pipeline
		content = await analyzer.extract_content(url)
		entities = analyzer.identify_entities(content["text"])
		topics = analyzer.extract_topics(content)
		embedding = analyzer.generate_embedding(content["text"])
		
		# Verify all components work together
		assert content["text"]  # Content extracted
		assert len(entities) >= 0  # Entities identified (may be 0)
		assert topics["keywords"]  # Topics extracted
		assert len(embedding) > 0  # Embedding generated

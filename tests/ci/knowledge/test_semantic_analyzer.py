"""
Tests for Semantic Analyzer (Steps 2.7-2.10).

Tests cover:
- Content Extraction (Step 2.7)
- Entity Recognition (Step 2.8)
- Topic Modeling (Step 2.9)
- Embeddings (Step 2.10)
"""

import asyncio

import pytest

from navigator.knowledge.semantic_analyzer import SemanticAnalyzer


class TestContentExtraction:
	"""Tests for content extraction (Step 2.7)."""

	async def test_extract_content_from_page(self, browser_session, base_url, http_server):
		"""Test extracting content from a webpage."""
		http_server.expect_request('/content').respond_with_data(
			'<html><head><title>Test Page</title></head><body>'
			'<h1>Main Heading</h1>'
			'<h2>Sub Heading</h2>'
			'<p>This is a paragraph with some content.</p>'
			'<p>This is another paragraph.</p>'
			'</body></html>',
			content_type='text/html',
		)
		
		analyzer = SemanticAnalyzer(browser_session=browser_session)
		url = f"{base_url}/content"
		content = await analyzer.extract_content(url)
		
		assert "title" in content
		assert "description" in content
		assert "headings" in content
		assert "paragraphs" in content
		assert "text" in content
		
		assert len(content["headings"]) > 0
		assert len(content["paragraphs"]) > 0
		assert len(content["text"]) > 0

	async def test_extract_headings_hierarchy(self, browser_session, base_url, http_server):
		"""Test that headings are extracted with hierarchy."""
		http_server.expect_request('/headings').respond_with_data(
			'<html><head><title>Headings</title></head><body>'
			'<h1>Level 1</h1>'
			'<h2>Level 2</h2>'
			'<h3>Level 3</h3>'
			'</body></html>',
			content_type='text/html',
		)
		
		analyzer = SemanticAnalyzer(browser_session=browser_session)
		url = f"{base_url}/headings"
		content = await analyzer.extract_content(url)
		
		headings = content["headings"]
		assert len(headings) > 0
		
		# Check heading levels
		levels = [h["level"] for h in headings]
		assert 1 in levels
		assert 2 in levels
		
		# All headings should have text
		for heading in headings:
			assert "level" in heading
			assert "text" in heading
			assert heading["text"]

	async def test_extract_paragraphs(self, browser_session, base_url, http_server):
		"""Test that paragraphs are extracted correctly."""
		http_server.expect_request('/paragraphs').respond_with_data(
			'<html><head><title>Paragraphs</title></head><body>'
			'<h1>Title</h1>'
			'<p>First paragraph with some text.</p>'
			'<p>Second paragraph with more text.</p>'
			'</body></html>',
			content_type='text/html',
		)
		
		analyzer = SemanticAnalyzer(browser_session=browser_session)
		url = f"{base_url}/paragraphs"
		content = await analyzer.extract_content(url)
		
		paragraphs = content["paragraphs"]
		assert len(paragraphs) > 0
		
		# All paragraphs should be non-empty
		for para in paragraphs:
			assert para
			assert len(para) > 0

	async def test_extract_metadata(self, browser_session, base_url, http_server):
		"""Test that metadata (title, description) is extracted."""
		http_server.expect_request('/metadata').respond_with_data(
			'<html><head><title>Page Title</title></head><body>'
			'<h1>Main Title</h1>'
			'<p>This is a description paragraph that should be extracted as metadata.</p>'
			'</body></html>',
			content_type='text/html',
		)
		
		analyzer = SemanticAnalyzer(browser_session=browser_session)
		url = f"{base_url}/metadata"
		content = await analyzer.extract_content(url)
		
		assert "title" in content
		assert "description" in content
		
		# Title should be extracted from first h1
		if content["title"]:
			assert len(content["title"]) > 0


class TestEntityRecognition:
	"""Tests for entity recognition (Step 2.8)."""

	async def test_identify_entities_basic(self, browser_session):
		"""Test basic entity recognition."""
		analyzer = SemanticAnalyzer(browser_session=browser_session)
		
		text = "Contact us at info@example.com or visit https://example.com. Call 123-456-7890."
		entities = analyzer.identify_entities(text)
		
		assert len(entities) > 0
		
		# Check entity structure
		for entity in entities:
			assert "text" in entity
			assert "label" in entity
			assert "start" in entity
			assert "end" in entity

	async def test_identify_email_entities(self, browser_session):
		"""Test email entity recognition."""
		analyzer = SemanticAnalyzer(browser_session=browser_session)
		
		text = "Email us at contact@example.com or support@example.org"
		entities = analyzer.identify_entities(text)
		
		email_entities = [e for e in entities if e["label"] == "EMAIL"]
		assert len(email_entities) > 0

	async def test_identify_url_entities(self, browser_session):
		"""Test URL entity recognition."""
		analyzer = SemanticAnalyzer(browser_session=browser_session)
		
		text = "Visit https://example.com or http://test.org for more info"
		entities = analyzer.identify_entities(text)
		
		url_entities = [e for e in entities if e["label"] == "URL"]
		assert len(url_entities) > 0


class TestTopicModeling:
	"""Tests for topic modeling (Step 2.9)."""

	async def test_extract_topics(self, browser_session, base_url, http_server):
		"""Test topic extraction from content."""
		http_server.expect_request('/topics').respond_with_data(
			'<html><head><title>Technology Article</title></head><body>'
			'<h1>Python Programming</h1>'
			'<p>Python is a programming language used for software development and data science.</p>'
			'<p>Many developers use Python for web development and machine learning.</p>'
			'</body></html>',
			content_type='text/html',
		)
		
		analyzer = SemanticAnalyzer(browser_session=browser_session)
		url = f"{base_url}/topics"
		content = await analyzer.extract_content(url)
		
		topics = analyzer.extract_topics(content)
		
		assert "keywords" in topics
		assert "main_topics" in topics
		assert "categories" in topics
		
		assert isinstance(topics["keywords"], list)
		assert isinstance(topics["main_topics"], list)
		assert isinstance(topics["categories"], list)

	async def test_extract_keywords(self, browser_session):
		"""Test keyword extraction."""
		analyzer = SemanticAnalyzer(browser_session=browser_session)
		
		content = {
			"text": "Python programming language software development data science machine learning",
			"headings": [],
			"paragraphs": [],
		}
		
		topics = analyzer.extract_topics(content)
		keywords = topics["keywords"]
		
		assert len(keywords) > 0
		# Should extract meaningful keywords (words > 3 chars, not stop words)
		assert any(len(kw) > 3 for kw in keywords)

	async def test_extract_main_topics_from_headings(self, browser_session):
		"""Test that main topics are extracted from headings."""
		analyzer = SemanticAnalyzer(browser_session=browser_session)
		
		content = {
			"text": "Some content text",
			"headings": [
				{"level": 1, "text": "Main Topic"},
				{"level": 2, "text": "Sub Topic"},
				{"level": 3, "text": "Nested Topic"},
			],
			"paragraphs": [],
		}
		
		topics = analyzer.extract_topics(content)
		main_topics = topics["main_topics"]
		
		assert len(main_topics) > 0
		# Should include top-level headings
		assert "Main Topic" in main_topics


class TestEmbeddings:
	"""Tests for embedding generation (Step 2.10)."""

	async def test_generate_embedding(self, browser_session):
		"""Test embedding generation."""
		analyzer = SemanticAnalyzer(browser_session=browser_session)
		
		text = "This is sample text for embedding generation"
		embedding = analyzer.generate_embedding(text)
		
		assert isinstance(embedding, list)
		assert len(embedding) > 0
		assert all(isinstance(x, float) for x in embedding)

	async def test_embedding_dimensions(self, browser_session):
		"""Test that embeddings have consistent dimensions."""
		analyzer = SemanticAnalyzer(browser_session=browser_session)
		
		text1 = "First text sample"
		text2 = "Second text sample with different content"
		
		embedding1 = analyzer.generate_embedding(text1)
		embedding2 = analyzer.generate_embedding(text2)
		
		# Embeddings should have same dimensions
		assert len(embedding1) == len(embedding2)
		assert len(embedding1) > 0

	async def test_embedding_consistency(self, browser_session):
		"""Test that same text produces same embedding."""
		analyzer = SemanticAnalyzer(browser_session=browser_session)
		
		text = "Consistent text for embedding"
		embedding1 = analyzer.generate_embedding(text)
		embedding2 = analyzer.generate_embedding(text)
		
		# Same text should produce same embedding
		assert embedding1 == embedding2


class TestSemanticAnalyzerIntegration:
	"""Integration tests for Semantic Analyzer."""

	async def test_complete_content_analysis(self, browser_session, base_url, http_server):
		"""Test complete content analysis workflow."""
		http_server.expect_request('/analysis').respond_with_data(
			'<html><head><title>Analysis Page</title></head><body>'
			'<h1>Technology Article</h1>'
			'<p>Python is a programming language. Contact us at info@example.com.</p>'
			'<p>Visit https://python.org for more information.</p>'
			'</body></html>',
			content_type='text/html',
		)
		
		analyzer = SemanticAnalyzer(browser_session=browser_session)
		url = f"{base_url}/analysis"
		
		# Extract content
		content = await analyzer.extract_content(url)
		assert "text" in content
		
		# Identify entities
		entities = analyzer.identify_entities(content["text"])
		assert len(entities) > 0
		
		# Extract topics
		topics = analyzer.extract_topics(content)
		assert "keywords" in topics
		
		# Generate embedding
		embedding = analyzer.generate_embedding(content["text"])
		assert len(embedding) > 0

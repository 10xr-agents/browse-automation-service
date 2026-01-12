"""
Semantic Analyzer for Knowledge Retrieval

Extracts and analyzes content from web pages, including:
- Content extraction (main content, headings, paragraphs, metadata)
- Entity recognition (people, organizations, locations, dates, etc.)
- Topic modeling (keywords, topics, categories)
- Embedding generation (for semantic search)
"""

import logging
import re
from typing import Any

from browser_use import BrowserSession
from browser_use.dom.markdown_extractor import extract_clean_markdown

logger = logging.getLogger(__name__)


class SemanticAnalyzer:
	"""
	Semantic analyzer for extracting and analyzing web page content.
	
	Supports:
	- Content extraction with navigation/footer/ad removal
	- Entity recognition (basic implementation, can be extended with spaCy)
	- Topic modeling (keyword extraction, topic identification)
	- Embedding generation (basic implementation, can be extended with sentence-transformers/OpenAI)
	"""
	
	def __init__(
		self,
		browser_session: BrowserSession | None = None,
	):
		"""
		Initialize the semantic analyzer.
		
		Args:
			browser_session: Browser session for accessing pages (optional, can pass URL directly)
		"""
		self.browser_session = browser_session
		logger.debug("SemanticAnalyzer initialized")
	
	async def extract_content(self, url: str | None = None) -> dict[str, Any]:
		"""
		Extract main content from a page.
		
		Args:
			url: URL of the page to extract content from (if browser_session provided)
		
		Returns:
			Dictionary with 'title', 'description', 'headings', 'paragraphs', 'text'
		"""
		if not self.browser_session:
			raise ValueError("browser_session required for extract_content")
		
		if not url:
			raise ValueError("url required for extract_content")
		
		logger.debug(f"Extracting content from {url}")
		
		try:
			# Navigate to URL if needed
			from browser_use.browser.events import NavigateToUrlEvent
			event = self.browser_session.event_bus.dispatch(NavigateToUrlEvent(url=url))
			await event
			import asyncio
			await asyncio.sleep(0.5)  # Wait for page load
			
			# Extract clean markdown using browser-use's extract_clean_markdown
			# This already handles navigation/footer/ad removal via markdownify
			markdown_content, content_stats = await extract_clean_markdown(
				browser_session=self.browser_session,
				extract_links=False,
			)
			
			# Parse markdown to extract structured content
			content = self._parse_markdown_content(markdown_content)
			
			# Extract metadata (title, description)
			# For now, we'll extract from markdown (title is usually first heading)
			# In a full implementation, we'd get this from DOM <title> and <meta> tags
			metadata = self._extract_metadata(markdown_content)
			content.update(metadata)
			
			logger.debug(f"Extracted content: {len(content.get('paragraphs', []))} paragraphs, {len(content.get('headings', []))} headings")
			return content
		
		except Exception as e:
			logger.error(f"Error extracting content from {url}: {e}", exc_info=True)
			raise
	
	def _parse_markdown_content(self, markdown: str) -> dict[str, Any]:
		"""
		Parse markdown content to extract headings, paragraphs, and text.
		
		Args:
			markdown: Markdown content string
		
		Returns:
			Dictionary with 'headings', 'paragraphs', 'text'
		"""
		headings = []
		paragraphs = []
		
		lines = markdown.split('\n')
		current_paragraph = []
		
		for line in lines:
			line = line.strip()
			if not line:
				if current_paragraph:
					paragraph_text = ' '.join(current_paragraph)
					if paragraph_text:
						paragraphs.append(paragraph_text)
					current_paragraph = []
				continue
			
			# Check for headings (# Heading)
			if line.startswith('#'):
				# Save current paragraph if any
				if current_paragraph:
					paragraph_text = ' '.join(current_paragraph)
					if paragraph_text:
						paragraphs.append(paragraph_text)
					current_paragraph = []
				
				# Extract heading level and text
				heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
				if heading_match:
					level = len(heading_match.group(1))
					text = heading_match.group(2).strip()
					headings.append({
						"level": level,
						"text": text,
					})
			else:
				# Regular text line - add to current paragraph
				current_paragraph.append(line)
		
		# Add final paragraph if any
		if current_paragraph:
			paragraph_text = ' '.join(current_paragraph)
			if paragraph_text:
				paragraphs.append(paragraph_text)
		
		# Combine all text
		all_text = ' '.join(paragraphs)
		
		return {
			"headings": headings,
			"paragraphs": paragraphs,
			"text": all_text,
		}
	
	def _extract_metadata(self, markdown: str) -> dict[str, str]:
		"""
		Extract metadata (title, description) from content.
		
		Args:
			markdown: Markdown content string
		
		Returns:
			Dictionary with 'title', 'description'
		"""
		# Extract title from first heading (h1)
		title = ""
		description = ""
		
		lines = markdown.split('\n')
		for line in lines:
			line = line.strip()
			if line.startswith('# '):
				# First h1 is usually the title
				title_match = re.match(r'^#\s+(.+)$', line)
				if title_match:
					title = title_match.group(1).strip()
					break
		
		# Extract description from first paragraph
		# Split by paragraphs (double newlines)
		paragraphs = re.split(r'\n\n+', markdown)
		for para in paragraphs:
			para = para.strip()
			# Skip headings
			if not para.startswith('#'):
				# Remove markdown formatting
				description = re.sub(r'[#*_\[\]()]', '', para).strip()
				if len(description) > 100:
					description = description[:100] + "..."
				break
		
		return {
			"title": title,
			"description": description,
		}
	
	def identify_entities(self, text: str) -> list[dict[str, Any]]:
		"""
		Identify entities in text.
		
		Note: Basic implementation using regex patterns.
		For production, integrate spaCy for better NER.
		
		Args:
			text: Text to analyze
		
		Returns:
			List of entity dictionaries with 'text', 'label', 'start', 'end'
		"""
		entities = []
		
		# Basic entity patterns (can be extended with spaCy)
		patterns = [
			# Email addresses
			(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', 'EMAIL'),
			# URLs
			(r'https?://[^\s<>"\']+', 'URL'),
			# Phone numbers (basic pattern)
			(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', 'PHONE'),
			# Dates (basic patterns)
			(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', 'DATE'),
			# Money (basic pattern)
			(r'\$\d+(?:,\d{3})*(?:\.\d{2})?', 'MONEY'),
		]
		
		for pattern, label in patterns:
			for match in re.finditer(pattern, text):
				entities.append({
					"text": match.group(0),
					"label": label,
					"start": match.start(),
					"end": match.end(),
				})
		
		logger.debug(f"Identified {len(entities)} entities")
		return entities
	
	def extract_topics(self, content: dict[str, Any]) -> dict[str, Any]:
		"""
		Extract topics and keywords from content.
		
		Note: Basic implementation using simple keyword extraction.
		For production, use topic modeling libraries (LDA, etc.).
		
		Args:
			content: Content dictionary with 'text', 'headings', 'paragraphs'
		
		Returns:
			Dictionary with 'keywords', 'main_topics', 'categories'
		"""
		text = content.get('text', '')
		headings = content.get('headings', [])
		
		# Extract keywords (simple word frequency approach)
		# Remove common stop words
		stop_words = {
			'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
			'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
			'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
			'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this',
			'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they',
		}
		
		# Tokenize and count words
		words = re.findall(r'\b[a-z]+\b', text.lower())
		word_freq: dict[str, int] = {}
		for word in words:
			if len(word) > 3 and word not in stop_words:  # Only words > 3 chars
				word_freq[word] = word_freq.get(word, 0) + 1
		
		# Get top keywords
		sorted_keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
		keywords = [word for word, count in sorted_keywords[:20]]  # Top 20 keywords
		
		# Extract main topics from headings
		main_topics = [h['text'] for h in headings if h['level'] <= 2][:10]  # Top-level headings
		
		# Basic categorization (can be improved)
		categories = self._categorize_content(text, headings)
		
		return {
			"keywords": keywords,
			"main_topics": main_topics,
			"categories": categories,
		}
	
	def _categorize_content(self, text: str, headings: list[dict[str, Any]]) -> list[str]:
		"""
		Categorize content based on keywords and headings.
		
		Args:
			text: Text content
			heading: List of heading dictionaries
		
		Returns:
			List of category strings
		"""
		categories = []
		text_lower = text.lower()
		
		# Basic category detection based on keywords
		category_keywords = {
			"Technology": ['software', 'programming', 'code', 'development', 'tech', 'computer', 'api', 'app'],
			"Business": ['business', 'company', 'service', 'product', 'sales', 'marketing', 'customer'],
			"Education": ['learn', 'course', 'education', 'tutorial', 'guide', 'lesson', 'teaching'],
			"News": ['news', 'article', 'report', 'update', 'latest', 'recent'],
			"Documentation": ['documentation', 'docs', 'reference', 'manual', 'guide', 'help'],
		}
		
		for category, keywords in category_keywords.items():
			if any(keyword in text_lower for keyword in keywords):
				categories.append(category)
		
		return categories
	
	def generate_embedding(self, text: str) -> list[float]:
		"""
		Generate embedding for text.
		
		Note: Basic implementation returns a simple feature vector.
		For production, integrate sentence-transformers or OpenAI embeddings.
		
		Args:
			text: Text to generate embedding for
		
		Returns:
			List of float values (embedding vector)
		"""
		# Basic implementation: simple feature vector based on word frequencies
		# In production, use sentence-transformers or OpenAI embeddings
		
		logger.warning("Using basic embedding implementation. For production, integrate sentence-transformers or OpenAI embeddings.")
		
		# Simple feature vector (can be replaced with real embeddings)
		# This is a placeholder - actual embeddings would use a model
		words = text.lower().split()
		word_count = len(words)
		char_count = len(text)
		avg_word_length = sum(len(w) for w in words) / word_count if word_count > 0 else 0
		
		# Return a simple feature vector (in production, this would be a real embedding)
		# For now, return a fixed-size vector with basic features
		embedding_size = 128  # Common embedding size
		embedding = [0.0] * embedding_size
		
		# Fill with basic features (hash-based to simulate embeddings)
		import hashlib
		hash_obj = hashlib.md5(text.encode())
		hash_bytes = hash_obj.digest()
		
		# Distribute hash bytes across embedding vector
		for i in range(min(embedding_size, len(hash_bytes))):
			embedding[i] = float(hash_bytes[i]) / 255.0
		
		# Add some statistical features
		if embedding_size > 3:
			embedding[0] = min(word_count / 1000.0, 1.0)  # Normalized word count
			embedding[1] = min(char_count / 10000.0, 1.0)  # Normalized char count
			embedding[2] = min(avg_word_length / 10.0, 1.0)  # Normalized avg word length
		
		logger.debug(f"Generated embedding of size {len(embedding)}")
		return embedding

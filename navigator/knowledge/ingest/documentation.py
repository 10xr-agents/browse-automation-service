"""
Technical documentation ingester.

Supports parsing and chunking of Markdown, HTML, and PDF documents.
Preserves document structure while creating semantically meaningful chunks.
"""

import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import markdown
import tiktoken
from bs4 import BeautifulSoup
from pypdf import PdfReader

from navigator.schemas import (
	ContentChunk,
	DocumentFormat,
	IngestionResult,
	SourceMetadata,
	SourceType,
	detect_document_format,
)

logger = logging.getLogger(__name__)


class DocumentationIngester:
	"""
	Ingests technical documentation from various formats.
	
	Supports:
	- Markdown (.md, .markdown)
	- HTML (.html, .htm)
	- PDF (.pdf)
	- Plain text (.txt)
	
	Features:
	- Semantic chunking (preserves code blocks, headings)
	- Token counting (max 2000 tokens per chunk)
	- Structure preservation
	- Metadata extraction
	"""
	
	def __init__(self, max_tokens_per_chunk: int = 2000):
		"""
		Initialize documentation ingester.
		
		Args:
			max_tokens_per_chunk: Maximum tokens per content chunk (default: 2000)
		"""
		self.max_tokens_per_chunk = max_tokens_per_chunk
		self.tokenizer = tiktoken.get_encoding("cl100k_base")  # GPT-4 tokenizer
	
	def ingest_file(self, file_path: str | Path) -> IngestionResult:
		"""
		Ingest a documentation file.
		
		Args:
			file_path: Path to the documentation file
		
		Returns:
			IngestionResult with chunks and metadata
		"""
		file_path = Path(file_path)
		
		# Create result
		result = IngestionResult(
			ingestion_id=str(uuid4()),
			source_type=SourceType.TECHNICAL_DOCUMENTATION,
			metadata=SourceMetadata(
				source_type=SourceType.TECHNICAL_DOCUMENTATION,
				url=str(file_path),
				title=file_path.stem,
				format=detect_document_format(str(file_path)),
				size_bytes=file_path.stat().st_size if file_path.exists() else 0,
				last_modified=datetime.fromtimestamp(file_path.stat().st_mtime) if file_path.exists() else None,
			)
		)
		
		try:
			# Detect format and parse
			doc_format = detect_document_format(str(file_path))
			
			if doc_format == DocumentFormat.MARKDOWN:
				content = self._parse_markdown(file_path)
			elif doc_format == DocumentFormat.HTML:
				content = self._parse_html(file_path)
			elif doc_format == DocumentFormat.PDF:
				content = self._parse_pdf(file_path)
			elif doc_format == DocumentFormat.PLAIN_TEXT:
				content = self._parse_plain_text(file_path)
			else:
				result.add_error(
					"UnsupportedFormat",
					f"Unsupported document format: {doc_format}",
					{"file_path": str(file_path)}
				)
				result.mark_complete()
				return result
			
			# Create chunks
			chunks = self._create_chunks(content, result.ingestion_id)
			result.content_chunks = chunks
			
			# Mark complete
			result.mark_complete()
			logger.info(f"✅ Ingested {file_path.name}: {len(chunks)} chunks, {result.total_tokens} tokens")
			
		except Exception as e:
			logger.error(f"❌ Error ingesting {file_path}: {e}", exc_info=True)
			result.add_error(
				"IngestionError",
				str(e),
				{"file_path": str(file_path), "format": str(result.metadata.format)}
			)
			result.mark_complete()
		
		return result
	
	def _parse_markdown(self, file_path: Path) -> str:
		"""
		Parse Markdown file.
		
		Converts to HTML for structure extraction, then extracts text
		while preserving headings and code blocks.
		
		Args:
			file_path: Path to Markdown file
		
		Returns:
			Extracted content with structure markers
		"""
		with open(file_path, 'r', encoding='utf-8') as f:
			md_content = f.read()
		
		# Convert to HTML with extensions for better parsing
		html = markdown.markdown(
			md_content,
			extensions=['fenced_code', 'tables', 'toc', 'codehilite']
		)
		
		# Parse HTML to extract structure
		soup = BeautifulSoup(html, 'html.parser')
		
		# Extract structured content
		content_parts = []
		
		for element in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'pre', 'code', 'ul', 'ol', 'table']):
			# Headings
			if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
				level = int(element.name[1])
				content_parts.append(f"\n{'#' * level} {element.get_text().strip()}\n")
			
			# Code blocks
			elif element.name == 'pre':
				code = element.get_text().strip()
				content_parts.append(f"\n```\n{code}\n```\n")
			
			# Inline code
			elif element.name == 'code' and element.parent.name != 'pre':
				content_parts.append(f"`{element.get_text().strip()}`")
			
			# Paragraphs
			elif element.name == 'p':
				content_parts.append(element.get_text().strip() + "\n")
			
			# Lists
			elif element.name in ['ul', 'ol']:
				for li in element.find_all('li', recursive=False):
					content_parts.append(f"- {li.get_text().strip()}\n")
			
			# Tables (simplified)
			elif element.name == 'table':
				content_parts.append("\n[Table]\n")
				for row in element.find_all('tr'):
					cells = [cell.get_text().strip() for cell in row.find_all(['td', 'th'])]
					content_parts.append(" | ".join(cells) + "\n")
		
		return "".join(content_parts)
	
	def _parse_html(self, file_path: Path) -> str:
		"""
		Parse HTML file.
		
		Extracts semantic structure (headings, paragraphs, code blocks)
		while removing scripts, styles, and navigation elements.
		
		Args:
			file_path: Path to HTML file
		
		Returns:
			Extracted content with structure
		"""
		with open(file_path, 'r', encoding='utf-8') as f:
			html_content = f.read()
		
		soup = BeautifulSoup(html_content, 'html.parser')
		
		# Remove scripts, styles, navigation
		for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
			element.decompose()
		
		# Extract title
		title = soup.find('title')
		content_parts = []
		
		if title:
			content_parts.append(f"# {title.get_text().strip()}\n\n")
		
		# Extract main content
		main_content = soup.find('main') or soup.find('article') or soup.find('body')
		
		if main_content:
			for element in main_content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'pre', 'code', 'ul', 'ol']):
				# Headings
				if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
					level = int(element.name[1])
					content_parts.append(f"\n{'#' * level} {element.get_text().strip()}\n")
				
				# Code blocks
				elif element.name == 'pre':
					code = element.get_text().strip()
					content_parts.append(f"\n```\n{code}\n```\n")
				
				# Paragraphs
				elif element.name == 'p':
					text = element.get_text().strip()
					if text:
						content_parts.append(text + "\n")
				
				# Lists
				elif element.name in ['ul', 'ol']:
					for li in element.find_all('li', recursive=False):
						content_parts.append(f"- {li.get_text().strip()}\n")
		
		return "".join(content_parts)
	
	def _parse_pdf(self, file_path: Path) -> str:
		"""
		Parse PDF file.
		
		Extracts text content with basic structure preservation.
		
		Args:
			file_path: Path to PDF file
		
		Returns:
			Extracted text content
		"""
		content_parts = []
		
		try:
			reader = PdfReader(file_path)
			
			for page_num, page in enumerate(reader.pages, start=1):
				text = page.extract_text()
				
				if text.strip():
					# Add page marker
					content_parts.append(f"\n--- Page {page_num} ---\n")
					content_parts.append(text)
					content_parts.append("\n")
			
		except Exception as e:
			logger.error(f"Error parsing PDF {file_path}: {e}")
			raise
		
		return "".join(content_parts)
	
	def _parse_plain_text(self, file_path: Path) -> str:
		"""
		Parse plain text file.
		
		Args:
			file_path: Path to text file
		
		Returns:
			File content
		"""
		with open(file_path, 'r', encoding='utf-8') as f:
			return f.read()
	
	def _create_chunks(self, content: str, ingestion_id: str) -> list[ContentChunk]:
		"""
		Create semantic chunks from content.
		
		Splits content into chunks while:
		- Respecting max token limit
		- Preserving code blocks
		- Preserving paragraph boundaries
		- Maintaining section context
		
		Args:
			content: Raw content to chunk
			ingestion_id: ID of the ingestion
		
		Returns:
			List of ContentChunk objects
		"""
		chunks = []
		
		# Split into sections (by headings)
		sections = re.split(r'\n(#{1,6}\s+.+?)\n', content)
		
		current_section_title = None
		current_chunk = []
		current_tokens = 0
		chunk_index = 0
		
		for i, part in enumerate(sections):
			# Check if this is a heading
			is_heading = re.match(r'^#{1,6}\s+.+?$', part.strip())
			
			if is_heading:
				current_section_title = part.strip()
				current_chunk.append(part)
				current_tokens += len(self.tokenizer.encode(part))
			else:
				# Split into paragraphs
				paragraphs = part.split('\n\n')
				
				for para in paragraphs:
					if not para.strip():
						continue
					
					para_tokens = len(self.tokenizer.encode(para))
					
					# Check if adding this paragraph would exceed limit
					if current_tokens + para_tokens > self.max_tokens_per_chunk and current_chunk:
						# Create chunk
						chunk_content = "\n".join(current_chunk)
						chunks.append(ContentChunk(
							chunk_id=f"{ingestion_id}_{chunk_index}",
							content=chunk_content,
							chunk_index=chunk_index,
							token_count=current_tokens,
							section_title=current_section_title,
							chunk_type="documentation"
						))
						
						# Reset for next chunk
						chunk_index += 1
						current_chunk = []
						current_tokens = 0
						
						# Carry over section title
						if current_section_title:
							current_chunk.append(current_section_title)
							current_tokens += len(self.tokenizer.encode(current_section_title))
					
					# Add paragraph to current chunk
					current_chunk.append(para)
					current_tokens += para_tokens
		
		# Add final chunk
		if current_chunk:
			chunk_content = "\n".join(current_chunk)
			chunks.append(ContentChunk(
				chunk_id=f"{ingestion_id}_{chunk_index}",
				content=chunk_content,
				chunk_index=chunk_index,
				token_count=current_tokens,
				section_title=current_section_title,
				chunk_type="documentation"
			))
		
		return chunks

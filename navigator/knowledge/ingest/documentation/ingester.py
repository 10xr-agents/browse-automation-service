"""
Main DocumentationIngester class.

Orchestrates document parsing, chunking, and metadata extraction.
"""

import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from navigator.knowledge.ingest.documentation.chunking import create_chunks
from navigator.knowledge.ingest.documentation.metadata import create_comprehensive_summary
from navigator.knowledge.ingest.documentation.parsers.html import parse_html
from navigator.knowledge.ingest.documentation.parsers.markdown import parse_markdown
from navigator.knowledge.ingest.documentation.parsers.pdf import parse_pdf
from navigator.knowledge.ingest.documentation.parsers.text import parse_docx, parse_plain_text
from navigator.schemas import (
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
	- DOCX (.docx, .doc)
	
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
		# Image caption cache (pHash -> caption) to reduce Vision API costs
		self.image_caption_cache: dict[str, str] = {}

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
				content, metadata = parse_markdown(file_path)
			elif doc_format == DocumentFormat.HTML:
				content, metadata = parse_html(file_path)
			elif doc_format == DocumentFormat.PDF:
				content, metadata = parse_pdf(file_path, image_caption_cache=self.image_caption_cache)
			elif doc_format == DocumentFormat.PLAIN_TEXT:
				content, metadata = parse_plain_text(file_path)
			elif doc_format == DocumentFormat.DOCX:
				content, metadata = parse_docx(file_path, image_caption_cache=self.image_caption_cache)
			else:
				result.add_error(
					"UnsupportedFormat",
					f"Unsupported document format: {doc_format}",
					{"file_path": str(file_path)}
				)
				result.mark_complete()
				return result

			# Store enhanced metadata
			if metadata:
				result.metadata.author = metadata.get('author') or result.metadata.author
				result.metadata.language = metadata.get('language') or result.metadata.language
				result.metadata.tags = metadata.get('tags', []) or result.metadata.tags

			# Create chunks (with code block extraction and breadcrumb context)
			chunks = create_chunks(
				content,
				result.ingestion_id,
				filename=file_path.name,
				max_tokens_per_chunk=self.max_tokens_per_chunk
			)
			result.content_chunks = chunks

			# Create comprehensive summary chunk
			summary_chunk = create_comprehensive_summary(
				file_path, metadata, chunks, doc_format
			)
			if summary_chunk:
				summary_chunk.chunk_id = f"{result.ingestion_id}_comprehensive_summary"
				summary_chunk.chunk_index = len(chunks)
				result.content_chunks.append(summary_chunk)

			# Mark complete
			result.mark_complete()

			# Log comprehensive feature extraction
			features_summary = (
				f"✅ Ingested {file_path.name}: {len(chunks)} chunks, {result.total_tokens} tokens"
			)
			if metadata:
				features = []
				if metadata.get('tables', 0) > 0:
					features.append(f"{metadata['tables']} tables")
				if metadata.get('images', 0) > 0:
					features.append(f"{metadata['images']} images")
				if metadata.get('code_blocks', 0) > 0:
					features.append(f"{metadata['code_blocks']} code blocks")
				if metadata.get('hyperlinks', 0) > 0:
					features.append(f"{metadata['hyperlinks']} links")
				if features:
					features_summary += f" | Features: {', '.join(features)}"

			logger.info(features_summary)

		except Exception as e:
			logger.error(f"❌ Error ingesting {file_path}: {e}", exc_info=True)
			result.add_error(
				"IngestionError",
				str(e),
				{"file_path": str(file_path), "format": str(result.metadata.format)}
			)
			result.mark_complete()

		return result

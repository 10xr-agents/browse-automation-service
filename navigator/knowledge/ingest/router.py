"""
Unified ingestion routing logic.

Routes ingestion requests to the appropriate ingester based on source type.
Provides a single entry point for all ingestion operations.
"""

import logging
from pathlib import Path

from navigator.knowledge.ingest.documentation import DocumentationIngester
from navigator.knowledge.ingest.video import VideoIngester
from navigator.knowledge.ingest.website import WebsiteCrawler
from navigator.schemas import (
	IngestionResult,
	SourceType,
	detect_source_type,
)

logger = logging.getLogger(__name__)


class IngestionRouter:
	"""
	Routes ingestion requests to appropriate ingesters.
	
	Supports:
	- Technical documentation (Markdown, HTML, PDF)
	- Website documentation (Cursor-style crawling)
	- Video walkthroughs (MP4, WebM, etc.)
	"""
	
	def __init__(
		self,
		max_tokens_per_chunk: int = 2000,
		max_crawl_depth: int = 5,
		max_crawl_pages: int = 100,
		thumbnail_count: int = 5,
	):
		"""
		Initialize ingestion router.
		
		Args:
			max_tokens_per_chunk: Maximum tokens per chunk for documentation
			max_crawl_depth: Maximum depth for website crawling
			max_crawl_pages: Maximum pages to crawl
			thumbnail_count: Number of thumbnails per video
		"""
		# Initialize ingesters
		self.doc_ingester = DocumentationIngester(max_tokens_per_chunk=max_tokens_per_chunk)
		self.website_crawler = WebsiteCrawler(
			max_depth=max_crawl_depth,
			max_pages=max_crawl_pages,
		)
		self.video_ingester = VideoIngester(thumbnail_count=thumbnail_count)
	
	async def ingest(
		self,
		source_url: str,
		source_type: SourceType | None = None,
		options: dict | None = None,
	) -> IngestionResult:
		"""
		Ingest content from a source.
		
		Routes to the appropriate ingester based on source type.
		
		Args:
			source_url: URL or file path of the source
			source_type: Explicit source type (auto-detected if None)
			options: Type-specific options
		
		Returns:
			IngestionResult with ingested content
		"""
		options = options or {}
		
		# Detect source type if not provided
		if source_type is None:
			source_type = detect_source_type(source_url)
			logger.info(f"Auto-detected source type: {source_type} for {source_url}")
		
		# Route to appropriate ingester
		try:
			if source_type == SourceType.TECHNICAL_DOCUMENTATION:
				return await self._ingest_documentation(source_url, options)
			
			elif source_type == SourceType.WEBSITE_DOCUMENTATION:
				return await self._ingest_website(source_url, options)
			
			elif source_type == SourceType.VIDEO_WALKTHROUGH:
				return await self._ingest_video(source_url, options)
			
			else:
				# Create error result
				from uuid import uuid4
				from navigator.schemas import SourceMetadata
				
				result = IngestionResult(
					ingestion_id=str(uuid4()),
					source_type=source_type,
					metadata=SourceMetadata(
						source_type=source_type,
						url=source_url,
					)
				)
				result.add_error(
					"UnsupportedSourceType",
					f"Unsupported source type: {source_type}",
					{"source_url": source_url, "source_type": str(source_type)}
				)
				result.mark_complete()
				return result
		
		except Exception as e:
			logger.error(f"Error ingesting {source_url}: {e}", exc_info=True)
			
			# Create error result
			from uuid import uuid4
			from navigator.schemas import SourceMetadata
			
			result = IngestionResult(
				ingestion_id=str(uuid4()),
				source_type=source_type,
				metadata=SourceMetadata(
					source_type=source_type,
					url=source_url,
				)
			)
			result.add_error("IngestionError", str(e), {"source_url": source_url})
			result.mark_complete()
			return result
	
	async def _ingest_documentation(self, source_url: str, options: dict) -> IngestionResult:
		"""Ingest technical documentation."""
		logger.info(f"Ingesting documentation: {source_url}")
		
		# Documentation ingestion is synchronous, so we wrap it
		return self.doc_ingester.ingest_file(source_url)
	
	async def _ingest_website(self, source_url: str, options: dict) -> IngestionResult:
		"""Ingest website documentation."""
		logger.info(f"Crawling website: {source_url}")
		
		# Override crawler options if provided
		max_depth = options.get('max_depth', self.website_crawler.max_depth)
		max_pages = options.get('max_pages', self.website_crawler.max_pages)
		
		# Create crawler with custom options
		crawler = WebsiteCrawler(
			max_depth=max_depth,
			max_pages=max_pages,
			rate_limit=options.get('rate_limit', 0.1),
		)
		
		return await crawler.crawl_website(source_url)
	
	async def _ingest_video(self, source_url: str, options: dict) -> IngestionResult:
		"""Ingest video walkthrough."""
		logger.info(f"Ingesting video: {source_url}")
		
		# Video ingestion is synchronous, so we wrap it
		return self.video_ingester.ingest_video(source_url)


# Singleton instance
_router: IngestionRouter | None = None


def get_ingestion_router() -> IngestionRouter:
	"""Get singleton ingestion router instance."""
	global _router
	if _router is None:
		_router = IngestionRouter()
	return _router

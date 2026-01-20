"""
Unified ingestion routing logic.

Routes ingestion requests to the appropriate ingester based on source type.
Provides a single entry point for all ingestion operations.
"""

import logging

from navigator.knowledge.ingest.documentation import DocumentationIngester
from navigator.knowledge.ingest.documentation_crawler import DocumentationCrawler
from navigator.knowledge.ingest.video import VideoIngester
from navigator.knowledge.ingest.website import WebsiteCrawler
from navigator.schemas import (
	IngestionResult,
	SourceType,
	detect_source_type,
)

logger = logging.getLogger(__name__)


def map_source_type_to_domain(source_type: str | SourceType) -> SourceType:
	"""
	Map REST API source type values to domain SourceType enum values.
	
	REST API uses: 'website', 'documentation', 'video'
	Domain uses: 'website_documentation', 'technical_documentation', 'video_walkthrough'
	
	Args:
		source_type: Source type from REST API (string) or domain (enum)
	
	Returns:
		Domain SourceType enum value
	
	Raises:
		ValueError: If source type is not recognized
	"""
	# If already a domain enum, return as-is
	if isinstance(source_type, SourceType):
		return source_type

	# Convert string to lowercase for case-insensitive matching
	source_str = str(source_type).lower()

	# Map REST API values to domain values
	mapping = {
		# REST API values (from collections.py)
		'website': SourceType.WEBSITE_DOCUMENTATION,
		'documentation': SourceType.TECHNICAL_DOCUMENTATION,
		'video': SourceType.VIDEO_WALKTHROUGH,
		# Also accept domain values directly (from domain.py)
		'website_documentation': SourceType.WEBSITE_DOCUMENTATION,
		'technical_documentation': SourceType.TECHNICAL_DOCUMENTATION,
		'video_walkthrough': SourceType.VIDEO_WALKTHROUGH,
	}

	if source_str in mapping:
		return mapping[source_str]

	# Fallback: raise error for unknown types
	raise ValueError(
		f"Unknown source type: '{source_type}'. "
		f"Supported values: 'website', 'documentation', 'video'"
	)


class IngestionRouter:
	"""
	Routes ingestion requests to appropriate ingesters.
	
	Supports:
	- Technical documentation (Markdown, HTML, PDF)
	- Website documentation (Browser-Use crawling)
	- Video walkthroughs (MP4, WebM, etc.)
	"""

	def __init__(
		self,
		max_tokens_per_chunk: int = 2000,
		max_crawl_depth: int = 5,
		max_crawl_pages: int = 100,
		thumbnail_count: int = 5,
		use_cloud_browser: bool = False,
		use_crawl4ai: bool = True,  # Use Crawl4AI for documentation sites
	):
		"""
		Initialize ingestion router.
		
		Args:
			max_tokens_per_chunk: Maximum tokens per chunk for documentation
			max_crawl_depth: Maximum depth for website crawling
			max_crawl_pages: Maximum pages to crawl
			thumbnail_count: Number of thumbnails per video
			use_cloud_browser: Use Browser-Use cloud browsers for better bot detection bypass
			use_crawl4ai: Use Crawl4AI for documentation site crawling (Firecrawl-like)
		"""
		# Initialize ingesters
		self.doc_ingester = DocumentationIngester(max_tokens_per_chunk=max_tokens_per_chunk)
		self.website_crawler = WebsiteCrawler(
			max_depth=max_crawl_depth,
			max_pages=max_crawl_pages,
			use_cloud=use_cloud_browser,
		)
		self.docs_crawler = DocumentationCrawler(
			max_pages=max_crawl_pages,
			max_depth=max_crawl_depth,
			crawl_strategy="bfs",  # Breadth-first for documentation
			rate_limit=0.5,
		)
		self.video_ingester = VideoIngester(thumbnail_count=thumbnail_count)
		self.use_crawl4ai = use_crawl4ai

	async def ingest(
		self,
		source_url: str,
		source_type: SourceType | str | None = None,
		options: dict | None = None,
	) -> IngestionResult:
		"""
		Ingest content from a source.
		
		Routes to the appropriate ingester based on source type.
		Supports both URL-based and file-based (file://) sources.
		
		Args:
			source_url: URL or file path of the source
				- HTTP(S) URL: https://example.com
				- File path: file:///path/to/file.pdf
			source_type: Explicit source type (auto-detected if None)
				Accepts REST API values: 'website', 'documentation', 'video', 'file'
				Or domain enum values: SourceType.WEBSITE_DOCUMENTATION, etc.
			options: Type-specific options
		
		Returns:
			IngestionResult with ingested content
		"""
		options = options or {}

		# Handle file:// URLs from S3 downloads
		is_file_path = source_url.startswith('file://')
		if is_file_path:
			# Extract local file path
			local_path = source_url.replace('file://', '')
			logger.info(f"Processing local file: {local_path}")

			# Auto-detect type based on file extension if needed
			if source_type is None or source_type == 'file':
				from pathlib import Path
				ext = Path(local_path).suffix.lower()

				# Map file extensions to source types
				if ext in ['.pdf', '.md', '.txt', '.html', '.rst', '.docx', '.doc']:
					source_type = SourceType.TECHNICAL_DOCUMENTATION
				elif ext in ['.mp4', '.webm', '.mov', '.avi', '.mkv']:
					source_type = SourceType.VIDEO_WALKTHROUGH
				else:
					# Default to documentation
					source_type = SourceType.TECHNICAL_DOCUMENTATION

				logger.info(f"Auto-detected source type from file extension: {source_type}")

		# Detect source type if not provided
		if source_type is None:
			source_type = detect_source_type(source_url)
			logger.info(f"Auto-detected source type: {source_type} for {source_url}")
		else:
			# Map REST API values to domain enum (if string)
			if isinstance(source_type, str) and source_type != 'file':
				try:
					source_type = map_source_type_to_domain(source_type)
					logger.info(f"Mapped source type: {source_type} for {source_url}")
				except ValueError as e:
					# Create error result for invalid source type
					from uuid import uuid4

					from navigator.schemas import SourceMetadata

					logger.error(f"Invalid source type: {e}")
					result = IngestionResult(
						ingestion_id=str(uuid4()),
						source_type=SourceType.WEBSITE_DOCUMENTATION,  # Default fallback
						metadata=SourceMetadata(
							source_type=SourceType.WEBSITE_DOCUMENTATION,
							url=source_url,
						)
					)
					result.add_error(
						"InvalidSourceType",
						str(e),
						{"source_url": source_url, "provided_source_type": str(source_type)}
					)
					result.mark_complete()
					return result

		# Route to appropriate ingester
		try:
			if source_type == SourceType.TECHNICAL_DOCUMENTATION:
				return await self._ingest_documentation(source_url, options)

			elif source_type == SourceType.WEBSITE_DOCUMENTATION:
				# Use Crawl4AI for documentation sites if enabled and no credentials (public docs)
				if self.use_crawl4ai and not options.get('credentials'):
					logger.info("🌐 Using Crawl4AI for public documentation crawling")
					return await self._ingest_documentation_site(source_url, options)
				else:
					# Use Browser-Use crawler for authenticated sites or when Crawl4AI disabled
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

		# Handle file:// URLs
		if source_url.startswith('file://'):
			file_path = source_url.replace('file://', '')
		else:
			file_path = source_url

		# Documentation ingestion is synchronous, so we wrap it
		return self.doc_ingester.ingest_file(file_path)

	async def _ingest_documentation_site(self, source_url: str, options: dict) -> IngestionResult:
		"""Ingest public documentation site using Crawl4AI (Firecrawl-like)."""
		logger.info(f"🌐 Crawling documentation site with Crawl4AI: {source_url}")

		# Override crawler options if provided
		max_depth = options.get('max_depth', self.docs_crawler.max_depth)
		max_pages = options.get('max_pages', self.docs_crawler.max_pages)
		crawl_strategy = options.get('crawl_strategy', 'bfs')
		rate_limit = options.get('rate_limit', 0.5)
		use_llm_extraction = options.get('use_llm_extraction', False)

		# Create crawler with custom options
		crawler = DocumentationCrawler(
			max_pages=max_pages,
			max_depth=max_depth,
			crawl_strategy=crawl_strategy,
			rate_limit=rate_limit,
			use_llm_extraction=use_llm_extraction,
		)

		return await crawler.crawl_documentation(source_url)

	async def _ingest_website(self, source_url: str, options: dict) -> IngestionResult:
		"""Ingest website documentation using Browser-Use (for authenticated sites)."""
		logger.info(f"Crawling website with Browser-Use: {source_url}")

		# Override crawler options if provided
		max_depth = options.get('max_depth', self.website_crawler.max_depth)
		max_pages = options.get('max_pages', self.website_crawler.max_pages)

		# Extract credentials if provided
		credentials = None
		if options.get('credentials'):
			credentials = options['credentials']
			logger.info("🔐 Credentials provided - will attempt login if needed")

		# Create crawler with custom options
		crawler = WebsiteCrawler(
			max_depth=max_depth,
			max_pages=max_pages,
			use_cloud=options.get('use_cloud_browser', self.website_crawler.use_cloud),
			rate_limit=options.get('rate_limit', 0.1),
			credentials=credentials,
		)

		return await crawler.crawl_website(source_url)

	async def _ingest_video(self, source_url: str, options: dict) -> IngestionResult:
		"""Ingest video walkthrough."""
		logger.info(f"Ingesting video: {source_url}")

		# Handle file:// URLs
		if source_url.startswith('file://'):
			file_path = source_url.replace('file://', '')
		else:
			file_path = source_url

		# Update video ingester with options
		extract_thumbnails = options.get('extract_thumbnails', True)
		self.video_ingester.thumbnail_count = 5 if extract_thumbnails else 0
		self.video_ingester.enable_transcription = options.get('enable_transcription', True)
		self.video_ingester.enable_frame_analysis = options.get('enable_frame_analysis', True)
		self.video_ingester.enable_action_extraction = options.get('enable_action_extraction', True)
		self.video_ingester.enable_subtitle_extraction = options.get('enable_subtitle_extraction', True)
		self.video_ingester.enable_scene_detection = options.get('enable_scene_detection', True)
		self.video_ingester.enable_ocr = options.get('enable_ocr', True)
		# Adaptive frame sampling
		self.video_ingester.frame_interval_seconds = options.get('frame_interval_seconds', 2.0)
		self.video_ingester.min_frame_interval_seconds = options.get('min_frame_interval_seconds', 0.5)

		# Video ingestion is now async
		return await self.video_ingester.ingest_video(file_path)


# Singleton instance
_router: IngestionRouter | None = None


def get_ingestion_router() -> IngestionRouter:
	"""Get singleton ingestion router instance."""
	global _router
	if _router is None:
		_router = IngestionRouter()
	return _router

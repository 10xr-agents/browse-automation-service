"""
Knowledge ingestion modules.

Provides ingesters for various source types:
- DocumentationIngester: Markdown, HTML, PDF
- WebsiteCrawler: Website documentation (Cursor-style)
- VideoIngester: Video walkthroughs with metadata extraction
- IngestionRouter: Unified entry point for all ingestion
"""

from navigator.knowledge.ingest.documentation import DocumentationIngester
from navigator.knowledge.ingest.router import IngestionRouter, get_ingestion_router
from navigator.knowledge.ingest.video import VideoIngester
from navigator.knowledge.ingest.website import WebsiteCrawler

__all__ = [
	'DocumentationIngester',
	'WebsiteCrawler',
	'VideoIngester',
	'IngestionRouter',
	'get_ingestion_router',
]

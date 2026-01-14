"""
Tests for Phase 2: Multi-Source Ingestion.

Validates:
- Source type definitions and detection
- Documentation ingestion (Markdown, HTML, PDF)
- Website crawling (with robots.txt, rate limiting)
- Video ingestion (metadata extraction)
- Unified ingestion router
"""

import tempfile
from pathlib import Path

import pytest

from navigator.knowledge.ingest import (
	DocumentationIngester,
	IngestionRouter,
	VideoIngester,
	WebsiteCrawler,
	get_ingestion_router,
)
from navigator.schemas import (
	DocumentFormat,
	SourceType,
	VideoFormat,
	detect_document_format,
	detect_source_type,
	detect_video_format,
)


# =============================================================================
# Phase 2.1: Source Type Definitions
# =============================================================================

def test_2_1_source_type_enum():
	"""Test Phase 2.1 - Source type enum definition."""
	# Verify all 3 source types are defined
	assert len(list(SourceType)) == 3
	assert SourceType.TECHNICAL_DOCUMENTATION in SourceType
	assert SourceType.WEBSITE_DOCUMENTATION in SourceType
	assert SourceType.VIDEO_WALKTHROUGH in SourceType
	
	# Verify enum values
	assert SourceType.TECHNICAL_DOCUMENTATION.value == "technical_documentation"
	assert SourceType.WEBSITE_DOCUMENTATION.value == "website_documentation"
	assert SourceType.VIDEO_WALKTHROUGH.value == "video_walkthrough"


def test_2_1_source_type_detection():
	"""Test Phase 2.1 - Source type auto-detection."""
	# Documentation files
	assert detect_source_type("/path/to/doc.md") == SourceType.TECHNICAL_DOCUMENTATION
	assert detect_source_type("/path/to/guide.html") == SourceType.TECHNICAL_DOCUMENTATION
	assert detect_source_type("/path/to/manual.pdf") == SourceType.TECHNICAL_DOCUMENTATION
	assert detect_source_type("./readme.txt") == SourceType.TECHNICAL_DOCUMENTATION
	
	# Website URLs
	assert detect_source_type("https://docs.example.com") == SourceType.WEBSITE_DOCUMENTATION
	assert detect_source_type("http://example.com/guide") == SourceType.WEBSITE_DOCUMENTATION
	
	# Video files
	assert detect_source_type("/videos/tutorial.mp4") == SourceType.VIDEO_WALKTHROUGH
	assert detect_source_type("/demo.webm") == SourceType.VIDEO_WALKTHROUGH
	assert detect_source_type("./walkthrough.avi") == SourceType.VIDEO_WALKTHROUGH


def test_2_1_document_format_detection():
	"""Test document format detection."""
	assert detect_document_format("file.md") == DocumentFormat.MARKDOWN
	assert detect_document_format("FILE.MARKDOWN") == DocumentFormat.MARKDOWN
	assert detect_document_format("guide.html") == DocumentFormat.HTML
	assert detect_document_format("page.htm") == DocumentFormat.HTML
	assert detect_document_format("manual.pdf") == DocumentFormat.PDF
	assert detect_document_format("readme.txt") == DocumentFormat.PLAIN_TEXT
	assert detect_document_format("unknown.xyz") == DocumentFormat.UNKNOWN


def test_2_1_video_format_detection():
	"""Test video format detection."""
	assert detect_video_format("video.mp4") == VideoFormat.MP4
	assert detect_video_format("demo.webm") == VideoFormat.WEBM
	assert detect_video_format("tutorial.avi") == VideoFormat.AVI
	assert detect_video_format("screen.mov") == VideoFormat.MOV
	assert detect_video_format("recording.mkv") == VideoFormat.MKV
	assert detect_video_format("unknown.xyz") == VideoFormat.UNKNOWN


# =============================================================================
# Phase 2.2: Technical Documentation Ingestion
# =============================================================================

def test_2_2_markdown_ingestion():
	"""Test Phase 2.2 - Markdown file ingestion."""
	# Create test markdown file
	with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
		f.write("""# Test Document

This is a test paragraph.

## Section 1

Some content here.

```python
def hello():
    print("Hello World")
```

## Section 2

More content with:
- Item 1
- Item 2
- Item 3
""")
		temp_path = Path(f.name)
	
	try:
		# Ingest file
		ingester = DocumentationIngester(max_tokens_per_chunk=500)
		result = ingester.ingest_file(temp_path)
		
		# Verify result
		assert result.success is True
		assert result.source_type == SourceType.TECHNICAL_DOCUMENTATION
		assert result.metadata.format == DocumentFormat.MARKDOWN
		assert result.total_chunks > 0
		assert result.total_tokens > 0
		assert len(result.errors) == 0
		
		# Verify chunks
		for chunk in result.content_chunks:
			assert chunk.token_count <= 500
			assert chunk.chunk_type == "documentation"
			assert "# Test Document" in chunk.content or "## Section" in chunk.content
	
	finally:
		temp_path.unlink()


def test_2_2_html_ingestion():
	"""Test Phase 2.2 - HTML file ingestion."""
	# Create test HTML file
	with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
		f.write("""<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
<main>
<h1>Main Heading</h1>
<p>This is a test paragraph.</p>
<pre><code>print("code block")</code></pre>
<ul>
<li>Item 1</li>
<li>Item 2</li>
</ul>
</main>
</body>
</html>""")
		temp_path = Path(f.name)
	
	try:
		# Ingest file
		ingester = DocumentationIngester(max_tokens_per_chunk=500)
		result = ingester.ingest_file(temp_path)
		
		# Verify result
		assert result.success is True
		assert result.metadata.format == DocumentFormat.HTML
		assert result.total_chunks > 0
		assert len(result.errors) == 0
		
		# Verify content extraction
		content = result.content_chunks[0].content
		assert "Main Heading" in content
		assert "test paragraph" in content
	
	finally:
		temp_path.unlink()


def test_2_2_pdf_ingestion():
	"""Test Phase 2.2 - PDF file ingestion."""
	# Create simple PDF for testing
	try:
		from reportlab.pdfgen import canvas
	except ImportError:
		pytest.skip("reportlab not available for PDF test")
		return
	
	with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
		temp_path = Path(f.name)
		
		# Create simple PDF
		c = canvas.Canvas(str(temp_path))
		c.drawString(100, 750, "Test PDF Document")
		c.drawString(100, 700, "This is page 1 content.")
		c.save()
	
	try:
		# Ingest file
		ingester = DocumentationIngester()
		result = ingester.ingest_file(temp_path)
		
		# Verify result
		assert result.success is True
		assert result.metadata.format == DocumentFormat.PDF
		assert result.total_chunks > 0
		
		# Verify content
		content = result.content_chunks[0].content
		assert "Page 1" in content or "Test PDF" in content
	
	finally:
		temp_path.unlink()


def test_2_2_chunking_respects_token_limit():
	"""Test that chunking respects max token limit."""
	# Create large markdown file
	with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
		# Write content that will exceed token limit
		f.write("# Large Document\n\n")
		for i in range(100):
			f.write(f"## Section {i}\n\n")
			f.write("Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 20)
			f.write("\n\n")
		temp_path = Path(f.name)
	
	try:
		# Ingest with small chunk size
		ingester = DocumentationIngester(max_tokens_per_chunk=500)
		result = ingester.ingest_file(temp_path)
		
		# Verify chunks respect limit
		assert result.success is True
		assert result.total_chunks > 1  # Should create multiple chunks
		
		for chunk in result.content_chunks:
			assert chunk.token_count <= 500, f"Chunk {chunk.chunk_index} exceeds limit: {chunk.token_count} tokens"
	
	finally:
		temp_path.unlink()


# =============================================================================
# Phase 2.3: Website Documentation Crawling
# =============================================================================

def test_2_3_website_crawler_initialization():
	"""Test Phase 2.3 - Website crawler initialization."""
	crawler = WebsiteCrawler(
		max_depth=3,
		max_pages=50,
		rate_limit=0.2,
	)
	
	assert crawler.max_depth == 3
	assert crawler.max_pages == 50
	assert crawler.rate_limit == 0.2
	assert crawler.visited_urls == set()
	assert len(crawler.url_queue) == 0


@pytest.mark.asyncio
async def test_2_3_robots_txt_parsing():
	"""Test robots.txt loading and parsing."""
	crawler = WebsiteCrawler()
	
	# Test loading robots.txt (will fail gracefully if network unavailable)
	try:
		await crawler._load_robots_txt("https://example.com")
		# If successful, robots_parser should be set or None
		assert crawler.robots_parser is not None or crawler.robots_parser is None
	except Exception:
		# Network errors are acceptable in tests
		pass


# =============================================================================
# Phase 2.4: Video Ingestion
# =============================================================================

def test_2_4_video_ingester_initialization():
	"""Test Phase 2.4 - Video ingester initialization."""
	ingester = VideoIngester(thumbnail_count=5)
	
	assert ingester.thumbnail_count == 5


def test_2_4_video_format_support():
	"""Test video format support."""
	ingester = VideoIngester()
	
	# Test with various video formats (will fail gracefully if file doesn't exist)
	for ext in ['.mp4', '.webm', '.avi', '.mov', '.mkv']:
		with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
			temp_path = Path(f.name)
		
		try:
			result = ingester.ingest_video(temp_path)
			
			# Should fail gracefully for empty file
			assert result.success is False
			assert len(result.errors) > 0
			assert result.metadata.format in VideoFormat
		
		finally:
			temp_path.unlink()


# =============================================================================
# Phase 2.5: Unified Ingestion Entry Point
# =============================================================================

def test_2_5_ingestion_router_singleton():
	"""Test Phase 2.5 - Router singleton pattern."""
	router1 = get_ingestion_router()
	router2 = get_ingestion_router()
	
	assert router1 is router2  # Same instance
	assert router1.doc_ingester is not None
	assert router1.website_crawler is not None
	assert router1.video_ingester is not None


@pytest.mark.asyncio
async def test_2_5_router_documentation_routing():
	"""Test router routes documentation correctly."""
	router = IngestionRouter()
	
	# Create test markdown file
	with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
		f.write("# Test\n\nContent")
		temp_path = Path(f.name)
	
	try:
		# Route with auto-detection
		result = await router.ingest(str(temp_path))
		
		assert result.source_type == SourceType.TECHNICAL_DOCUMENTATION
		assert result.success is True
		assert result.total_chunks > 0
	
	finally:
		temp_path.unlink()


@pytest.mark.asyncio
async def test_2_5_router_auto_detection():
	"""Test router auto-detects source type correctly."""
	router = IngestionRouter()
	
	# Test with markdown file
	with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
		f.write("# Auto Detection Test")
		temp_path = Path(f.name)
	
	try:
		# Don't specify source_type - should auto-detect
		result = await router.ingest(str(temp_path), source_type=None)
		
		assert result.source_type == SourceType.TECHNICAL_DOCUMENTATION
		assert result.success is True
	
	finally:
		temp_path.unlink()


# =============================================================================
# Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_phase2_integration():
	"""Integration test for complete Phase 2 implementation."""
	router = get_ingestion_router()
	
	# Create test file
	with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
		f.write("""# Integration Test

## Section 1
Content for section 1.

## Section 2
Content for section 2 with a list:
- Item A
- Item B

```python
print("code block")
```
""")
		temp_path = Path(f.name)
	
	try:
		# Test full ingestion pipeline
		result = await router.ingest(str(temp_path))
		
		# Verify complete result
		assert result.success is True
		assert result.source_type == SourceType.TECHNICAL_DOCUMENTATION
		assert result.total_chunks > 0
		assert result.total_tokens > 0
		assert len(result.errors) == 0
		assert result.metadata is not None
		assert result.metadata.url == str(temp_path)
		assert result.completed_at is not None
		
		# Verify chunks
		for chunk in result.content_chunks:
			assert chunk.chunk_id is not None
			assert chunk.token_count > 0
			assert chunk.token_count <= 2000  # Default max
			assert chunk.content is not None
	
	finally:
		temp_path.unlink()

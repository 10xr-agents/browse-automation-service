# Knowledge Extraction - Public Documentation Crawling Guide

**Version**: 2.3.0  
**Last Updated**: January 18, 2026  
**Status**: Production Ready

This document provides comprehensive details on public documentation crawling for knowledge extraction using Crawl4AI.

**See Also**:
- [General Architecture Guide](./KNOWLEDGE_ARCHITECTURE_GENERAL.md) - S3 ingestion, schema design, workflow orchestration
- [Text File Processing Guide](./KNOWLEDGE_EXTRACTION_TEXT_FILES.md) - PDF, Markdown, HTML, DOCX file processing details
- [Video Extraction Guide](./KNOWLEDGE_EXTRACTION_VIDEO.md) - Video file processing details
- [Authenticated Portal Guide](./KNOWLEDGE_EXTRACTION_AUTHENTICATED_PORTAL.md) - Authenticated portal exploration using Browser-Use

---

## Table of Contents

1. [Overview](#overview)
2. [Crawl4AI for Public Documentation](#crawl4ai-for-public-documentation)
3. [Processing Pipeline](#processing-pipeline)
4. [Implementation Details](#implementation-details)
5. [API Usage](#api-usage)
6. [Configuration](#configuration)

---

## Overview

Public documentation crawling extracts knowledge from public documentation websites that don't require authentication. All crawled content produces structured content chunks that flow through the unified knowledge extraction pipeline (see [General Architecture Guide](./KNOWLEDGE_ARCHITECTURE_GENERAL.md)).

### Key Features

- ✅ **Firecrawl-like Functionality**: Comprehensive content extraction using Crawl4AI
- ✅ **Clean Markdown Extraction**: LLM-ready content extraction
- ✅ **Comprehensive Content Extraction**: Tables, code blocks, structure, images, links
- ✅ **Deep Crawling**: BFS/DFS strategies with configurable depth
- ✅ **Documentation-Focused Filtering**: Prioritizes docs pages (`/docs/`, `/api/`, `/guide/`, etc.)
- ✅ **Business Function Extraction**: LLM analysis from crawled content
- ✅ **Operational Workflow Extraction**: Step-by-step procedures from documentation sites
- ✅ **Rate Limiting**: Respects server resources

### When to Use

Use Crawl4AI for public documentation crawling when:
- ✅ Documentation is publicly accessible (no login required)
- ✅ You want to crawl API documentation, user guides, technical docs
- ✅ URLs are public and don't require authentication
- ✅ You need clean Markdown output for LLM processing

**For authenticated portals that require login**, see [Authenticated Portal Guide](./KNOWLEDGE_EXTRACTION_AUTHENTICATED_PORTAL.md).

---

## Crawl4AI for Public Documentation

### Overview

Crawl4AI is used for public documentation websites that don't require authentication. It provides Firecrawl-like comprehensive content extraction with clean Markdown output.

### Use Case

**Public Documentation Sites**:
- API documentation (e.g., `https://docs.example.com/api`)
- User guides (e.g., `https://example.com/guide`)
- Technical documentation (e.g., `https://docs.example.com/technical`)
- Public knowledge bases
- Developer documentation
- Open-source project docs

### Features

- ✅ **Firecrawl-like Functionality**: Comprehensive content extraction
- ✅ **Clean Markdown Extraction**: LLM-ready content extraction
- ✅ **Comprehensive Content Extraction**: Tables, code blocks, structure, images, links
- ✅ **Deep Crawling**: BFS/DFS strategies with configurable depth
- ✅ **Documentation-Focused Filtering**: Prioritizes docs pages (`/docs/`, `/api/`, `/guide/`, etc.)
- ✅ **Business Function Extraction**: LLM analysis from crawled content
- ✅ **Operational Workflow Extraction**: Step-by-step procedures from documentation sites
- ✅ **Rate Limiting**: Respects server resources

### Implementation

**Location**: `navigator/knowledge/ingest/documentation_crawler.py`

**Library**: `crawl4ai`

**Process**:
1. **Crawl Strategy**: Configure BFS (breadth-first) or DFS (depth-first) crawling
2. **URL Filtering**: Filter links to prioritize documentation pages
3. **Content Extraction**: Extract HTML content from each page
4. **Markdown Conversion**: Convert HTML to clean Markdown using Crawl4AI's converter
5. **Structure Preservation**: Preserve tables, code blocks, images, links
6. **Chunking**: Split content into manageable chunks with metadata
7. **Storage**: Store ingestion results in MongoDB

**Content Extraction**:
- Tables with structured data (headers, rows)
- Code blocks with syntax highlighting
- Images with alt text and source URLs
- Hyperlinks with text and destinations
- Headings and hierarchical structure
- Lists (ordered and unordered)
- Metadata (page titles, descriptions)

### Configuration

**Crawl Options**:
```json
{
  "max_depth": 3,           // Maximum crawl depth
  "crawl_strategy": "bfs",  // "bfs" or "dfs"
  "include_paths": ["/docs/", "/api/", "/guide/"],  // Paths to include
  "exclude_paths": ["/blog/", "/news/"],  // Paths to exclude
  "rate_limit": 1.0  // Seconds between requests
}
```

**Documentation-Focused Filtering**:
- Prioritizes URLs containing: `/docs/`, `/api/`, `/guide/`, `/reference/`, `/tutorials/`
- Excludes common non-documentation paths: `/blog/`, `/news/`, `/about/`, `/contact/`

---

## Processing Pipeline

### Phase 1: Public Documentation Crawling & Ingestion

**Input**: Public documentation URL provided in ingestion request (no credentials)

**Steps**:

1. **Strategy Selection**: Detect public documentation site (no credentials)
2. **Crawl Configuration**: Set up BFS/DFS crawling with depth limits
3. **URL Filtering**: Filter links to prioritize documentation pages
4. **Crawl Execution**: Crawl pages using Crawl4AI
5. **Content Extraction**: Extract HTML content from each page
6. **Markdown Conversion**: Convert HTML to clean Markdown
7. **Feature Extraction**: Extract tables, code blocks, structure, images, links
8. **Chunking**: Split content into manageable chunks
9. **Metadata Extraction**: Extract page metadata (titles, descriptions)
10. **Storage**: Store ingestion results in MongoDB

**Output**: Structured content chunks with metadata (`documentation` chunks)

### Phase 2: Knowledge Extraction

All extraction activities support crawled public documentation content:

- **Screen Extraction**: Identify application states from web page structure
- **Task Extraction**: Parse workflows and procedures from documentation pages
- **Action Extraction**: Extract UI interactions from forms and interactive elements
- **Transition Extraction**: Identify navigation patterns from links
- **Business Function Extraction**: LLM analysis to identify business functions
- **Operational Workflow Extraction**: LLM analysis to extract step-by-step workflows

**Supported Source Types**:
- ✅ **Crawl4AI**: Crawled public documentation pages (`documentation` chunks)

**AI Providers**:
- **OpenAI GPT-4o**: Primary choice for business function and workflow extraction
- **Google Gemini 1.5 Pro**: Fallback option for business function and workflow extraction

### Feature Completeness

**Public Documentation Crawling**:
- ✅ All documentation pages are crawled (Crawl4AI)
- ✅ Clean Markdown content extracted (LLM-ready)
- ✅ All tables, code blocks, structure preserved
- ✅ Documentation-focused link filtering
- ✅ Business functions extracted from crawled content
- ✅ Operational workflows extracted from documentation sites
- ✅ Comprehensive summary aggregates all pages

---

## Implementation Details

### Crawl4AI Implementation

**Location**: `navigator/knowledge/ingest/documentation_crawler.py`

**Library**: `crawl4ai`

**Key Classes**:
- `DocumentationCrawler` - Handles Crawl4AI-based web crawling

**Crawling Process**:
1. Initialize Crawl4AI crawler with configuration
2. Set up BFS/DFS crawling strategy
3. Configure URL filtering (documentation-focused)
4. Execute crawl with rate limiting
5. Extract HTML content from each page
6. Convert HTML to Markdown using Crawl4AI's converter
7. Preserve structure (tables, code blocks, images, links)
8. Generate content chunks with metadata
9. Store ingestion results in MongoDB

**Configuration**:
- **Max Depth**: Configurable crawl depth (default: 3)
- **Crawl Strategy**: BFS or DFS (default: BFS)
- **Rate Limiting**: Configurable delay between requests (default: 1.0 seconds)
- **URL Filtering**: Prioritize documentation paths, exclude non-docs

---

## API Usage

### Public Documentation Crawling (Crawl4AI)

```bash
curl -X POST http://localhost:8000/api/knowledge/ingest/start \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "website",
    "source_url": "https://docs.example.com/api",
    "source_name": "Example API Documentation",
    "options": {
      "max_depth": 3,
      "crawl_strategy": "bfs",
      "include_paths": ["/docs/", "/api/", "/guide/"],
      "exclude_paths": ["/blog/", "/news/"],
      "rate_limit": 1.0
    }
  }'
```

**Key Points**:
- ✅ No `credentials` field (public documentation)
- ✅ `source_type` should be `"website"`
- ✅ Crawl4AI is automatically selected when no credentials are provided

### Response Format

**Success Response**:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "workflow_id": "workflow-123",
  "status": "queued",
  "estimated_duration_seconds": 600,
  "message": "Web crawling started"
}
```

---

## Configuration

### Crawl Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `max_depth` | integer | 3 | Maximum crawl depth from seed URL |
| `crawl_strategy` | string | `"bfs"` | `"bfs"` (breadth-first) or `"dfs"` (depth-first) |
| `include_paths` | array | `[]` | Path patterns to prioritize (e.g., `["/docs/", "/api/"]`) |
| `exclude_paths` | array | `[]` | Path patterns to exclude (e.g., `["/blog/", "/news/"]`) |
| `rate_limit` | float | 1.0 | Seconds between requests |

### Documentation-Focused Filtering

**Included Paths** (by default):
- `/docs/` - Documentation pages
- `/api/` - API documentation
- `/guide/` - User guides
- `/reference/` - Reference documentation
- `/tutorials/` - Tutorial pages

**Excluded Paths** (by default):
- `/blog/` - Blog posts
- `/news/` - News articles
- `/about/` - About pages
- `/contact/` - Contact pages

---

## Multi-Source Integration

Public documentation crawling supports aggregation with other sources:

### Supported Combinations

- **Multiple URLs**: Combine multiple public documentation URLs in single extraction
- **Public Docs + Text Files**: Combine public docs with text files
- **Public Docs + Video**: Combine public docs with video files
- **Mixed Sources**: Combine all source types in single extraction

### Multi-Source Aggregation

**Key Feature**: All extraction activities support `ingestion_ids[]` parameter:

```python
ExtractScreensInput(
    ingestion_id=primary_id,  # For backward compatibility
    ingestion_ids=[crawl4ai_id, doc_id, video_id]  # All sources
)
```

**Benefits**:
- Merges knowledge from all sources
- Deduplicates entities (screens, tasks, actions) across sources
- Creates unified knowledge base
- Single workflow execution for all sources

### Knowledge Merging & Deduplication

**Automatic Deduplication**:
- Screens: By URL pattern and state signature
- Tasks: By name and step sequence
- Actions: By action type and target
- Transitions: By source/target screen pairs

**Cross-Source Merging**:
- Same screen found in Crawl4AI + other sources → Single unified screen
- Same task described in multiple sources → Enriched with all details
- Content from all sources → Combined knowledge base

---

## Summary

Public documentation crawling provides:

1. **Crawl4AI Integration**: Firecrawl-like functionality for public documentation sites
2. **Comprehensive Content Extraction**: Tables, code blocks, structure, images, links
3. **Clean Markdown Output**: LLM-ready content from HTML
4. **Deep Crawling**: BFS/DFS strategies with configurable depth
5. **Documentation-Focused**: Prioritizes documentation pages
6. **Business Knowledge**: LLM analysis for business functions and operational workflows
7. **Multi-Source Integration**: Aggregation with text files and video processing

All crawled content produces structured content chunks that flow through the unified knowledge extraction pipeline, ensuring consistent knowledge representation.

**For authenticated portals that require login**, see [Authenticated Portal Guide](./KNOWLEDGE_EXTRACTION_AUTHENTICATED_PORTAL.md).

**For general architecture details**, see [General Architecture Guide](./KNOWLEDGE_ARCHITECTURE_GENERAL.md).

**For text file processing details**, see [Text File Processing Guide](./KNOWLEDGE_EXTRACTION_TEXT_FILES.md).

---

**Last Updated**: January 18, 2026  
**Status**: Production Ready ✅  
**Version**: 2.3.0

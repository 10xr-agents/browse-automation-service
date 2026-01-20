# Knowledge Extraction - Text File Processing Guide

**Version**: 2.5.0  
**Last Updated**: January 20, 2026  
**Status**: Production Ready (Enhanced with OCR, Vision, Advanced Tables, pHash Deduplication, Breadcrumb Context, Code Block Protection)

This document provides comprehensive details on text file processing for knowledge extraction, including PDF, Markdown, HTML, DOCX, and plain text files.

**See Also**:
- [General Architecture Guide](./KNOWLEDGE_ARCHITECTURE_GENERAL.md) - S3 ingestion, schema design, workflow orchestration
- [Public Documentation Guide](./KNOWLEDGE_EXTRACTION_PUBLIC_DOCUMENTATION.md) - Public documentation crawling (Crawl4AI)
- [Authenticated Portal Guide](./KNOWLEDGE_EXTRACTION_AUTHENTICATED_PORTAL.md) - Authenticated portal exploration (Browser-Use)
- [Video Extraction Guide](./KNOWLEDGE_EXTRACTION_VIDEO.md) - Video file processing details

---

## Table of Contents

1. [Overview](#overview)
2. [Supported File Types](#supported-file-types)
3. [Content Extraction](#content-extraction)
4. [Processing Pipeline](#processing-pipeline)
5. [Implementation Details](#implementation-details)
6. [API Usage](#api-usage)

---

## Overview

Text file processing extracts knowledge from static documentation files including PDF, Markdown, HTML, DOCX, and plain text formats. All text files produce structured content chunks that flow through the unified knowledge extraction pipeline (see [General Architecture Guide](./KNOWLEDGE_ARCHITECTURE_GENERAL.md)).

### Key Features

- ✅ **Multi-Format Support**: PDF, Markdown, HTML, DOCX, Plain Text
- ✅ **Comprehensive Content Extraction**: Tables, code blocks, images, links, structure, metadata
- ✅ **Business Function Extraction**: LLM analysis to identify business functions
- ✅ **Operational Workflow Extraction**: Step-by-step procedures with preconditions/postconditions
- ✅ **Multi-File Processing**: Batch processing of multiple files in single workflow
- ✅ **Structured Outputs**: Clean content chunks ready for knowledge extraction

---

## Supported File Types

| Extension | Content Type | Auto-Detected As | Processing Details |
|-----------|-------------|------------------|------------|
| `.pdf` | `application/pdf` | Documentation | PDF parsing, metadata extraction, table/image detection, text extraction |
| `.md` | `text/markdown` | Documentation | Markdown parsing, frontmatter, tables, code blocks, images, sections |
| `.txt` | `text/plain` | Documentation | Text chunking, section/list detection, structure analysis |
| `.html` | `text/html` | Documentation | HTML parsing, meta tags, tables, images, links, code blocks, structure |
| `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | Documentation | DOCX parsing, document properties, tables, images, hyperlinks, headings |
| `.doc` | `application/msword` | Documentation | DOCX parsing (converted) |

---

## Content Extraction

### Enhanced Content Extraction

All supported file types extract comprehensive content with advanced processing capabilities:

#### Structured Content

- ✅ **Tables**: Advanced extraction with `pdfplumber` for PDFs, preserved as Markdown tables for LLM-native format
- ✅ **Code Blocks**: Syntax preservation for programming languages
- ✅ **Lists**: Ordered and unordered lists with proper hierarchy
- ✅ **Headings**: Hierarchical structure (H1-H6)
- ✅ **Blockquotes**: Quote extraction with attribution
- ✅ **Horizontal Rules**: Section separators

#### Rich Media

- ✅ **Images**: **Vision-Enhanced Captioning** - AI-generated descriptions for diagrams, flowcharts, and screenshots using GPT-4o Vision/Gemini Vision
- ✅ **Image Deduplication**: **Perceptual Hashing (pHash)** - Caches captions for visually identical images (logos/icons) to reduce Vision API costs by 30-50%
- ✅ **Hyperlinks**: Link text and destination URLs
- ✅ **Embedded Content**: Preserved structure for embedded elements

#### Advanced Processing

- ✅ **Hybrid PDF Parsing**: Automatic detection and OCR fallback for scanned documents (Tesseract/Vision LLM)
- ✅ **Table Structure Preservation**: Tables converted to clean Markdown format (`| Header | ... |`) for optimal LLM reasoning
- ✅ **Header/Footer Cleaning**: Automatic removal of page artifacts (headers, footers, page numbers) to maintain semantic continuity
- ✅ **Semantic Chunking**: Recursive splitting by Header > Paragraph > Sentence (not fixed token limits) to preserve context boundaries
- ✅ **Breadcrumb Context**: Heading hierarchy (H1 > H2 > H3) prepended to chunks for context-aware retrieval
- ✅ **Code Block Protection**: Code blocks extracted before chunking and re-inserted after to preserve syntax validity

#### Metadata

- ✅ **Document Metadata**: Author, title, creation/modification dates
- ✅ **Tags/Categories**: Classification tags and categories
- ✅ **Language Detection**: Automatic language identification
- ✅ **Format-Specific Metadata**: Format-dependent properties (PDF metadata, Markdown frontmatter, HTML meta tags, DOCX properties)

### Enhanced vs Standard Processing

| Feature | Standard (Basic) | **Enhanced (Recommended)** |
| --- | --- | --- |
| **Scanned Docs** | Fails / Garbage Text | **Hybrid OCR:** Auto-detects scanned pages (density check: <50 chars/page), routes to Vision/OCR engine |
| **Images** | Alt Text Only | **AI Captioning:** Vision LLM (GPT-4o/Gemini) generates descriptive text + **pHash deduplication** (30-50% cost reduction) |
| **Tables** | Text Dump | **Structure Preservation:** Uses `pdfplumber` to extract tables, converts to Clean Markdown format |
| **Layout** | Raw Stream | **Header/Footer Removal:** Regex-based cleaning strips page artifacts, maintains sentence continuity |
| **Chunking** | Fixed Token Limit (2000) | **Recursive Semantic:** Splits by Header > Paragraph > Sentence + **Breadcrumb context** (heading hierarchy) + **Code block protection** |

---

## Processing Pipeline

### Phase 1: File Ingestion

**Input**: File uploaded to S3 (via presigned URL) or provided as local path

**Steps**:
1. **File Detection**: Auto-detect format from file extension
2. **Content Parsing**: Format-specific parsing with enhanced processing
   - **PDF**: Hybrid parsing with `pypdf` + OCR/Vision fallback, `pdfplumber` for tables
   - **Markdown**: Uses `markdownify` for Markdown parsing
   - **HTML**: Uses `beautifulsoup4` for HTML parsing
   - **DOCX**: Uses `python-docx` with Vision LLM for image captioning
   - **Text**: Plain text chunking with structure analysis
3. **Pre-Processing (PDF/DOCX)**:
   - **Header/Footer Cleaning**: Regex-based removal of page artifacts (page numbers, headers, footers)
   - **Density Check (PDF)**: Detects scanned pages (<50 chars/page) and routes to OCR/Vision
4. **Feature Extraction**: Extract tables (as Markdown), code blocks, images (with Vision captioning + pHash deduplication), links, structure
5. **Pre-Chunking Processing**:
   - **Code Block Extraction**: Extract code blocks before chunking, replace with placeholders `<<CODE_BLOCK_{uuid}>>`
   - **Image Deduplication**: Calculate perceptual hash (pHash) for images, check cache before Vision API calls
6. **Semantic Chunking**: Recursive splitting by Header > Paragraph > Sentence (preserves context boundaries)
   - **Breadcrumb Context**: Track heading hierarchy (H1 > H2 > H3) and prepend to chunks: `File: {filename} | Section: {breadcrumb}`
   - Chunks preserve structure (headings, lists, tables as atomic units)
   - Only falls back to hard token limits for extremely long paragraphs
   - Metadata is extracted and attached to chunks
7. **Post-Chunking Processing**:
   - **Code Block Re-insertion**: Replace placeholders with original code block content
   - Ensures syntax validity for technical documentation
8. **Metadata Extraction**: Extract document metadata (author, title, dates, tags)
9. **Storage**: Store ingestion results in MongoDB (`knowledge_ingestion_results` collection)

**Output**: Structured content chunks with metadata

### Phase 2: Knowledge Extraction

All extraction activities support text file content:

- **Screen Extraction**: Identify application states from documentation descriptions
- **Task Extraction**: Parse workflows and procedures from documentation
- **Action Extraction**: Extract UI interactions from documentation
- **Transition Extraction**: Identify navigation patterns from documentation
- **Business Function Extraction**: LLM analysis to identify business functions
- **Operational Workflow Extraction**: LLM analysis to extract step-by-step workflows

**Supported Source Types**:
- ✅ **PDF Files**: PDF parsing with metadata extraction
- ✅ **Markdown Files**: Markdown parsing with frontmatter support
- ✅ **HTML Files**: HTML parsing with meta tag extraction
- ✅ **DOCX Files**: DOCX parsing with document properties
- ✅ **Text Files**: Plain text chunking with structure analysis

**AI Providers**:
- **OpenAI GPT-4o**: Primary choice for business function and workflow extraction
- **Google Gemini 1.5 Pro**: Fallback option for business function and workflow extraction

### Feature Completeness

**Text File Processing**:
- ✅ All documentation files in batch are processed
- ✅ All tables are extracted with structured data
- ✅ All code blocks are preserved with syntax
- ✅ All images are captured with metadata
- ✅ All hyperlinks are extracted with text
- ✅ All headings and structure are maintained
- ✅ All metadata is extracted (author, title, dates, tags)
- ✅ Business functions are identified from all content
- ✅ Operational workflows are extracted from all content
- ✅ Comprehensive summary aggregates all features

---

## Implementation Details

### File Processing Location

**Main Module**: `navigator/knowledge/ingest/documentation.py`

**Key Classes**:
- `DocumentationIngester` - Handles file parsing and chunking

### Parser Details

#### PDF Parsing

**Libraries**: `pypdf` (primary), `pdfplumber` (advanced tables), OCR (scanned docs)

**Features**:
- **Hybrid Text Extraction**: Attempts `pypdf` first, detects scanned pages via density check (<50 chars/page)
- **OCR Fallback**: Routes scanned pages to Tesseract OCR or Vision LLM (GPT-4o Vision/Gemini Vision)
- **Advanced Table Extraction**: Uses `pdfplumber` for visual table detection and converts to Markdown format (`| Header | ... |`)
- **Vision-Enhanced Images**: Extracts images and sends to Vision LLM for detailed captioning (diagrams, flowcharts, screenshots)
- **Header/Footer Cleaning**: Regex-based removal of page artifacts before chunking
- **Metadata Extraction**: Title, author, creation date, modification date

**Processing Flow**:
1. **Step A**: Attempt text extraction with `pypdf`
2. **Step B (Density Check)**: If <50 chars/page OR heavy "unknown character" markers → **Trigger OCR/Vision**
3. **Step C**: Extract tables with `pdfplumber`, convert to Markdown
4. **Step D**: Process images with Vision LLM for captioning
5. **Step E**: Clean headers/footers/page numbers via regex
6. **Step F**: Apply semantic chunking (Header > Paragraph > Sentence)

**Output**: Structured text with metadata, Markdown tables, vision-captioned images, cleaned layout

**Implementation Notes**:
- **Density Check**: If `len(page.extract_text()) < 50` OR text contains many "□" (unknown character markers) → route to OCR/Vision
- **OCR Routing**: Tesseract OCR (local/free) or Vision LLM (GPT-4o Vision/Gemini Vision) for scanned pages
- **Table Markdown**: `pdfplumber.extract_tables()` → Convert rows to `| Header1 | Header2 |` format
- **Vision Captioning**: Reuses video extraction pipeline (`navigator/knowledge/ingest/video.py::_analyze_frame_with_vision`) for image analysis
- **Header/Footer Patterns**: Regex detection for patterns like `Page 1 of 50`, `CONFIDENTIAL`, `© 2025 Company`

#### Markdown Parsing

**Library**: `markdownify` (with custom extensions)

**Features**:
- Frontmatter extraction (YAML metadata)
- Table parsing with headers and rows
- Code block extraction with language tags
- Image extraction with alt text
- Link extraction with text and URLs
- Heading hierarchy preservation
- List structure preservation

**Output**: Structured Markdown content with frontmatter

#### HTML Parsing

**Library**: `beautifulsoup4`

**Features**:
- Meta tag extraction (title, description, keywords, author)
- Table parsing with headers and rows
- Code block detection and extraction
- Image extraction with alt text and src attributes
- Link extraction with text and href attributes
- Heading hierarchy (H1-H6)
- List structure preservation
- Structure normalization

**Output**: Clean structured content from HTML

#### DOCX Parsing

**Library**: `python-docx` (primary), Vision LLM (image captioning)

**Features**:
- Document properties extraction (title, author, created, modified, subject)
- **Advanced Table Extraction**: Converts tables to Markdown format for LLM-native processing
- **Vision-Enhanced Image Captioning**: Extracts images and sends to Vision LLM (GPT-4o/Gemini) for detailed descriptions of diagrams, flowcharts, and screenshots
- Hyperlink extraction with text and destinations
- Heading extraction with styles
- List extraction (ordered and unordered)
- Paragraph structure preservation

**Image Processing**: When images lack alt text (common in 90% of corporate docs), images are cropped and sent to Vision LLM with prompt: "Describe this diagram in detail. If it is a flowchart, explain the steps. If it is a screenshot, describe the UI state."

**Output**: Structured content with document properties, Markdown tables, vision-captioned images

**Implementation Notes**:
- **Image Extraction**: `doc.part.rels` → Extract images as PIL Images → Convert to base64 for Vision LLM
- **Perceptual Hashing**: Calculate pHash using `imagehash` library before Vision API call
- **Cache Check**: Check `image_caption_cache[pHash]` - return cached caption if exists (0 cost)
- **Size Filtering**: Skip images < 50x50px (icons/bullets) before Vision API calls
- **Vision Reuse**: Same Vision LLM pipeline as video extraction (`navigator/knowledge/ingest/video.py`)
- **Caption Embedding**: Generated descriptions embedded immediately after image anchor in text stream

#### Text Parsing

**Library**: Native Python text processing

**Features**:
- Section detection (by blank lines or patterns)
- List detection (ordered and unordered)
- Structure analysis (headings, paragraphs)
- Chunking with structure preservation

**Output**: Structured text chunks

### Enhanced Processing Features

#### 1. Hybrid PDF Parsing (OCR Fallback)

**Problem**: `pypdf` fails on scanned PDFs (images of text), complex layouts (multi-column), and charts/graphs.

**Solution**: Router logic for PDFs:
- **Step A**: Attempt text extraction with `pypdf`
- **Step B (Density Check)**: If `< 50 characters per page` OR heavy "unknown character" markers:
  - **Trigger OCR**: Use Tesseract OCR (free/local) or Vision LLM (GPT-4o Vision/Gemini Vision)
  - Process specific pages as images
- **Result**: No silent failures on scanned invoices or older contracts

**Code Pattern** (conceptual):
```python
text = page.extract_text()
if len(text.strip()) < 50 or contains_unknown_chars(text):
    # Route to OCR/Vision
    ocr_text = await process_page_with_ocr_or_vision(page_image)
    text = ocr_text
```

#### 2. Vision-Enhanced Image Captioning

**Problem**: 90% of corporate PDFs/DOCX files lack Alt Text. Images (architecture diagrams, flowcharts) contain critical knowledge that gets ignored.

**Solution**: Reuse Video Vision Pipeline:
1. Crop image from DOCX/PDF
2. Send to **GPT-4o Vision** / **Gemini Vision**
3. **Prompt**: "Describe this diagram in detail. If it is a flowchart, explain the steps. If it is a screenshot, describe the UI state."
4. Embed generated description into text chunk immediately following image anchor

**Code Pattern** (conceptual):
```python
for image in document.images:
    if not image.alt_text:
        caption = await vision_llm.analyze_image(
            image_data=image.bytes,
            prompt="Describe this diagram in detail..."
        )
        content.append(f"[Image: {caption}]")
```

#### 3. Advanced Table Extraction

**Problem**: `pypdf` and `python-docx` flatten tables into messy strings, losing row/column structure.

**Solution**: 
- **Library Swap**: Use `pdfplumber` (built on pdfminer.six) for PDFs instead of `pypdf` specifically for table extraction
- **Markdown Conversion**: Convert extracted tables to **Markdown Tables** format (`| Header | ... |`)
- **LLM-Native**: Markdown tables improve LLM reasoning capability compared to raw text dumps

**Code Pattern** (conceptual):
```python
import pdfplumber
with pdfplumber.open(file_path) as pdf:
    for page in pdf.pages:
        tables = page.extract_tables()
        for table in tables:
            markdown_table = convert_to_markdown(table)  # | Header1 | Header2 |
            content.append(markdown_table)
```

#### 4. Header/Footer Cleaning Pre-processor

**Problem**: Headers, footers, and page numbers break semantic continuity (sentences split across pages).

**Solution**: Regex Cleaning Step before chunking:
- Detect repetitive header/footer patterns: `Page 1 of 50`, `CONFIDENTIAL`, `© 2025 Company`
- Remove page numbers: `\bPage \d+ of \d+\b`
- Remove headers/footers that repeat on every page
- Maintain sentence continuity across page breaks

**Code Pattern** (conceptual):
```python
# Remove page numbers
text = re.sub(r'\bPage \d+ of \d+\b', '', text)
# Detect and remove repetitive headers/footers (appear on every page)
header_footer_patterns = detect_repetitive_patterns(text)
for pattern in header_footer_patterns:
    text = re.sub(pattern, '', text)
```

#### 5. Semantic Chunking (vs Token Chunking)

**Problem**: Fixed token limits (2000 tokens) may slice complex logic rules or procedures in half.

**Solution**: **Recursive Character Text Splitting** (LangChain pattern):
- **Logic**: Split by `H1`, then `H2`, then `Paragraph`, then `Sentence`
- **Fallback**: Only use hard token limits if a single paragraph exceeds limit
- **Result**: Keeps related concepts (whole procedures) in one context window

**Code Pattern** (conceptual):
```python
# Priority order: H1 > H2 > Paragraph > Sentence
chunks = []
if content_has_h1(content):
    chunks = split_by_h1(content)
elif content_has_h2(content):
    chunks = split_by_h2(content)
else:
    chunks = split_by_paragraph(content)

# Only fallback to token limits for very long paragraphs
for chunk in chunks:
    if token_count(chunk) > max_tokens:
        chunk = split_by_sentence(chunk, max_tokens)
```

#### 6. Visual Deduplication (Perceptual Hashing)

**Problem**: Corporate documents contain repetitive images (company logos, icons) that get sent to Vision LLM repeatedly, increasing costs.

**Solution**: **Perceptual Hashing (pHash)** for image deduplication:
- **Logic**: Before sending image to Vision LLM, calculate its `pHash` using `imagehash` library
- **Check**: Check if hash exists in `image_caption_cache` dictionary
- **Action**: If hash exists (cache hit), use cached caption (0 cost). If not (cache miss), analyze with Vision LLM and cache result
- **Benefit**: Reduces Vision API costs by ~30-50% for formatted documents with repeated logos/icons

**Code Pattern** (conceptual):
```python
# Calculate perceptual hash
image_hash = calculate_image_hash(image_bytes)

# Check cache
if image_hash in image_caption_cache:
    caption = image_caption_cache[image_hash]  # Cache hit - 0 cost
else:
    caption = await vision_llm.caption_image(image_bytes)  # Cache miss - API call
    image_caption_cache[image_hash] = caption  # Cache result
```

**Additional Optimization**: Filters out images smaller than 50x50px (icons/bullets) before Vision API calls.

#### 7. Breadcrumb Context Injection

**Problem**: Semantic chunking preserves context, but once a chunk is isolated in vector DB, it loses its document location.

**Solution**: **Heading Hierarchy Tracking** with breadcrumb context:
- **Logic**: As parser traverses H1/H2/H3 headings, maintain `heading_path` list
- **Prefix**: Prepend metadata to chunk: `File: {filename} | Section: {H1} > {H2} > {H3}`
- **Content**: Actual text content follows
- **Benefit**: Massive accuracy boost for retrieval - LLM knows document location even when chunk is isolated

**Code Pattern** (conceptual):
```python
heading_path = []  # Track hierarchy: ["# Installation", "## Windows", "### Prerequisites"]

# As parser encounters headings, update path
for heading in headings:
    heading_level = count_hashes(heading)  # H1=1, H2=2, etc.
    # Remove headings at same or deeper level
    heading_path = [h for h in heading_path if get_level(h) < heading_level]
    heading_path.append(heading)

# Prepend breadcrumb to chunk
breadcrumb = " > ".join([h.lstrip('#') for h in heading_path])
chunk_content = f"File: {filename} | Section: {breadcrumb}\n\n{actual_content}"
```

**Example Output**:
```
File: user_guide.pdf | Section: Installation > Windows > Prerequisites

Click the blue button to save.
```

#### 8. Code Block Safe Zones

**Problem**: Recursive splitting (Paragraph > Sentence) can break code blocks by splitting JSON objects or Python functions in the middle.

**Solution**: **Code Block Extraction/Re-insertion** pattern:
- **Pre-Processing**: Extract all code blocks (markdown format: `` ```code ... ``` ``), replace with placeholders `<<CODE_BLOCK_{uuid}>>`
- **Chunking**: Run semantic splitter on text with placeholders
- **Re-Hydration**: Replace placeholders with original code content in final chunks
- **Benefit**: Ensures syntax validity for technical documentation (JSON, Python, etc.)

**Code Pattern** (conceptual):
```python
# Step 1: Extract code blocks
code_blocks = {}
def replace_code_block(match):
    code_id = uuid4()
    code_blocks[code_id] = match.group(0)  # Store original
    return f"<<CODE_BLOCK_{code_id}>>"  # Placeholder

content = re.sub(r'```.*?```', replace_code_block, content, flags=re.DOTALL)

# Step 2: Chunk with placeholders
chunks = semantic_chunk(content_with_placeholders)

# Step 3: Re-insert code blocks
for chunk in chunks:
    for code_id, code_content in code_blocks.items():
        chunk.content = chunk.content.replace(f"<<CODE_BLOCK_{code_id}>>", code_content)
```

### Content Chunking Strategy

**Chunking Method**: Recursive Semantic Chunking (not fixed token limits)

**Chunking Strategy**:
- **Semantic Boundaries**: Splits by Header (H1) > Subheader (H2) > Paragraph > Sentence, preserving logical units
- **Structure Preservation**: Preserves headings, lists, tables as atomic units (never splits mid-table or mid-list)
- **Context Continuity**: Only falls back to hard token limits if a single paragraph exceeds limit (rare)
- **Metadata Preservation**: Attaches metadata to each chunk
- **No Arbitrary Cuts**: Avoids slicing complex logic rules or procedures in half

**Implementation Details**:
1. **Pre-Processing**: Extract code blocks, replace with placeholders
2. **First Pass**: Split by major headings (H1, H2) - track heading hierarchy for breadcrumb
3. **Second Pass**: Split sections by paragraphs
4. **Third Pass**: If paragraph > token limit, split by sentences
5. **Post-Processing**: Re-insert code blocks, add breadcrumb context to each chunk
6. **Fallback**: Hard token limit only for very long sentences/strings

**Chunk Content Format**: Each chunk includes:
- **Breadcrumb Context**: `File: {filename} | Section: {H1} > {H2} > {H3}`
- **Actual Content**: Text, tables, code blocks (with syntax preserved)

**Storage**: Chunks stored in `knowledge_ingestion_results` collection with:
- `content`: Chunk text content with breadcrumb prefix (semantic units, not arbitrary slices)
- `metadata`: Extracted metadata
- `structure`: Structural information (headings, lists, tables)
- `source_file`: Source file information
- `chunk_index`: Chunk position in document

---

## API Usage

### Single File Ingestion

```bash
curl -X POST http://localhost:8000/api/knowledge/ingest/start \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "file",
    "source_name": "Product Documentation",
    "s3_reference": {
      "bucket": "knowledge-extraction",
      "key": "org-123/docs/docs.pdf",
      "region": "us-east-1",
      "presigned_url": "https://knowledge-extraction.s3.us-east-1.amazonaws.com/...",
      "expires_at": "2025-01-15T13:00:00Z"
    },
    "file_metadata": {
      "filename": "docs.pdf",
      "size": 2097152,
      "content_type": "application/pdf",
      "uploaded_at": "2025-01-15T12:00:00Z"
    }
  }'
```

### Multiple Files (Batch Processing)

```bash
curl -X POST http://localhost:8000/api/knowledge/ingest/start \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "file",
    "source_name": "Documentation Set",
    "s3_references": [
      {
        "bucket": "knowledge-extraction",
        "key": "org-123/docs/doc1.pdf",
        "presigned_url": "https://...",
        "expires_at": "2025-01-15T13:00:00Z"
      },
      {
        "bucket": "knowledge-extraction",
        "key": "org-123/docs/doc2.md",
        "presigned_url": "https://...",
        "expires_at": "2025-01-15T13:00:00Z"
      }
    ],
    "file_metadata_list": [
      {
        "filename": "doc1.pdf",
        "size": 1048576,
        "content_type": "application/pdf",
        "uploaded_at": "2025-01-15T12:00:00Z"
      },
      {
        "filename": "doc2.md",
        "size": 512000,
        "content_type": "text/markdown",
        "uploaded_at": "2025-01-15T12:00:00Z"
      }
    ]
  }'
```

**Key Points**:
- All files are processed in a **single workflow execution**
- Each file is ingested separately (creates separate ingestion results)
- Chunks from all files are **aggregated** for extraction phase
- One `job_id` tracks the entire batch
- If one file fails, others continue processing

### Response Format

**Success Response**:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "workflow_id": "workflow-123",
  "status": "queued",
  "estimated_duration_seconds": 300,
  "message": "Documentation ingestion started"
}
```

---

## Multi-Source Integration

Text file processing supports aggregation with other sources:

### Supported Combinations

- **Multiple Text Files**: Combine PDF, Markdown, HTML, DOCX, text files in single extraction
- **Text Files + Web Crawling**: Combine text files with website URLs
- **Text Files + Video**: Combine text files with video files
- **Mixed Sources**: Combine all source types in single extraction

### Multi-Source Aggregation

**Key Feature**: All extraction activities support `ingestion_ids[]` parameter:

```python
ExtractScreensInput(
    ingestion_id=primary_id,  # For backward compatibility
    ingestion_ids=[pdf_id, md_id, html_id, docx_id]  # All text files
)
```

**Benefits**:
- Merges knowledge from all text file sources
- Deduplicates entities (screens, tasks, actions) across files
- Creates unified knowledge base
- Single workflow execution for all sources

### Knowledge Merging & Deduplication

**Automatic Deduplication**:
- Screens: By URL pattern and state signature
- Tasks: By name and step sequence
- Actions: By action type and target
- Transitions: By source/target screen pairs

**Cross-Source Merging**:
- Same screen found in PDF + Markdown → Single unified screen
- Same task described in multiple files → Enriched with all details
- Content from all files → Combined knowledge base

---

## Summary

Text file processing provides:

1. **Multi-Format Support**: Comprehensive processing of PDF, Markdown, HTML, DOCX, and text files
2. **Enhanced Content Extraction**: 
   - **Hybrid PDF Parsing**: OCR fallback for scanned documents (Tesseract/Vision LLM)
   - **Vision-Enhanced Images**: AI captioning for diagrams, flowcharts, screenshots with **pHash deduplication** (30-50% cost reduction)
   - **Advanced Table Extraction**: `pdfplumber` with Markdown conversion for LLM-native processing
   - **Header/Footer Cleaning**: Regex-based removal of page artifacts for semantic continuity
   - **Semantic Chunking**: Recursive splitting by Header > Paragraph > Sentence (preserves context boundaries)
   - **Breadcrumb Context**: Heading hierarchy (H1 > H2 > H3) prepended to chunks for context-aware retrieval
   - **Code Block Protection**: Code blocks extracted before chunking, re-inserted after to preserve syntax validity
3. **Business Knowledge**: LLM analysis for business functions and operational workflows
4. **Multi-File Processing**: Batch processing of multiple files in single workflow
5. **Multi-Source Integration**: Aggregation with web crawling and video processing

All text files produce structured content chunks that flow through the unified knowledge extraction pipeline, ensuring consistent knowledge representation regardless of file format.

**For general architecture details**, see [General Architecture Guide](./KNOWLEDGE_ARCHITECTURE_GENERAL.md).

**For web crawling details**, see [Public Documentation Guide](./KNOWLEDGE_EXTRACTION_PUBLIC_DOCUMENTATION.md) and [Authenticated Portal Guide](./KNOWLEDGE_EXTRACTION_AUTHENTICATED_PORTAL.md).

---

**Last Updated**: January 20, 2026  
**Status**: Production Ready (Enhanced with OCR, Vision, Advanced Tables, pHash Deduplication, Breadcrumb Context, Code Block Protection) ✅  
**Version**: 2.5.0
# Knowledge Extraction - Authenticated Portal Exploration Guide

**Version**: 2.3.0  
**Last Updated**: January 18, 2026  
**Status**: Production Ready

This document provides comprehensive details on authenticated portal exploration for knowledge extraction using Browser-Use.

**See Also**:
- [General Architecture Guide](./KNOWLEDGE_ARCHITECTURE_GENERAL.md) - S3 ingestion, schema design, workflow orchestration
- [Text File Processing Guide](./KNOWLEDGE_EXTRACTION_TEXT_FILES.md) - PDF, Markdown, HTML, DOCX file processing details
- [Video Extraction Guide](./KNOWLEDGE_EXTRACTION_VIDEO.md) - Video file processing details
- [Public Documentation Guide](./KNOWLEDGE_EXTRACTION_PUBLIC_DOCUMENTATION.md) - Public documentation crawling using Crawl4AI

---

## Table of Contents

1. [Overview](#overview)
2. [Browser-Use for Authenticated Portals](#browser-use-for-authenticated-portals)
3. [Processing Pipeline](#processing-pipeline)
4. [Implementation Details](#implementation-details)
5. [API Usage](#api-usage)
6. [Credential Management](#credential-management)
7. [Security Considerations](#security-considerations)

---

## Overview

Authenticated portal exploration extracts knowledge from web portals that require login credentials. Browser-Use is used to navigate authenticated pages, extract DOM content, and build knowledge about the portal's structure and functionality.

All explored content produces structured content chunks that flow through the unified knowledge extraction pipeline (see [General Architecture Guide](./KNOWLEDGE_ARCHITECTURE_GENERAL.md)).

### Key Features

- ✅ **BrowserSession-based Crawling**: Uses Browser-Use for authenticated navigation
- ✅ **Credential Support**: Username/password authentication
- ✅ **DOM-level Analysis**: Deep DOM analysis for knowledge extraction
- ✅ **Authenticated Content Access**: Accesses protected content after login
- ✅ **Session Management**: Maintains authenticated session across pages
- ✅ **JavaScript Execution**: Handles JavaScript-rendered content
- ✅ **Form Extraction**: Extracts interactive forms and fields
- ✅ **Navigation Mapping**: Identifies navigation patterns in authenticated portals

### When to Use

Use Browser-Use for authenticated portal exploration when:
- ✅ Portal requires login credentials (username/password)
- ✅ Content is protected behind authentication
- ✅ You need to explore internal documentation portals
- ✅ You want to extract knowledge from customer portals or admin panels
- ✅ JavaScript-rendered content needs to be captured

**For public documentation sites without authentication**, see [Public Documentation Guide](./KNOWLEDGE_EXTRACTION_PUBLIC_DOCUMENTATION.md).

---

## Browser-Use for Authenticated Portals

### Overview

Browser-Use is used for authenticated portals that require login credentials. It uses browser automation to navigate authenticated pages and extract DOM content.

### Use Case

**Authenticated Portals**:
- Internal documentation portals
- Customer portals with protected content
- Enterprise knowledge bases requiring authentication
- Admin panels and dashboards
- SaaS application portals
- Private documentation sites
- Intranet sites with authentication

### Features

- ✅ **BrowserSession-based Crawling**: Uses Browser-Use for authenticated navigation
- ✅ **Credential Support**: Username/password authentication
- ✅ **DOM-level Analysis**: Deep DOM analysis for knowledge extraction
- ✅ **Authenticated Content Access**: Accesses protected content after login
- ✅ **Session Management**: Maintains authenticated session across pages
- ✅ **JavaScript Execution**: Handles JavaScript-rendered content
- ✅ **Form Field Extraction**: Identifies form inputs and interactive elements
- ✅ **Navigation Structure**: Maps portal navigation and page relationships

### Implementation

**Location**: `navigator/knowledge/ingest/website.py`

**Library**: Browser-Use (`browser_use`)

**Process**:
1. **Authentication**: Login with provided credentials (username/password)
2. **Session Management**: Maintain authenticated session
3. **Page Navigation**: Navigate to target pages
4. **DOM Extraction**: Extract DOM content and structure
5. **Content Processing**: Convert DOM to structured content chunks
6. **Chunking**: Split content into manageable chunks with metadata
7. **Storage**: Store ingestion results in MongoDB

**DOM Extraction**:
- HTML structure preservation
- Form field extraction
- Interactive element detection
- Content hierarchy (headings, sections, lists)
- Link extraction with navigation targets
- Image extraction with sources
- JavaScript-rendered content capture

---

## Processing Pipeline

### Phase 1: Authenticated Portal Exploration & Ingestion

**Input**: Portal URL with credentials provided in ingestion request

**Steps**:

1. **Strategy Selection**: Detect authenticated portal (credentials provided)
2. **Authentication**: Login with provided credentials
3. **Session Management**: Maintain authenticated session
4. **Page Navigation**: Navigate to target pages
5. **DOM Extraction**: Extract DOM content and structure
6. **Content Processing**: Convert DOM to structured content
7. **Feature Extraction**: Extract forms, interactive elements, structure
8. **Chunking**: Split content into manageable chunks
9. **Metadata Extraction**: Extract page metadata
10. **Storage**: Store ingestion results in MongoDB

**Output**: Structured content chunks with metadata (`webpage` chunks)

### Phase 2: Knowledge Extraction

All extraction activities support explored authenticated portal content:

- **Screen Extraction**: Identify application states from web page structure
  - ✅ **New Format Support**: Screens are automatically classified as `content_type="web_ui"` and `is_actionable=True`
  - ✅ **Content Classification**: Uses `_is_web_ui_screen()` to distinguish web UI from documentation
  - ✅ **State Signatures**: Extracts actual DOM indicators (buttons, headings, inputs) for better recognition
  - ✅ **URL Patterns**: Generates specific URL patterns (e.g., `^https://app\\.example\\.com/dashboard.*`)
- **Task Extraction**: Parse workflows and procedures from portal pages
- **Action Extraction**: Extract UI interactions from forms and interactive elements
  - ✅ **Browser-Use Mapping**: Actions are automatically translated to browser-use compatible actions via `ActionTranslator`
  - ✅ **Tool Mapping**: Action types (click, type, navigate, etc.) mapped to browser-use tools (click, input, navigate, etc.)
  - ✅ **Parameter Conversion**: Parameters converted to browser-use format (e.g., `target_selector` → `index`/`selector`)
- **Transition Extraction**: Identify navigation patterns from authenticated pages
- **Business Function Extraction**: LLM analysis to identify business functions
- **Operational Workflow Extraction**: LLM analysis to extract step-by-step workflows
- **Action Gap Filling**: LLM-based extrapolation to infer missing actions and transitions
  - ✅ **Gemini LLM**: Uses `gemini-2.0-flash-exp` to infer missing actions between known actions
  - ✅ **Confidence Scoring**: Stores inferred actions with confidence scores (>0.6 threshold)

**Supported Source Types**:
- ✅ **Browser-Use**: Explored authenticated portal pages (`webpage` chunks)
  - Content chunks have `chunk_type="webpage"` 
  - Automatically processed through new knowledge restructuring pipeline

**AI Providers**:
- **OpenAI GPT-4o**: Primary choice for business function and workflow extraction
- **Google Gemini 1.5 Pro**: Fallback option for business function and workflow extraction
- **Google Gemini 2.0 Flash Exp**: Used for action gap extrapolation

### Feature Completeness

**Authenticated Portal Exploration**:
- ✅ All authenticated pages are accessed (Browser-Use)
- ✅ DOM content extracted with structure preserved
- ✅ Interactive elements (forms, buttons) identified
- ✅ Navigation patterns mapped
- ✅ Business functions extracted from portal content
- ✅ Operational workflows extracted from portal pages
- ✅ Session maintained across page navigations

**New Knowledge Restructuring Formats (Phase 1-6)**:
- ✅ **Content Type Classification**: Screens automatically classified as `web_ui` vs `documentation`
- ✅ **Actionable Screens**: Web UI screens marked as `is_actionable=True` for agent use
- ✅ **Browser-Use Action Mapping**: All actions translated to browser-use compatible format
- ✅ **Screen Recognition**: Improved recognition using actual DOM indicators and URL patterns
- ✅ **Agent Communication**: Agent-friendly query API with browser-use actions
- ✅ **Action Extrapolation**: LLM-based gap filling for missing actions and transitions

---

## Implementation Details

### Browser-Use Implementation

**Location**: `navigator/knowledge/ingest/website.py`

**Library**: Browser-Use (`browser_use`)

**Key Classes**:
- `WebsiteCrawler` - Handles Browser-Use-based authenticated crawling

**Crawling Process**:
1. Initialize Browser-Use BrowserSession
2. Navigate to login page
3. Authenticate with provided credentials
4. Maintain authenticated session
5. Navigate to target pages
6. Extract DOM content and structure
7. Process interactive elements (forms, buttons, links)
8. Convert DOM to structured content
9. Generate content chunks with metadata
10. Store ingestion results in MongoDB

**Session Management**:
- Maintains authenticated session across page navigations
- Handles session cookies and tokens
- Cleans up session after processing

**DOM Extraction**:
- Extracts HTML structure
- Detects form fields and interactive elements
- Preserves content hierarchy (headings, sections, lists)
- Extracts links with navigation targets
- Extracts images with sources
- Captures JavaScript-rendered content

**Knowledge Restructuring Integration**:
- Content chunks from authenticated portals have `chunk_type="webpage"`
- Screens extracted from authenticated portals are automatically classified:
  - `content_type="web_ui"` (authenticated portals are web UIs, not documentation)
  - `is_actionable=True` (all authenticated portal screens are actionable)
- Actions extracted from authenticated portals are automatically mapped to browser-use actions:
  - Uses `ActionTranslator` to convert `ActionDefinition` → `BrowserUseAction`
  - Parameters converted to browser-use format (e.g., `target_selector` → `index`)
  - Ready for direct execution by browser-use agents
- Screen recognition uses actual DOM indicators:
  - UI element patterns (buttons, headings, inputs, links)
  - Specific URL patterns (e.g., `^https://app\\.example\\.com/dashboard.*`)
  - Excludes documentation phrases and generic patterns

---

## API Usage

### Authenticated Portal Exploration (Browser-Use)

```bash
curl -X POST http://localhost:8000/api/knowledge/ingest/start \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "website",
    "source_url": "https://portal.example.com",
    "source_name": "Example Portal",
    "credentials": {
      "username": "user@example.com",
      "password": "secure_password"
    },
    "options": {
      "max_depth": 2,
      "include_paths": ["/docs/", "/knowledge/"],
      "exclude_paths": ["/admin/", "/settings/"]
    }
  }'
```

**Key Points**:
- ✅ **MUST** include `credentials` field with `username` and `password`
- ✅ `source_type` should be `"website"`
- ✅ Browser-Use is automatically selected when credentials are provided

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

## Credential Management

### Credential Format

**Required Fields**:
```json
{
  "credentials": {
    "username": "user@example.com",
    "password": "secure_password"
  }
}
```

**Optional Fields**:
```json
{
  "credentials": {
    "username": "user@example.com",
    "password": "secure_password",
    "login_url": "https://portal.example.com/login"  // Optional: specific login URL
  }
}
```

### Security

**Security Best Practices**:
- ✅ Credentials are never stored in logs
- ✅ Credentials are passed securely to Browser-Use
- ✅ Sessions are managed securely and cleaned up after processing
- ✅ No credential storage in database or files
- ✅ HTTPS recommended for credential transmission

**Security Guidelines**:
- **Never log credentials**: Credentials are filtered from all log output
- **Secure transmission**: Use HTTPS for all API requests
- **Session cleanup**: All browser sessions are terminated after processing
- **No persistence**: Credentials are not stored anywhere in the system
- **Access control**: Ensure API access is properly authenticated and authorized

---

## Security Considerations

### Credential Security

**DO**:
- ✅ Use HTTPS for all API requests
- ✅ Rotate credentials regularly
- ✅ Use read-only accounts when possible
- ✅ Monitor access logs for unauthorized use
- ✅ Use environment variables or secure secret management in production

**DON'T**:
- ❌ Store credentials in code or configuration files
- ❌ Log credentials in application logs
- ❌ Share credentials via insecure channels
- ❌ Use production credentials in development/testing

### Session Management

**Browser Session Lifecycle**:
1. Browser session created with credentials
2. Login performed automatically
3. Session maintained during exploration
4. Session terminated after processing
5. All cookies/tokens cleared

**Session Security**:
- Sessions are isolated per extraction job
- No session sharing between jobs
- Automatic cleanup after completion
- No persistent session storage

### Network Security

**Recommendations**:
- Use VPN or private networks for internal portals
- Ensure portal access is properly authorized
- Monitor network traffic for anomalies
- Use firewall rules to restrict access

---

## Multi-Source Integration

Authenticated portal exploration supports aggregation with other sources:

### Supported Combinations

- **Multiple Portals**: Combine multiple authenticated portal URLs in single extraction
- **Authenticated + Public**: Combine authenticated portals with public documentation
- **Portals + Text Files**: Combine portal exploration with text files
- **Portals + Video**: Combine portal exploration with video files
- **Mixed Sources**: Combine all source types in single extraction

### Multi-Source Aggregation

**Key Feature**: All extraction activities support `ingestion_ids[]` parameter:

```python
ExtractScreensInput(
    ingestion_id=primary_id,  # For backward compatibility
    ingestion_ids=[browseruse_id, crawl4ai_id, doc_id]  # All sources
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
- Same screen found in Browser-Use + other sources → Single unified screen
- Same task described in multiple sources → Enriched with all details
- Content from all sources → Combined knowledge base

---

## Summary

Authenticated portal exploration provides:

1. **Browser-Use Integration**: Browser automation for authenticated portal navigation
2. **Credential Management**: Secure username/password authentication
3. **DOM-level Analysis**: Deep DOM extraction for interactive elements
4. **Session Management**: Maintains authenticated sessions across pages
5. **Form Extraction**: Identifies forms and interactive elements
6. **Navigation Mapping**: Maps portal structure and page relationships
7. **Business Knowledge**: LLM analysis for business functions and operational workflows
8. **Multi-Source Integration**: Aggregation with other knowledge sources
9. **New Knowledge Formats**: Full support for knowledge restructuring (Phases 1-6)
   - Content type classification (web_ui vs documentation)
   - Browser-use action mapping
   - Improved screen recognition
   - Agent-friendly query API
   - LLM-based action extrapolation

All explored content produces structured content chunks that flow through the unified knowledge extraction pipeline, ensuring consistent knowledge representation.

**Knowledge Restructuring Benefits for Authenticated Portals**:
- ✅ Screens automatically classified as `web_ui` and `is_actionable=True`
- ✅ Actions automatically mapped to browser-use compatible format
- ✅ Screen recognition uses actual DOM indicators for better accuracy
- ✅ Agent queries return browser-use actions ready for execution
- ✅ Missing actions inferred using LLM extrapolation

**For public documentation sites without authentication**, see [Public Documentation Guide](./KNOWLEDGE_EXTRACTION_PUBLIC_DOCUMENTATION.md).

**For general architecture details**, see [General Architecture Guide](./KNOWLEDGE_ARCHITECTURE_GENERAL.md).

**For text file processing details**, see [Text File Processing Guide](./KNOWLEDGE_EXTRACTION_TEXT_FILES.md).

---

**Last Updated**: January 18, 2026  
**Status**: Production Ready ✅  
**Version**: 2.3.0

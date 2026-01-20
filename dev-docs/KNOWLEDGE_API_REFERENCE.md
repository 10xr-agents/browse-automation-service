# Knowledge Extraction API Reference

**Version**: 1.0.4  
**Last Updated**: January 18, 2026  
**Status**: Production Ready  
**OpenAPI Spec**: `/openapi.json` | **Swagger UI**: `/docs` | **ReDoc**: `/redoc`

Complete REST API reference for the Knowledge Extraction System - 100% aligned with OpenAPI specification.

---

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [API Fundamentals](#2-api-fundamentals)
3. [Enum Reference](#3-enum-reference)
4. [S3 File-Based Ingestion](#4-s3-file-based-ingestion)
5. [Ingestion API](#5-ingestion-api)
6. [Workflow Status API](#6-workflow-status-api)
7. [Graph Query API](#7-graph-query-api)
8. [Knowledge Retrieval API](#8-knowledge-retrieval-api)
9. [Verification API](#9-verification-api)
10. [Worker Status API](#10-worker-status-api)
11. [Error Handling](#11-error-handling)
12. [Frontend Integration Guide](#12-frontend-integration-guide)

---

## 1. Quick Start

### 1.1 Start Knowledge Extraction

```bash
curl -X POST http://localhost:8000/api/knowledge/ingest/start \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "website",
    "source_url": "https://app.example.com",
    "source_name": "Example App",
    "knowledge_id": "know-abc-123"
  }'
```

**Key Parameter: `knowledge_id`**
- **Optional**: If not provided, knowledge is extracted but not grouped by `knowledge_id`
- **Recommended**: Always provide `knowledge_id` for proper persistence and querying
- **Replacement Behavior**: When resyncing/re-extracting with the same `knowledge_id`, all existing knowledge for that ID is automatically **replaced** using MongoDB's native `delete_many` (by `knowledge_id` filter) followed by `upsert=True` (replace-on-insert) - ensures clean replacement without orphaned entities

**Response**:
```json
{
  "job_id": "job-abc-123",
  "workflow_id": "knowledge-extraction-job-abc-123",
  "status": "queued",
  "estimated_duration_seconds": 900,
  "message": "Knowledge extraction workflow started successfully for website"
}
```

### 1.2 Check Progress

```bash
curl http://localhost:8000/api/knowledge/workflows/status/job-abc-123
```

### 1.3 Query Knowledge

```bash
curl -X POST http://localhost:8000/api/knowledge/graph/query \
  -H "Content-Type: application/json" \
  -d '{
    "query_type": "search_screens",
    "website_id": "example.com",
    "limit": 10
  }'
```

---

## 2. API Fundamentals

### 2.1 Base Configuration

- **Base URL**: `http://localhost:8000` (development) / `https://api.yourservice.com` (production)
- **API Prefix**: `/api/knowledge`
- **Content Type**: `application/json`
- **Field Naming**: **`snake_case`** (NOT `camelCase`)

### 2.2 Complete Endpoint List

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/knowledge/ingest/start` | Start knowledge extraction |
| `POST` | `/api/knowledge/ingest/upload` | Start extraction with file upload (501 Not Implemented) |
| `GET` | `/api/knowledge/workflows/status/{job_id}` | Get workflow status |
| `GET` | `/api/knowledge/workflows/list` | List workflows (with optional status filter) |
| `POST` | `/api/knowledge/graph/query` | Query knowledge graph |
| `GET` | `/api/knowledge/screens/{screen_id}` | Get screen definition |
| `GET` | `/api/knowledge/screens` | List screens for website |
| `GET` | `/api/knowledge/tasks/{task_id}` | Get task definition |
| `GET` | `/api/knowledge/tasks` | List tasks for website |
| `GET` | `/api/knowledge/actions/{action_id}` | Get action definition |
| `GET` | `/api/knowledge/transitions/{transition_id}` | Get transition definition |
| `POST` | `/api/knowledge/verify/start` | Start verification workflow |
| `GET` | `/api/knowledge/worker/status` | Get worker health status |
| `GET` | `/api/knowledge/health` | Health check endpoint |

### 2.3 HTTP Status Codes

| Code | Meaning | Use Case |
|------|---------|----------|
| `200` | Success | Request completed successfully |
| `400` | Bad Request | Invalid parameters or missing required fields |
| `404` | Not Found | Resource doesn't exist |
| `410` | Gone | Presigned URL expired (S3 ingestion) |
| `422` | Validation Error | Pydantic validation failed |
| `500` | Internal Server Error | Unexpected server error |
| `501` | Not Implemented | Feature not yet available |
| `502` | Bad Gateway | S3 download failed (network error) |
| `503` | Service Unavailable | Feature disabled (e.g., verification) |

### 2.4 Error Response Format

All errors return:
```json
{
  "detail": "Human-readable error message"
}
```

**Validation Errors (422)**:
```json
{
  "detail": [
    {
      "loc": ["body", "source_type"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## 3. Enum Reference

### 3.1 SourceType Enum

**CRITICAL**: Use exact values (lowercase, no modification)

| Enum Value | Description | Ingestion Mode | Use Case |
|------------|-------------|----------------|----------|
| `documentation` | Technical documentation | URL or File | Markdown, PDF, HTML docs |
| `website` | Website crawling | URL only | Multi-page websites with navigation |
| `video` | Video walkthrough | URL or File | Tutorial videos, product demos |
| `file` | File from S3 | **S3 only** | Files uploaded to S3 (requires `s3_reference`) |

**Example Usage**:
```json
{
  "source_type": "documentation"
}
```

**TypeScript Definition**:
```typescript
type SourceType = 'documentation' | 'website' | 'video' | 'file';
```

**Python Definition**:
```python
from enum import Enum

class SourceType(str, Enum):
    DOCUMENTATION = 'documentation'
    WEBSITE = 'website'
    VIDEO = 'video'
    FILE = 'file'
```

### 3.2 WorkflowStatus Enum

| Value | Description |
|-------|-------------|
| `queued` | Workflow queued, not yet started |
| `running` | Workflow currently executing |
| `completed` | Workflow finished successfully |
| `failed` | Workflow failed with errors |
| `cancelled` | Workflow was cancelled |

**TypeScript Definition**:
```typescript
type WorkflowStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
```

---

## 4. S3 File-Based Ingestion

### 4.1 Overview

File-based ingestion allows processing files uploaded to S3 (AWS S3 or DigitalOcean Spaces) using secure presigned URLs.

**Flow**:
```
UI → S3 Upload → Generate Presigned URL → API → Download → Process
```

**Key Features**:
- ✅ No direct file upload to API (scalable for large files)
- ✅ Secure presigned URLs (1-hour validity)
- ✅ Supports AWS S3 (IAM-based) and DigitalOcean Spaces (access key-based)
- ✅ Automatic file type detection from extensions
- ✅ Streaming downloads (memory-efficient)
- ✅ Automatic retry with exponential backoff
- ✅ Comprehensive error handling (410, 502, 404)

### 4.2 S3Reference Schema

**Required Fields**:
- `bucket` (string): S3 bucket name
- `key` (string): Object key/path in bucket
- `presigned_url` (string): Presigned URL for downloading (valid for 1 hour)
- `expires_at` (string): ISO 8601 timestamp when presigned URL expires

**Optional Fields**:
- `region` (string | null): AWS region (e.g., `us-east-1`). Optional for DigitalOcean Spaces
- `endpoint` (string | null): Custom S3 endpoint for DigitalOcean Spaces (e.g., `https://nyc3.digitaloceanspaces.com`)

**TypeScript Interface**:
```typescript
interface S3Reference {
  bucket: string;
  key: string;
  region?: string;           // For AWS S3
  endpoint?: string;         // For DigitalOcean Spaces
  presigned_url: string;     // Valid for 1 hour
  expires_at: string;        // ISO 8601 timestamp
}
```

**Example (AWS S3)**:
```json
{
  "bucket": "knowledge-extraction",
  "key": "org-123/knowledge/know-456/documentation.pdf",
  "region": "us-east-1",
  "presigned_url": "https://knowledge-extraction.s3.us-east-1.amazonaws.com/org-123/knowledge/know-456/documentation.pdf?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=...",
  "expires_at": "2025-01-15T13:00:00Z"
}
```

**Example (DigitalOcean Spaces)**:
```json
{
  "bucket": "knowledge-extraction",
  "key": "org-123/knowledge/know-789/demo.mp4",
  "endpoint": "https://nyc3.digitaloceanspaces.com",
  "presigned_url": "https://knowledge-extraction.nyc3.digitaloceanspaces.com/org-123/knowledge/know-789/demo.mp4?AWSAccessKeyId=...",
  "expires_at": "2025-01-15T13:00:00Z"
}
```

### 4.3 FileMetadata Schema

**Required Fields**:
- `filename` (string): Original filename
- `size` (integer): File size in bytes (must be > 0)
- `content_type` (string): MIME type (e.g., `application/pdf`, `video/mp4`)
- `uploaded_at` (string): ISO 8601 timestamp when file was uploaded

**TypeScript Interface**:
```typescript
interface FileMetadata {
  filename: string;
  size: number;              // Bytes, must be > 0
  content_type: string;      // MIME type
  uploaded_at: string;       // ISO 8601 timestamp
}
```

**Example**:
```json
{
  "filename": "user-manual.pdf",
  "size": 2097152,
  "content_type": "application/pdf",
  "uploaded_at": "2025-01-15T12:00:00Z"
}
```

### 4.4 Supported File Types

| Extension | Content Type | Auto-Detected As | Max Size (Recommended) |
|-----------|-------------|------------------|------------------------|
| `.pdf` | `application/pdf` | Documentation | 50 MB |
| `.md` | `text/markdown` | Documentation | 10 MB |
| `.txt` | `text/plain` | Documentation | 10 MB |
| `.html` | `text/html` | Documentation | 10 MB |
| `.mp4` | `video/mp4` | Video | 500 MB |
| `.webm` | `video/webm` | Video | 500 MB |
| `.mov` | `video/quicktime` | Video | 500 MB |

**Auto-Detection Logic**:
- File extension determines internal `source_type` for processing
- PDF/MD/TXT/HTML → `documentation` ingestion pipeline
- MP4/WebM/MOV → `video` ingestion pipeline

### 4.5 Request Examples

#### PDF from AWS S3
```bash
curl -X POST http://localhost:8000/api/knowledge/ingest/start \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "file",
    "source_name": "Product Documentation",
    "s3_reference": {
      "bucket": "knowledge-extraction",
      "key": "org-123/knowledge/know-456/docs.pdf",
      "region": "us-east-1",
      "presigned_url": "https://knowledge-extraction.s3.us-east-1.amazonaws.com/org-123/knowledge/know-456/docs.pdf?X-Amz-Algorithm=...",
      "expires_at": "2025-01-15T13:00:00Z"
    },
    "file_metadata": {
      "filename": "product-docs.pdf",
      "size": 2097152,
      "content_type": "application/pdf",
      "uploaded_at": "2025-01-15T12:00:00Z"
    }
  }'
```

#### Video from DigitalOcean Spaces
```bash
curl -X POST http://localhost:8000/api/knowledge/ingest/start \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "file",
    "source_name": "Demo Video",
    "s3_reference": {
      "bucket": "knowledge-extraction",
      "key": "org-123/knowledge/know-789/demo.mp4",
      "endpoint": "https://nyc3.digitaloceanspaces.com",
      "presigned_url": "https://knowledge-extraction.nyc3.digitaloceanspaces.com/org-123/knowledge/know-789/demo.mp4?AWSAccessKeyId=...",
      "expires_at": "2025-01-15T13:00:00Z"
    },
    "file_metadata": {
      "filename": "product-demo.mp4",
      "size": 15728640,
      "content_type": "video/mp4",
      "uploaded_at": "2025-01-15T12:00:00Z"
    }
  }'
```

#### Multiple Files from S3 (Batch Processing)
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
        "key": "org-123/docs/doc2.pdf",
        "presigned_url": "https://...",
        "expires_at": "2025-01-15T13:00:00Z"
      },
      {
        "bucket": "knowledge-extraction",
        "key": "org-123/docs/doc3.md",
        "presigned_url": "https://...",
        "expires_at": "2025-01-15T13:00:00Z"
      }
    ],
    "file_metadata_list": [
      {
        "filename": "documentation1.pdf",
        "size": 1048576,
        "content_type": "application/pdf",
        "uploaded_at": "2025-01-15T12:00:00Z"
      },
      {
        "filename": "documentation2.pdf",
        "size": 2097152,
        "content_type": "application/pdf",
        "uploaded_at": "2025-01-15T12:00:00Z"
      },
      {
        "filename": "readme.md",
        "size": 51200,
        "content_type": "text/markdown",
        "uploaded_at": "2025-01-15T12:00:00Z"
      }
    ]
  }'
```

**Note**: All files are processed in a single workflow execution. Each file is ingested separately, then chunks from all files are aggregated for extraction.

### 4.6 Error Handling

| HTTP Status | Error | Cause | Solution |
|-------------|-------|-------|----------|
| **400** | Missing fields | `s3_reference` or `file_metadata` not provided | Include both fields |
| **410** | URL expired | Presigned URL expired | Generate new presigned URL and retry |
| **502** | Download failed | Network error, S3 unavailable | Retry request after delay |
| **404** | Object not found | File doesn't exist in S3 | Verify bucket/key are correct |

**400 Bad Request (Missing Fields)**:
```json
{
  "detail": "s3_reference and file_metadata are required for file-based ingestion (source_type='file')"
}
```

**410 Gone (Expired URL)**:
```json
{
  "detail": "Presigned URL expired at 2025-01-15T10:00:00Z"
}
```

**502 Bad Gateway (Download Failed)**:
```json
{
  "detail": "Failed to download file from S3: Connection timeout"
}
```

**404 Not Found (Object Missing)**:
```json
{
  "detail": "S3 object not found: bucket=knowledge-extraction, key=org-123/file.pdf"
}
```

### 4.7 Best Practices

**✅ DO**:
- Use 1-hour expiry for presigned URLs
- Start ingestion immediately after generating URL
- Use IAM roles in production (AWS S3)
- Enable server-side encryption (SSE-S3 or SSE-KMS)
- Validate file size and content type before upload

**❌ DON'T**:
- Share S3 credentials in API requests
- Use overly long expiry times (> 1 hour)
- Store presigned URLs for later use
- Skip validation of file metadata

---

## 5. Ingestion API

### 5.1 Start Ingestion

**Endpoint**: `POST /api/knowledge/ingest/start`

Start a knowledge extraction workflow for a website, documentation, video, or file from S3.

#### Request Schema

**StartIngestionRequest**:
```typescript
interface StartIngestionRequest {
  source_type: SourceType;              // Required: 'documentation' | 'website' | 'video' | 'file'
  source_url?: string;                  // Required for URL-based (not for 'file')
  source_name?: string;                 // Optional: Human-readable name
  s3_reference?: S3Reference;           // Single file ingestion (use with file_metadata)
  file_metadata?: FileMetadata;         // Single file ingestion (use with s3_reference)
  s3_references?: S3Reference[];       // Multiple file ingestion (use with file_metadata_list)
  file_metadata_list?: FileMetadata[];  // Multiple file ingestion (must match s3_references length)
  options?: IngestionOptionsModel;      // Optional: Type-specific options
  job_id?: string;                      // Optional: Auto-generated if not provided
  knowledge_id?: string;                // Optional: Knowledge ID for persistence and querying (recommended)
}
```

**Knowledge ID Parameter**:
- **Purpose**: Groups all extracted knowledge entities (screens, tasks, actions, transitions, business functions, workflows) under a single identifier for querying and persistence
- **Replacement Behavior**: When resyncing/re-extracting with the same `knowledge_id`, all existing knowledge for that ID is automatically **replaced** using MongoDB's native operations:
  1. `delete_many({ knowledge_id: "..." })` - Efficiently deletes all existing entities with that `knowledge_id`
  2. `upsert=True` - MongoDB's replace-on-insert for saving new entities
- **Benefits**: 
  - Clean replacement without orphaned entities from previous extractions
  - Efficient queries using `knowledge_id` index
  - Enables resyncing to update knowledge without manual cleanup

**IngestionOptionsModel**:
```typescript
interface IngestionOptionsModel {
  max_pages?: number;               // Website only: Maximum pages to crawl
  max_depth?: number;               // Website only: Maximum crawl depth
  extract_code_blocks?: boolean;    // Documentation only: Extract code blocks (default: true)
  extract_thumbnails?: boolean;     // Video only: Extract video thumbnails (default: true)
  credentials?: {                    // Website only: Login credentials for authenticated crawling
    username: string;                // Username or email for login
    password: string;                // Password for login
    login_url?: string;              // Optional: Explicit login page URL (auto-detected if not provided)
  };
}
```

#### Validation Rules

| Condition | Requirement |
|-----------|-------------|
| `source_type='file'` (single) | **MUST** include `s3_reference` AND `file_metadata` |
| `source_type='file'` (multiple) | **MUST** include `s3_references` AND `file_metadata_list` (arrays with matching lengths) |
| `source_type!='file'` | **MUST** include `source_url` |
| Presigned URL | **MUST NOT** be expired |
| File size | **MUST** be > 0 |
| Multiple files | `s3_references.length` **MUST EQUAL** `file_metadata_list.length` |

#### Response Schema

**StartIngestionResponse**:
```typescript
interface StartIngestionResponse {
  job_id: string;                       // ← STORE THIS for tracking!
  workflow_id: string;                  // Temporal workflow ID
  status: string;                       // Always 'queued' initially
  estimated_duration_seconds?: number;  // Estimated completion time
  message: string;                      // Human-readable message
}
```

#### Request Examples

**Website Crawling (No Login)**:
```bash
curl -X POST http://localhost:8000/api/knowledge/ingest/start \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "website",
    "source_url": "https://app.example.com",
    "source_name": "Example App",
    "options": {
      "max_pages": 100,
      "max_depth": 3
    }
  }'
```

**Website Crawling with Login Credentials**:
```bash
curl -X POST http://localhost:8000/api/knowledge/ingest/start \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "website",
    "source_url": "https://app.example.com",
    "source_name": "Example App",
    "options": {
      "max_pages": 100,
      "max_depth": 3,
      "credentials": {
        "username": "user@example.com",
        "password": "secure-password",
        "login_url": "https://app.example.com/signin"
      }
    }
  }'
```

**Note**: `login_url` is optional - the crawler will auto-detect login pages if not provided. Credentials are used securely and never logged or persisted.

**Documentation from URL**:
```bash
curl -X POST http://localhost:8000/api/knowledge/ingest/start \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "documentation",
    "source_url": "https://docs.example.com",
    "source_name": "Example Docs",
    "options": {
      "extract_code_blocks": true
    }
  }'
```

**Video from URL**:
```bash
curl -X POST http://localhost:8000/api/knowledge/ingest/start \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "video",
    "source_url": "https://example.com/tutorial.mp4",
    "source_name": "Tutorial Video",
    "options": {
      "extract_thumbnails": true
    }
  }'
```

**Single File from S3** (see Section 4 for complete examples)

**Multiple Files from S3**:
```bash
curl -X POST http://localhost:8000/api/knowledge/ingest/start \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "file",
    "source_name": "Documentation Set",
    "s3_references": [
      {
        "bucket": "knowledge-extraction",
        "key": "org-123/doc1.pdf",
        "presigned_url": "https://...",
        "expires_at": "2025-01-15T13:00:00Z"
      },
      {
        "bucket": "knowledge-extraction",
        "key": "org-123/doc2.pdf",
        "presigned_url": "https://...",
        "expires_at": "2025-01-15T13:00:00Z"
      }
    ],
    "file_metadata_list": [
      {
        "filename": "documentation1.pdf",
        "size": 1048576,
        "content_type": "application/pdf",
        "uploaded_at": "2025-01-15T12:00:00Z"
      },
      {
        "filename": "documentation2.pdf",
        "size": 2097152,
        "content_type": "application/pdf",
        "uploaded_at": "2025-01-15T12:00:00Z"
      }
    ]
  }'
```

**Note**: `s3_references` and `file_metadata_list` must have the same length. All files are processed in a single workflow execution.

#### Response Example

```json
{
  "job_id": "job-abc-123",
  "workflow_id": "knowledge-extraction-job-abc-123",
  "status": "queued",
  "estimated_duration_seconds": 300,
  "message": "Knowledge extraction workflow started successfully for documentation"
}
```

#### Estimated Durations

| Source Type | Estimated Duration |
|-------------|-------------------|
| `documentation` | 300 seconds (5 minutes) |
| `website` | 900 seconds (15 minutes) |
| `video` | 600 seconds (10 minutes) |
| `file` | 300 seconds (5 minutes, varies by file type) |

#### HTTP Status Codes

| Code | Description |
|------|-------------|
| `200` | Workflow started successfully |
| `400` | Invalid request parameters |
| `410` | Presigned URL expired (S3 ingestion) |
| `422` | Validation error |
| `500` | Internal server error |
| `502` | S3 download failed (file ingestion) |

### 5.2 Upload File (Not Implemented)

**Endpoint**: `POST /api/knowledge/ingest/upload`

**Status**: `501 Not Implemented`

This endpoint is planned for future releases. Use S3-based file ingestion instead (see Section 4).

**Response**:
```json
{
  "detail": "File upload not yet implemented. Use URL-based ingestion instead."
}
```

---

## 6. Workflow Status API & Job Tracking

### 6.1 Overview

When you start a knowledge extraction job, you receive a `job_id` that you can use to track the job's progress. The system provides detailed status updates including:

- Current status (queued, running, completed, failed, etc.)
- Current phase (ingestion, extraction, url_exploration, etc.)
- Progress percentage (0-100)
- Checkpoint information (for long-running activities)
- Errors and warnings
- Timestamps

**Important:** Save the `job_id` from the response when starting a job - you'll use it to track progress.

### 6.2 Get Workflow Status

**Endpoint**: `GET /api/knowledge/workflows/status/{job_id}`

Get detailed status, progress, and errors for a specific workflow.

#### Path Parameters

- `job_id` (string, required): The job ID returned from `/ingest/start`

#### Response Schema

**WorkflowStatusResponse**:
```typescript
interface WorkflowStatusResponse {
  job_id: string;
  workflow_id: string;
  status: WorkflowStatus;           // 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  phase?: string;                   // Current phase (e.g., 'extraction', 'normalization')
  progress: number;                 // 0.0 to 1.0 (0% to 100%)
  errors: string[];                 // List of error messages
  warnings: string[];               // List of warning messages
  checkpoints: CheckpointInfo[];    // Progress checkpoints
  created_at: string;               // ISO 8601 timestamp
  updated_at: string;               // ISO 8601 timestamp
  metadata: Record<string, any>;    // Additional metadata
}

interface CheckpointInfo {
  activity_name: string;
  checkpoint_id: number;
  items_processed: number;
  total_items: number;
  progress_percentage: number;      // 0.0 to 100.0
}
```

#### Request Example

```bash
curl http://localhost:8000/api/knowledge/workflows/status/job-abc-123
```

#### Response Example

```json
{
  "job_id": "job-abc-123",
  "workflow_id": "knowledge-extraction-job-abc-123",
  "status": "running",
  "phase": "extraction",
  "progress": 0.45,
  "errors": [],
  "warnings": ["Some URLs were skipped due to robots.txt"],
  "checkpoints": [
    {
      "activity_name": "ingest_website",
      "checkpoint_id": 1,
      "items_processed": 45,
      "total_items": 100,
      "progress_percentage": 45.0
    }
  ],
  "created_at": "2025-01-15T12:00:00Z",
  "updated_at": "2025-01-15T12:05:23Z",
  "metadata": {
    "source_type": "website",
    "source_url": "https://app.example.com"
  }
}
```

#### HTTP Status Codes

| Code | Description |
|------|-------------|
| `200` | Status retrieved successfully |
| `404` | Workflow not found |
| `500` | Internal server error |

### 6.3 UI Implementation Best Practices

#### Polling Strategy

**Recommended:** Poll every 2-5 seconds while status is `queued` or `running`.

```typescript
// Example React hook
function useJobStatus(jobId: string) {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!jobId) return;

    const pollInterval = setInterval(async () => {
      try {
        const response = await fetch(
          `/api/knowledge/workflows/status/${jobId}`
        );
        const data = await response.json();
        setStatus(data);

        // Stop polling if job is done
        if (['completed', 'failed', 'cancelled'].includes(data.status)) {
          clearInterval(pollInterval);
        }
      } catch (err) {
        setError(err);
        clearInterval(pollInterval);
      }
    }, 3000); // Poll every 3 seconds

    return () => clearInterval(pollInterval);
  }, [jobId]);

  return { status, error };
}
```

#### Progress Display

Display progress using:
- **Overall progress:** `progress` field (0-100)
- **Phase name:** `phase` field
- **Checkpoint details:** `checkpoints` array for granular progress

```typescript
// Example progress bar component
function JobProgress({ status }: { status: WorkflowStatusResponse }) {
  if (!status) return null;

  return (
    <div>
      <div className="progress-bar">
        <div 
          className="progress-fill" 
          style={{ width: `${status.progress}%` }}
        />
      </div>
      <div className="phase-info">
        Phase: {status.phase || 'Initializing...'}
      </div>
      {status.checkpoints?.map((cp, i) => (
        <div key={i} className="checkpoint">
          {cp.activity_name}: {cp.items_processed}/{cp.total_items} 
          ({cp.progress_percentage.toFixed(1)}%)
        </div>
      ))}
    </div>
  );
}
```

#### Error Handling

Check the `errors` array for any errors:

```typescript
function JobStatus({ status }: { status: WorkflowStatusResponse }) {
  if (status?.errors?.length > 0) {
    return (
      <div className="error-container">
        <h3>Errors:</h3>
        {status.errors.map((error, i) => (
          <div key={i} className="error">{error}</div>
        ))}
      </div>
    );
  }

  if (status?.warnings?.length > 0) {
    return (
      <div className="warning-container">
        <h3>Warnings:</h3>
        {status.warnings.map((warning, i) => (
          <div key={i} className="warning">{warning}</div>
        ))}
      </div>
    );
  }

  return null;
}
```

#### Status Values

The `status` field comes from **Temporal** (authoritative source) and can be one of:

- **`queued`** - Job is queued and waiting to start
- **`running`** - Job is currently executing in Temporal
- **`paused`** - Job is paused (rare)
- **`completed`** - Job completed successfully in Temporal
- **`failed`** - Job failed with errors
- **`cancelled`** - Job was cancelled in Temporal

#### Phase Values

The `phase` field indicates the current workflow phase:

- **`ingestion`** - Processing files/documentation URLs (Phase 1)
- **`extraction`** - Extracting knowledge from ingested content
- **`url_exploration`** - Exploring website URLs and extracting screens/actions/tasks
- **`verification`** - Verifying extracted knowledge (if enabled)

#### Notes

1. **Polling Frequency:** Don't poll too frequently (every 1 second) as it can overload the server. 2-5 seconds is recommended.

2. **Job Duration:** Knowledge extraction jobs can take 5-60+ minutes depending on:
   - Number of files to process
   - Size of documentation sites
   - Number of pages to explore
   - Video processing (if applicable)

3. **Checkpoints:** For long-running activities (like video processing), checkpoints provide detailed progress within an activity.

4. **Knowledge ID:** Make sure to pass `knowledge_id` when starting a job - this is required for proper persistence and querying.

5. **Error Recovery:** If a job fails, check the `errors` array for details. You may need to restart the job with corrected parameters.

### 6.4 List Workflows

**Endpoint**: `GET /api/knowledge/workflows/list`

List workflows with optional filtering by status.

#### Query Parameters

- `status` (WorkflowStatus, optional): Filter by status (`queued`, `running`, `completed`, `failed`, `cancelled`)
- `limit` (integer, optional): Maximum results to return (default: 100)

#### Response Schema

```typescript
interface WorkflowListItem {
  job_id: string;
  workflow_id: string;
  status: WorkflowStatus;
  phase?: string;
  progress: number;
  created_at: string;
  updated_at: string;
}

type WorkflowListResponse = WorkflowListItem[];
```

#### Request Examples

**List all workflows**:
```bash
curl "http://localhost:8000/api/knowledge/workflows/list?limit=50"
```

**List completed workflows**:
```bash
curl "http://localhost:8000/api/knowledge/workflows/list?status=completed&limit=20"
```

**List failed workflows**:
```bash
curl "http://localhost:8000/api/knowledge/workflows/list?status=failed"
```

#### Response Example

```json
[
  {
    "job_id": "job-abc-123",
    "workflow_id": "knowledge-extraction-job-abc-123",
    "status": "completed",
    "phase": "completed",
    "progress": 1.0,
    "created_at": "2025-01-15T12:00:00Z",
    "updated_at": "2025-01-15T12:15:30Z"
  },
  {
    "job_id": "job-def-456",
    "workflow_id": "knowledge-extraction-job-def-456",
    "status": "running",
    "phase": "normalization",
    "progress": 0.67,
    "created_at": "2025-01-15T13:00:00Z",
    "updated_at": "2025-01-15T13:10:15Z"
  }
]
```

#### HTTP Status Codes

| Code | Description |
|------|-------------|
| `200` | Workflows retrieved successfully |
| `500` | Internal server error |

---

## 7. Graph Query API

### 7.1 Query Knowledge Graph

**Endpoint**: `POST /api/knowledge/graph/query`

Query the extracted knowledge graph for navigation paths, screen relationships, and transitions.

#### Request Schema

**GraphQueryRequest**:
```typescript
interface GraphQueryRequest {
  query_type: 'find_path' | 'get_neighbors' | 'search_screens' | 'get_transitions';
  source_screen_id?: string;        // Required for find_path, get_neighbors, get_transitions
  target_screen_id?: string;        // Required for find_path
  screen_name?: string;             // Required for search_screens (or website_id)
  website_id?: string;              // Optional filter
  limit?: number;                   // Default: 10, Max: 100
}
```

#### Query Types

| Query Type | Description | Required Fields | Returns |
|------------|-------------|----------------|---------|
| `find_path` | Find shortest path between two screens | `source_screen_id`, `target_screen_id` | List of path edges |
| `get_neighbors` | Get adjacent screens | `source_screen_id` | List of neighbor screens |
| `search_screens` | Search screens by name or website | `screen_name` or `website_id` | List of matching screens |
| `get_transitions` | Get transitions from a screen | `source_screen_id` | List of transitions |

#### Response Schema

**GraphQueryResponse**:
```typescript
interface GraphQueryResponse {
  query_type: string;
  results: Array<Record<string, any>>;
  count: number;
  execution_time_ms?: number;
}
```

#### Request Examples

**Find Path**:
```bash
curl -X POST http://localhost:8000/api/knowledge/graph/query \
  -H "Content-Type: application/json" \
  -d '{
    "query_type": "find_path",
    "source_screen_id": "dashboard",
    "target_screen_id": "settings"
  }'
```

**Get Neighbors**:
```bash
curl -X POST http://localhost:8000/api/knowledge/graph/query \
  -H "Content-Type: application/json" \
  -d '{
    "query_type": "get_neighbors",
    "source_screen_id": "dashboard",
    "limit": 5
  }'
```

**Search Screens**:
```bash
curl -X POST http://localhost:8000/api/knowledge/graph/query \
  -H "Content-Type: application/json" \
  -d '{
    "query_type": "search_screens",
    "website_id": "example.com",
    "limit": 10
  }'
```

**Get Transitions**:
```bash
curl -X POST http://localhost:8000/api/knowledge/graph/query \
  -H "Content-Type: application/json" \
  -d '{
    "query_type": "get_transitions",
    "source_screen_id": "dashboard"
  }'
```

#### Response Example

```json
{
  "query_type": "search_screens",
  "results": [
    {
      "count": 42,
      "website_id": "example.com"
    }
  ],
  "count": 1,
  "execution_time_ms": 125.5
}
```

#### HTTP Status Codes

| Code | Description |
|------|-------------|
| `200` | Query executed successfully |
| `400` | Invalid query parameters |
| `500` | Query execution failed |

---

## 8. Knowledge Retrieval API

### 8.1 Get Screen Definition

**Endpoint**: `GET /api/knowledge/screens/{screen_id}`

Get complete screen definition with state signature, UI elements, and affordances.

#### Path Parameters

- `screen_id` (string, required): Unique screen identifier

#### Response Schema

```typescript
interface ScreenDefinitionResponse {
  screen_id: string;
  name: string;
  website_id: string;
  url_patterns: string[];
  state_signature: Record<string, any>;
  ui_elements: Array<Record<string, any>>;
  metadata: Record<string, any>;
}
```

#### Request Example

```bash
curl http://localhost:8000/api/knowledge/screens/dashboard
```

#### Response Example

```json
{
  "screen_id": "dashboard",
  "name": "Dashboard Screen",
  "website_id": "example.com",
  "url_patterns": [
    "^https://app\\.example\\.com/dashboard$"
  ],
  "state_signature": {
    "required_indicators": [
      {
        "type": "url_matches",
        "pattern": "/dashboard"
      }
    ]
  },
  "ui_elements": [
    {
      "element_id": "search_input",
      "type": "input",
      "selector": {
        "strategies": [
          {
            "type": "semantic",
            "label_contains": "Search"
          }
        ]
      }
    }
  ],
  "metadata": {
    "description": "Main dashboard",
    "complexity": "medium"
  }
}
```

#### HTTP Status Codes

| Code | Description |
|------|-------------|
| `200` | Screen retrieved successfully |
| `404` | Screen not found |
| `500` | Internal server error |

### 8.2 Get Task Definition

**Endpoint**: `GET /api/knowledge/tasks/{task_id}`

Get complete task definition with steps, preconditions, postconditions, and IO spec.

#### Path Parameters

- `task_id` (string, required): Unique task identifier

#### Response Schema

```typescript
interface TaskDefinitionResponse {
  task_id: string;
  name: string;
  website_id: string;
  description: string;
  goal: string;
  steps: Array<Record<string, any>>;
  preconditions: Array<Record<string, any>>;
  postconditions: Array<Record<string, any>>;
  iterator_spec?: Record<string, any>;
  io_spec?: Record<string, any>;
}
```

#### Request Example

```bash
curl http://localhost:8000/api/knowledge/tasks/create_agent
```

#### Response Example

```json
{
  "task_id": "create_agent",
  "name": "Create AI Agent",
  "website_id": "example.com",
  "description": "Create a new AI agent with configuration",
  "goal": "Successfully create and save a new agent",
  "steps": [
    {
      "step_id": "navigate_to_create",
      "order": 1,
      "type": "navigation",
      "action": {
        "action_type": "navigate",
        "target_screen": "agent_create"
      }
    }
  ],
  "preconditions": [
    {
      "type": "authenticated",
      "hard_dependency": true
    }
  ],
  "postconditions": [
    {
      "type": "screen_reached",
      "screen_id": "agent_list"
    }
  ],
  "io_spec": {
    "inputs": [
      {
        "name": "agent_name",
        "type": "string",
        "required": true
      }
    ],
    "outputs": [
      {
        "name": "created_agent_id",
        "type": "string"
      }
    ]
  }
}
```

#### HTTP Status Codes

| Code | Description |
|------|-------------|
| `200` | Task retrieved successfully |
| `404` | Task not found |
| `500` | Internal server error |

### 8.3 Get Action Definition

**Endpoint**: `GET /api/knowledge/actions/{action_id}`

Get complete action definition with parameters, preconditions, and error handling.

#### Path Parameters

- `action_id` (string, required): Unique action identifier

#### Request Example

```bash
curl http://localhost:8000/api/knowledge/actions/type_text
```

#### HTTP Status Codes

| Code | Description |
|------|-------------|
| `200` | Action retrieved successfully |
| `404` | Action not found |
| `500` | Internal server error |

### 8.4 Get Transition Definition

**Endpoint**: `GET /api/knowledge/transitions/{transition_id}`

Get complete transition definition with conditions, effects, cost, and reliability.

#### Path Parameters

- `transition_id` (string, required): Unique transition identifier

#### Request Example

```bash
curl http://localhost:8000/api/knowledge/transitions/dashboard_to_settings
```

#### HTTP Status Codes

| Code | Description |
|------|-------------|
| `200` | Transition retrieved successfully |
| `404` | Transition not found |
| `500` | Internal server error |

### 8.5 List Screens

**Endpoint**: `GET /api/knowledge/screens`

List all screens for a website.

#### Query Parameters

- `website_id` (string, required): Website identifier
- `limit` (integer, optional): Maximum results (default: 100)

#### Request Example

```bash
curl "http://localhost:8000/api/knowledge/screens?website_id=example.com&limit=50"
```

#### HTTP Status Codes

| Code | Description |
|------|-------------|
| `200` | Screens retrieved successfully |
| `500` | Internal server error |

### 8.6 List Tasks

**Endpoint**: `GET /api/knowledge/tasks`

List all tasks for a website.

#### Query Parameters

- `website_id` (string, required): Website identifier
- `limit` (integer, optional): Maximum results (default: 100)

#### Request Example

```bash
curl "http://localhost:8000/api/knowledge/tasks?website_id=example.com&limit=50"
```

#### HTTP Status Codes

| Code | Description |
|------|-------------|
| `200` | Tasks retrieved successfully |
| `500` | Internal server error |

---

## 9. Verification API

### 9.1 Start Verification

**Endpoint**: `POST /api/knowledge/verify/start`

Start browser-based verification workflow to validate extracted knowledge.

**Note**: Requires `FEATURE_BROWSER_VERIFICATION=true` in environment.

#### Request Schema

**VerificationRequest**:
```typescript
interface VerificationRequest {
  target_type: 'job' | 'screen' | 'task';
  target_id: string;
  verification_options?: Record<string, any>;
}
```

#### Response Schema

**VerificationResponse**:
```typescript
interface VerificationResponse {
  verification_job_id: string;
  target_type: string;
  target_id: string;
  status: string;                   // Always 'queued' initially
  message: string;
}
```

#### Request Example

```bash
curl -X POST http://localhost:8000/api/knowledge/verify/start \
  -H "Content-Type: application/json" \
  -d '{
    "target_type": "job",
    "target_id": "job-abc-123",
    "verification_options": {
      "check_ui_elements": true,
      "validate_state_signatures": true
    }
  }'
```

#### Response Example

```json
{
  "verification_job_id": "verify-xyz-789",
  "target_type": "job",
  "target_id": "job-abc-123",
  "status": "queued",
  "message": "Verification workflow started for job job-abc-123"
}
```

#### HTTP Status Codes

| Code | Description |
|------|-------------|
| `200` | Verification started successfully |
| `400` | Invalid request parameters |
| `500` | Internal server error |
| `503` | Verification feature not enabled |

---

## 10. Worker Status API

### 10.1 Get Worker Status

**Endpoint**: `GET /api/knowledge/worker/status`

Get health status of the Temporal worker.

#### Response Schema

```typescript
interface WorkerStatusResponse {
  status: 'healthy' | 'unhealthy';
  worker_id?: string;
  temporal_url?: string;
  task_queue?: string;
  message?: string;
}
```

#### Request Example

```bash
curl http://localhost:8000/api/knowledge/worker/status
```

#### Response Example (Healthy)

```json
{
  "status": "healthy",
  "worker_id": "worker-1",
  "temporal_url": "localhost:7233",
  "task_queue": "knowledge-extraction-queue",
  "message": "Worker is healthy and processing tasks"
}
```

#### Response Example (Unhealthy)

```json
{
  "status": "unhealthy",
  "message": "Worker not connected to Temporal server"
}
```

#### HTTP Status Codes

| Code | Description |
|------|-------------|
| `200` | Status retrieved successfully |
| `500` | Internal server error |

---

## 11. Error Handling

### 11.1 Error Response Format

All errors follow the same format:

```typescript
interface ErrorResponse {
  detail: string | ValidationError[];
}

interface ValidationError {
  loc: (string | number)[];
  msg: string;
  type: string;
}
```

### 11.2 Common Errors

#### 400 Bad Request

**Missing Required Field**:
```json
{
  "detail": "source_url is required for website ingestion"
}
```

**Invalid Enum Value**:
```json
{
  "detail": "source_type must be one of: documentation, website, video, file"
}
```

#### 404 Not Found

```json
{
  "detail": "Screen not found: invalid_screen_id"
}
```

#### 410 Gone (S3 Presigned URL Expired)

```json
{
  "detail": "Presigned URL expired at 2025-01-15T10:00:00Z"
}
```

#### 422 Validation Error

```json
{
  "detail": [
    {
      "loc": ["body", "source_type"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

#### 500 Internal Server Error

```json
{
  "detail": "Failed to start workflow: Temporal client not initialized"
}
```

#### 501 Not Implemented

```json
{
  "detail": "File upload not yet implemented. Use URL-based ingestion instead."
}
```

#### 502 Bad Gateway (S3 Download Failed)

```json
{
  "detail": "Failed to download file from S3: Connection timeout"
}
```

#### 503 Service Unavailable

```json
{
  "detail": "Browser verification is not enabled. Set FEATURE_BROWSER_VERIFICATION=true to enable."
}
```

---

## 12. Frontend Integration Guide

### 12.1 Field Naming Convention

**CRITICAL**: Use `snake_case` for all JSON fields, not `camelCase`.

**✅ Correct**:
```typescript
const request = {
  source_type: 'website',
  source_url: 'https://example.com',
  source_name: 'Example'
};
```

**❌ Wrong**:
```typescript
const request = {
  sourceType: 'website',    // WRONG - will cause 422 error
  sourceUrl: 'https://example.com',
  sourceName: 'Example'
};
```

### 12.2 Website Crawling with Login Credentials

**For authenticated websites**, include credentials in `options.credentials`:

```typescript
interface Credentials {
  username: string;      // Required: Username or email
  password: string;      // Required: Password
  login_url?: string;    // Optional: Explicit login page URL (auto-detected if not provided)
}

// Example request with login
const request: StartIngestionRequest = {
  source_type: 'website',
  source_url: 'https://app.example.com',
  source_name: 'Example App',
  options: {
    credentials: {
      username: 'user@example.com',
      password: 'secure-password',
      login_url: 'https://app.example.com/signin'  // Optional
    }
  }
};
```

**UI Implementation:**
- Add "Requires Login" checkbox to website ingestion form
- Show username/password fields when checked
- Include credentials in `options.credentials` when submitting
- Credentials are never logged or persisted (secure handling)

**Security Notes:**
- ⚠️ Never log credentials in console
- ⚠️ Clear credentials from form after submission
- ⚠️ Use HTTPS for all API calls
- ⚠️ Credentials are used only for the crawling session

### 12.3 TypeScript Integration

#### Complete Type Definitions

```typescript
// Enums
type SourceType = 'documentation' | 'website' | 'video' | 'file';
type WorkflowStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';

// S3 Schemas
interface S3Reference {
  bucket: string;
  key: string;
  region?: string;
  endpoint?: string;
  presigned_url: string;
  expires_at: string;
}

interface FileMetadata {
  filename: string;
  size: number;
  content_type: string;
  uploaded_at: string;
}

// Request Schemas
interface IngestionOptionsModel {
  max_pages?: number;
  max_depth?: number;
  extract_code_blocks?: boolean;
  extract_thumbnails?: boolean;
  credentials?: {
    username: string;
    password: string;
    login_url?: string;  // Optional: Auto-detected if not provided
  };
}

interface StartIngestionRequest {
  source_type: SourceType;
  source_url?: string;
  source_name?: string;
  s3_reference?: S3Reference;           // Single file (use with file_metadata)
  file_metadata?: FileMetadata;         // Single file (use with s3_reference)
  s3_references?: S3Reference[];       // Multiple files (use with file_metadata_list)
  file_metadata_list?: FileMetadata[];  // Multiple files (must match s3_references length)
  options?: IngestionOptionsModel;
  job_id?: string;
}

// Response Schemas
interface StartIngestionResponse {
  job_id: string;
  workflow_id: string;
  status: string;
  estimated_duration_seconds?: number;
  message: string;
}

interface WorkflowStatusResponse {
  job_id: string;
  workflow_id: string;
  status: WorkflowStatus;
  phase?: string;
  progress: number;
  errors: string[];
  warnings: string[];
  checkpoints: CheckpointInfo[];
  created_at: string;
  updated_at: string;
  metadata: Record<string, any>;
}

interface CheckpointInfo {
  activity_name: string;
  checkpoint_id: number;
  items_processed: number;
  total_items: number;
  progress_percentage: number;
}
```

#### Complete API Client Example

```typescript
class KnowledgeExtractionClient {
  private baseUrl: string;

  constructor(baseUrl: string = 'http://localhost:8000') {
    this.baseUrl = baseUrl;
  }

  // Start URL-based ingestion
  async startIngestion(request: StartIngestionRequest): Promise<StartIngestionResponse> {
    const response = await fetch(`${this.baseUrl}/api/knowledge/ingest/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail);
    }

    return response.json();
  }

  // Start S3-based file ingestion
  async startFileIngestion(
    file: File,
    s3Reference: S3Reference
  ): Promise<StartIngestionResponse> {
    const fileMetadata: FileMetadata = {
      filename: file.name,
      size: file.size,
      content_type: file.type,
      uploaded_at: new Date().toISOString(),
    };

    return this.startIngestion({
      source_type: 'file',
      source_name: file.name,
      s3_reference: s3Reference,
      file_metadata: fileMetadata,
    });
  }

  // Get workflow status
  async getStatus(jobId: string): Promise<WorkflowStatusResponse> {
    const response = await fetch(
      `${this.baseUrl}/api/knowledge/workflows/status/${jobId}`
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail);
    }

    return response.json();
  }

  // Poll workflow until completion
  async pollUntilComplete(
    jobId: string,
    onProgress?: (status: WorkflowStatusResponse) => void
  ): Promise<WorkflowStatusResponse> {
    while (true) {
      const status = await this.getStatus(jobId);

      if (onProgress) {
        onProgress(status);
      }

      if (status.status === 'completed') {
        return status;
      }

      if (status.status === 'failed' || status.status === 'cancelled') {
        throw new Error(`Workflow ${status.status}: ${status.errors.join(', ')}`);
      }

      // Poll every 2 seconds
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
  }

  // Query knowledge graph
  async queryGraph(request: GraphQueryRequest): Promise<GraphQueryResponse> {
    const response = await fetch(`${this.baseUrl}/api/knowledge/graph/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail);
    }

    return response.json();
  }
}
```

#### Usage Example with S3

```typescript
// Initialize client
const client = new KnowledgeExtractionClient('http://localhost:8000');

// Upload file to S3 and start ingestion
async function extractKnowledgeFromFile(file: File) {
  try {
    // 1. Upload to S3
    const { bucket, key } = await uploadToS3(file);

    // 2. Generate presigned URL (1-hour expiry)
    const presignedUrl = await generatePresignedUrl(bucket, key);
    const expiresAt = new Date(Date.now() + 3600000).toISOString();

    // 3. Start extraction
    const response = await client.startFileIngestion(file, {
      bucket,
      key,
      region: 'us-east-1',
      presigned_url: presignedUrl,
      expires_at: expiresAt,
    });

    console.log('Started extraction:', response.job_id);

    // 4. Poll for completion
    const result = await client.pollUntilComplete(
      response.job_id,
      (status) => {
        console.log(`Progress: ${Math.round(status.progress * 100)}%`);
      }
    );

    console.log('Extraction complete!', result);
    return result;
  } catch (error) {
    console.error('Extraction failed:', error);
    throw error;
  }
}
```

### 12.4 Error Handling Best Practices

```typescript
async function handleKnowledgeExtraction(request: StartIngestionRequest) {
  try {
    const response = await client.startIngestion(request);
    return response;
  } catch (error: any) {
    // Handle specific HTTP status codes
    if (error.status === 400) {
      console.error('Invalid request:', error.message);
      // Show validation errors to user
    } else if (error.status === 410) {
      console.error('Presigned URL expired, regenerating...');
      // Regenerate presigned URL and retry
      const newPresignedUrl = await regeneratePresignedUrl();
      return handleKnowledgeExtraction({
        ...request,
        s3_reference: {
          ...request.s3_reference!,
          presigned_url: newPresignedUrl,
        },
      });
    } else if (error.status === 502) {
      console.error('S3 download failed, retrying...');
      // Retry after delay
      await new Promise(resolve => setTimeout(resolve, 5000));
      return handleKnowledgeExtraction(request);
    } else {
      console.error('Unexpected error:', error);
      throw error;
    }
  }
}
```

### 12.5 Polling Best Practices

**✅ Recommended Polling Intervals**:
- First 5 minutes: Poll every 2 seconds
- After 5 minutes: Poll every 5 seconds
- After 15 minutes: Poll every 10 seconds

**✅ Implement Exponential Backoff**:
```typescript
async function pollWithBackoff(jobId: string) {
  let interval = 2000; // Start with 2 seconds
  const maxInterval = 10000; // Max 10 seconds
  const startTime = Date.now();

  while (true) {
    const status = await client.getStatus(jobId);

    if (status.status === 'completed' || status.status === 'failed') {
      return status;
    }

    await new Promise(resolve => setTimeout(resolve, interval));

    // Increase interval after 5 minutes
    const elapsed = Date.now() - startTime;
    if (elapsed > 300000 && interval < maxInterval) {
      interval = Math.min(interval * 1.5, maxInterval);
    }
  }
}
```

### 12.6 Testing Checklist

- [ ] Test URL-based ingestion (website, documentation, video)
- [ ] Test S3-based file ingestion (PDF, video)
- [ ] Test expired presigned URL handling (410 error)
- [ ] Test S3 download failure handling (502 error)
- [ ] Test missing required fields (400 error)
- [ ] Test workflow status polling
- [ ] Test graph queries
- [ ] Test knowledge retrieval endpoints
- [ ] Verify all fields use `snake_case`
- [ ] Verify error messages are displayed correctly

---

**End of API Reference**

For complete implementation details and architecture, see:
- **Architecture**: `/dev-docs/KNOWLEDGE_ARCHITECTURE.md`
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI Spec**: `http://localhost:8000/openapi.json`

---

**Last Updated**: January 17, 2026  
**Version**: 1.0.1  
**Status**: Production Ready ✅

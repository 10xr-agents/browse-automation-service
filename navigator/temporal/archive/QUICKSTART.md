# Temporal Knowledge Extraction - Quick Start

Get up and running with Temporal-based knowledge extraction in 5 minutes.

---

## Prerequisites

- Python 3.11+
- Docker (for Temporal server)
- MongoDB (local or cloud)
- Redis (local or cloud)

---

## Step 1: Start Temporal Server

```bash
# Start Temporal with Docker
docker run -d \
  -p 7233:7233 \
  -p 8233:8233 \
  --name temporal-server \
  temporalio/auto-setup:latest

# Verify it's running
curl http://localhost:8233
```

**Temporal Web UI**: http://localhost:8233

---

## Step 2: Configure Environment

```bash
# Create environment file
cp .env.example .env.local

# Edit .env.local
cat > .env.local << EOF
# Temporal
TEMPORAL_URL=localhost:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_KNOWLEDGE_QUEUE=knowledge-extraction-queue

# MongoDB
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=browser_automation_service

# Redis
REDIS_URL=redis://localhost:6379
EOF
```

---

## Step 3: Install Dependencies

```bash
# Install all dependencies
uv sync

# Or if you prefer pip
pip install -e .
```

---

## Step 4: Start the Service

```bash
# Start the server (includes Temporal worker)
uv run python navigator/start_server.py
```

You should see:
```
✅ Required environment variables found
🚀 Starting Temporal Worker
   Temporal URL: localhost:7233
   Namespace: default
   Task Queue: knowledge-extraction-queue
✅ Temporal worker started successfully
✅ Knowledge retrieval API registered (Temporal-based)
Starting uvicorn server...
```

---

## Step 5: Submit a Knowledge Extraction Job

```bash
# Start exploration
curl -X POST http://localhost:8000/api/knowledge/explore/start \
  -H "Content-Type: application/json" \
  -d '{
    "start_url": "https://example.com",
    "max_pages": 50,
    "max_depth": 3,
    "strategy": "BFS"
  }'
```

**Response**:
```json
{
  "job_id": "01940e4c-7d8f-72b3-93f7-8e6f9d0c1a2b",
  "workflow_id": "knowledge-extraction-01940e4c-7d8f-72b3-93f7-8e6f9d0c1a2b",
  "status": "running",
  "message": "Workflow started. Use /api/knowledge/explore/status/{job_id} to check progress."
}
```

---

## Step 6: Monitor Progress

### Via REST API

```bash
# Check status
curl http://localhost:8000/api/knowledge/explore/status/01940e4c-7d8f-72b3-93f7-8e6f9d0c1a2b
```

**Response**:
```json
{
  "job_id": "01940e4c-7d8f-72b3-93f7-8e6f9d0c1a2b",
  "status": "running",
  "paused": false,
  "current_page": "https://example.com/about",
  "pages_completed": 12,
  "pages_queued": 8,
  "pages_failed": 0,
  "links_discovered": 45,
  "external_links_detected": 7
}
```

### Via Temporal UI

1. Open http://localhost:8233
2. Click on "Workflows"
3. Find your workflow: `knowledge-extraction-{job_id}`
4. View real-time execution history

---

## Step 7: Control the Workflow

### Pause

```bash
curl -X POST http://localhost:8000/api/knowledge/explore/pause \
  -H "Content-Type: application/json" \
  -d '{"job_id": "01940e4c-7d8f-72b3-93f7-8e6f9d0c1a2b"}'
```

### Resume

```bash
curl -X POST http://localhost:8000/api/knowledge/explore/resume \
  -H "Content-Type: application/json" \
  -d '{"job_id": "01940e4c-7d8f-72b3-93f7-8e6f9d0c1a2b"}'
```

### Cancel

```bash
curl -X POST http://localhost:8000/api/knowledge/explore/cancel \
  -H "Content-Type: application/json" \
  -d '{"job_id": "01940e4c-7d8f-72b3-93f7-8e6f9d0c1a2b"}'
```

---

## Step 8: Get Results

```bash
# Get final results (after workflow completes)
curl http://localhost:8000/api/knowledge/explore/results/01940e4c-7d8f-72b3-93f7-8e6f9d0c1a2b
```

**Response**:
```json
{
  "job_id": "01940e4c-7d8f-72b3-93f7-8e6f9d0c1a2b",
  "status": "completed",
  "pages_processed": 50,
  "pages_completed": 48,
  "pages_failed": 2,
  "links_discovered": 213,
  "external_links_detected": 34,
  "processing_time": 145.7,
  "errors": [...]
}
```

---

## Common Operations

### List All Jobs

```bash
curl http://localhost:8000/api/knowledge/explore/jobs
```

### Health Check

```bash
curl http://localhost:8000/health
```

### Stop the Service

```bash
# Press Ctrl+C in the terminal running the service
# The service will gracefully shutdown:
# 1. Stop accepting new requests
# 2. Wait for running activities to complete
# 3. Close browser sessions
# 4. Disconnect from Temporal
```

---

## Troubleshooting

### Service won't start

**Problem**: `Failed to connect to Temporal`

**Solution**: Check Temporal is running
```bash
docker ps | grep temporal
curl http://localhost:7233
```

### No workflows executing

**Problem**: Workflows queued but not running

**Solution**: Check worker logs
```bash
# Look for this in startup logs:
✅ Temporal worker started successfully
   Task queue: knowledge-extraction-queue
   Workflows: ['KnowledgeExtractionWorkflow']
```

### Activities timing out

**Problem**: `Activity timeout exceeded`

**Solution**: Check browser session
```bash
# Look for browser-related errors in logs
# Ensure sufficient resources (memory/CPU)
```

---

## Next Steps

- **Path Filtering**: Use `include_paths`/`exclude_paths` to filter URLs
- **Custom Depth**: Adjust `max_depth` for deeper exploration
- **Strategy Selection**: Try `"DFS"` for different exploration order
- **Scaling**: Add more workers for parallel processing
- **Production**: Deploy to Temporal Cloud for managed infrastructure

---

## API Reference

See `navigator/temporal/README.md` for complete API documentation.

---

**Last Updated**: 2026-01-14  
**Version**: 1.0.0

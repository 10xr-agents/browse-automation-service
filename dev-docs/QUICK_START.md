# Quick Start & Development Guide

**Version**: 1.0.0  
**Date**: 2026-01-14

Single canonical entry point for developers. Setup, run, and deploy the Browser Automation Service.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Development Setup](#development-setup)
3. [Starting the Server](#starting-the-server)
4. [Environment Configuration](#environment-configuration)
5. [Verifying Installation](#verifying-installation)
6. [Troubleshooting](#troubleshooting)
7. [Production Deployment](#production-deployment)

---

## Prerequisites

### Required

- **Python 3.11+**
- **Docker** (for Temporal, Redis, MongoDB)
- **uv** (Python package manager)

### Install uv

Use official installer from https://docs.astral.sh/uv/

---

## Development Setup

### Step 1: Install Dependencies

```bash
uv venv --python 3.11
source .venv/bin/activate
uv sync
uvx browser-use install
```

### Step 2: Start Infrastructure (Docker)

Start required services:

```bash
# Temporal Server (workflow orchestration)
docker run -d -p 7233:7233 -p 8233:8233 --name temporal-server temporalio/auto-setup:latest

# Redis (events and job queue)
docker run -d -p 6379:6379 --name redis redis:latest

# MongoDB (persistent storage)
docker run -d -p 27017:27017 --name mongodb mongo:latest
```

**Verify**: `docker ps | grep -E "temporal|redis|mongodb"`

### Step 3: Configure Environment

Create `.env.local`:

```bash
TEMPORAL_URL=localhost:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_KNOWLEDGE_QUEUE=knowledge-extraction-queue
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=browser_automation_service
REDIS_URL=redis://localhost:6379
```

Optional variables: LLM keys (OPENAI_API_KEY, ANTHROPIC_API_KEY), LiveKit credentials, Browser Use Cloud key.

---

## Starting the Server

**Single Command**: `uv run python navigator/start_server.py`

**Server Endpoints**:
- Health: `http://localhost:8000/health`
- API Docs: `http://localhost:8000/docs`
- MCP Tools: `POST http://localhost:8000/mcp/tools/call`
- Knowledge API: `http://localhost:8000/api/knowledge/explore/start`
- Temporal UI: `http://localhost:8233`

**What Happens**:
1. Connects to Temporal server
2. Starts embedded Temporal worker
3. Registers workflows and activities
4. Starts FastAPI server on port 8000
5. Enables MCP tools and REST API

---

## Environment Configuration

### Required Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `TEMPORAL_URL` | `localhost:7233` | Temporal server connection |
| `MONGODB_URI` | `mongodb://localhost:27017` | MongoDB connection |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection |

### Optional Variables

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | OpenAI models for semantic analysis |
| `ANTHROPIC_API_KEY` | Claude models |
| `GOOGLE_API_KEY` | Gemini models |
| `LIVEKIT_URL` | LiveKit server for video streaming |
| `LIVEKIT_API_KEY` | LiveKit API key |
| `LIVEKIT_API_SECRET` | LiveKit API secret |
| `BROWSER_USE_API_KEY` | Browser Use Cloud key |
| `BROWSER_USE_LOGGING_LEVEL` | Log level (debug, info, warning, error) |

**Environment File Priority**: `.env.local` > `.env` > system environment

---

## Verifying Installation

### Health Check

`curl http://localhost:8000/health`

Expected: `{"status": "ok", "service": "browser-automation-websocket"}`

### List MCP Tools

`curl http://localhost:8000/mcp/tools | jq`

Expected: List of ~52 MCP tools

### Check Temporal Worker

Look for in server logs:
```
✅ Temporal worker started successfully
   Task queue: knowledge-extraction-queue
   Workflows: ['KnowledgeExtractionWorkflow']
```

### Test Knowledge Extraction

`POST /api/knowledge/explore/start` with `{"start_url": "https://example.com", "max_pages": 5}`

Expected: `{"job_id": "...", "status": "running"}`

### View Workflow in Temporal UI

Visit `http://localhost:8233` to monitor workflow execution

---

## Troubleshooting

### Server Won't Start

**Problem**: `Failed to connect to Temporal`

**Solution**:
- Check: `docker ps | grep temporal`
- If not running: `docker start temporal-server`
- Verify: `curl http://localhost:8233`

**Problem**: `Redis not available`

**Solution**:
- Check: `docker ps | grep redis`
- If not running: `docker start redis`
- Test: `docker exec redis redis-cli ping` (should return PONG)

**Problem**: `MongoDB connection failed`

**Solution**:
- Check: `docker ps | grep mongodb`
- If not running: `docker start mongodb`

### Port Already in Use

**Problem**: `Address already in use: :8000`

**Solution**:
- Find process: `lsof -i :8000`
- Kill process: `kill -9 <PID>`
- Or use different port: `PORT=8080 uv run python navigator/start_server.py`

### Chromium Not Found

**Problem**: `Browser executable not found`

**Solution**: `uvx browser-use install`

### Workflows Not Executing

**Problem**: Jobs queued but not executing

**Solution**:
- Check worker logs for: "✅ Temporal worker started successfully"
- Verify Temporal UI: `http://localhost:8233`
- Check task queue name matches: `knowledge-extraction-queue`

---

## Production Deployment

### Docker Compose Setup

See `docker-compose.yml` in repository for complete configuration.

**Key services**:
- `temporal`: Temporal server
- `redis`: Redis for events
- `mongodb`: MongoDB with persistent volume
- `server`: Browser Automation Service

**Deploy**: `docker-compose up -d`

### Environment Variables for Production

Use managed services:
- Temporal Cloud: `your-namespace.tmprl.cloud:7233`
- MongoDB Atlas: `mongodb+srv://...`
- Redis Cloud: `redis://user:pass@...`

### Scaling

**Horizontal Scaling**: Run multiple worker instances, all poll same task queue.

**Docker Compose**: Use `deploy: replicas: N` for workers

---

## Quick Reference

### Service URLs

| Service | URL | Purpose |
|---------|-----|---------|
| FastAPI Server | http://localhost:8000 | REST API & WebSocket |
| API Docs | http://localhost:8000/docs | Interactive documentation |
| Health Check | http://localhost:8000/health | Service status |
| Temporal UI | http://localhost:8233 | Workflow monitoring |

### Docker Commands

```bash
docker start temporal-server redis mongodb    # Start services
docker stop temporal-server redis mongodb     # Stop services
docker logs -f temporal-server                # View logs
```

### File Locations

```
browse-automation-service/
├── navigator/
│   ├── start_server.py          # Server entry point
│   ├── temporal/                # Temporal workflows
│   ├── knowledge/               # Knowledge extraction
│   └── server/                  # FastAPI server
├── dev-docs/
│   ├── QUICK_START.md          # This file
│   ├── BROWSER_AUTOMATION_AGENT.md
│   └── KNOWLEDGE_EXTRACTION.md
└── .env.local                   # Your configuration
```

---

## Next Steps

1. **Agent Integration**: See `dev-docs/BROWSER_AUTOMATION_AGENT.md`
2. **Knowledge Extraction**: See `dev-docs/KNOWLEDGE_EXTRACTION.md`
3. **API Reference**: Visit http://localhost:8000/docs

---

**Last Updated**: 2026-01-14  
**Version**: 1.0.0

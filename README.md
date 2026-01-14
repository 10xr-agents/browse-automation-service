# Browser Automation Service

Production-ready browser automation service built on [Browser-Use](https://github.com/browser-use/browser-use) with Temporal workflows, LiveKit streaming, and knowledge extraction.

---

## Quick Start

### 1. Install Dependencies

```bash
uv venv --python 3.11
source .venv/bin/activate
uv sync
uvx browser-use install
```

### 2. Start Infrastructure

```bash
# Temporal (workflow orchestration)
docker run -d -p 7233:7233 -p 8233:8233 --name temporal-server temporalio/auto-setup:latest

# Redis (events)
docker run -d -p 6379:6379 --name redis redis:latest

# MongoDB (storage)
docker run -d -p 27017:27017 --name mongodb mongo:latest
```

### 3. Configure Environment

Create `.env.local`:

```bash
TEMPORAL_URL=localhost:7233
MONGODB_URI=mongodb://localhost:27017
REDIS_URL=redis://localhost:6379
```

### 4. Start Server

```bash
uv run python navigator/start_server.py
```

**Service URLs**:
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Temporal UI: http://localhost:8233

---

## Architecture

### Two Major Flows

**1. Presentation/Agent Flow**
- Real-time browser automation with video streaming
- LiveKit WebRTC for low-latency video
- MCP tools for agent control
- Redis Pub/Sub for events

**2. Knowledge Extraction Flow**
- Long-running website exploration
- Temporal workflows for durability
- Semantic analysis and graph storage
- REST API for job management

### Key Components

```
┌─────────────────────────────────────────────────────────────┐
│                  Browser Automation Service                  │
│                                                               │
│  ┌────────────────────────────────────────────────────┐    │
│  │  FastAPI Server (port 8000)                        │    │
│  │  - REST API                                        │    │
│  │  - MCP Tools (52 tools)                            │    │
│  │  - WebSocket Events                                │    │
│  └────────────┬───────────────────────────────────────┘    │
│               │                                             │
│  ┌────────────▼───────────────────────────────────────┐    │
│  │  Temporal Worker (embedded)                         │    │
│  │  - Knowledge extraction workflows                   │    │
│  │  - Page processing activities                       │    │
│  └────────────┬───────────────────────────────────────┘    │
│               │                                             │
│  ┌────────────▼───────────────────────────────────────┐    │
│  │  Browser-Use Core                                   │    │
│  │  - Browser automation (CDP)                         │    │
│  │  - LiveKit streaming                                │    │
│  └──────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Data Storage

- **MongoDB**: Sessions, pages, links, knowledge graph
- **Redis**: Event streams, job status
- **Temporal**: Workflow state, activity history

---

## Documentation

We maintain **3 canonical documentation guides**:

### 1. [Quick Start & Development Guide](dev-docs/QUICK_START.md)

Development setup, server operations, troubleshooting, deployment.

### 2. [Browser Automation Agent Guide](dev-docs/BROWSER_AUTOMATION_AGENT.md)

Agent integration reference with MCP tools (52 tools), browser actions (45+ actions), event schemas, and session lifecycle.

### 3. [Knowledge Extraction Guide](dev-docs/KNOWLEDGE_EXTRACTION.md)

Knowledge extraction pipeline with Temporal workflows, exploration strategies, semantic analysis, storage schemas, and REST API reference.

---

## Quick Reference

### MCP Tools (52 tools available)

**Session Management**:
- `start_browser_session`: Start browser with LiveKit streaming
- `pause_browser_session`: Pause video publishing
- `resume_browser_session`: Resume video publishing
- `close_browser_session`: Close browser session
- `get_browser_context`: Get current browser state
- `get_screen_content`: Get DOM content
- `find_form_fields`: Intelligent form field detection

**Action Execution**:
- `execute_action`: Execute 45+ browser actions (navigate, click, type, scroll, etc.)

See [full MCP tools reference](dev-docs/BROWSER_AUTOMATION_AGENT.md#mcp-tools-reference)

---

### Knowledge Extraction API

**Start exploration**:
```bash
POST /api/knowledge/explore/start
{
  "start_url": "https://example.com",
  "max_pages": 100,
  "max_depth": 3,
  "strategy": "BFS"
}
```

**Monitor progress**:
```bash
GET /api/knowledge/explore/status/{job_id}
```

**Control workflow**:
```bash
POST /api/knowledge/explore/pause
POST /api/knowledge/explore/resume
POST /api/knowledge/explore/cancel
```

See [full API reference](dev-docs/KNOWLEDGE_EXTRACTION.md#rest-api-reference)

---

## Production Deployment

### Docker Compose

```yaml
services:
  temporal:
    image: temporalio/auto-setup:latest
    ports: ["7233:7233", "8233:8233"]
  
  redis:
    image: redis:latest
    ports: ["6379:6379"]
  
  mongodb:
    image: mongo:latest
    ports: ["27017:27017"]
    volumes:
      - mongodb_data:/data/db
  
  server:
    build: .
    ports: ["8000:8000"]
    environment:
      - TEMPORAL_URL=temporal:7233
      - MONGODB_URI=mongodb://mongodb:27017
      - REDIS_URL=redis://redis:6379
```

### Managed Services (Recommended)

- **Temporal Cloud**: https://temporal.io/cloud
- **MongoDB Atlas**: https://cloud.mongodb.com
- **Redis Cloud**: https://redis.com/cloud

---

## Key Features

### Browser Automation
- 52 MCP tools for agent control
- 45+ browser actions (navigate, click, type, scroll, forms, etc.)
- LiveKit WebRTC streaming
- Intelligent form field detection
- Error recovery and retry logic

### Knowledge Extraction
- Temporal workflows for durability
- BFS/DFS exploration strategies
- Semantic analysis (entities, topics, embeddings)
- Knowledge graph storage
- Real-time progress monitoring
- Pause/resume/cancel support

### Agent Integration
- MCP protocol compliance
- Redis Pub/Sub events
- Session lifecycle management
- Authentication patterns
- Comprehensive error handling

---

## Project Structure

```
browse-automation-service/
├── browser_use/            # Browser-Use library (upstream)
├── navigator/              # Our extensions
│   ├── temporal/           # Temporal workflows
│   ├── knowledge/          # Knowledge extraction
│   ├── server/             # FastAPI server
│   ├── streaming/          # LiveKit streaming
│   └── action/             # Action dispatching
├── dev-docs/               # Documentation (3 canonical files)
│   ├── QUICK_START.md
│   ├── BROWSER_AUTOMATION_AGENT.md
│   └── KNOWLEDGE_EXTRACTION.md
├── examples/               # Usage examples
├── tests/                  # Test suite
└── .env.local              # Your configuration
```

---

## Environment Variables

### Required

```bash
TEMPORAL_URL=localhost:7233
MONGODB_URI=mongodb://localhost:27017
REDIS_URL=redis://localhost:6379
```

### Optional

```bash
# LLM API Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...

# LiveKit (for video streaming)
LIVEKIT_URL=wss://...
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...

# Browser Use Cloud
BROWSER_USE_API_KEY=...

# Logging
BROWSER_USE_LOGGING_LEVEL=info
```

---

## Development

### Code Organization

We maintain separation between:
- **`browser_use/`**: Browser-Use core library (upstream code)
- **`navigator/`**: Our extensions and services

See [.cursorrules](.cursorrules) for development guidelines.

### Running Tests

```bash
uv run pytest tests/ci/
```

### Development Mode

```bash
uv run uvicorn navigator.server.websocket:get_app --factory --reload
```

---

## Links

- **Documentation**: [dev-docs/](dev-docs/)
- **API Docs**: http://localhost:8000/docs
- **Temporal UI**: http://localhost:8233
- **Browser-Use**: https://github.com/browser-use/browser-use
- **Browser-Use Docs**: https://docs.browser-use.com

---

## License

MIT License - See [LICENSE](LICENSE)

---

**Version**: 1.0.0  
**Last Updated**: 2026-01-14

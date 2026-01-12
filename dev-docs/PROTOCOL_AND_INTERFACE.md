# Protocol and Interface - Browser Automation Service

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Communication Architecture](#communication-architecture)
4. [Redis Integration](#redis-integration)
5. [REST API](#rest-api)
   - [OpenAPI/Swagger Specification](#openapiswagger-specification)
6. [MCP Protocol](#mcp-protocol)
7. [WebSocket Interface](#websocket-interface)
8. [LiveKit Integration](#livekit-integration)
9. [Event Types](#event-types)
10. [Integration Examples](#integration-examples)

---

## Overview

This document describes all communication protocols and interfaces for interacting with the Browser Automation Service. The service supports multiple communication channels:

- **Redis (BullMQ + Pub/Sub)**: For commands and high-frequency events
- **REST API**: HTTP endpoints for tool execution and knowledge retrieval
- **MCP Protocol**: Model Context Protocol for standardized tool access
- **WebSocket**: Real-time event streaming (fallback to Redis Pub/Sub)
- **LiveKit**: Video streaming and real-time data channels

**Quick Start**: See `dev-docs/START_SERVER.md` for instructions on starting the server.

---

## Quick Start

### Starting the Server

```bash
# 1. Install dependencies
uv sync

# 2. Start Redis (optional but recommended)
redis-server  # Or ensure Redis is running on localhost:6379

# 3. Start the server
uv run python navigator/start_server.py
```

The server will start on `http://localhost:8000` with:
- **REST API**: `http://localhost:8000`
- **WebSocket**: `ws://localhost:8000/mcp/events/{room_name}`
- **Health Check**: `http://localhost:8000/health`
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### Prerequisites

- **Python >= 3.11**
- **Redis** (optional, for BullMQ and Redis Pub/Sub)
- **Chromium** (install with `uvx browser-use install`)

### Environment Variables

Create a `.env` file (optional):

```bash
# Optional: LLM API Keys
OPENAI_API_KEY=your_key
ANTHROPIC_API_KEY=your_key

# Optional: LiveKit (for video streaming)
LIVEKIT_URL=wss://livekit.example.com
LIVEKIT_API_KEY=your_key
LIVEKIT_API_SECRET=your_secret

# Optional: Redis (if not using default)
REDIS_URL=redis://localhost:6379
```

**For detailed setup instructions, see**: `dev-docs/START_SERVER.md`

---

## Communication Architecture

### Critical Architectural Decision

**Important**: This architecture is designed to handle **thousands of concurrent browser sessions** efficiently.

### The Problem

We need two types of communication:
1. **Commands** (Agent → Browser): Reliable, must not be lost (e.g., "Navigate to URL", "Click element")
2. **Events** (Browser → Agent): High-frequency, real-time updates (e.g., "page loaded", "mouse moved", "DOM updated")

Using the wrong technology for each will cause performance issues at scale.

---

### Recommended Architecture

#### 1. Agent → Browser Service (Commands)

**Use: BullMQ (or Redis List)**

**Why BullMQ?**
- ✅ **Reliability**: Commands must not be lost. If Browser Service is restarting or busy, commands sit in the queue until processed.
- ✅ **Retry Logic**: Failed commands can be retried automatically.
- ✅ **Job Management**: Track job status (queued → active → completed/failed).
- ✅ **Scalability**: Handle thousands of concurrent commands efficiently.

**Why NOT REST/WebSocket?**
- ❌ With thousands of agents, managing thousands of HTTP/WebSocket connections is resource-intensive.
- ❌ TCP handshakes add latency.
- ❌ No built-in retry or persistence.

**Implementation:**
```python
# LiveKit Agent (Producer)
from bullmq import Queue
import time

command_queue = Queue("browser_commands") 

async def send_navigation(session_id, url):
    await command_queue.add(
        "navigate", 
        {"url": url, "session_id": session_id},
        job_id=f"{session_id}_{int(time.time())}"  # Prevent duplicates
    )
```

---

#### 2. Browser Service → Agent (Events)

**Use: Redis Pub/Sub** (NOT BullMQ)

**Why Redis Pub/Sub?**
- ✅ **Speed**: Sub-millisecond latency for real-time events.
- ✅ **Fan-Out**: Multiple agents can subscribe to the same channel.
- ✅ **Lightweight**: No persistence overhead - events are fire-and-forget.
- ✅ **High Throughput**: Can handle millions of events per second.

**Why NOT BullMQ?**
- ❌ BullMQ creates a Redis key for every job. If you treat every event as a job, you flood Redis with millions of keys.
- ❌ Persistence overhead for ephemeral events ("mouse moved" events don't need to be stored).
- ❌ State management overhead (queued → active → completed) is unnecessary for real-time events.
- ❌ If an agent misses a "hover" event from 500ms ago, it doesn't matter - no need to queue it.

**Implementation:**
```python
# Browser Service (Publisher)
from redis.asyncio import Redis
import json
import time

redis_client = Redis(host='localhost', port=6379)

async def broadcast_event(session_id, event_type, event_data):
    channel = f"browser:events:{session_id}"
    await redis_client.publish(
        channel,
        json.dumps({
            "type": event_type,
            "data": event_data,
            "timestamp": time.time()
        })
    )
```

```python
# LiveKit Agent (Consumer)
import asyncio
from redis.asyncio import Redis
import json

async def listen_for_events(session_id):
    redis = Redis(host='localhost', port=6379)
    pubsub = redis.pubsub()
    
    # Subscribe to this session's channel
    channel = f"browser:events:{session_id}"
    await pubsub.subscribe(channel)

    async for message in pubsub.listen():
        if message['type'] == 'message':
            event_data = json.loads(message['data'])
            # React immediately (e.g., Speak "Page loaded")
            if event_data['type'] == 'page_loaded':
                await ctx.api.speak("I see the page is ready.")
```

---

#### 3. Heavy Results (Browser → Agent)

**Use: Redis/S3 + Pub/Sub Notification**

For large data (e.g., 5MB scraped JSON, screenshots):
- Store data in Redis (for small data) or S3 (for large data)
- Send notification via Pub/Sub with a reference ID
- Agent retrieves data using the reference ID

**Implementation:**
```python
# Browser Service
async def return_large_result(session_id, result_data):
    # Store large result
    result_id = f"result:{session_id}:{int(time.time())}"
    await redis_client.setex(result_id, 3600, json.dumps(result_data))  # TTL: 1 hour
    
    # Notify via Pub/Sub
    channel = f"browser:events:{session_id}"
    await redis_client.publish(
        channel,
        json.dumps({
            "type": "result_ready",
            "result_id": result_id
        })
    )
```

```python
# LiveKit Agent
async def handle_result_ready(event_data):
    result_id = event_data['result_id']
    result_data = json.loads(await redis_client.get(result_id))
    # Process result_data
```

---

### Summary Strategy

| Communication Type | Direction | Technology | Why? |
|-------------------|-----------|------------|------|
| **Commands** (Navigate, Click, Type) | Agent → Browser | **BullMQ** | Needs persistence & retry if browser is busy. |
| **Real-time Events** (Page loaded, DOM updated, Mouse moved) | Browser → Agent | **Redis Pub/Sub** | Needs <5ms latency. No persistence needed. |
| **Heavy Results** (Scraped data, Screenshots) | Browser → Agent | **Redis/S3 + Pub/Sub** | Store data, notify agent of location via Pub/Sub. |

### Benefits

- **Fast Event Loop**: Pub/Sub keeps real-time events fast (<5ms latency)
- **Reliable Commands**: BullMQ ensures automation tasks never get lost
- **Scalable**: Handles thousands of concurrent sessions efficiently
- **Cost-Effective**: Redis handles both use cases with different patterns

---

## Redis Integration

### Redis Configuration

**Default Connection**: `redis://localhost:6379`

**Environment Variables**:
```bash
REDIS_URL=redis://localhost:6379  # Optional: Custom Redis URL
```

### Redis Pub/Sub Channels

#### Browser Events Channel

**Channel Pattern**: `browser:events:{room_name}`

**Purpose**: Real-time event streaming for browser automation sessions

**Message Format**:
```json
{
  "type": "event_type",
  "room_name": "string",
  "data": {},
  "timestamp": 1234567890.123
}
```

**Event Types**:
- `page_navigation`: Page navigation occurred
- `page_load_complete`: Page finished loading
- `action_completed`: Action completed successfully
- `action_error`: Action failed
- `dom_change`: Significant DOM change
- `browser_error`: Browser error occurred
- `screen_content_update`: Screen content updated
- `presentation_started`: Presentation session started
- `presentation_paused`: Presentation paused
- `presentation_resumed`: Presentation resumed
- `action_queued`: Action queued for execution
- `action_processing`: Action being processed

**Example Subscription**:
```python
from redis.asyncio import Redis
import json

redis = Redis(host='localhost', port=6379)
pubsub = redis.pubsub()

# Subscribe to room's event channel
channel = f"browser:events:{room_name}"
await pubsub.subscribe(channel)

# Listen for events
async for message in pubsub.listen():
    if message['type'] == 'message':
        event = json.loads(message['data'])
        handle_event(event)
```

---

#### Knowledge Retrieval Progress Channels

**Channel Pattern**: `exploration:{job_id}:progress`

**Purpose**: Real-time progress updates for knowledge retrieval jobs

**Message Format**:
```json
{
  "job_id": "string",
  "status": "running",
  "completed": 5,
  "queued": 10,
  "failed": 0,
  "current_url": "https://example.com/page",
  "timestamp": 1234567890.123
}
```

**Channels**:
- `exploration:{job_id}:progress`: Progress updates
- `exploration:{job_id}:page_completed`: Page completion
- `exploration:external_links`: External link detection
- `exploration:errors`: Error notifications

**Example Subscription**:
```python
channel = f"exploration:{job_id}:progress"
await pubsub.subscribe(channel)

async for message in pubsub.listen():
    if message['type'] == 'message':
        progress = json.loads(message['data'])
        print(f"Progress: {progress['completed']}/{progress['queued']}")
```

---

### BullMQ Queues

#### Browser Commands Queue

**Queue Name**: `browser_commands`

**Purpose**: Reliable command processing (Agent → Browser)

**Job Data Format**:
```json
{
  "action_type": "navigate",
  "params": {
    "url": "https://example.com"
  },
  "session_id": "string",
  "room_name": "string"
}
```

**Job Options**:
- `removeOnComplete`: `true` (auto-cleanup completed jobs)
- `attempts`: `3` (retry failed commands)
- `jobId`: Unique job ID (prevents duplicates)

**Example Usage**:
```python
from bullmq import Queue

queue = Queue("browser_commands")

# Add command
await queue.add(
    "navigate",
    {
        "url": "https://example.com",
        "session_id": "session_123",
        "room_name": "room_456"
    },
    {
        "jobId": "navigate_session_123_1234567890",
        "removeOnComplete": True,
        "attempts": 3
    }
)
```

---

#### Knowledge Retrieval Queue

**Queue Name**: `knowledge-retrieval`

**Purpose**: Durable job queue for long-running knowledge retrieval tasks

**Job Data Format**:
```json
{
  "start_url": "https://example.com",
  "max_pages": 100,
  "max_depth": 3,
  "strategy": "BFS",
  "job_id": "string"
}
```

**Job Options**:
- `removeOnComplete`: `false` (keep completed jobs for inspection)
- `removeOnFail`: `false` (keep failed jobs for debugging)
- `jobId`: Job ID for tracking

**Example Usage**:
```python
from navigator.knowledge.job_queue import add_exploration_job

job_id = await add_exploration_job(
    start_url="https://example.com",
    max_pages=100,
    max_depth=3,
    strategy="BFS",
    job_id=None  # Auto-generated if None
)
```

---

## REST API

### Base URL

**Default**: `http://localhost:8000`

### OpenAPI/Swagger Specification

The complete OpenAPI 3.0 specification is available in `dev-docs/openapi.yaml`. This specification can be used to:

- **Generate API clients** in various languages (Python, TypeScript, Go, etc.)
- **View interactive API documentation** using Swagger UI or ReDoc
- **Validate API requests/responses** during development
- **Generate mock servers** for testing
- **Integrate with API gateways** and documentation platforms

**Viewing the API Documentation:**

1. **Swagger UI** (recommended):
   ```bash
   # Install swagger-ui-cli
   npm install -g swagger-ui-cli
   
   # Serve the OpenAPI spec
   swagger-ui dev-docs/openapi.yaml
   ```
   
   Or use the online Swagger Editor: https://editor.swagger.io/

2. **ReDoc**:
   ```bash
   # Install redoc-cli
   npm install -g redoc-cli
   
   # Generate static HTML
   redoc-cli build dev-docs/openapi.yaml
   ```

3. **FastAPI Auto-Generated Docs**:
   If the FastAPI server is running, visit:
   - Swagger UI: `http://localhost:8000/docs`
   - ReDoc: `http://localhost:8000/redoc`

**Using the OpenAPI Spec:**

```python
# Generate Python client using openapi-generator
openapi-generator generate \
  -i dev-docs/openapi.yaml \
  -g python \
  -o ./generated-client

# Or use openapi-python-client
pip install openapi-python-client
openapi-python-client generate --path dev-docs/openapi.yaml
```

```typescript
// Generate TypeScript client
openapi-generator generate \
  -i dev-docs/openapi.yaml \
  -g typescript-axios \
  -o ./generated-client
```

**FastAPI Auto-Generated Documentation:**

FastAPI automatically generates OpenAPI documentation from your code. When the server is running:

- **Swagger UI**: Visit `http://localhost:8000/docs` for interactive API documentation
- **ReDoc**: Visit `http://localhost:8000/redoc` for alternative documentation view
- **OpenAPI JSON**: Visit `http://localhost:8000/openapi.json` for the OpenAPI spec in JSON format

**Note**: The `dev-docs/openapi.yaml` file is a manually maintained specification that matches the actual API. FastAPI's auto-generated docs are based on the code, while the YAML file provides a stable, version-controlled reference.

**Integrating OpenAPI Spec with FastAPI:**

If you want to use the YAML spec file instead of auto-generated docs, you can load it in FastAPI:

```python
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
import yaml

app = FastAPI()

# Load custom OpenAPI spec
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    with open("dev-docs/openapi.yaml", "r") as f:
        spec = yaml.safe_load(f)
    
    app.openapi_schema = spec
    return app.openapi_schema

app.openapi = custom_openapi
```

**Validating the OpenAPI Spec:**

```bash
# Install swagger-cli
npm install -g @apidevtools/swagger-cli

# Validate the spec
swagger-cli validate dev-docs/openapi.yaml

# Bundle the spec (resolve $ref references)
swagger-cli bundle dev-docs/openapi.yaml -o openapi-bundled.yaml
```

---

### Browser Automation Endpoints

#### POST `/mcp/tools/call`

**Purpose**: Execute MCP tools via HTTP

**Request:**
```json
{
  "tool": "start_browser_session",
  "arguments": {
    "room_name": "demo-room",
    "initial_url": "https://www.google.com"
  }
}
```

**Response:**
```json
{
  "status": "started",
  "room_name": "demo-room"
}
```

---

#### GET `/mcp/tools`

**Purpose**: List all available MCP tools

**Response:**
```json
{
  "tools": [
    {
      "name": "start_browser_session",
      "description": "Start a browser session for a LiveKit room with video streaming"
    },
    {
      "name": "execute_action",
      "description": "Execute a browser action command"
    }
    // ... more tools
  ]
}
```

---

#### GET `/health`

**Purpose**: Health check endpoint

**Response:**
```json
{
  "status": "ok",
  "service": "browser-automation-websocket"
}
```

---

#### GET `/rooms/{room_name}/connections`

**Purpose**: Get WebSocket connection count for a room

**Response:**
```json
{
  "room_name": "demo-room",
  "connections": 2
}
```

---

### Knowledge Retrieval Endpoints

#### POST `/api/knowledge/explore/start`

**Purpose**: Start a knowledge retrieval job

**Request:**
```json
{
  "start_url": "https://example.com",
  "max_pages": 100,
  "max_depth": 3,
  "strategy": "BFS",
  "job_id": "optional-job-id"
}
```

**Response:**
```json
{
  "job_id": "generated-job-id",
  "status": "queued",
  "message": "Job queued via BullMQ. Use /api/knowledge/explore/status/{job_id} to check progress."
}
```

---

#### GET `/api/knowledge/explore/status/{job_id}`

**Purpose**: Get live progress for a job

**Response:**
```json
{
  "job_id": "string",
  "status": "running",
  "progress": {
    "completed": 5,
    "queued": 10,
    "failed": 0,
    "current_url": "https://example.com/page"
  },
  "started_at": "2025-01-12T10:00:00Z",
  "updated_at": "2025-01-12T10:05:00Z"
}
```

---

#### POST `/api/knowledge/explore/pause`

**Purpose**: Pause a running job

**Request:**
```json
{
  "job_id": "string"
}
```

**Response:**
```json
{
  "job_id": "string",
  "status": "paused"
}
```

---

#### POST `/api/knowledge/explore/resume`

**Purpose**: Resume a paused job

**Request:**
```json
{
  "job_id": "string"
}
```

**Response:**
```json
{
  "job_id": "string",
  "status": "running"
}
```

---

#### POST `/api/knowledge/explore/cancel`

**Purpose**: Cancel a job

**Request:**
```json
{
  "job_id": "string"
}
```

**Response:**
```json
{
  "job_id": "string",
  "status": "cancelled"
}
```

---

#### GET `/api/knowledge/explore/results/{job_id}`

**Purpose**: Get job results (partial or final)

**Query Parameters**:
- `partial`: `true` or `false` (default: `false`) - If `true`, return partial results even if job is still running

**Response:**
```json
{
  "job_id": "string",
  "status": "completed",
  "results": {
    "pages_stored": 50,
    "links_stored": 200,
    "external_links_detected": 10,
    "errors": []
  },
  "pages": [
    {
      "url": "https://example.com",
      "title": "Example",
      "content": "..."
    }
  ],
  "links": [
    {
      "from": "https://example.com",
      "to": "https://example.com/page1",
      "type": "internal"
    }
  ]
}
```

---

#### GET `/api/knowledge/explore/jobs`

**Purpose**: List all jobs

**Response:**
```json
{
  "jobs": [
    {
      "job_id": "string",
      "status": "running",
      "start_url": "https://example.com",
      "started_at": "2025-01-12T10:00:00Z"
    }
  ]
}
```

---

## MCP Protocol

The Browser Automation Service exposes capabilities as MCP tools, allowing external services to control browser automation via the Model Context Protocol.

### MCP Server Configuration

**Server Name**: `browser-automation-service`

**Connection**: 
- **HTTP**: `http://localhost:8000/mcp/tools/call`
- **WebSocket**: `ws://localhost:8000/mcp/events/{room_name}` (optional, Redis Pub/Sub preferred)
- **STDIO**: For Claude Desktop integration

### Browser Automation Tools

#### 1. `start_browser_session`

**Purpose**: Start a new browser session for a LiveKit room with video streaming

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "room_name": {
      "type": "string",
      "description": "LiveKit room name (required)"
    },
    "livekit_url": {
      "type": "string",
      "description": "LiveKit server URL (optional if LIVEKIT_URL env var is set)"
    },
    "livekit_api_key": {
      "type": "string",
      "description": "LiveKit API key (optional if LIVEKIT_API_KEY env var is set)"
    },
    "livekit_api_secret": {
      "type": "string",
      "description": "LiveKit API secret (optional if LIVEKIT_API_SECRET env var is set)"
    },
    "livekit_token": {
      "type": "string",
      "description": "Pre-generated LiveKit access token (optional if api_key/secret provided)"
    },
    "initial_url": {
      "type": "string",
      "description": "Optional initial URL to navigate to"
    },
    "viewport_width": {
      "type": "integer",
      "description": "Browser viewport width in pixels",
      "default": 1920
    },
    "viewport_height": {
      "type": "integer",
      "description": "Browser viewport height in pixels",
      "default": 1080
    },
    "fps": {
      "type": "integer",
      "description": "Video frames per second",
      "default": 10
    }
  },
  "required": ["room_name"]
}
```

**Output Schema:**
```json
{
  "status": "started",
  "room_name": "string"
}
```

---

#### 2. `pause_browser_session`

**Purpose**: Pause video publishing for a browser session (keep browser alive)

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "room_name": {
      "type": "string",
      "description": "LiveKit room name"
    }
  },
  "required": ["room_name"]
}
```

**Output Schema:**
```json
{
  "status": "paused",
  "room_name": "string"
}
```

---

#### 3. `resume_browser_session`

**Purpose**: Resume video publishing for a browser session

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "room_name": {
      "type": "string",
      "description": "LiveKit room name"
    }
  },
  "required": ["room_name"]
}
```

**Output Schema:**
```json
{
  "status": "resumed",
  "room_name": "string"
}
```

---

#### 4. `close_browser_session`

**Purpose**: Close a browser session and stop streaming

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "room_name": {
      "type": "string",
      "description": "LiveKit room name"
    }
  },
  "required": ["room_name"]
}
```

**Output Schema:**
```json
{
  "status": "closed",
  "room_name": "string"
}
```

---

#### 5. `execute_action`

**Purpose**: Execute a browser action command

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "room_name": {
      "type": "string",
      "description": "LiveKit room name"
    },
    "action_type": {
      "type": "string",
      "enum": ["navigate", "click", "type", "scroll", "wait", "go_back", "refresh", "send_keys"],
      "description": "Type of action to execute"
    },
    "params": {
      "type": "object",
      "description": "Action-specific parameters"
    }
  },
  "required": ["room_name", "action_type"]
}
```

**Action Types and Parameters:**

**`navigate`**:
```json
{
  "action_type": "navigate",
  "params": {
    "url": "https://example.com"
  }
}
```

**`click`**:
```json
{
  "action_type": "click",
  "params": {
    "index": 0
  }
}
```

**`type`**:
```json
{
  "action_type": "type",
  "params": {
    "text": "Hello World",
    "index": 0
  }
}
```

**`scroll`**:
```json
{
  "action_type": "scroll",
  "params": {
    "direction": "down",
    "amount": 500
  }
}
```

**`wait`**:
```json
{
  "action_type": "wait",
  "params": {
    "seconds": 2.0
  }
}
```

**`send_keys`**:
```json
{
  "action_type": "send_keys",
  "params": {
    "keys": "Enter"
  }
}
```

**Output Schema:**
```json
{
  "success": true,
  "error": null,
  "data": {}
}
```

---

#### 6. `get_browser_context`

**Purpose**: Get current browser context (URL, title, ready state, scroll position, viewport, cursor position)

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "room_name": {
      "type": "string",
      "description": "LiveKit room name"
    }
  },
  "required": ["room_name"]
}
```

**Output Schema:**
```json
{
  "url": "string",
  "title": "string",
  "ready_state": "string",
  "scroll_x": 0,
  "scroll_y": 0,
  "viewport_width": 1920,
  "viewport_height": 1080,
  "cursor_x": 0,
  "cursor_y": 0
}
```

---

#### 7. `get_screen_content`

**Purpose**: Get screen content with DOM summary, scroll position, viewport, and cursor position for agent communication

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "room_name": {
      "type": "string",
      "description": "LiveKit room name"
    }
  },
  "required": ["room_name"]
}
```

**Output Schema:**
```json
{
  "url": "string",
  "title": "string",
  "dom_summary": "string",
  "visible_elements_count": 0,
  "scroll_x": 0,
  "scroll_y": 0,
  "viewport_width": 1920,
  "viewport_height": 1080,
  "cursor_x": 0,
  "cursor_y": 0
}
```

---

#### 8. `recover_browser_session`

**Purpose**: Attempt to recover a failed browser session (reconnect LiveKit, restore state)

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "room_name": {
      "type": "string",
      "description": "LiveKit room name"
    }
  },
  "required": ["room_name"]
}
```

**Output Schema:**
```json
{
  "status": "recovered",
  "room_name": "string"
}
```

---

### Knowledge Retrieval Tools

#### 9. `start_knowledge_exploration`

**Purpose**: Start a knowledge retrieval job to explore and extract knowledge from a website

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "start_url": {
      "type": "string",
      "description": "Starting URL for exploration"
    },
    "max_pages": {
      "type": "integer",
      "description": "Maximum number of pages to explore (optional)"
    },
    "max_depth": {
      "type": "integer",
      "description": "Maximum exploration depth (default: 3)"
    },
    "strategy": {
      "type": "string",
      "enum": ["BFS", "DFS"],
      "description": "Exploration strategy: BFS (breadth-first) or DFS (depth-first)"
    },
    "job_id": {
      "type": "string",
      "description": "Optional job ID (auto-generated if not provided)"
    }
  },
  "required": ["start_url"]
}
```

**Output Schema:**
```json
{
  "job_id": "string",
  "status": "queued",
  "message": "Job started successfully"
}
```

---

#### 10. `get_exploration_status`

**Purpose**: Get live status and progress for a knowledge retrieval job

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "job_id": {
      "type": "string",
      "description": "Job ID"
    }
  },
  "required": ["job_id"]
}
```

**Output Schema:**
```json
{
  "job_id": "string",
  "status": "running",
  "progress": {
    "completed": 5,
    "queued": 10,
    "failed": 0,
    "current_url": "https://example.com/page"
  }
}
```

---

#### 11. `pause_exploration`

**Purpose**: Pause a running knowledge retrieval job

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "job_id": {
      "type": "string",
      "description": "Job ID"
    }
  },
  "required": ["job_id"]
}
```

**Output Schema:**
```json
{
  "job_id": "string",
  "status": "paused"
}
```

---

#### 12. `resume_exploration`

**Purpose**: Resume a paused knowledge retrieval job

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "job_id": {
      "type": "string",
      "description": "Job ID"
    }
  },
  "required": ["job_id"]
}
```

**Output Schema:**
```json
{
  "job_id": "string",
  "status": "running"
}
```

---

#### 13. `cancel_exploration`

**Purpose**: Cancel a knowledge retrieval job

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "job_id": {
      "type": "string",
      "description": "Job ID"
    }
  },
  "required": ["job_id"]
}
```

**Output Schema:**
```json
{
  "job_id": "string",
  "status": "cancelled"
}
```

---

#### 14. `get_knowledge_results`

**Purpose**: Get results for a knowledge retrieval job

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "job_id": {
      "type": "string",
      "description": "Job ID"
    },
    "partial": {
      "type": "boolean",
      "description": "If true, return partial results even if job is still running",
      "default": false
    }
  },
  "required": ["job_id"]
}
```

**Output Schema:**
```json
{
  "job_id": "string",
  "status": "completed",
  "results": {
    "pages_stored": 50,
    "links_stored": 200,
    "external_links_detected": 10
  }
}
```

---

#### 15. `query_knowledge`

**Purpose**: Query stored knowledge (pages, semantic search, links, sitemaps)

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "query_type": {
      "type": "string",
      "enum": ["page", "search", "links", "sitemap_semantic", "sitemap_functional"],
      "description": "Type of query"
    },
    "params": {
      "type": "object",
      "description": "Query-specific parameters"
    }
  },
  "required": ["query_type"]
}
```

**Query Types:**

**`page`**:
```json
{
  "query_type": "page",
  "params": {
    "url": "https://example.com"
  }
}
```

**`search`**:
```json
{
  "query_type": "search",
  "params": {
    "query": "search terms",
    "top_k": 5
  }
}
```

**`links`**:
```json
{
  "query_type": "links",
  "params": {
    "url": "https://example.com",
    "direction": "from"
  }
}
```

**`sitemap_semantic`**:
```json
{
  "query_type": "sitemap_semantic",
  "params": {}
}
```

**`sitemap_functional`**:
```json
{
  "query_type": "sitemap_functional",
  "params": {}
}
```

**Output Schema:**
```json
{
  "success": true,
  "data": {},
  "error": null
}
```

---

## WebSocket Interface

### WebSocket Endpoint

**URL**: `/mcp/events/{room_name}`

**Purpose**: Alternative real-time event streaming via WebSocket (optional fallback)

**Note**: The primary event streaming mechanism is **Redis Pub/Sub** for better performance and scalability. WebSocket is available as an optional fallback for clients that prefer it.

**Connection:**
```javascript
const ws = new WebSocket('ws://localhost:8000/mcp/events/demo-room');
```

**Message Format:**
All events are sent as JSON strings.

**Example Event:**
```json
{
  "type": "page_navigation",
  "room_name": "demo-room",
  "url": "https://www.google.com",
  "timestamp": 1234567890.123
}
```

---

## LiveKit Integration

### LiveKit Room Connection

**Purpose**: Video streaming and real-time data

**Transport**: WebRTC via LiveKit

**Connection Flow:**
- **Browser Service → LiveKit**: Video track publishing
- **LiveKit → Agent**: Video track subscription
- **Both services**: Data channels for real-time events (optional)

**Configuration**:
- **Environment Variables**:
  - `LIVEKIT_URL`: LiveKit server URL (e.g., `wss://livekit.example.com`)
  - `LIVEKIT_API_KEY`: LiveKit API key
  - `LIVEKIT_API_SECRET`: LiveKit API secret
- **Or**: Provide pre-generated token via `livekit_token` parameter

**Video Streaming**:
- **Frame Rate**: Configurable (default: 10 FPS)
- **Viewport**: Configurable (default: 1920x1080)
- **Encoding**: H.264
- **Quality**: Adaptive based on network conditions

---

## Event Types

### Browser Automation Events

#### `page_navigation`

**Purpose**: Notify agent when page navigation occurs

**Schema:**
```json
{
  "type": "page_navigation",
  "room_name": "string",
  "url": "string",
  "timestamp": 1234567890.123
}
```

---

#### `page_load_complete`

**Purpose**: Notify agent when page finishes loading

**Schema:**
```json
{
  "type": "page_load_complete",
  "room_name": "string",
  "url": "string",
  "timestamp": 1234567890.123
}
```

---

#### `action_completed`

**Purpose**: Notify agent when an action completes successfully

**Schema:**
```json
{
  "type": "action_completed",
  "room_name": "string",
  "action": {
    "action_type": "string",
    "params": {}
  },
  "timestamp": 1234567890.123
}
```

---

#### `action_error`

**Purpose**: Notify agent when an action fails

**Schema:**
```json
{
  "type": "action_error",
  "room_name": "string",
  "error": "string",
  "action": {
    "action_type": "string",
    "params": {}
  },
  "timestamp": 1234567890.123
}
```

---

#### `dom_change`

**Purpose**: Notify agent of significant DOM changes

**Schema:**
```json
{
  "type": "dom_change",
  "room_name": "string",
  "change_type": "string",
  "timestamp": 1234567890.123
}
```

---

#### `browser_error`

**Purpose**: Notify agent of browser errors

**Schema:**
```json
{
  "type": "browser_error",
  "room_name": "string",
  "error": "string",
  "timestamp": 1234567890.123
}
```

---

#### `screen_content_update`

**Purpose**: Broadcast screen content updates for agent communication

**Schema:**
```json
{
  "type": "screen_content_update",
  "room_name": "string",
  "screen_content": {
    "url": "string",
    "title": "string",
    "dom_summary": "string",
    "visible_elements_count": 0,
    "scroll_x": 0,
    "scroll_y": 0,
    "viewport_width": 1920,
    "viewport_height": 1080,
    "cursor_x": 0,
    "cursor_y": 0
  },
  "timestamp": 1234567890.123
}
```

---

#### `presentation_started`

**Purpose**: Notify agent when presentation session starts

**Schema:**
```json
{
  "type": "presentation_started",
  "room_name": "string",
  "session_id": "string",
  "timestamp": 1234567890.123
}
```

---

#### `presentation_paused`

**Purpose**: Notify agent when presentation is paused

**Schema:**
```json
{
  "type": "presentation_paused",
  "room_name": "string",
  "session_id": "string",
  "timestamp": 1234567890.123
}
```

---

#### `presentation_resumed`

**Purpose**: Notify agent when presentation is resumed

**Schema:**
```json
{
  "type": "presentation_resumed",
  "room_name": "string",
  "session_id": "string",
  "timestamp": 1234567890.123
}
```

---

#### `action_queued`

**Purpose**: Notify agent when action is queued for execution

**Schema:**
```json
{
  "type": "action_queued",
  "room_name": "string",
  "action": {
    "action_type": "string",
    "params": {}
  },
  "timestamp": 1234567890.123
}
```

---

#### `action_processing`

**Purpose**: Notify agent when action is being processed

**Schema:**
```json
{
  "type": "action_processing",
  "room_name": "string",
  "action": {
    "action_type": "string",
    "params": {}
  },
  "timestamp": 1234567890.123
}
```

---

### Knowledge Retrieval Events

#### `exploration_progress`

**Purpose**: Real-time progress updates for knowledge retrieval jobs

**Schema:**
```json
{
  "type": "exploration_progress",
  "job_id": "string",
  "status": "running",
  "completed": 5,
  "queued": 10,
  "failed": 0,
  "current_url": "https://example.com/page",
  "timestamp": 1234567890.123
}
```

---

#### `page_completed`

**Purpose**: Notify when a page is completed during exploration

**Schema:**
```json
{
  "type": "page_completed",
  "job_id": "string",
  "url": "https://example.com/page",
  "success": true,
  "timestamp": 1234567890.123
}
```

---

#### `external_link_detected`

**Purpose**: Notify when an external link is detected (not followed)

**Schema:**
```json
{
  "type": "external_link_detected",
  "job_id": "string",
  "from_url": "https://example.com",
  "external_url": "https://external.com",
  "timestamp": 1234567890.123
}
```

---

#### `exploration_error`

**Purpose**: Notify when an error occurs during exploration

**Schema:**
```json
{
  "type": "exploration_error",
  "job_id": "string",
  "url": "https://example.com/page",
  "error": "string",
  "timestamp": 1234567890.123
}
```

---

## Integration Examples

### Agent Side (MCP Client)

```python
import httpx
import asyncio
from redis.asyncio import Redis
import json

class BrowserController:
    def __init__(self, mcp_server_url: str, room_name: str):
        self.mcp_url = mcp_server_url
        self.room_name = room_name
        self.session = None
        self.redis = None
        self.pubsub = None
    
    async def connect(self):
        """Connect to MCP server (HTTP and Redis Pub/Sub)"""
        # HTTP client for tool calls
        self.session = httpx.AsyncClient(
            base_url=self.mcp_url,
            timeout=30.0
        )
        
        # Redis Pub/Sub for events
        self.redis = Redis(host='localhost', port=6379)
        self.pubsub = self.redis.pubsub()
        
        # Subscribe to room's event channel
        channel = f"browser:events:{self.room_name}"
        await self.pubsub.subscribe(channel)
        
        # Start event listener
        asyncio.create_task(self._listen_for_events())
    
    async def _listen_for_events(self):
        """Listen for events from browser service via Redis Pub/Sub"""
        try:
            async for message in self.pubsub.listen():
                if message['type'] == 'message':
                    event = json.loads(message['data'])
                    event_type = event.get("type")
                    
                    # Handle event
                    if event_type == "page_navigation":
                        await self._on_page_navigation(event)
                    elif event_type == "action_error":
                        await self._on_action_error(event)
                    # ... more handlers
        except Exception as e:
            logger.error(f"Error in event listener: {e}")
    
    async def call_tool(self, tool_name: str, arguments: dict):
        """Call MCP tool via HTTP"""
        response = await self.session.post(
            "/mcp/tools/call",
            json={
                "tool": tool_name,
                "arguments": arguments
            }
        )
        return response.json()
    
    async def start_browser_session(self, **kwargs):
        return await self.call_tool("start_browser_session", {
            "room_name": self.room_name,
            **kwargs
        })
    
    async def execute_action(self, action_type: str, params: dict):
        return await self.call_tool("execute_action", {
            "room_name": self.room_name,
            "action_type": action_type,
            "params": params
        })
    
    async def start_knowledge_exploration(self, start_url: str, **kwargs):
        return await self.call_tool("start_knowledge_exploration", {
            "start_url": start_url,
            **kwargs
        })
```

---

### Knowledge Retrieval Client

```python
import httpx
import asyncio
from redis.asyncio import Redis
import json

class KnowledgeRetrievalClient:
    def __init__(self, api_url: str = "http://localhost:8000"):
        self.api_url = api_url
        self.session = httpx.AsyncClient(base_url=api_url)
        self.redis = Redis(host='localhost', port=6379)
    
    async def start_exploration(self, start_url: str, **kwargs):
        """Start knowledge retrieval job"""
        response = await self.session.post(
            "/api/knowledge/explore/start",
            json={
                "start_url": start_url,
                **kwargs
            }
        )
        return response.json()
    
    async def get_status(self, job_id: str):
        """Get job status"""
        response = await self.session.get(
            f"/api/knowledge/explore/status/{job_id}"
        )
        return response.json()
    
    async def subscribe_to_progress(self, job_id: str, callback):
        """Subscribe to progress updates via Redis Pub/Sub"""
        pubsub = self.redis.pubsub()
        channel = f"exploration:{job_id}:progress"
        await pubsub.subscribe(channel)
        
        async for message in pubsub.listen():
            if message['type'] == 'message':
                progress = json.loads(message['data'])
                await callback(progress)
    
    async def pause_job(self, job_id: str):
        """Pause job"""
        response = await self.session.post(
            "/api/knowledge/explore/pause",
            json={"job_id": job_id}
        )
        return response.json()
    
    async def resume_job(self, job_id: str):
        """Resume job"""
        response = await self.session.post(
            "/api/knowledge/explore/resume",
            json={"job_id": job_id}
        )
        return response.json()
    
    async def get_results(self, job_id: str, partial: bool = False):
        """Get job results"""
        response = await self.session.get(
            f"/api/knowledge/explore/results/{job_id}",
            params={"partial": partial}
        )
        return response.json()
```

---

### Using BullMQ for Commands

```python
from bullmq import Queue
import time

# Create queue
command_queue = Queue("browser_commands")

# Send navigation command
async def navigate(session_id: str, url: str):
    await command_queue.add(
        "navigate",
        {
            "url": url,
            "session_id": session_id,
            "room_name": f"room_{session_id}"
        },
        {
            "jobId": f"navigate_{session_id}_{int(time.time())}",
            "removeOnComplete": True,
            "attempts": 3
        }
    )

# Send click command
async def click(session_id: str, index: int):
    await command_queue.add(
        "click",
        {
            "index": index,
            "session_id": session_id,
            "room_name": f"room_{session_id}"
        },
        {
            "jobId": f"click_{session_id}_{int(time.time())}",
            "removeOnComplete": True,
            "attempts": 3
        }
    )
```

---

### Using Redis Pub/Sub for Events

```python
from redis.asyncio import Redis
import json
import asyncio

async def listen_for_browser_events(room_name: str):
    """Listen for browser events via Redis Pub/Sub"""
    redis = Redis(host='localhost', port=6379)
    pubsub = redis.pubsub()
    
    channel = f"browser:events:{room_name}"
    await pubsub.subscribe(channel)
    
    async for message in pubsub.listen():
        if message['type'] == 'message':
            event = json.loads(message['data'])
            event_type = event.get("type")
            
            # Handle different event types
            if event_type == "page_navigation":
                print(f"Navigated to: {event['url']}")
            elif event_type == "action_completed":
                print(f"Action completed: {event['action']['action_type']}")
            elif event_type == "action_error":
                print(f"Action failed: {event['error']}")
            # ... more handlers

# Start listening
asyncio.run(listen_for_browser_events("demo-room"))
```

---

### Using REST API

```python
import httpx

async def control_browser():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # Start browser session
        response = await client.post(
            "/mcp/tools/call",
            json={
                "tool": "start_browser_session",
                "arguments": {
                    "room_name": "demo-room",
                    "initial_url": "https://www.google.com"
                }
            }
        )
        print(response.json())
        
        # Execute action
        response = await client.post(
            "/mcp/tools/call",
            json={
                "tool": "execute_action",
                "arguments": {
                    "room_name": "demo-room",
                    "action_type": "click",
                    "params": {"index": 0}
                }
            }
        )
        print(response.json())
        
        # Get browser context
        response = await client.post(
            "/mcp/tools/call",
            json={
                "tool": "get_browser_context",
                "arguments": {
                    "room_name": "demo-room"
                }
            }
        )
        print(response.json())
```

---

## Connection Pooling Best Practices

### ⚠️ Critical: Connection Pooling

With thousands of agents, you cannot open a new Redis connection for every single message.

**❌ DON'T DO THIS:**
```python
async def send_event():
    redis = Redis()  # New connection every time - BAD!
    await redis.publish(...)
```

**✅ DO THIS:**
```python
# Global connection pool (shared across all agents in process)
_redis_pool = None

async def get_redis():
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = Redis(host='localhost', port=6379)
    return _redis_pool

async def send_event():
    redis = await get_redis()  # Reuse connection pool
    await redis.publish(...)
```

---

## Error Handling

### Connection Failures

**Redis Connection Failure**:
- Service gracefully degrades to in-memory fallback
- Events logged but not published
- Commands queued in-memory (lost on restart)

**BullMQ Connection Failure**:
- Service falls back to in-memory queue
- Jobs processed in-memory (lost on restart)
- Warning logged

**LiveKit Connection Failure**:
- Browser session continues without streaming
- Error logged
- Agent notified via Redis Pub/Sub

### Retry Logic

**BullMQ Commands**:
- Automatic retry (3 attempts by default)
- Exponential backoff between retries
- Failed jobs kept for inspection

**HTTP Requests**:
- Client-side retry recommended
- Exponential backoff
- Timeout handling

---

## Performance Considerations

### Redis Pub/Sub

- **Latency**: Sub-millisecond for local Redis
- **Throughput**: Millions of events per second
- **Fan-Out**: Multiple subscribers per channel
- **No Persistence**: Events are fire-and-forget

### BullMQ

- **Latency**: ~1-5ms for job queuing
- **Throughput**: Thousands of jobs per second
- **Persistence**: Jobs stored in Redis
- **Retry**: Automatic retry with backoff

### WebSocket

- **Latency**: ~10-50ms (network dependent)
- **Throughput**: Limited by connection count
- **Persistence**: No persistence (connection-based)
- **Use Case**: Fallback for clients that prefer WebSocket

---

*Last Updated: 2025-01-12*
*Version: 1.0.0*

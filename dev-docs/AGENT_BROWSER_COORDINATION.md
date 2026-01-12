# Agent-Browser Coordination Protocol

## Overview

This document describes the complete protocol for communication and coordination between the **Browser Automation Service** and external agents (Voice Agent Service, CLI tools, Web UI, etc.). The protocol enables real-time browser automation with video streaming, bidirectional event communication, and comprehensive action execution.

## Communication Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         LiveKit Room                             │
│                                                                   │
│  ┌──────────────────┐              ┌──────────────────────┐   │
│  │  External Agent   │              │  Browser Automation   │   │
│  │  (Server A)       │              │  (Server B)           │   │
│  │                  │              │                       │   │
│  │  - Subscribes to │◀─────────────│  - Publishes video    │   │
│  │    video track   │   LiveKit     │    track directly    │   │
│  │  - Publishes     │   WebRTC      │  - Joins room as     │   │
│  │    audio track   │              │    participant       │   │
│  └──────────────────┘              └──────────────────────┘   │
│         │                                    │                   │
└─────────┼────────────────────────────────────┼──────────────────┘
          │                                    │
          │                                    │
          │          Redis (BullMQ + Pub/Sub)  │
          └────────────────────────────────────┘
              (Commands & Events)
```

**Key Principles:**
- Browser Automation Service publishes video **directly to LiveKit** (no relay through agent)
- Both services connect to the **same LiveKit room**
- **Commands** (Agent → Browser): Use **BullMQ** for reliable, persistent command processing
- **Events** (Browser → Agent): Use **Redis Pub/Sub** for high-frequency, real-time events
- Video flows through LiveKit WebRTC, not between servers
- Bidirectional event communication via Redis Pub/Sub

---

## Communication Architecture: Redis (BullMQ + Pub/Sub)

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

## Dual Communication Mechanism

The system uses **three communication channels** for different purposes:

### Channel 1: BullMQ (Commands)

**Purpose:** Reliable command processing (Agent → Browser)

**Transport:** Redis-based job queue (BullMQ)

**Communication Flow:**
- **Agent → Browser Service**: Action commands, session control (via BullMQ queue)
- Commands persist in Redis, won't be lost if service restarts
- Automatic retry logic for failed commands
- Job status tracking (queued → active → completed/failed)

### Channel 2: Redis Pub/Sub (Events)

**Purpose:** High-frequency, real-time events (Browser → Agent)

**Transport:** Redis Pub/Sub

**Communication Flow:**
- **Browser Service → Agent**: Action results, browser state, error responses, real-time events (via Redis Pub/Sub)
- Sub-millisecond latency for real-time updates
- Fan-out to multiple subscribers
- Fire-and-forget events (no persistence overhead)

### Channel 3: LiveKit Room

**Purpose:** Video streaming and real-time data

**Transport:** WebRTC via LiveKit

**Communication Flow:**
- **Browser Service → LiveKit**: Video track publishing
- **LiveKit → Agent**: Video track subscription
- **Both services**: Data channels for real-time events (optional)

---

## MCP Tools

The Browser Automation Service exposes the following MCP tools:

### 1. `start_browser_session`

**Purpose:** Start a new browser session for a LiveKit room with video streaming.

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
      "description": "LiveKit server URL (e.g., 'wss://livekit.example.com') (optional if LIVEKIT_URL env var is set)"
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
    "participant_identity": {
      "type": "string",
      "description": "Participant identity for token generation (default: 'browser-agent')"
    },
    "participant_name": {
      "type": "string",
      "description": "Participant name for token generation (default: 'Browser Automation Agent')"
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

**Example:**
```json
{
  "tool": "start_browser_session",
  "arguments": {
    "room_name": "demo-room-123",
    "initial_url": "https://www.google.com",
    "viewport_width": 1920,
    "viewport_height": 1080,
    "fps": 10
  }
}
```

---

### 2. `pause_browser_session`

**Purpose:** Pause video publishing for a browser session (keep browser alive).

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

### 3. `resume_browser_session`

**Purpose:** Resume video publishing for a browser session.

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

### 4. `close_browser_session`

**Purpose:** Close a browser session and stop streaming.

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

### 5. `execute_action`

**Purpose:** Execute a browser action command.

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

#### `navigate`
```json
{
  "action_type": "navigate",
  "params": {
    "url": "https://example.com"
  }
}
```

#### `click`
```json
{
  "action_type": "click",
  "params": {
    "index": 0
  }
}
```

#### `type`
```json
{
  "action_type": "type",
  "params": {
    "text": "Hello World",
    "index": 0
  }
}
```

#### `scroll`
```json
{
  "action_type": "scroll",
  "params": {
    "direction": "down",
    "amount": 500
  }
}
```

#### `wait`
```json
{
  "action_type": "wait",
  "params": {
    "seconds": 2.0
  }
}
```

#### `send_keys`
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

### 6. `get_browser_context`

**Purpose:** Get current browser context (URL, title, ready state, scroll position, viewport, cursor position).

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

### 7. `get_screen_content`

**Purpose:** Get screen content with DOM summary, scroll position, viewport, and cursor position for agent communication.

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

### 8. `recover_browser_session`

**Purpose:** Attempt to recover a failed browser session (reconnect LiveKit, restore state).

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

## WebSocket Events

The Browser Automation Service broadcasts the following events via WebSocket:

### Event: `page_navigation`

**Purpose:** Notify agent when page navigation occurs.

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

### Event: `page_load_complete`

**Purpose:** Notify agent when page finishes loading.

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

### Event: `action_completed`

**Purpose:** Notify agent when an action completes successfully.

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

### Event: `action_error`

**Purpose:** Notify agent when an action fails.

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

### Event: `dom_change`

**Purpose:** Notify agent of significant DOM changes.

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

### Event: `browser_error`

**Purpose:** Notify agent of browser errors.

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

### Event: `screen_content_update`

**Purpose:** Broadcast screen content updates for agent communication.

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

### Event: `vision_analysis_complete`

**Purpose:** Notify agent when vision analysis completes (for self-correction).

**Schema:**
```json
{
  "type": "vision_analysis_complete",
  "room_name": "string",
  "analysis_id": "string",
  "visual_understanding": {
    "blockers": ["popup", "loading_indicator"],
    "suggested_actions": ["close_popup", "wait"],
    "confidence": 0.95
  },
  "failed_action": {
    "action_type": "string",
    "params": {}
  },
  "timestamp": 1234567890.123
}
```

---

### Event: `self_correction_attempt`

**Purpose:** Notify agent when self-correction is attempted.

**Schema:**
```json
{
  "type": "self_correction_attempt",
  "room_name": "string",
  "original_action": {
    "action_type": "string",
    "params": {}
  },
  "corrective_action": {
    "action_type": "string",
    "params": {}
  },
  "attempt_number": 1,
  "max_attempts": 3,
  "timestamp": 1234567890.123
}
```

---

## HTTP REST API

### POST `/mcp/tools/call`

**Purpose:** Execute MCP tools via HTTP.

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

### GET `/mcp/tools`

**Purpose:** List all available MCP tools.

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

### GET `/health`

**Purpose:** Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "service": "browser-automation-websocket"
}
```

---

### GET `/rooms/{room_name}/connections`

**Purpose:** Get WebSocket connection count for a room.

**Response:**
```json
{
  "room_name": "demo-room",
  "connections": 2
}
```

---

## Redis Pub/Sub Channel

### `browser:events:{room_name}`

**Purpose:** Real-time event streaming for a specific room via Redis Pub/Sub.

**Connection:**
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
        # Handle event
        handle_event(event)
```

**Message Format:**
All events are sent as JSON strings via Redis Pub/Sub.

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

## WebSocket Endpoint (Legacy/Optional)

### `/mcp/events/{room_name}`

**Purpose:** Alternative real-time event streaming via WebSocket (optional fallback).

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

## Complete Session Lifecycle

### Phase 1: Agent Session Initialization

**When:** User starts interaction

**Flow:**
1. User connects to LiveKit room via frontend
2. External Agent Service receives job request
3. Agent session starts
4. Agent joins LiveKit room as participant
5. **Browser service is NOT yet active** - no video track published

**State:**
- ✅ Agent active
- ❌ Browser automation inactive
- ❌ No video track in room

---

### Phase 2: Initiating Screen Share

**When:** User requests browser interaction or agent determines browser is needed

**Flow:**
1. **Agent** detects need for browser
2. **Agent** makes MCP call to Browser Automation Service:
   ```python
   result = await mcp_client.call_tool(
       name="start_browser_session",
       arguments={
           "room_name": room_name,
           "initial_url": "https://www.google.com"
       }
   )
   ```

3. **Browser Service** receives MCP call:
   - Launches browser
   - Connects to LiveKit room
   - Starts video publishing
   - Stores session state

4. **Browser Service** connects to LiveKit room and starts publishing video track
5. **Agent** detects new video track in room and subscribes

**State:**
- ✅ Agent active
- ✅ Browser automation active
- ✅ Video track published and subscribed
- ✅ Agent can see browser content

---

### Phase 3: Active Browser Interaction

**When:** User requests browser actions or agent needs to interact with page

**Flow:**
1. **User speaks**: "Click the login button"
2. **Agent** processes:
   - Transcribes speech
   - LLM generates action plan
   - Determines browser action needed

3. **Agent** sends action via MCP:
   ```python
   result = await mcp_client.call_tool(
       name="execute_action",
       arguments={
           "room_name": room_name,
           "action_type": "click",
           "params": {"index": 5}
       }
   )
   ```

4. **Browser Service** receives and executes:
   - Executes action
   - Broadcasts events (action_started, action_completed)
   - Continues publishing video frames

5. **Browser Service** broadcasts events via WebSocket:
   - `action_completed`: Action succeeded
   - `page_navigation`: If navigation occurred
   - `page_load_complete`: When page finishes loading

6. **Agent** receives updated video frame via LiveKit subscription
7. **Agent** analyzes with vision LLM
8. **Agent** speaks response to user

**State:**
- ✅ Continuous video stream (10-15 FPS)
- ✅ Real-time action execution
- ✅ Vision analysis of results
- ✅ Bidirectional communication via MCP

---

### Phase 4: Pausing Screen Share

**When:** User requests to pause or agent determines browser not needed temporarily

**Flow:**
1. **Agent** sends pause command via MCP
2. **Browser Service** pauses video publishing (keeps browser alive)
3. **Agent** detects video track removed and unsubscribes

**State:**
- ✅ Agent active
- ⏸️ Browser automation paused (browser still running)
- ❌ No video track in room

---

### Phase 5: Resuming Screen Share

**When:** User requests browser interaction again

**Flow:**
1. **Agent** sends resume command via MCP
2. **Browser Service** resumes video publishing
3. **Agent** detects new video track and resubscribes

**State:**
- ✅ Agent active
- ✅ Browser automation resumed
- ✅ Video track published again

---

### Phase 6: Closing Screen Share

**When:** User explicitly closes browser or agent determines browser no longer needed

**Flow:**
1. **Agent** sends close command via MCP
2. **Browser Service** closes browser and disconnects:
   - Stops video publishing
   - Unpublishes video track
   - Closes browser
   - Disconnects from LiveKit
   - Cleans up session

3. **Agent** detects video track removed

**State:**
- ✅ Agent active
- ❌ Browser automation closed
- ❌ No video track in room

---

### Phase 7: Agent Session Termination

**When:** User ends interaction

**Flow:**
1. **Agent** receives session termination signal
2. **Agent** checks if browser session is active and closes if needed
3. **Agent** disconnects from LiveKit room
4. **Browser Service** (if still active) receives disconnect event and cleans up

**State:**
- ❌ Agent terminated
- ❌ Browser automation terminated
- ❌ Room closed

---

## Error Handling & Recovery

### Browser Service Failures

**Scenario:** Browser crashes or becomes unresponsive

**Recovery:**
1. Browser service detects failure
2. Sends `browser_error` event via Redis Pub/Sub to agent
3. Agent receives event in Pub/Sub handler
4. Agent informs user and offers to restart
5. If user agrees, agent enqueues command via BullMQ: `start_browser_session`

---

### Network Interruptions

**Scenario:** LiveKit connection lost

**Recovery:**
1. Both services implement reconnection logic
2. Browser service republishes video track on reconnect
3. Agent resubscribes to video track
4. MCP connection retries automatically

---

### Action Failures

**Scenario:** Browser action fails (element not found, timeout, etc.)

**Recovery:**
1. Browser service sends `action_error` event via Redis Pub/Sub
2. Agent receives event in Pub/Sub handler
3. Agent uses vision to analyze current page state (latest video frame)
4. Agent generates corrective action and enqueues via BullMQ, or asks user for clarification

---

## Performance Optimization

### Frame Rate Management

- **Static pages**: 1-2 FPS
- **Active interactions**: 10-15 FPS
- **Rapid changes**: 20-30 FPS (if needed)

### Bandwidth Optimization

- Use simulcast for adaptive quality
- Adjust bitrate based on network conditions
- Consider frame skipping during high activity

### Latency Minimization

- Minimize screenshot capture time
- Use efficient encoding (H.264)
- Optimize frame conversion pipeline
- Keep MCP calls asynchronous

---

## Security Considerations

### Access Control

- Validate room tokens before allowing browser connections
- Restrict browser automation to authorized domains
- Validate actions before execution
- Log all browser actions for audit

### Content Filtering

- Filter sensitive content before streaming
- Respect privacy settings
- Handle authentication pages carefully
- Don't stream passwords or sensitive form data

---

## Implementation Examples

### Agent Side (MCP Client)

```python
import httpx
import websockets
import json

class BrowserController:
    def __init__(self, mcp_server_url: str, room_name: str):
        self.mcp_url = mcp_server_url
        self.room_name = room_name
        self.session = None
        self.websocket = None
    
    async def connect(self):
        """Connect to MCP server (HTTP and WebSocket)"""
        # HTTP client for tool calls
        self.session = httpx.AsyncClient(
            base_url=self.mcp_url,
            timeout=30.0
        )
        
        # WebSocket connection for events
        ws_url = self.mcp_url.replace("http://", "ws://").replace("https://", "wss://")
        self.websocket = await websockets.connect(
            f"{ws_url}/mcp/events/{self.room_name}"
        )
        
        # Start event listener
        asyncio.create_task(self._listen_for_events())
    
    async def _listen_for_events(self):
        """Listen for events from browser service"""
        try:
            async for message in self.websocket:
                event = json.loads(message)
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
```

---

*Last Updated: 2025*
*Version: 1.0.0*

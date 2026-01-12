# Agent-Browser Coordination Protocol

## Table of Contents

1. [Overview](#overview)
2. [Communication Architecture](#communication-architecture)
3. [Complete Session Lifecycle](#complete-session-lifecycle)
4. [Error Handling & Recovery](#error-handling--recovery)
5. [Performance Optimization](#performance-optimization)
6. [Security Considerations](#security-considerations)
7. [Implementation Examples](#implementation-examples)

---

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

3. **Agent** sends action via MCP or BullMQ:
   ```python
   # Option 1: Via MCP (HTTP)
   result = await mcp_client.call_tool(
       name="execute_action",
       arguments={
           "room_name": room_name,
           "action_type": "click",
           "params": {"index": 5}
       }
   )
   
   # Option 2: Via BullMQ (recommended for reliability)
   await command_queue.add(
       "click",
       {
           "room_name": room_name,
           "index": 5
       },
       job_id=f"click_{room_name}_{int(time.time())}"
   )
   ```

4. **Browser Service** receives and executes:
   - Executes action
   - Broadcasts events (action_started, action_completed) via Redis Pub/Sub
   - Continues publishing video frames

5. **Browser Service** broadcasts events via Redis Pub/Sub:
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
- ✅ Bidirectional communication via MCP/BullMQ + Redis Pub/Sub

---

### Phase 4: Pausing Screen Share

**When:** User requests to pause or agent determines browser not needed temporarily

**Flow:**
1. **Agent** sends pause command via MCP or BullMQ
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
1. **Agent** sends resume command via MCP or BullMQ
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
1. **Agent** sends close command via MCP or BullMQ
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

### Knowledge Retrieval Job Failures

**Scenario:** Knowledge retrieval job fails (network error, timeout, etc.)

**Recovery:**
1. Job status updated to `failed`
2. Error details stored in job registry
3. Progress observer emits error event
4. Agent can:
   - Retry job with same parameters
   - Resume from last successful page
   - Cancel and start new job

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
- Use Redis Pub/Sub for events (<5ms latency)

### Command Processing

- Use BullMQ for reliable command queuing
- Batch commands when possible
- Implement rate limiting to prevent overload
- Use connection pooling for Redis

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

### Domain Restrictions

- Use `allowed_domains` to restrict navigation
- Use `prohibited_domains` to block specific sites
- Validate URLs before navigation
- Log domain violations for audit

---

## Implementation Examples

### Agent Side (MCP Client with Redis Pub/Sub)

```python
import httpx
import asyncio
from redis.asyncio import Redis
from bullmq import Queue
import json
import logging

logger = logging.getLogger(__name__)

class BrowserController:
    def __init__(self, mcp_server_url: str, room_name: str):
        self.mcp_url = mcp_server_url
        self.room_name = room_name
        self.session = None
        self.redis = None
        self.pubsub = None
        self.command_queue = None
    
    async def connect(self):
        """Connect to MCP server (HTTP), Redis Pub/Sub, and BullMQ"""
        # HTTP client for tool calls
        self.session = httpx.AsyncClient(
            base_url=self.mcp_url,
            timeout=30.0
        )
        
        # Redis Pub/Sub for events
        self.redis = Redis(host='localhost', port=6379)
        self.pubsub = self.redis.pubsub()
        
        # BullMQ for commands
        self.command_queue = Queue("browser_commands")
        
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
                    elif event_type == "action_completed":
                        await self._on_action_completed(event)
                    elif event_type == "action_error":
                        await self._on_action_error(event)
                    elif event_type == "browser_error":
                        await self._on_browser_error(event)
                    # ... more handlers
        except Exception as e:
            logger.error(f"Error in event listener: {e}")
    
    async def _on_page_navigation(self, event):
        """Handle page navigation event"""
        url = event.get("url")
        logger.info(f"Page navigated to: {url}")
        # React to navigation (e.g., speak to user)
    
    async def _on_action_completed(self, event):
        """Handle action completion event"""
        action = event.get("action", {})
        logger.info(f"Action completed: {action.get('action_type')}")
        # React to completion
    
    async def _on_action_error(self, event):
        """Handle action error event"""
        error = event.get("error")
        action = event.get("action", {})
        logger.warning(f"Action failed: {action.get('action_type')} - {error}")
        # React to error (e.g., retry, ask user)
    
    async def _on_browser_error(self, event):
        """Handle browser error event"""
        error = event.get("error")
        logger.error(f"Browser error: {error}")
        # React to browser error (e.g., restart session)
    
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
    
    async def send_command_via_bullmq(self, action_type: str, params: dict):
        """Send command via BullMQ (recommended for reliability)"""
        await self.command_queue.add(
            action_type,
            {
                "room_name": self.room_name,
                **params
            },
            {
                "jobId": f"{action_type}_{self.room_name}_{int(time.time())}",
                "removeOnComplete": True,
                "attempts": 3
            }
        )
    
    async def start_browser_session(self, **kwargs):
        """Start browser session"""
        return await self.call_tool("start_browser_session", {
            "room_name": self.room_name,
            **kwargs
        })
    
    async def execute_action(self, action_type: str, params: dict, use_bullmq: bool = True):
        """Execute browser action"""
        if use_bullmq:
            # Use BullMQ for reliability
            await self.send_command_via_bullmq(action_type, params)
            return {"status": "queued"}
        else:
            # Use MCP HTTP for immediate execution
            return await self.call_tool("execute_action", {
                "room_name": self.room_name,
                "action_type": action_type,
                "params": params
            })
    
    async def pause_browser_session(self):
        """Pause browser session"""
        return await self.call_tool("pause_browser_session", {
            "room_name": self.room_name
        })
    
    async def resume_browser_session(self):
        """Resume browser session"""
        return await self.call_tool("resume_browser_session", {
            "room_name": self.room_name
        })
    
    async def close_browser_session(self):
        """Close browser session"""
        return await self.call_tool("close_browser_session", {
            "room_name": self.room_name
        })
    
    async def get_browser_context(self):
        """Get current browser context"""
        return await self.call_tool("get_browser_context", {
            "room_name": self.room_name
        })
    
    async def get_screen_content(self):
        """Get screen content for agent communication"""
        return await self.call_tool("get_screen_content", {
            "room_name": self.room_name
        })
```

---

### Knowledge Retrieval Coordination

```python
import asyncio
from redis.asyncio import Redis
import json

class KnowledgeRetrievalCoordinator:
    def __init__(self, api_url: str, job_id: str):
        self.api_url = api_url
        self.job_id = job_id
        self.redis = Redis(host='localhost', port=6379)
        self.pubsub = None
    
    async def start_exploration(self, start_url: str, **kwargs):
        """Start knowledge retrieval and monitor progress"""
        import httpx
        
        # Start exploration via REST API
        async with httpx.AsyncClient(base_url=self.api_url) as client:
            response = await client.post(
                "/api/knowledge/explore/start",
                json={
                    "start_url": start_url,
                    "job_id": self.job_id,
                    **kwargs
                }
            )
            result = response.json()
            self.job_id = result.get("job_id", self.job_id)
        
        # Subscribe to progress updates
        await self._subscribe_to_progress()
        
        return result
    
    async def _subscribe_to_progress(self):
        """Subscribe to progress updates via Redis Pub/Sub"""
        self.pubsub = self.redis.pubsub()
        channel = f"exploration:{self.job_id}:progress"
        await self.pubsub.subscribe(channel)
        
        # Start progress listener
        asyncio.create_task(self._listen_to_progress())
    
    async def _listen_to_progress(self):
        """Listen for progress updates"""
        try:
            async for message in self.pubsub.listen():
                if message['type'] == 'message':
                    progress = json.loads(message['data'])
                    await self._on_progress(progress)
        except Exception as e:
            logger.error(f"Error in progress listener: {e}")
    
    async def _on_progress(self, progress: dict):
        """Handle progress update"""
        status = progress.get("status")
        completed = progress.get("completed", 0)
        queued = progress.get("queued", 0)
        current_url = progress.get("current_url")
        
        logger.info(
            f"Progress: {status} | "
            f"Completed: {completed} | "
            f"Queued: {queued} | "
            f"Current: {current_url}"
        )
        
        # React to progress (e.g., update UI, notify user)
    
    async def pause(self):
        """Pause exploration"""
        import httpx
        async with httpx.AsyncClient(base_url=self.api_url) as client:
            response = await client.post(
                "/api/knowledge/explore/pause",
                json={"job_id": self.job_id}
            )
            return response.json()
    
    async def resume(self):
        """Resume exploration"""
        import httpx
        async with httpx.AsyncClient(base_url=self.api_url) as client:
            response = await client.post(
                "/api/knowledge/explore/resume",
                json={"job_id": self.job_id}
            )
            return response.json()
    
    async def cancel(self):
        """Cancel exploration"""
        import httpx
        async with httpx.AsyncClient(base_url=self.api_url) as client:
            response = await client.post(
                "/api/knowledge/explore/cancel",
                json={"job_id": self.job_id}
            )
            return response.json()
    
    async def get_results(self, partial: bool = False):
        """Get exploration results"""
        import httpx
        async with httpx.AsyncClient(base_url=self.api_url) as client:
            response = await client.get(
                f"/api/knowledge/explore/results/{self.job_id}",
                params={"partial": partial}
            )
            return response.json()
```

---

### Complete Coordination Example

```python
import asyncio
from browser_controller import BrowserController
from knowledge_retrieval_coordinator import KnowledgeRetrievalCoordinator

async def coordinate_browser_and_knowledge():
    """Example of coordinating browser automation and knowledge retrieval"""
    
    # Initialize browser controller
    browser = BrowserController(
        mcp_server_url="http://localhost:8000",
        room_name="demo-room"
    )
    await browser.connect()
    
    # Start browser session
    await browser.start_browser_session(
        initial_url="https://example.com"
    )
    
    # Execute some actions
    await browser.execute_action("navigate", {"url": "https://example.com/page1"})
    await browser.execute_action("click", {"index": 0})
    await browser.execute_action("type", {"text": "Hello", "index": 0})
    
    # Start knowledge retrieval for the same site
    knowledge = KnowledgeRetrievalCoordinator(
        api_url="http://localhost:8000",
        job_id=None  # Auto-generated
    )
    
    result = await knowledge.start_exploration(
        start_url="https://example.com",
        max_pages=50,
        max_depth=3,
        strategy="BFS"
    )
    
    # Monitor both browser and knowledge retrieval
    # (progress updates come via Redis Pub/Sub)
    
    # Pause knowledge retrieval if needed
    await knowledge.pause()
    
    # Continue browser automation
    await browser.execute_action("scroll", {"direction": "down", "amount": 500})
    
    # Resume knowledge retrieval
    await knowledge.resume()
    
    # Get knowledge results when done
    results = await knowledge.get_results(partial=True)
    print(f"Pages stored: {results['results']['pages_stored']}")
    
    # Close browser session
    await browser.close_browser_session()
```

---

## Best Practices

### 1. Use BullMQ for Commands

**✅ DO:**
```python
# Reliable command queuing
await command_queue.add("navigate", {...}, {"attempts": 3})
```

**❌ DON'T:**
```python
# Direct HTTP calls for critical commands (no retry, no persistence)
await http_client.post("/mcp/tools/call", ...)
```

### 2. Use Redis Pub/Sub for Events

**✅ DO:**
```python
# Subscribe to Redis Pub/Sub for real-time events
await pubsub.subscribe(f"browser:events:{room_name}")
```

**❌ DON'T:**
```python
# Poll HTTP endpoints for events (high latency, inefficient)
while True:
    events = await http_client.get("/events")
    await asyncio.sleep(1)  # Polling delay
```

### 3. Connection Pooling

**✅ DO:**
```python
# Reuse Redis connection
_redis = Redis(host='localhost', port=6379)
await _redis.publish(...)
```

**❌ DON'T:**
```python
# New connection every time
redis = Redis()  # Creates new connection - BAD!
await redis.publish(...)
```

### 4. Error Handling

**✅ DO:**
```python
try:
    result = await browser.execute_action("click", {"index": 0})
    if not result.get("success"):
        # Handle error
        await handle_action_error(result)
except Exception as e:
    logger.error(f"Action failed: {e}")
    # Retry or notify user
```

**❌ DON'T:**
```python
# Ignore errors
await browser.execute_action("click", {"index": 0})
# No error handling - BAD!
```

### 5. Session Lifecycle Management

**✅ DO:**
```python
# Always close sessions
try:
    await browser.start_browser_session(...)
    # ... use browser ...
finally:
    await browser.close_browser_session()  # Always cleanup
```

**❌ DON'T:**
```python
# Leave sessions open
await browser.start_browser_session(...)
# ... use browser ...
# Forgot to close - BAD! (zombie browser processes)
```

---

*Last Updated: 2025-01-12*
*Version: 1.0.0*

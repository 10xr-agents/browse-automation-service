# Browser Automation Service - Implementation Guide

## Overview

This guide provides a detailed, step-by-step implementation plan for converting the Browser Automation Service into a production-ready server with two major flows:

1. **Presentation/Agent Flow**: Real-time browser automation with video streaming for live demonstrations
2. **Knowledge Retrieval & Storage Flow**: Comprehensive website exploration and knowledge extraction

**Important Architecture Note**: 

We are **extending the Browser-Use codebase directly** (we have the source code in `browser_use/` directory), not building on top of it as an external library. This approach provides:

- **Better Performance**: Direct access to source code, no abstraction overhead
- **Full Control**: Can modify Browser-Use internals (BrowserSession, BrowserProfile, Tools, etc.) directly
- **Optimization**: Optimize Browser-Use components specifically for our use cases
- **Integration**: Seamlessly integrate new capabilities with existing Browser-Use components

Our MVP extensions (`mvp/` directory) extend existing Browser-Use functionality, and we can modify Browser-Use source code directly in `browser_use/` if needed for performance or functionality improvements.

---

## Implementation Philosophy

### Step-by-Step Approach

Each implementation phase is broken down into:
1. **Small, Incremental Steps**: Each step builds on the previous one
2. **Testing Checkpoints**: Test after each major step before proceeding
3. **Verification Steps**: Verify functionality works as expected
4. **Integration Tests**: Test components work together
5. **Documentation Updates**: Update docs as we build

### Testing Strategy

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test components work together
- **End-to-End Tests**: Test complete flows
- **Performance Tests**: Test with realistic workloads
- **Regression Tests**: Ensure existing functionality still works

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

**Why NOT REST?**
- ❌ With thousands of agents, managing thousands of HTTP connections is resource-intensive.
- ❌ TCP handshakes add latency.
- ❌ No built-in retry or persistence.

**Implementation**:
```python
# LiveKit Agent (Producer)
from bullmq import Queue

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

**Implementation**:
```python
# Browser Service (Publisher)
from redis.asyncio import Redis

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

**Implementation**:
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

### Technology Stack Updates

**Required Dependencies**:
- `bullmq` - Job queue for commands
- `redis` (async) - Redis client for Pub/Sub and data storage
- `redis-py` - Python Redis client

**Installation**:
```bash
uv add bullmq redis redis-py
```

---

### Implementation Steps

This architecture will be integrated into:
1. **Step 1.16**: Enhanced Event Broadcasting - Replace WebSocket with Redis Pub/Sub
2. **Step 1.4**: Presentation Flow Manager - Add BullMQ integration for command queue
3. **Step 1.13-1.15**: Action Queue Management - Integrate with BullMQ

---

---

## Part 1: Presentation/Agent Flow

### Overview

The Presentation/Agent Flow enables live browser automation for presentations, demonstrations, and interactive sessions. It provides:

- Agent session management with room-based isolation
- Real-time screen streaming to LiveKit
- MCP-based action execution from external services
- Extensive human-like presentation actions
- Session timeout (6 hours) or explicit close
- Event broadcasting for real-time feedback

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    External Agent Service                     │
│  (Voice Agent, CLI, Web UI, etc.)                           │
└────────────────────┬────────────────────────────────────────┘
                     │
                     │ MCP Protocol (HTTP/WebSocket)
                     │
┌────────────────────▼────────────────────────────────────────┐
│         Browser Automation Service Server                   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Presentation Flow Manager                            │  │
│  │  - Session lifecycle (start, pause, resume, close)   │  │
│  │  - 6-hour timeout management                         │  │
│  │  - Action queue management                           │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Presentation Action Registry                         │  │
│  │  - Extensive human-like actions                      │  │
│  │  - Presentation-specific actions                     │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Browser Session Manager (existing)                   │  │
│  │  - Per-room session management                       │  │
│  │  - LiveKit streaming                                 │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### Implementation Steps

#### Step 1.1: Presentation Flow Manager - Basic Structure

**Goal**: Create basic presentation flow manager with session tracking

**Implementation**:
1. Create `presentation/flow_manager.py`
2. Implement `PresentationFlowManager` class with:
   - Session dictionary tracking
   - Basic session lifecycle methods (`start_session`, `close_session`)
   - Session state tracking (active, paused, closed)

**Testing Checkpoint 1.1**:
- [ ] Unit test: Create flow manager instance
- [ ] Unit test: Start session and verify it's tracked
- [ ] Unit test: Close session and verify cleanup
- [ ] Integration test: Create and close multiple sessions

**Verification**:
```python
# Test basic session management
manager = PresentationFlowManager()
session_id = await manager.start_session(room_name="test_room")
assert session_id in manager.sessions
await manager.close_session(session_id)
assert session_id not in manager.sessions
```

---

#### Step 1.2: Presentation Flow Manager - Timeout Management

**Goal**: Add 6-hour timeout handling

**Implementation**:
1. Add session start time tracking
2. Add background task for timeout monitoring
3. Implement timeout detection (6 hours)
4. Add graceful shutdown on timeout

**Testing Checkpoint 1.2**:
- [ ] Unit test: Verify timeout detection (use short timeout for testing, e.g., 1 minute)
- [ ] Unit test: Verify timeout triggers session cleanup
- [ ] Integration test: Create session, wait for timeout, verify cleanup

**Verification**:
```python
# Test timeout with short duration (1 minute for testing)
manager = PresentationFlowManager(timeout_minutes=1)
session_id = await manager.start_session(room_name="test_room")
await asyncio.sleep(65)  # Wait for timeout
# Verify session is cleaned up
assert session_id not in manager.sessions
```

---

#### Step 1.3: Presentation Flow Manager - BullMQ Integration

**Goal**: Add action queue management using BullMQ for reliable command processing

**Implementation**:
1. Install BullMQ and configure Redis connection
2. Create BullMQ queue for browser commands: `browser_commands`
3. Integrate BullMQ into `PresentationFlowManager`:
   - Replace in-memory queue with BullMQ queue
   - Implement `enqueue_action` using `queue.add()`
   - Implement worker to process queue with `QueueWorker`
4. Add queue status tracking
5. Add retry logic for failed actions

**Why BullMQ?**
- Reliability: Commands persist in Redis, won't be lost if service restarts
- Retry logic: Failed commands automatically retried
- Job tracking: Monitor job status (queued → active → completed/failed)
- Scalability: Handle thousands of concurrent commands

**Testing Checkpoint 1.3**:
- [ ] Unit test: BullMQ connection
- [ ] Unit test: Enqueue actions via BullMQ and verify ordering
- [ ] Unit test: Process queue and verify actions executed
- [ ] Integration test: Enqueue multiple actions, process queue, verify execution order
- [ ] Integration test: Service restart, verify queued actions persist
- [ ] Performance test: Enqueue 1000 actions, measure throughput

**Verification**:
```python
# Test BullMQ action queue
from bullmq import Queue
from bullmq.types import JobOptions

queue = Queue("browser_commands")
manager = PresentationFlowManager(command_queue=queue)

session_id = await manager.start_session(room_name="test_room")
await manager.enqueue_action(session_id, {"type": "navigate", "url": "https://example.com"})
await manager.enqueue_action(session_id, {"type": "click", "index": 0})

# Verify jobs in queue
jobs = await queue.getJobs(['waiting'])
assert len(jobs) == 2

# Process queue (using worker)
await manager.process_queue(session_id)

# Verify jobs completed
completed = await queue.getJobs(['completed'])
assert len(completed) == 2
```

---

#### Step 1.4: Presentation Flow Manager - Integration with Browser Session Manager

**Goal**: Integrate with existing `BrowserSessionManager`

**Implementation**:
1. Integrate `BrowserSessionManager` into `PresentationFlowManager`
2. Connect session lifecycle to browser sessions
3. Add browser session cleanup on timeout/close

**Testing Checkpoint 1.4**:
- [ ] Integration test: Start presentation session, verify browser session created
- [ ] Integration test: Close presentation session, verify browser session closed
- [ ] Integration test: Timeout triggers browser session cleanup

**Verification**:
```python
# Test integration
manager = PresentationFlowManager()
session_id = await manager.start_session(room_name="test_room")
# Verify browser session exists
browser_session = manager.get_browser_session(session_id)
assert browser_session is not None
await manager.close_session(session_id)
# Verify browser session cleaned up
```

---

#### Step 1.5: Presentation Action Registry - Basic Actions

**Goal**: Extend existing action dispatcher with basic presentation actions

**Implementation**:
1. Review existing actions in `ActionDispatcher`
2. Identify actions that need extension
3. Create `presentation/action_registry.py`
4. Implement wrapper around `ActionDispatcher` for presentation actions

**Testing Checkpoint 1.5**:
- [ ] Unit test: Verify action registry initialization
- [ ] Unit test: Verify action registration
- [ ] Integration test: Execute basic actions (navigate, click, type)

**Verification**:
```python
# Test action registry
registry = PresentationActionRegistry(action_dispatcher)
result = await registry.execute_action("navigate", {"url": "https://example.com"})
assert result.success
```

---

#### Step 1.6: Presentation Action Registry - Advanced Navigation Actions

**Goal**: Add advanced navigation actions (go_back, go_forward, refresh, reload)

**Implementation**:
1. Implement `go_back` action
2. Implement `go_forward` action
3. Implement `refresh` action
4. Implement `reload` action

**Testing Checkpoint 1.6**:
- [ ] Unit test: Each navigation action independently
- [ ] Integration test: Navigate → go_back → verify URL
- [ ] Integration test: Refresh and verify page reload

**Verification**:
```python
# Test navigation actions
await registry.execute_action("navigate", {"url": "https://example.com/page1"})
await registry.execute_action("navigate", {"url": "https://example.com/page2"})
await registry.execute_action("go_back")
# Verify we're back at page1
```

---

#### Step 1.7: Presentation Action Registry - Interaction Actions

**Goal**: Add interaction actions (right_click, double_click, hover, drag_drop)

**Implementation**:
1. Implement `right_click` action
2. Implement `double_click` action
3. Implement `hover` action
4. Implement `drag_drop` action

**Testing Checkpoint 1.7**:
- [ ] Unit test: Each interaction action independently
- [ ] Integration test: Right-click and verify context menu
- [ ] Integration test: Double-click and verify action
- [ ] Integration test: Drag and drop element

**Verification**:
```python
# Test interaction actions
await registry.execute_action("right_click", {"index": 0})
# Verify context menu appears
await registry.execute_action("double_click", {"index": 0})
# Verify double-click action executed
```

---

#### Step 1.8: Presentation Action Registry - Text Input Actions

**Goal**: Add text input actions (type_slowly, clear, select_all, copy, paste, cut)

**Implementation**:
1. Implement `type_slowly` action (with delays)
2. Implement `clear` action
3. Implement `select_all` action (Ctrl+A)
4. Implement `copy` action (Ctrl+C)
5. Implement `paste` action (Ctrl+V)
6. Implement `cut` action (Ctrl+X)

**Testing Checkpoint 1.8**:
- [ ] Unit test: Each text input action independently
- [ ] Integration test: Type slowly and verify timing
- [ ] Integration test: Copy/paste flow
- [ ] Integration test: Select all and copy

**Verification**:
```python
# Test text input actions
await registry.execute_action("type_slowly", {"index": 0, "text": "Hello", "delay": 0.1})
# Verify text typed with delays
await registry.execute_action("select_all")
await registry.execute_action("copy")
await registry.execute_action("paste", {"index": 1})
# Verify text copied and pasted
```

---

#### Step 1.9: Presentation Action Registry - Form Actions

**Goal**: Add form actions (fill_form, select_dropdown, select_multiple, upload_file, submit_form, reset_form)

**Implementation**:
1. Implement `fill_form` action (fill multiple fields)
2. Implement `select_dropdown` action
3. Implement `select_multiple` action
4. Implement `upload_file` action
5. Implement `submit_form` action
6. Implement `reset_form` action

**Testing Checkpoint 1.9**:
- [ ] Unit test: Each form action independently
- [ ] Integration test: Fill form with multiple fields
- [ ] Integration test: Select dropdown and verify selection
- [ ] Integration test: Submit form and verify submission

**Verification**:
```python
# Test form actions
await registry.execute_action("fill_form", {
    "fields": [
        {"index": 0, "value": "John"},
        {"index": 1, "value": "Doe"}
    ]
})
await registry.execute_action("submit_form", {"index": 0})
# Verify form submitted
```

---

#### Step 1.10: Presentation Action Registry - Media Actions

**Goal**: Add media actions (play_video, pause_video, seek_video, adjust_volume, toggle_fullscreen, toggle_mute)

**Implementation**:
1. Implement `play_video` action
2. Implement `pause_video` action
3. Implement `seek_video` action
4. Implement `adjust_volume` action
5. Implement `toggle_fullscreen` action
6. Implement `toggle_mute` action

**Testing Checkpoint 1.10**:
- [ ] Unit test: Each media action independently
- [ ] Integration test: Play video and verify playback
- [ ] Integration test: Seek video and verify position
- [ ] Integration test: Toggle fullscreen and verify state

**Verification**:
```python
# Test media actions
await registry.execute_action("play_video", {"index": 0})
# Verify video playing
await registry.execute_action("seek_video", {"index": 0, "timestamp": 30})
# Verify video seeked to 30 seconds
```

---

#### Step 1.11: Presentation Action Registry - Advanced Actions

**Goal**: Add advanced actions (keyboard_shortcut, multi_select, highlight_element, zoom_in, zoom_out, zoom_reset, take_screenshot, download_file)

**Implementation**:
1. Implement `keyboard_shortcut` action
2. Implement `multi_select` action
3. Implement `highlight_element` action (visual feedback)
4. Implement zoom actions (zoom_in, zoom_out, zoom_reset)
5. Implement `take_screenshot` action
6. Implement `download_file` action

**Testing Checkpoint 1.11**:
- [ ] Unit test: Each advanced action independently
- [ ] Integration test: Keyboard shortcuts (Ctrl+S, Alt+F4)
- [ ] Integration test: Zoom in/out and verify zoom level
- [ ] Integration test: Take screenshot and verify file created

**Verification**:
```python
# Test advanced actions
await registry.execute_action("keyboard_shortcut", {"keys": ["Control", "s"]})
# Verify shortcut executed
await registry.execute_action("zoom_in")
# Verify zoom level increased
await registry.execute_action("take_screenshot", {"path": "screenshot.png"})
# Verify screenshot file exists
```

---

#### Step 1.12: Presentation Action Registry - Presentation-Specific Actions

**Goal**: Add presentation-specific actions (presentation_mode, show_pointer, animate_scroll, highlight_region, draw_on_page, focus_element)

**Implementation**:
1. Implement `presentation_mode` action (fullscreen, hide UI)
2. Implement `show_pointer` action
3. Implement `animate_scroll` action (smooth scrolling)
4. Implement `highlight_region` action
5. Implement `draw_on_page` action (temporary annotations)
6. Implement `focus_element` action (visual indicator)

**Testing Checkpoint 1.12**:
- [ ] Unit test: Each presentation action independently
- [ ] Integration test: Enter presentation mode and verify UI hidden
- [ ] Integration test: Animate scroll and verify smooth scrolling
- [ ] Integration test: Highlight region and verify visual feedback

**Verification**:
```python
# Test presentation actions
await registry.execute_action("presentation_mode", {"enabled": True})
# Verify UI hidden, fullscreen enabled
await registry.execute_action("animate_scroll", {"direction": "down", "duration": 1.0})
# Verify smooth scrolling
```

---

#### Step 1.13: Action Queue Management - BullMQ Integration

**Goal**: Implement reliable action queue using BullMQ

**Implementation**:
1. Create `presentation/action_queue.py`
2. Implement `ActionQueue` class wrapping BullMQ `Queue`
3. Add `enqueue_action` method using `queue.add()`
4. Add `process_queue` method using `QueueWorker`
5. Add job options (retry, timeout, priority)

**Why BullMQ?**
- Persistence: Actions persist in Redis, won't be lost
- Reliability: Automatic retries for failed actions
- Scalability: Handle thousands of concurrent actions
- Monitoring: Track job status and metrics

**Testing Checkpoint 1.13**:
- [ ] Unit test: BullMQ queue creation
- [ ] Unit test: Enqueue actions and verify ordering (FIFO)
- [ ] Unit test: Process queue and verify FIFO execution
- [ ] Integration test: Enqueue multiple actions, process queue
- [ ] Integration test: Verify actions persist after service restart
- [ ] Performance test: Enqueue 1000 actions, measure throughput

**Verification**:
```python
# Test BullMQ action queue
from bullmq import Queue, QueueWorker

queue = Queue("browser_actions")
action_queue = ActionQueue(queue=queue)

await action_queue.enqueue_action(action1, job_id="action1")
await action_queue.enqueue_action(action2, job_id="action2")

# Verify jobs in queue
jobs = await queue.getJobs(['waiting'])
assert len(jobs) == 2

# Process queue (using worker)
worker = QueueWorker("browser_actions", processor=action_queue.process_action)
await action_queue.process_queue()

# Verify jobs completed
completed = await queue.getJobs(['completed'])
assert len(completed) == 2
assert completed[0].id == "action1"  # FIFO order
assert completed[1].id == "action2"
```

---

#### Step 1.14: Action Queue Management - Rate Limiting

**Goal**: Add rate limiting to action queue

**Implementation**:
1. Add rate limiting using `asyncio.Semaphore`
2. Configure max actions per second
3. Add delays between actions if needed

**Testing Checkpoint 1.14**:
- [ ] Unit test: Rate limiting with max actions per second
- [ ] Integration test: Enqueue many actions, verify rate limiting works
- [ ] Performance test: Measure throughput with rate limiting

**Verification**:
```python
# Test rate limiting
queue = ActionQueue(max_actions_per_second=2)
start_time = time.time()
await queue.enqueue_action(action1)
await queue.enqueue_action(action2)
await queue.process_queue()
# Verify actions processed with rate limiting (at least 1 second for 2 actions)
```

---

#### Step 1.15: Action Queue Management - Retry Logic

**Goal**: Add retry logic for failed actions

**Implementation**:
1. Add retry logic for failed actions
2. Configure max retries
3. Add exponential backoff
4. Track failed actions

**Testing Checkpoint 1.15**:
- [ ] Unit test: Retry logic with max retries
- [ ] Unit test: Exponential backoff timing
- [ ] Integration test: Fail action, verify retry, verify max retries reached

**Verification**:
```python
# Test retry logic
queue = ActionQueue(max_retries=3)
await queue.enqueue_action(failing_action)
results = await queue.process_queue()
# Verify action retried 3 times before failing
```

---

#### Step 1.16: Enhanced Event Broadcasting - Redis Pub/Sub Integration

**Goal**: Replace WebSocket with Redis Pub/Sub for high-frequency events

**Implementation**:
1. Install Redis and configure connection
2. Replace `EventBroadcaster` WebSocket implementation with Redis Pub/Sub:
   - Use `redis.publish()` for broadcasting events
   - Use channel naming: `browser:events:{session_id}`
3. Add new event types:
   - `presentation_started`
   - `presentation_paused`
   - `presentation_resumed`
   - `presentation_timeout_warning`
   - `presentation_ending`
   - `action_queued`
   - `action_processing`
   - `presentation_mode_enabled`
   - `page_loaded`
   - `dom_updated`
   - `element_hovered`
   - `mouse_moved`
4. Keep WebSocket as optional fallback for clients that prefer it

**Why Redis Pub/Sub?**
- Sub-millisecond latency for real-time events
- Can handle millions of events per second
- No persistence overhead for ephemeral events
- Fan-out to multiple subscribers

**Testing Checkpoint 1.16**:
- [ ] Unit test: Redis Pub/Sub connection
- [ ] Unit test: Each new event type broadcast via Pub/Sub
- [ ] Integration test: Start presentation, verify events published to Redis
- [ ] Integration test: Subscribe to Redis channel, verify events received
- [ ] Performance test: Measure Pub/Sub latency (<5ms target)
- [ ] Load test: Send 1000 events/second, verify no performance degradation

**Verification**:
```python
# Test Redis Pub/Sub event broadcasting
from redis.asyncio import Redis

redis_client = Redis(host='localhost', port=6379)
broadcaster = EventBroadcaster(redis_client=redis_client)

# Publish event
await broadcaster.broadcast_presentation_started(session_id="test_session")

# Subscribe and verify
pubsub = redis_client.pubsub()
channel = "browser:events:test_session"
await pubsub.subscribe(channel)

message = await pubsub.get_message(timeout=1.0)
assert message is not None
event_data = json.loads(message['data'])
assert event_data['type'] == 'presentation_started'
```

---

#### Step 1.17: Session Persistence - Redis Integration (Optional)

**Goal**: Add session persistence using Redis

**Implementation**:
1. Add Redis client integration
2. Implement `save_session` method
3. Implement `load_session` method
4. Add session serialization/deserialization

**Testing Checkpoint 1.17**:
- [ ] Unit test: Save and load session from Redis
- [ ] Integration test: Save session, restart, verify session restored
- [ ] Performance test: Measure save/load latency

**Verification**:
```python
# Test session persistence
store = SessionStore(redis_client)
session_state = {"room_name": "test", "status": "active"}
await store.save_session("session_1", session_state)
loaded = await store.load_session("session_1")
assert loaded == session_state
```

---

### Phase 1 Testing Summary

**End-to-End Test**: Complete Presentation Flow
- [ ] Start presentation session
- [ ] Execute various actions (navigate, click, type, etc.)
- [ ] Verify actions executed correctly
- [ ] Verify events broadcast
- [ ] Verify timeout handling (with short timeout)
- [ ] Close session and verify cleanup

**Performance Test**:
- [ ] Test with high action rates (100+ actions/second)
- [ ] Test with multiple concurrent sessions (10+ sessions)
- [ ] Test timeout handling with 6-hour duration (use 1-minute for testing)

---

## Part 2: Knowledge Retrieval & Storage Flow

### Overview

The Knowledge Retrieval & Storage Flow enables comprehensive website exploration and knowledge extraction. It provides:

- Complete website exploration (all links, all flows)
- Semantic understanding of content structure
- Functional understanding of navigation flows
- Site map generation (semantic + functional)
- Knowledge storage in structured format
- Link tracking and flow mapping

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              Knowledge Retrieval Service                     │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Exploration Engine                                  │  │
│  │  - Link discovery                                    │  │
│  │  - Flow tracking                                     │  │
│  │  - Depth management                                  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Semantic Analyzer                                   │  │
│  │  - Content extraction                                │  │
│  │  - Entity recognition                                │  │
│  │  - Topic modeling                                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Functional Flow Mapper                              │  │
│  │  - Navigation flow analysis                          │  │
│  │  - User journey mapping                              │  │
│  │  - Action sequence tracking                          │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Knowledge Storage                                   │  │
│  │  - Vector database (embeddings)                     │  │
│  │  - Graph database (relationships)                   │  │
│  │  - Document store (content)                         │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### Graph Database Recommendation: ArangoDB

**Why ArangoDB is the Best Choice for Knowledge Graphs:**

1. **Multi-Model Database**: Graph + Document + Key-Value in one database
   - Store graph structure (nodes/edges) AND document content (page HTML, metadata) in the same database
   - No need for separate document store - single database solution

2. **Excellent Python Support**: `python-arango` library with async support
   - Native Python integration
   - Active maintenance and good documentation

3. **Powerful Query Language (AQL)**: Flexible and expressive
   - Supports complex graph traversals
   - Good for both graph and document queries
   - Can query graph + documents together

4. **Performance**: Fast graph traversals, good for real-time queries
   - Indexed graph queries
   - Efficient path finding

5. **Great for Website Knowledge Graphs**:
   - Perfect for storing pages (nodes) + links (edges) + page content (documents)
   - Navigation flows map naturally to graph structure
   - Entity relationships fit well

**Alternative Options**:
- **Neo4j**: Most popular, best graph algorithms, but requires separate document store
- **Amazon Neptune**: Fully managed, AWS-only, higher cost
- **NetworkX**: Great for development/prototyping, not production-ready

### Implementation Steps

#### Step 2.1: Exploration Engine - Basic Link Discovery

**Goal**: Discover links on a single page

**Implementation**:
1. Create `knowledge/exploration_engine.py`
2. Implement `ExplorationEngine` class
3. Add `discover_links` method to extract `<a>` tags
4. Return list of discovered links

**Testing Checkpoint 2.1**:
- [ ] Unit test: Discover links from HTML string
- [ ] Integration test: Discover links from actual webpage
- [ ] Verify link extraction (href, text, attributes)

**Verification**:
```python
# Test link discovery
engine = ExplorationEngine(browser_session)
links = await engine.discover_links("https://example.com")
assert len(links) > 0
assert all("href" in link for link in links)
```

---

#### Step 2.2: Exploration Engine - Link Tracking

**Goal**: Track visited URLs to avoid duplicates

**Implementation**:
1. Add visited URLs set
2. Add `track_visited` method
3. Add `is_visited` method
4. Filter discovered links by visited status

**Testing Checkpoint 2.2**:
- [ ] Unit test: Track visited URLs
- [ ] Unit test: Filter visited links
- [ ] Integration test: Discover links, mark visited, verify filtering

**Verification**:
```python
# Test link tracking
engine = ExplorationEngine(browser_session)
links = await engine.discover_links("https://example.com")
engine.track_visited(links[0]["href"])
assert engine.is_visited(links[0]["href"])
filtered = engine.filter_unvisited(links)
assert links[0] not in filtered
```

---

#### Step 2.3: Exploration Engine - Depth Management

**Goal**: Control exploration depth

**Implementation**:
1. Add depth tracking per URL
2. Add `max_depth` configuration
3. Filter links by depth limit
4. Track depth for each discovered link

**Testing Checkpoint 2.3**:
- [ ] Unit test: Depth tracking
- [ ] Unit test: Depth limit filtering
- [ ] Integration test: Explore with max_depth=2, verify depth limits

**Verification**:
```python
# Test depth management
engine = ExplorationEngine(browser_session, max_depth=2)
await engine.explore("https://example.com", depth=0)
# Verify only links within depth 2 are explored
```

---

#### Step 2.4: Exploration Engine - BFS Strategy

**Goal**: Implement breadth-first search exploration

**Implementation**:
1. Implement BFS algorithm using queue
2. Explore level by level (depth 0, then 1, then 2, etc.)
3. Track exploration progress

**Testing Checkpoint 2.4**:
- [ ] Unit test: BFS ordering (verify level-by-level exploration)
- [ ] Integration test: Explore small website with BFS, verify order
- [ ] Performance test: Explore medium website (100+ pages)

**Verification**:
```python
# Test BFS strategy
engine = ExplorationEngine(browser_session, strategy="BFS", max_depth=2)
pages = await engine.explore("https://example.com")
# Verify pages explored level by level
```

---

#### Step 2.5: Exploration Engine - DFS Strategy

**Goal**: Implement depth-first search exploration

**Implementation**:
1. Implement DFS algorithm using stack
2. Explore deep paths first
3. Track exploration progress

**Testing Checkpoint 2.5**:
- [ ] Unit test: DFS ordering (verify deep paths first)
- [ ] Integration test: Explore small website with DFS, verify order
- [ ] Performance test: Compare BFS vs DFS

**Verification**:
```python
# Test DFS strategy
engine = ExplorationEngine(browser_session, strategy="DFS", max_depth=3)
pages = await engine.explore("https://example.com")
# Verify deep paths explored first
```

---

#### Step 2.6: Exploration Engine - Form Handling

**Goal**: Handle forms during exploration

**Implementation**:
1. Detect form elements
2. Generate test data for form fields
3. Submit forms (if safe - read-only or GET)
4. Track form submissions

**Testing Checkpoint 2.6**:
- [ ] Unit test: Form detection
- [ ] Unit test: Test data generation
- [ ] Integration test: Discover form, fill, submit (read-only forms only)

**Verification**:
```python
# Test form handling
engine = ExplorationEngine(browser_session)
forms = await engine.discover_forms("https://example.com/contact")
assert len(forms) > 0
# Only handle GET forms or read-only forms
```

---

#### Step 2.7: Semantic Analyzer - Content Extraction

**Goal**: Extract main content from pages

**Implementation**:
1. Create `knowledge/semantic_analyzer.py`
2. Implement `SemanticAnalyzer` class
3. Add `extract_content` method:
   - Remove navigation, footer, ads
   - Extract headings hierarchy
   - Extract paragraphs and text
   - Extract metadata (title, description)

**Testing Checkpoint 2.7**:
- [ ] Unit test: Extract content from HTML string
- [ ] Unit test: Verify navigation/footer removed
- [ ] Integration test: Extract content from actual webpage

**Verification**:
```python
# Test content extraction
analyzer = SemanticAnalyzer()
content = await analyzer.extract_content("https://example.com")
assert "title" in content
assert "headings" in content
assert "paragraphs" in content
assert len(content["paragraphs"]) > 0
```

---

#### Step 2.8: Semantic Analyzer - Entity Recognition

**Goal**: Identify entities in content

**Implementation**:
1. Integrate spaCy for NER
2. Extract people, organizations, locations
3. Extract dates, numbers, currencies
4. Extract product names, features

**Testing Checkpoint 2.8**:
- [ ] Unit test: Entity recognition from text
- [ ] Unit test: Verify entity types (PERSON, ORG, LOC, etc.)
- [ ] Integration test: Extract entities from webpage content

**Verification**:
```python
# Test entity recognition
analyzer = SemanticAnalyzer()
content = await analyzer.extract_content("https://example.com")
entities = analyzer.identify_entities(content["text"])
assert len(entities) > 0
assert all("label" in e and "text" in e for e in entities)
```

---

#### Step 2.9: Semantic Analyzer - Topic Modeling

**Goal**: Identify topics and keywords

**Implementation**:
1. Extract keywords from content
2. Identify main topics
3. Categorize content
4. Generate summaries

**Testing Checkpoint 2.9**:
- [ ] Unit test: Keyword extraction
- [ ] Unit test: Topic identification
- [ ] Integration test: Extract topics from webpage

**Verification**:
```python
# Test topic modeling
analyzer = SemanticAnalyzer()
content = await analyzer.extract_content("https://example.com")
topics = analyzer.extract_topics(content)
assert len(topics) > 0
assert "keywords" in topics
assert "main_topics" in topics
```

---

#### Step 2.10: Semantic Analyzer - Embeddings

**Goal**: Generate embeddings for semantic search

**Implementation**:
1. Integrate sentence-transformers or OpenAI embeddings
2. Generate embeddings for page content
3. Store embeddings for semantic search

**Testing Checkpoint 2.10**:
- [ ] Unit test: Generate embeddings from text
- [ ] Unit test: Verify embedding dimensions
- [ ] Integration test: Generate embeddings for webpage content

**Verification**:
```python
# Test embeddings
analyzer = SemanticAnalyzer()
content = await analyzer.extract_content("https://example.com")
embedding = analyzer.generate_embedding(content["text"])
assert len(embedding) == 384  # or 1536 for OpenAI
```

---

#### Step 2.11: Functional Flow Mapper - Navigation Tracking

**Goal**: Track navigation flows

**Implementation**:
1. Create `knowledge/flow_mapper.py`
2. Implement `FunctionalFlowMapper` class
3. Track page transitions
4. Map click paths

**Testing Checkpoint 2.11**:
- [ ] Unit test: Track page transitions
- [ ] Unit test: Map click paths
- [ ] Integration test: Track navigation during exploration

**Verification**:
```python
# Test navigation tracking
mapper = FunctionalFlowMapper()
mapper.track_transition("page1", "page2", "click")
paths = mapper.get_click_paths()
assert ("page1", "page2") in paths
```

---

#### Step 2.12: Functional Flow Mapper - User Journey Mapping

**Goal**: Map user journeys

**Implementation**:
1. Identify entry points
2. Map conversion paths
3. Identify drop-off points
4. Map multi-step processes

**Testing Checkpoint 2.12**:
- [ ] Unit test: Identify entry points
- [ ] Unit test: Map conversion paths
- [ ] Integration test: Map user journey during exploration

**Verification**:
```python
# Test user journey mapping
mapper = FunctionalFlowMapper()
journeys = mapper.map_user_journeys(entry_point="homepage")
assert len(journeys) > 0
assert all("path" in j and "conversion" in j for j in journeys)
```

---

#### Step 2.13: Knowledge Storage - ArangoDB Setup

**Goal**: Set up ArangoDB for knowledge storage

**Implementation**:
1. Install ArangoDB (Docker or managed)
2. Install `python-arango` library
3. Create database connection
4. Create graph structure (collections for pages, links, entities)

**Testing Checkpoint 2.13**:
- [ ] Unit test: Connect to ArangoDB
- [ ] Unit test: Create graph structure
- [ ] Integration test: Create database, graph, collections

**Verification**:
```python
# Test ArangoDB setup
from arango import ArangoClient
client = ArangoClient(hosts='http://localhost:8529')
db = client.db('knowledge_graph', username='root', password='password')
graph = db.create_graph('website_graph')
pages = graph.create_vertex_collection('pages')
links = graph.create_edge_collection('links')
assert db.has_graph('website_graph')
```

---

#### Step 2.14: Knowledge Storage - Graph Store Implementation

**Goal**: Implement graph store for ArangoDB

**Implementation**:
1. Create `knowledge/storage/graph_store.py`
2. Implement `GraphStore` class
3. Add methods:
   - `add_node` (page, entity)
   - `add_edge` (link, relationship)
   - `query_path` (find path between nodes)
   - `get_related_nodes` (find related nodes)

**Testing Checkpoint 2.14**:
- [ ] Unit test: Add node to graph
- [ ] Unit test: Add edge to graph
- [ ] Unit test: Query path between nodes
- [ ] Integration test: Store page graph, query paths

**Verification**:
```python
# Test graph store
store = GraphStore(arangodb_client)
page1_id = await store.add_node("page", {"url": "https://example.com/page1"})
page2_id = await store.add_node("page", {"url": "https://example.com/page2"})
await store.add_edge(page1_id, page2_id, {"type": "link"})
path = await store.query_path(page1_id, page2_id)
assert len(path) > 0
```

---

#### Step 2.15: Knowledge Storage - Document Store (Using ArangoDB)

**Goal**: Store page content as documents in ArangoDB

**Implementation**:
1. Create document collection in ArangoDB
2. Store page content, metadata, extracted data
3. Add document retrieval methods
4. Add document search (AQL queries)

**Testing Checkpoint 2.15**:
- [ ] Unit test: Store document
- [ ] Unit test: Retrieve document
- [ ] Unit test: Search documents
- [ ] Integration test: Store page content, retrieve, search

**Verification**:
```python
# Test document store (using ArangoDB documents)
store = GraphStore(arangodb_client)  # ArangoDB supports documents too!
doc_id = await store.store_document({
    "url": "https://example.com/page1",
    "content": "...",
    "metadata": {...}
})
doc = await store.retrieve_document(doc_id)
assert doc["url"] == "https://example.com/page1"
```

---

#### Step 2.16: Knowledge Storage - Vector Store (For Embeddings)

**Goal**: Store embeddings for semantic search

**Implementation**:
1. Choose vector database (Pinecone, Weaviate, Qdrant, or Chroma)
2. Create `knowledge/storage/vector_store.py`
3. Implement `VectorStore` class:
   - `store_embedding`
   - `search_similar`
   - `update_embedding`

**Testing Checkpoint 2.16**:
- [ ] Unit test: Store embedding
- [ ] Unit test: Search similar embeddings
- [ ] Integration test: Store page embeddings, search similar pages

**Verification**:
```python
# Test vector store
store = VectorStore(vector_db_client)
embedding = [0.1, 0.2, ...]  # 384 or 1536 dimensions
await store.store_embedding("page1", embedding, {"url": "https://example.com/page1"})
results = await store.search_similar(embedding, top_k=5)
assert len(results) > 0
```

---

#### Step 2.17: Integration - Exploration → Analysis → Storage

**Goal**: Integrate exploration, analysis, and storage

**Implementation**:
1. Connect exploration engine → semantic analyzer → storage
2. Store pages, links, content, embeddings, entities in ArangoDB
3. Store embeddings in vector database
4. Create knowledge pipeline

**Testing Checkpoint 2.17**:
- [ ] Integration test: Explore → Analyze → Store complete pipeline
- [ ] Integration test: Verify data stored correctly (graph + documents + embeddings)
- [ ] Performance test: Explore small website (50+ pages), measure time

**Verification**:
```python
# Test complete pipeline
engine = ExplorationEngine(browser_session)
analyzer = SemanticAnalyzer()
graph_store = GraphStore(arangodb_client)
vector_store = VectorStore(vector_db_client)

# Explore
pages = await engine.explore("https://example.com", max_pages=50)

# Analyze and store
for page in pages:
    content = await analyzer.extract_content(page["url"])
    entities = analyzer.identify_entities(content["text"])
    embedding = analyzer.generate_embedding(content["text"])
    
    # Store in ArangoDB (graph + documents)
    node_id = await graph_store.add_node("page", {
        "url": page["url"],
        "content": content,
        "entities": entities
    })
    
    # Store embedding
    await vector_store.store_embedding(node_id, embedding, {"url": page["url"]})

# Verify storage
assert graph_store.get_node_count() == 50
assert vector_store.get_embedding_count() == 50
```

---

#### Step 2.18: Site Map Generator - Semantic Site Map

**Goal**: Generate semantic site map

**Implementation**:
1. Create `knowledge/sitemap_generator.py`
2. Implement `SiteMapGenerator` class
3. Generate hierarchical structure based on content
4. Group by topics/categories
5. Export to JSON/XML

**Testing Checkpoint 2.18**:
- [ ] Unit test: Generate semantic site map structure
- [ ] Integration test: Generate site map from stored knowledge
- [ ] Verify site map format (hierarchical, grouped by topics)

**Verification**:
```python
# Test semantic site map
generator = SiteMapGenerator(graph_store, vector_store)
sitemap = await generator.generate_semantic_sitemap()
assert "hierarchy" in sitemap
assert "topics" in sitemap
assert len(sitemap["topics"]) > 0
```

---

#### Step 2.19: Site Map Generator - Functional Site Map

**Goal**: Generate functional site map (navigation flows)

**Implementation**:
1. Generate navigation structure
2. Map user journeys
3. Map action sequences
4. Export to GraphML/Mermaid

**Testing Checkpoint 2.19**:
- [ ] Unit test: Generate functional site map structure
- [ ] Integration test: Generate site map from stored flows
- [ ] Verify site map format (navigation flows, user journeys)

**Verification**:
```python
# Test functional site map
generator = SiteMapGenerator(graph_store, flow_mapper)
sitemap = await generator.generate_functional_sitemap()
assert "navigation" in sitemap
assert "user_journeys" in sitemap
assert len(sitemap["user_journeys"]) > 0
```

---

#### Step 2.20: Knowledge Retrieval API - Basic Endpoints

**Goal**: Create API endpoints for knowledge retrieval

**Implementation**:
1. Extend `websocket_server.py` with new endpoints
2. Create endpoints:
   - `POST /knowledge/explore` - Start exploration
   - `GET /knowledge/exploration/{job_id}/status` - Get status
   - `GET /knowledge/search` - Semantic search
   - `GET /knowledge/flows` - Get navigation flows
   - `GET /knowledge/sitemap` - Get site map
   - `GET /knowledge/page/{url}` - Get page knowledge

**Testing Checkpoint 2.20**:
- [ ] Unit test: Each endpoint independently
- [ ] Integration test: Start exploration via API, check status
- [ ] Integration test: Search via API, verify results

**Verification**:
```python
# Test API endpoints
response = await client.post("/knowledge/explore", json={
    "url": "https://example.com",
    "max_depth": 2
})
job_id = response.json()["job_id"]

status = await client.get(f"/knowledge/exploration/{job_id}/status")
assert status.json()["status"] in ["running", "completed"]

results = await client.get("/knowledge/search", params={"query": "test", "top_k": 5})
assert len(results.json()["results"]) > 0
```

---

### Phase 2 Testing Summary

**End-to-End Test**: Complete Knowledge Retrieval Flow
- [ ] Start exploration via API
- [ ] Verify exploration completes
- [ ] Verify knowledge stored (graph + documents + embeddings)
- [ ] Verify semantic search works
- [ ] Verify navigation flows stored
- [ ] Verify site map generation works
- [ ] Verify API endpoints work

**Performance Test**:
- [ ] Explore medium website (100+ pages), measure time
- [ ] Test semantic search performance (query time)
- [ ] Test graph query performance (path finding)
- [ ] Test with large knowledge graph (1000+ pages)

---

## Technology Stack Summary

### Core Technologies (Existing)
- **Browser Automation**: Browser-Use library (CDP-based)
- **Event System**: `bubus` event bus
- **Web Framework**: FastAPI
- **Async Runtime**: Python asyncio
- **Type Safety**: Pydantic v2

### Presentation Flow Technologies
- **Action Execution**: Existing `ActionDispatcher`
- **Command Queue**: **BullMQ** (Redis-based job queue for reliable commands)
- **Event Broadcasting**: **Redis Pub/Sub** (for high-frequency real-time events)
- **Visual Effects**: `PIL` (Pillow) or `opencv-python`
- **Keyboard Shortcuts**: `keyboard` library
- **Session Storage**: `redis` (for BullMQ + Pub/Sub) or `sqlalchemy`

**Required Dependencies**:
- `bullmq` - Job queue for commands (Agent → Browser)
- `redis` (async) - Redis client for Pub/Sub and data storage
- `redis-py` - Python Redis client

### Knowledge Retrieval Technologies
- **HTML Parsing**: `BeautifulSoup4` or `lxml`
- **NLP**: `spaCy`, `nltk`, `transformers`
- **Embeddings**: `sentence-transformers`, OpenAI embeddings
- **Vector DB**: Pinecone, Weaviate, Qdrant, or Chroma
- **Graph DB**: **ArangoDB** (recommended) - Multi-model (graph + document)
- **Alternative Graph DB**: Neo4j (if you prefer pure graph approach)
- **Graph Visualization**: `networkx`, `graphviz`, `pyvis`
- **LLM Integration**: Existing LLM infrastructure

---

## Implementation Priority

### Phase 0: Critical Architecture Gaps (Week 1-2) - **START HERE**

**Priority**: Close critical gaps before building new features

#### Priority 1: Vision Analysis Integration (Days 1-3)

**Goal**: Enable visual page understanding and self-correction

**Implementation**:
1. Create `mvp/vision_analyzer.py`
2. Integrate with OpenAI Vision or Anthropic Claude
3. Implement `analyze_frame()` method
4. Implement `detect_blockers()` method
5. Implement `suggest_corrective_action()` method
6. Integrate with ActionDispatcher for failure handling
7. Broadcast vision results via Redis Pub/Sub

**Testing Checkpoint**:
- [ ] Unit test: Vision analyzer with test frames
- [ ] Integration test: Vision analysis on action failures
- [ ] Test with common error scenarios (popups, loading indicators)

**Dependencies**: `openai` or `anthropic` SDK with vision support

---

#### Priority 2: Primitive Validation Layer (Day 4)

**Goal**: Add comprehensive validation at service boundaries

**Implementation**:
1. Enhance Pydantic models in `mvp/action_command.py`:
   - Add validators for `ClickActionCommand` (index >= 0)
   - Add validators for `NavigateActionCommand` (valid URL)
   - Add validators for `TypeActionCommand` (non-empty text)
   - Add validators for `ScrollActionCommand` (valid direction/amount)
2. Add validation middleware in `mvp/mcp_server.py`
3. Add validation in BullMQ consumer
4. Add consistent error format for validation failures

**Testing Checkpoint**:
- [ ] Unit test: Each validator independently
- [ ] Integration test: Invalid commands rejected at MCP boundary
- [ ] Integration test: Invalid commands rejected at BullMQ boundary

---

#### Priority 3: Self-Correction Loop (Days 5-7)

**Goal**: Automatic error recovery with vision-guided corrections

**Implementation**:
1. Create `mvp/self_correction.py`
2. Implement `SelfCorrectionCoordinator` class:
   - `handle_action_failure()` method
   - `analyze_error_pattern()` method
   - `generate_correction()` method
   - `enforce_retry_limits()` method (max 3 attempts)
3. Integrate with VisionAnalyzer
4. Add circuit breaker logic
5. Broadcast correction attempts via Redis Pub/Sub

**Testing Checkpoint**:
- [ ] Unit test: Error pattern analysis
- [ ] Unit test: Correction generation
- [ ] Unit test: Retry limit enforcement
- [ ] Integration test: End-to-end correction flow
- [ ] Test with common errors (popups, loading delays)

---

#### Priority 4: Ghost Cursor Injection (Days 8-9)

**Goal**: Visual feedback for action execution

**Implementation**:
1. Create `mvp/ghost_cursor.py`
2. Implement `GhostCursorInjector` class:
   - `inject_cursor()` method
   - `create_cursor_overlay()` method
   - `animate_cursor()` method (optional)
3. Integrate with LiveKit frame pipeline
4. Record cursor coordinates in ActionDispatcher
5. Inject cursor overlay before frame encoding

**Testing Checkpoint**:
- [ ] Unit test: Cursor overlay creation
- [ ] Integration test: Cursor visible in LiveKit stream
- [ ] Test cursor timing (1 second visibility)

---

#### Priority 5: Domain Allowlist Verification (Day 10)

**Goal**: Strengthen security enforcement

**Implementation**:
1. Audit SecurityWatchdog integration in BrowserSession
2. Add explicit validation in ActionDispatcher `_execute_navigate()`
3. Add audit logging for domain checks
4. Add clear error messages for blocked domains
5. Test with various domain scenarios

**Testing Checkpoint**:
- [ ] Verify SecurityWatchdog is active
- [ ] Test allowlist enforcement
- [ ] Test prohibited domains blocking
- [ ] Verify audit logging

**Dependencies**: Existing `SecurityWatchdog` from Browser-Use

---

#### Priority 6: Telemetry and Observability (Days 11-12)

**Goal**: Operational visibility and metrics

**Implementation**:
1. Create `mvp/telemetry.py`
2. Implement `TelemetryService` class:
   - `emit_metric()` method
   - `emit_event()` method
   - `start_trace()` method
   - `record_latency()` method
3. Integrate throughout action execution flow
4. Add metrics for:
   - Action execution latency (p50, p95, p99)
   - Action success/failure rates
   - Browser session count and duration
   - Frame capture and encoding latency
   - Memory and CPU usage
5. Enhance health check endpoint with metrics

**Testing Checkpoint**:
- [ ] Unit test: Telemetry emission
- [ ] Integration test: Metrics collected during execution
- [ ] Verify metrics exposed in health endpoint

**Dependencies**: `prometheus-client` or `opentelemetry` (optional)

---

#### Priority 7: Resource Management (Days 13-14)

**Goal**: Admission control and resource limits

**Implementation**:
1. Create `mvp/resource_manager.py`
2. Implement `ResourceManager` class:
   - `check_capacity()` method
   - `monitor_session_resources()` method
   - `enforce_limits()` method
   - `handle_memory_leak()` method (restart browser)
3. Add PID reaper for zombie browser processes (using `psutil`)
4. Integrate with BrowserSessionManager
5. Add resource limits configuration

**Testing Checkpoint**:
- [ ] Unit test: Capacity checking
- [ ] Unit test: Resource monitoring
- [ ] Integration test: Admission control when at capacity
- [ ] Test zombie process cleanup
- [ ] Test memory leak detection and browser restart

**Dependencies**: `psutil` for process management

**Critical Fix**: Implement PID reaper to prevent zombie browser processes:
```python
import psutil

def kill_browser_process(pid):
    """Kill browser process tree to prevent zombie processes"""
    try:
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
    except psutil.NoSuchProcess:
        pass  # Already terminated
```

---

### Phase 1: Presentation Flow (Week 3-4) - After Critical Gaps

**Prerequisites**: Complete Phase 0 (Critical Gaps) first

1. ✅ Basic browser automation (existing)
2. ✅ MCP server (existing)
3. ✅ LiveKit streaming (existing)
4. ⏳ Presentation flow manager (Steps 1.1-1.4)
5. ⏳ Extended action registry (Steps 1.5-1.12)
6. ⏳ Action queue management (Steps 1.13-1.15)
7. ✅ Enhanced event broadcasting (Redis Pub/Sub - completed)
8. ⏳ Session persistence (Step 1.17 - optional)

### Phase 2: Knowledge Retrieval Flow (Week 5-6)

**Prerequisites**: Complete Phase 1 (Presentation Flow) first

1. ⏳ Exploration engine (Steps 2.1-2.6)
2. ⏳ Semantic analyzer (Steps 2.7-2.10)
3. ⏳ Functional flow mapper (Steps 2.11-2.12)
4. ⏳ Knowledge storage - ArangoDB (Steps 2.13-2.16)
5. ⏳ Integration pipeline (Step 2.17)
6. ⏳ Site map generator (Steps 2.18-2.19)
7. ⏳ Knowledge retrieval API (Step 2.20)

---

## Next Steps

1. **Review and approve** this implementation guide
2. **Set up development environment** with required dependencies
3. **Start with Phase 1, Step 1.1** - Presentation Flow Manager - Basic Structure
4. **Follow step-by-step** - Implement, test, verify, then move to next step
5. **Complete Phase 1** before starting Phase 2
6. **Integration testing** of both flows after Phase 2
7. **Production deployment** preparation

---

*Last Updated: 2025*
*Version: 2.0.0*

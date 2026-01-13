# Sequenced Communication: Implementation Guide

**Version**: 1.0.0  
**Date**: 2026-01-13  
**Purpose**: Complete implementation guide for ordered, low-latency communication between Voice AI Agent and Browser Agent using Redis Streams.

---

## Table of Contents

1. [Overview & Problems Being Solved](#overview--problems-being-solved)
2. [Architecture Decision](#architecture-decision)
3. [System Architecture](#system-architecture)
4. [Message Schemas](#message-schemas)
5. [Implementation Components](#implementation-components)
6. [Integration Points](#integration-points)
7. [Implementation Checklist](#implementation-checklist)

---

## Overview & Problems Being Solved

### Current Problems

1. **Ordered Message Processing**: Messages between Voice AI and Browser Agent must be processed in sequence across many instances. REST/MCP/WebSocket alone cannot guarantee ordered delivery/processing when multiple servers are serving the same agent.

2. **Screen-State Visibility & Latency**: After the Browser Agent acts, the Voice AI Agent must learn the resulting on-screen state. Currently, the Voice AI Agent polls or re-queries state and spends time re-processing — this causes latency and poor reasoning because it lacks an immediate, clear, compact representation of "what changed" between actions.

### Solution Overview

We introduce **Redis Streams** as an augmentation layer that provides:

- **Ordered Command Processing**: Per-session FIFO ordering via Redis Streams consumer groups
- **Push-Based State Updates**: Low-latency state propagation with structured diffs
- **Backward Compatibility**: Existing MCP/REST/WebSocket remain functional as fallbacks

### Why This Solution

**Alignment with Current Architecture**:
- ✅ Redis infrastructure already present (RQ + Pub/Sub)
- ✅ Session-based isolation maps directly (`room_name` = stream key)
- ✅ Horizontal scaling patterns align with RQ worker scaling
- ✅ Fallback mechanisms match existing graceful degradation philosophy

**Benefits**:
- No new infrastructure needed (Redis already in use)
- Per-session isolation (each `room_name` gets its own streams)
- Low latency (sub-millisecond message delivery)
- Scalable (consumer groups enable multiple instances)

---

## Architecture Decision

### Chosen Pattern: Redis Streams with Per-Session Consumer Groups

**Why Redis Streams Over Alternatives**:

| Alternative | Why Not Chosen |
|------------|----------------|
| **Apache Kafka** | Higher latency (5-20ms vs sub-1ms), operational complexity, requires dedicated cluster |
| **RabbitMQ** | Lacks native ordering guarantees, would duplicate Redis infrastructure |
| **Direct WebSocket with Sequencing** | Struggles with multi-instance deployment, requires sticky sessions |
| **Custom Sequence Coordinator** | Significant development effort, single point of failure, adds latency |

**Key Design Decisions**:

1. **Per-Session Streams**: `commands:{room_name}` and `state:{room_name}` ensure complete isolation
2. **Consumer Groups**: Enable multiple instances to share load while guaranteeing each message processed once
3. **Application-Level Sequence Numbers**: Defense-in-depth validation beyond Redis ordering
4. **Dual-Mode Support**: Streams as primary, MCP/REST as fallback

---

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│              Voice AI Agent Cluster (Multiple Instances)        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ Instance A   │  │ Instance B   │  │ Instance C   │         │
│  │              │  │              │  │              │         │
│  │ Command      │  │ Command      │  │ Command      │         │
│  │ Publisher    │  │ Publisher    │  │ Publisher    │         │
│  │ State        │  │ State        │  │ State        │         │
│  │ Consumer     │  │ Consumer     │  │ Consumer     │         │
│  │ State Cache  │  │ State Cache  │  │ State Cache  │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                  │                  │                  │
│         └──────────────────┼──────────────────┘                  │
│                            │                                     │
│         Redis Streams                                          │
│         ┌─────────────────────────────────────┐                 │
│         │ commands:{room_name} (per session)  │                 │
│         │ state:{room_name} (per session)     │                 │
│         │ Consumer Groups:                    │                 │
│         │ - browser_agent_cluster             │                 │
│         │ - voice_agent_cluster               │                 │
│         └────────────┬────────────────────────┘                 │
└──────────────────────┼──────────────────────────────────────────┘
                       │
┌──────────────────────┼──────────────────────────────────────────┐
│              Browser Agent Cluster (Multiple Instances)        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ Instance 1   │  │ Instance 2   │  │ Instance 3   │         │
│  │              │  │              │  │              │         │
│  │ Command      │  │ Command      │  │ Command      │         │
│  │ Consumer     │  │ Consumer     │  │ Consumer     │         │
│  │ (Consumer    │  │ (Consumer    │  │ (Consumer    │         │
│  │  Group)      │  │  Group)      │  │  Group)      │         │
│  │ State        │  │ State        │  │ State        │         │
│  │ Publisher    │  │ Publisher    │  │ Publisher    │         │
│  │ State Diff   │  │ State Diff   │  │ State Diff   │         │
│  │ Engine       │  │ Engine       │  │ Engine       │         │
│  │ Dedup Cache  │  │ Dedup Cache  │  │ Dedup Cache  │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                  │                  │                  │
└─────────┼──────────────────┼──────────────────┼──────────────────┘
          │                  │                  │
          └──────────────────┼──────────────────┘
                             │
          ┌──────────────────▼──────────────────┐
          │    Existing MCP/REST/WebSocket      │
          │    (Backward Compatible Fallback)   │
          └─────────────────────────────────────┘
```

### Data Flow

**Primary Path (Redis Streams)**:
1. Voice AI Agent publishes command to `commands:{room_name}` stream
2. Browser Agent consumer reads command (via consumer group)
3. Browser Agent executes action, computes state diff
4. Browser Agent publishes state update to `state:{room_name}` stream
5. Voice AI Agent consumer reads state update
6. Voice AI Agent applies diff to state cache

**Fallback Path (Existing)**:
1. Voice AI Agent calls MCP HTTP endpoint (`execute_action`)
2. Browser Agent executes action synchronously
3. Response includes action result
4. Voice AI Agent polls `get_screen_content` if needed

---

## Message Schemas

### Voice-to-Browser Command Envelope

```json
{
  "version": "1.0",
  "type": "command",
  "command_id": "cmd_7d8f9a2b3c4d5e6f",
  "session_id": "room_abc123",
  "room_name": "room_abc123",
  "sequence_number": 42,
  "timestamp_ms": 1705123456789,
  "trace_context": {
    "trace_id": "trace_abc123",
    "span_id": "span_def456"
  },
  "command": {
    "action_type": "click",
    "params": {
      "index": 5
    }
  },
  "timeout_ms": 10000
}
```

**Key Fields**:
- `command_id`: Unique identifier (UUID v7) for idempotency
- `session_id` / `room_name`: Session identifier (maps to stream key)
- `sequence_number`: Monotonically increasing per session
- `command`: Action details (action_type, params)

### Browser-to-Voice State Update Envelope

```json
{
  "version": "1.0",
  "type": "state_update",
  "update_id": "update_9a8b7c6d5e4f",
  "session_id": "room_abc123",
  "room_name": "room_abc123",
  "sequence_number": 42,
  "command_id": "cmd_7d8f9a2b3c4d5e6f",
  "command_sequence": 42,
  "received_at_ms": 1705123456790,
  "generated_at_ms": 1705123457200,
  "action_result": {
    "success": true,
    "error": null,
    "duration_ms": 410,
    "data": {
      "element_index": 5,
      "element_selector": "button.submit"
    }
  },
  "state_diff": {
    "format_version": "1.0",
    "diff_type": "incremental",
    "pre_state_hash": "sha256_pre123...",
    "post_state_hash": "sha256_post456...",
    "dom_changes": {
      "elements_added": [],
      "elements_removed": [],
      "elements_modified": [
        {
          "index": 5,
          "selector": "button.submit",
          "changes": {
            "classes": {"added": ["clicked"], "removed": []}
          }
        }
      ]
    },
    "navigation_changes": {
      "url_changed": false,
      "title_changed": false
    },
    "semantic_events": [
      {
        "event_type": "ui_state",
        "event_name": "button_clicked",
        "target_selector": "button.submit",
        "confidence": 1.0
      }
    ]
  },
  "current_state_summary": {
    "url": "https://example.com/form",
    "title": "Form Submission",
    "state_hash": "sha256_post456..."
  },
  "screenshot": {
    "captured": true,
    "url": "https://storage.example.com/screenshots/room_abc123_42.png",
    "content_hash": "sha256_screenshot..."
  }
}
```

### State Diff Format (Detailed)

```json
{
  "format_version": "1.0",
  "diff_type": "incremental",
  "pre_state_hash": "sha256_pre...",
  "post_state_hash": "sha256_post...",
  "dom_changes": {
    "elements_added": [
      {
        "index": 16,
        "selector": "div.success-message",
        "tag": "div",
        "role": "alert",
        "text_content": "Success! Form submitted.",
        "attributes": {"class": "success-message"},
        "bounding_box": {"x": 100, "y": 300, "width": 500, "height": 50}
      }
    ],
    "elements_removed": [
      {
        "index": 5,
        "selector": "button.submit",
        "tag": "button"
      }
    ],
    "elements_modified": [
      {
        "index": 4,
        "selector": "form.login",
        "changes": {
          "attributes": {
            "data-submitted": {"old": "false", "new": "true"}
          },
          "classes": {"added": ["submitted"], "removed": []}
        }
      }
    ]
  },
  "navigation_changes": {
    "url_changed": false,
    "title_changed": false
  },
  "form_state_changes": [
    {
      "form_index": 0,
      "form_selector": "form.login",
      "fields_changed": [
        {
          "field_index": 0,
          "validation_state": {"before": "invalid", "after": "valid"}
        }
      ],
      "form_valid": true
    }
  ],
  "accessibility_changes": {
    "focus_changed": {
      "from_index": 5,
      "to_index": 16
    }
  },
  "semantic_events": [
    {
      "event_type": "form",
      "event_name": "form_submitted",
      "target_selector": "form.login",
      "confidence": 1.0
    },
    {
      "event_type": "feedback",
      "event_name": "success_message_appeared",
      "target_selector": "div.success-message",
      "confidence": 0.95
    }
  ]
}
```

**Semantic Events Reference**:
- **Navigation**: `page_load_complete`, `client_side_route`, `hash_change`
- **UI State**: `modal_opened`, `modal_closed`, `dropdown_expanded`, `tab_switched`
- **Form**: `form_submitted`, `validation_error`, `field_focused`
- **Feedback**: `error_banner_appeared`, `success_message_appeared`, `toast_notification`
- **Authentication**: `login_success`, `login_failure`
- **Data**: `list_updated`, `table_sorted`, `pagination_changed`

---

## Implementation Components

### Browser Agent Components

#### 1. CommandConsumer

**Purpose**: Consumes commands from Redis Streams, validates sequence numbers, executes actions.

**Location**: `navigator/streaming/command_consumer.py`

**Key Methods**:
- `start_consuming()`: Start consumption loop for active sessions
- `_process_message()`: Process command, validate sequence, execute action
- `_validate_sequence()`: Check sequence number matches expected
- `_handle_sequence_gap()`: Handle missing sequence numbers

**Implementation Notes**:
- Uses consumer group: `browser_agent_cluster`
- Consumer name: Instance identifier (e.g., `browser_agent_1`)
- Claims pending messages from failed consumers
- Blocks on stream read (timeout: 1 second)
- Acknowledges after successful processing

#### 2. StatePublisher

**Purpose**: Publishes state updates to Redis Streams after action execution.

**Location**: `navigator/streaming/state_publisher.py`

**Key Methods**:
- `publish_state_update()`: Publish state update envelope to stream
- `_construct_state_update()`: Build state update envelope from action result and diff

**Implementation Notes**:
- Stream key: `state:{room_name}`
- Includes action result, state diff, current state summary
- Screenshot uploaded asynchronously, URL included in update

#### 3. StateDiffEngine

**Purpose**: Computes structured state diffs (before/after action).

**Location**: `navigator/state/diff_engine.py`

**Key Methods**:
- `capture_state()`: Capture current browser state snapshot
- `compute_diff()`: Compute diff between two state snapshots
- `_detect_semantic_events()`: Detect high-level semantic events from DOM/navigation changes

**State Snapshot Structure**:
- DOM tree (interactive elements with indices)
- Navigation state (URL, title, ready state)
- Form states (field values, validation states)
- Accessibility tree (landmarks, focus, live regions)

**Diff Computation**:
- Compare DOM trees (elements added/removed/modified/moved)
- Compare navigation state
- Compare form states
- Compare accessibility tree
- Detect semantic events from changes

#### 4. DedupCache

**Purpose**: Tracks processed commands for idempotency.

**Location**: `navigator/state/dedup_cache.py`

**Key Methods**:
- `is_processed(command_id)`: Check if command already processed
- `mark_processing(command_id)`: Mark command as processing
- `mark_processed(command_id)`: Mark command as processed

**Implementation Notes**:
- In-memory cache with TTL (5 minutes)
- Key: `command_id`
- Value: Processing status (`processing`, `processed`)
- Cleans up expired entries periodically

#### 5. SequenceTracker

**Purpose**: Tracks last processed sequence number per session.

**Location**: `navigator/state/sequence_tracker.py`

**Key Methods**:
- `get_last_processed(session_id)`: Get last processed sequence number
- `update_last_processed(session_id, seq_num)`: Update last processed sequence number
- `validate_sequence(session_id, seq_num)`: Validate sequence number matches expected

**Implementation Notes**:
- In-memory per session (can persist to Redis for durability)
- Expected sequence = last_processed + 1
- If gap detected, publish error event requesting retransmission

### Voice AI Agent Components

#### 1. CommandPublisher

**Purpose**: Publishes commands to Redis Streams.

**Location**: `{voice_ai_agent}/streaming/command_publisher.py`

**Key Methods**:
- `publish_command()`: Publish command envelope to stream
- `_construct_command_envelope()`: Build command envelope

**Implementation Notes**:
- Stream key: `commands:{room_name}`
- Generates unique `command_id` (UUID v7)
- Uses sequence tracker to get next sequence number
- Returns command_id for correlation

#### 2. StateConsumer

**Purpose**: Consumes state updates from Redis Streams.

**Location**: `{voice_ai_agent}/streaming/state_consumer.py`

**Key Methods**:
- `start_consuming()`: Start consumption loop for active sessions
- `wait_for_update(command_id, timeout)`: Wait for state update matching command_id
- `_process_state_update()`: Process state update, apply diff to cache

**Implementation Notes**:
- Uses consumer group: `voice_agent_cluster`
- Consumer name: Instance identifier
- Blocks on stream read
- Correlates state updates with commands via `command_id`

#### 3. StateCache

**Purpose**: Maintains local browser state cache, applies diffs incrementally.

**Location**: `{voice_ai_agent}/state/cache.py`

**Key Methods**:
- `apply_diff(state_diff)`: Apply diff to cached state
- `get_current_state()`: Get current cached state
- `get_element_index(selector)`: Get element index from cache

**State Structure**:
- `url`: Current URL
- `title`: Page title
- `dom_elements`: List of interactive elements
- `element_indices`: Map of index -> element
- `form_states`: Map of form selector -> form state
- `state_hash`: Current state hash

#### 4. SequenceTracker (Voice AI)

**Purpose**: Tracks sequence numbers per session for command publishing.

**Location**: `{voice_ai_agent}/state/sequence_tracker.py`

**Key Methods**:
- `get_next(session_id)`: Get next sequence number for session
- `increment(session_id)`: Increment sequence counter
- `recover_from_stream()`: Query stream to recover highest sequence number

**Implementation Notes**:
- Maintains sequence counter per session
- On restart, queries stream to recover highest sequence number
- Continues from next number

---

## Integration Points

### Browser Agent Integration

#### Modify BrowserSessionManager

**File**: `navigator/session/manager.py`

**Changes**:
1. Add `StateDiffEngine` instance
2. Add `StatePublisher` instance
3. Modify `execute_action()` to:
   - Capture state before action (if stream mode enabled)
   - Execute action (existing logic)
   - Capture state after action
   - Compute diff
   - Publish state update to stream
   - Return result (existing synchronous response for backward compatibility)

**Example Integration**:

```python
class BrowserSessionManager:
    def __init__(self, ...):
        # ... existing initialization ...
        self.state_diff_engine = StateDiffEngine()
        self.state_publisher = StatePublisher(redis_client)
        self.command_consumer = CommandConsumer(
            redis_client, 
            instance_id,
            self
        )
    
    async def execute_action(self, room_name, action_type, params):
        session = self.sessions.get(room_name)
        if not session:
            return {'success': False, 'error': 'Session not found'}
        
        # Capture state before action (for stream mode)
        pre_state = None
        if await self._is_stream_mode_enabled(room_name):
            pre_state = await self.state_diff_engine.capture_state(session)
        
        # Execute action (existing logic)
        result = await self._execute_action_internal(session, action_type, params)
        
        # Publish state update to stream (if stream mode enabled)
        if pre_state and await self._is_stream_mode_enabled(room_name):
            post_state = await self.state_diff_engine.capture_state(session)
            state_diff = await self.state_diff_engine.compute_diff(pre_state, post_state)
            
            await self.state_publisher.publish_state_update(
                room_name,
                result,
                state_diff,
                post_state
            )
        
        return result  # Existing synchronous response
```

#### Add CommandConsumer Background Task

**File**: `navigator/session/manager.py` or separate background task

**Changes**:
1. Start command consumer on server startup
2. Consumer loop runs continuously
3. Processes commands for all active sessions

**Example Integration**:

```python
# In server startup
async def startup():
    # ... existing startup ...
    
    # Start command consumer
    command_consumer = CommandConsumer(redis_client, instance_id, session_manager)
    asyncio.create_task(command_consumer.start_consuming())
```

#### Modify MCP Server (Optional Dual-Mode)

**File**: `navigator/server/mcp.py`

**Changes**:
1. Add feature flag: `ENABLE_STREAM_MODE` (per-session or global)
2. Modify `_execute_action()` to support dual mode:
   - If stream mode enabled: Publish to stream, return command_id
   - If stream mode disabled: Execute synchronously (existing behavior)

**Note**: This is optional. Commands can flow through streams exclusively, with MCP serving as fallback for debugging/manual testing.

### Voice AI Agent Integration

#### Command Execution Flow

**Integration Pattern**:

```python
class VoiceAIAgent:
    def __init__(self, ...):
        # ... existing initialization ...
        self.command_publisher = CommandPublisher(redis_client)
        self.state_consumer = StateConsumer(redis_client, instance_id)
        self.state_cache = StateCache()
        self.sequence_tracker = SequenceTracker()
    
    async def execute_action(self, action_type, params):
        # Publish command to stream
        command_id = await self.command_publisher.publish_command(
            self.session_id,
            action_type,
            params
        )
        
        # Wait for state update (with timeout)
        try:
            state_update = await self.state_consumer.wait_for_update(
                command_id,
                timeout=5.0
            )
            
            # Apply diff to state cache
            semantic_events = self.state_cache.apply_diff(
                state_update["state_diff"]
            )
            
            # Return result
            return {
                "action_result": state_update["action_result"],
                "state": self.state_cache.get_current_state(),
                "semantic_events": semantic_events
            }
        except TimeoutError:
            # Fallback to MCP
            return await self._fallback_to_mcp(action_type, params)
```

#### State Consumer Background Task

**Integration Pattern**:

```python
# Start state consumer on agent initialization
async def initialize():
    # ... existing initialization ...
    
    # Start state consumer
    asyncio.create_task(self.state_consumer.start_consuming())
```

---

## Implementation Checklist

### Browser Agent Implementation

#### Phase 1: Core Components

- [ ] **StateDiffEngine** (`navigator/state/diff_engine.py`)
  - [ ] State snapshot capture (DOM, navigation, forms, accessibility)
  - [ ] Diff computation (elements added/removed/modified/moved)
  - [ ] Semantic event detection
  - [ ] Unit tests for diff computation

- [ ] **DedupCache** (`navigator/state/dedup_cache.py`)
  - [ ] In-memory cache with TTL
  - [ ] Command ID tracking (processing, processed)
  - [ ] Cleanup of expired entries
  - [ ] Unit tests

- [ ] **SequenceTracker** (`navigator/state/sequence_tracker.py`)
  - [ ] Per-session sequence tracking
  - [ ] Sequence validation (expected = last + 1)
  - [ ] Gap detection and error handling
  - [ ] Unit tests

- [ ] **StatePublisher** (`navigator/streaming/state_publisher.py`)
  - [ ] Redis Streams connection
  - [ ] State update envelope construction
  - [ ] Stream publishing (with error handling)
  - [ ] Integration tests

#### Phase 2: Command Consumption

- [ ] **CommandConsumer** (`navigator/streaming/command_consumer.py`)
  - [ ] Redis Streams consumer group setup
  - [ ] Message consumption loop (blocking read)
  - [ ] Sequence validation
  - [ ] Dedup check
  - [ ] Action execution integration
  - [ ] Message acknowledgment
  - [ ] Error handling (transient vs permanent)
  - [ ] Integration tests

- [ ] **BrowserSessionManager Integration**
  - [ ] Add StateDiffEngine instance
  - [ ] Add StatePublisher instance
  - [ ] Modify execute_action() to capture state and publish updates
  - [ ] Add command consumer background task
  - [ ] Integration tests

#### Phase 3: Integration & Testing

- [ ] **End-to-End Testing**
  - [ ] Command → Action → State Update flow
  - [ ] Sequence ordering validation
  - [ ] Idempotency testing (duplicate commands)
  - [ ] Error handling (sequence gaps, processing failures)
  - [ ] Multiple instance testing (consumer groups)

- [ ] **Performance Testing**
  - [ ] Latency measurement (command → state update)
  - [ ] Throughput testing (messages per second)
  - [ ] Memory usage (state snapshots, diffs)

### Voice AI Agent Implementation

#### Phase 1: Core Components

- [ ] **SequenceTracker** (`{voice_ai_agent}/state/sequence_tracker.py`)
  - [ ] Per-session sequence tracking
  - [ ] Sequence number generation
  - [ ] Stream recovery (query highest sequence number)
  - [ ] Unit tests

- [ ] **StateCache** (`{voice_ai_agent}/state/cache.py`)
  - [ ] State structure (URL, DOM elements, form states)
  - [ ] Diff application (elements added/removed/modified)
  - [ ] State query methods
  - [ ] Unit tests

#### Phase 2: Stream Integration

- [ ] **CommandPublisher** (`{voice_ai_agent}/streaming/command_publisher.py`)
  - [ ] Redis Streams connection
  - [ ] Command envelope construction
  - [ ] Stream publishing
  - [ ] Integration tests

- [ ] **StateConsumer** (`{voice_ai_agent}/streaming/state_consumer.py`)
  - [ ] Redis Streams consumer group setup
  - [ ] Message consumption loop
  - [ ] Command ID correlation
  - [ ] State update processing
  - [ ] Integration tests

#### Phase 3: Agent Integration

- [ ] **Voice AI Agent Integration**
  - [ ] Modify command execution to use CommandPublisher
  - [ ] Add StateConsumer background task
  - [ ] Integrate StateCache for state management
  - [ ] Add fallback to MCP on timeout/errors
  - [ ] Integration tests

- [ ] **End-to-End Testing**
  - [ ] Command → State Update flow
  - [ ] State cache updates
  - [ ] Semantic event extraction
  - [ ] Fallback behavior

### Configuration

- [ ] **Environment Variables**
  - [ ] `REDIS_STREAMS_ENABLED`: Enable/disable stream mode (default: true)
  - [ ] `REDIS_STREAMS_CONSUMER_GROUP_BROWSER`: Browser agent consumer group name
  - [ ] `REDIS_STREAMS_CONSUMER_GROUP_VOICE`: Voice agent consumer group name
  - [ ] `REDIS_STREAMS_INSTANCE_ID`: Instance identifier
  - [ ] `REDIS_STREAMS_DEDUP_TTL`: Dedup cache TTL in seconds

- [ ] **Stream Configuration**
  - [ ] Stream max length: 10,000 messages
  - [ ] Stream TTL: 1 hour after last activity
  - [ ] Consumer idle timeout: 60 seconds (for pending message claims)

### Documentation

- [ ] **API Documentation**
  - [ ] Message schema documentation
  - [ ] State diff format documentation
  - [ ] Semantic events reference

- [ ] **Developer Documentation**
  - [ ] Component architecture
  - [ ] Integration guide
  - [ ] Troubleshooting guide

---

## Key Implementation Details

### Redis Streams Operations

**Create Consumer Group**:
```python
await redis.xgroup_create(
    stream_key,
    consumer_group,
    id="0",  # Start from beginning
    mkstream=True  # Create stream if doesn't exist
)
```

**Read from Consumer Group**:
```python
messages = await redis.xreadgroup(
    consumer_group,
    consumer_name,
    {stream_key: ">"},  # ">" means new messages
    count=1,
    block=1000  # Block for 1 second
)
```

**Acknowledge Message**:
```python
await redis.xack(stream_key, consumer_group, message_id)
```

**Claim Pending Messages**:
```python
pending = await redis.xpending_range(
    stream_key,
    consumer_group,
    min="-",
    max="+",
    count=100
)
# Claim messages idle > 60 seconds
claimed = await redis.xclaim(
    stream_key,
    consumer_group,
    consumer_name,
    min_idle_time=60000,  # 60 seconds in milliseconds
    message_ids=[msg.id for msg in pending]
)
```

### State Diff Computation

**State Snapshot Structure**:
- DOM tree: List of interactive elements with indices, selectors, attributes
- Navigation: URL, title, ready state
- Forms: Field values, validation states
- Accessibility: Landmarks, focus, live regions

**Diff Algorithm**:
1. Compare DOM trees (element-by-element comparison by index/selector)
2. Identify added/removed/modified/moved elements
3. Compare navigation state
4. Compare form states
5. Compare accessibility tree
6. Detect semantic events from changes

### Error Handling

**Sequence Gap**:
- If sequence number > expected: Publish error event, request retransmission
- If sequence number < expected: Skip (duplicate), acknowledge

**Processing Failure**:
- Transient error: Don't acknowledge (allows redelivery)
- Permanent error: Publish error event, then acknowledge (prevents infinite retry)

**Stream Unavailability**:
- Fallback to MCP/REST synchronous execution
- Log warning, continue operation

---

## Testing Strategy

### Unit Tests

- StateDiffEngine: Diff computation logic
- DedupCache: Cache operations, TTL expiration
- SequenceTracker: Sequence validation, gap detection
- StateCache: Diff application, state updates

### Integration Tests

- CommandConsumer: End-to-end command consumption
- StatePublisher: State update publishing
- CommandPublisher + StateConsumer: Full round-trip

### End-to-End Tests

- Multiple commands in sequence (ordering validation)
- Multiple instances (consumer group load distribution)
- Failure scenarios (consumer crash, sequence gaps)
- Idempotency (duplicate commands)

### Performance Tests

- Latency: Command → State Update round-trip
- Throughput: Messages per second
- Memory: State snapshot and diff sizes

---

## Next Steps

1. **Start with Browser Agent Components**:
   - Implement StateDiffEngine (core functionality)
   - Implement DedupCache and SequenceTracker (supporting components)
   - Implement StatePublisher (output component)

2. **Add Command Consumption**:
   - Implement CommandConsumer
   - Integrate with BrowserSessionManager
   - Test end-to-end command → action → state update flow

3. **Implement Voice AI Agent Components**:
   - Implement CommandPublisher and StateConsumer
   - Integrate with Voice AI Agent
   - Test full round-trip

4. **Testing & Refinement**:
   - Comprehensive testing (unit, integration, e2e)
   - Performance tuning
   - Error handling refinement

---

**Last Updated**: 2026-01-13  
**Version**: 1.0.0
# Browser Automation Agent Guide

**Version**: 1.0.0  
**Date**: 2026-01-14

Complete technical reference for agent integration. Schemas, contracts, and architectural details.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Agent Responsibilities](#agent-responsibilities)
3. [Communication Protocols](#communication-protocols)
4. [MCP Tools Reference](#mcp-tools-reference)
5. [Browser Actions Reference](#browser-actions-reference)
6. [Event Streams](#event-streams)
7. [Session Lifecycle](#session-lifecycle)
8. [Authentication Patterns](#authentication-patterns)
9. [Error Handling](#error-handling)

---

## Architecture

### System Flows

**1. Presentation/Agent Flow**
- Real-time browser automation with video streaming
- LiveKit WebRTC for video
- MCP tools for control
- Redis Pub/Sub for events
- Use case: Demos, presentations, interactive sessions

**2. Knowledge Retrieval Flow** (see `KNOWLEDGE_EXTRACTION.md`)
- Long-running website exploration
- Temporal workflows for durability
- Use case: Website analysis, data extraction

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      LiveKit Room                            │
│                                                               │
│  ┌──────────────┐              ┌──────────────────────┐    │
│  │ External     │              │ Browser Automation    │    │
│  │ Agent        │──────────────▶│ Service              │    │
│  │              │  HTTP POST    │                      │    │
│  │ - Calls MCP  │  (tools)      │ - Executes actions   │    │
│  │ - Subscribes │◀──────────────│ - Publishes video    │    │
│  │   to video   │  WebRTC       │ - Broadcasts events  │    │
│  │ - Listens to │◀──────────────│                      │    │
│  │   events     │  Redis        │                      │    │
│  └──────────────┘  Pub/Sub      └──────────────────────┘    │
└───────────────────────────────────────────────────────────────┘

Data Storage:
├── MongoDB: Sessions, browser state, knowledge
└── Redis: Event streams, job queue
```

---

## Agent Responsibilities

### Core Responsibilities

| Responsibility | Description |
|----------------|-------------|
| **Session Management** | Start/pause/resume/close browser sessions |
| **Action Execution** | Convert high-level intents to browser actions |
| **Visual Observation** | Process LiveKit video frames with vision models |
| **Authentication** | Detect login pages, enter credentials |
| **Event Processing** | React to Redis Pub/Sub browser events |
| **Error Recovery** | Detect stuck states, retry failed actions |

### Agent Boundaries

**Agent SHOULD do**:
- High-level decision making
- User intent interpretation
- Authentication credential management
- Error recovery strategies
- User communication

**Agent SHOULD NOT do**:
- Low-level browser control (use MCP tools)
- Direct DOM manipulation (use actions)
- Video encoding/streaming (handled by service)
- State persistence (handled by MongoDB)

---

## Communication Protocols

### 1. MCP Tools (HTTP REST API)

**Direction**: Agent → Browser Automation Service

**Endpoint**: `POST http://localhost:8000/mcp/tools/call`

**Request Schema**:
```json
{
  "tool": "string (tool name)",
  "arguments": {
    "room_name": "string (required for session tools)",
    ...
  }
}
```

**Response Schema**:
```json
[
  {
    "type": "text",
    "text": "string (JSON-encoded result)"
  }
]
```

**Use case**: All browser actions and session management

---

### 2. LiveKit WebRTC (Video Stream)

**Direction**: Browser → Agent

**Protocol**: WebRTC video track subscription

**Frame Format**: H.264/VP8 video at configurable FPS (default: 10)

**Use case**: Visual observation, UI analysis, verification

---

### 3. Redis Pub/Sub (Event Stream)

**Direction**: Browser → Agent

**Channel Pattern**: `browser:events:{room_name}`

**Message Schema**:
```json
{
  "type": "string (event_type)",
  "data": {
    "url": "string",
    ...
  }
}
```

**Event Types**:
- `page_navigation`: Page URL changed
- `action_completed`: Action executed successfully
- `action_error`: Action failed
- `dom_change`: DOM structure changed
- `page_load_complete`: Page fully loaded
- `browser_error`: Browser-level error

**Use case**: Real-time state updates, background notifications

---

### 4. MongoDB (Persistent Storage)

**Direction**: Service → Storage

**Collections** (prefix: `brwsr_auto_svc_`):
- `brwsr_auto_svc_sessions`: Session state
- `brwsr_auto_svc_pages`: Knowledge pages
- `brwsr_auto_svc_links`: Link relationships
- `brwsr_auto_svc_jobs`: Job metadata

**Use case**: Long-term storage, cross-session state, analytics

---

## MCP Tools Reference

### Session Management Tools (8 tools)

#### 1. `start_browser_session`

Start a browser session for a LiveKit room with video streaming.

**Input Schema**:
```json
{
  "room_name": "string (required)",
  "initial_url": "string (optional)",
  "viewport_width": "integer (default: 1920)",
  "viewport_height": "integer (default: 1080)",
  "fps": "integer (default: 10)",
  "livekit_url": "string (optional if env var set)",
  "livekit_api_key": "string (optional if env var set)",
  "livekit_api_secret": "string (optional if env var set)"
}
```

**Output Schema**:
```json
{
  "status": "started",
  "room_name": "string"
}
```

---

#### 2. `pause_browser_session`

Pause video publishing (browser stays alive).

**Input Schema**: `{"room_name": "string"}`

---

#### 3. `resume_browser_session`

Resume video publishing.

**Input Schema**: `{"room_name": "string"}`

---

#### 4. `close_browser_session`

Close browser session and stop streaming.

**Input Schema**: `{"room_name": "string"}`

---

#### 5. `recover_browser_session`

Attempt to recover a failed session.

**Input Schema**: `{"room_name": "string"}`

---

#### 6. `get_browser_context`

Get current browser state.

**Input Schema**: `{"room_name": "string"}`

**Output Schema**:
```json
{
  "url": "string",
  "title": "string",
  "scroll_x": "integer",
  "scroll_y": "integer",
  "viewport_width": "integer",
  "viewport_height": "integer",
  "cursor_x": "integer",
  "cursor_y": "integer"
}
```

---

#### 7. `get_screen_content`

Get detailed screen content with DOM summary.

**Input Schema**: `{"room_name": "string"}`

**Output Schema**:
```json
{
  "url": "string",
  "title": "string",
  "dom_summary": "string (text representation)",
  "visible_elements_count": "integer"
}
```

---

#### 8. `find_form_fields`

Intelligently find form field indices (username, password, submit).

**Input Schema**: `{"room_name": "string"}`

**Output Schema**:
```json
{
  "username_index": "integer",
  "password_index": "integer",
  "submit_index": "integer"
}
```

**Performance**: 3-5x faster than brute-force searching

**Detection Logic**:
- Username: `type="email"` or `type="text"` with semantic indicators (placeholder/name/id contains "email", "username", "user", "login")
- Password: `type="password"`
- Submit: `type="submit"` or button with text containing "login", "sign in", "submit"

---

### Action Execution Tool

#### 9. `execute_action`

Execute any of 45+ browser actions.

**Input Schema**:
```json
{
  "room_name": "string (required)",
  "action_type": "string (required, see actions below)",
  "params": "object (action-specific parameters)"
}
```

**Output Schema**:
```json
{
  "success": "boolean",
  "error": "string | null",
  "data": "object (optional)"
}
```

---

## Browser Actions Reference

### Navigation Actions (9 actions)

| Action | Parameters | Purpose |
|--------|------------|---------|
| `navigate` | `url`, `new_tab` (optional) | Navigate to URL |
| `click` | `index` OR `coordinate_x/y`, `button` (optional) | Click element |
| `type` | `text`, `index` (optional) | Type into input |
| `scroll` | `direction` (up/down/left/right), `amount` (optional) | Scroll page |
| `wait` | `seconds` | Wait for time |
| `go_back` | none | Browser back |
| `go_forward` | none | Browser forward |
| `refresh` | none | Reload page |
| `send_keys` | `keys`, `index` (optional) | Keyboard events |

**Click Button Options**: `"left"`, `"right"`, `"middle"`

**Supported Keys**: `Enter`, `Escape`, `Tab`, `ArrowUp`, `ArrowDown`, `ArrowLeft`, `ArrowRight`, `Home`, `End`, `PageUp`, `PageDown`, `Backspace`, `Delete`

---

### Interaction Actions (4 actions)

| Action | Parameters | Purpose |
|--------|------------|---------|
| `right_click` | `index` OR `coordinate_x/y` | Right-click |
| `double_click` | `index` OR `coordinate_x/y` | Double-click |
| `hover` | `index` OR `coordinate_x/y` | Hover |
| `drag_drop` | `start_index`, `end_index` OR coordinates | Drag and drop |

---

### Form Actions (10 actions)

| Action | Parameters | Purpose |
|--------|------------|---------|
| `upload_file` | `file_path`, `index` (optional) | Upload file |
| `select_dropdown` | `index`, `value`/`text`/`option_index` | Select dropdown |
| `fill_form` | `fields` (array of {index, value}) | Fill multiple fields |
| `submit_form` | `index` (optional) | Submit form |
| `checkbox_set` | `index`, `checked` | Set checkbox |
| `radio_select` | `index` | Select radio |
| `multi_select` | `index`, `values` (array) | Multi-select |
| `clear` | `index` (optional) | Clear input |
| `select_all` | `index` (optional) | Select all text |
| `keyboard_shortcut` | `shortcut` | Execute shortcut |

**Form Fill Schema**:
```json
{
  "fields": [
    {"index": 3, "value": "user@example.com"},
    {"index": 4, "value": "password123"}
  ]
}
```

---

### Text Input Actions (6 actions)

| Action | Parameters | Purpose |
|--------|------------|---------|
| `type_slowly` | `text`, `delay` (optional), `index` (optional) | Type with delay |
| `copy` | none | Copy selected text |
| `paste` | `index` (optional) | Paste from clipboard |
| `cut` | none | Cut selected text |
| `select_all` | `index` (optional) | Select all text |
| `clear` | `index` (optional) | Clear input |

---

### Media Actions (5 actions)

| Action | Parameters | Purpose |
|--------|------------|---------|
| `play_video` | `index` | Play video |
| `pause_video` | `index` | Pause video |
| `seek_video` | `index`, `time` | Seek to time |
| `adjust_volume` | `index`, `volume` (0-100) | Set volume |
| `toggle_mute` | `index` | Mute/unmute |

---

### Tab Management Actions (4 actions)

| Action | Parameters | Purpose |
|--------|------------|---------|
| `switch_tab` | `index` | Switch to tab |
| `close_tab` | `index` (optional) | Close tab |
| `new_tab` | `url` (optional) | Open new tab |
| `reopen_tab` | none | Reopen closed tab |

---

### Advanced Actions (7 actions)

| Action | Parameters | Purpose |
|--------|------------|---------|
| `screenshot` | `full_page` (optional) | Take screenshot |
| `get_element_text` | `index` | Extract text |
| `get_element_attribute` | `index`, `attribute` | Get attribute |
| `execute_javascript` | `code` | Run JS code |
| `zoom_in` | none | Zoom in |
| `zoom_out` | none | Zoom out |
| `fullscreen` | none | Toggle fullscreen |

---

## Event Streams

### Event Schemas

#### 1. `page_navigation`

```json
{
  "type": "page_navigation",
  "data": {
    "url": "string",
    "title": "string"
  }
}
```

#### 2. `action_completed`

```json
{
  "type": "action_completed",
  "data": {
    "action_type": "string",
    "success": true,
    "index": "integer (optional)"
  }
}
```

#### 3. `action_error`

```json
{
  "type": "action_error",
  "data": {
    "action_type": "string",
    "error": "string",
    "index": "integer (optional)"
  }
}
```

#### 4. `page_load_complete`

```json
{
  "type": "page_load_complete",
  "data": {
    "url": "string",
    "load_time_ms": "integer"
  }
}
```

#### 5. `browser_error`

```json
{
  "type": "browser_error",
  "data": {
    "error": "string",
    "url": "string"
  }
}
```

---

## Session Lifecycle

### 1. Initialization Phase

**Actions**:
1. Agent joins LiveKit room
2. Call `start_browser_session` tool
3. Subscribe to Redis channel: `browser:events:{room_name}`
4. Subscribe to LiveKit video track

**State**: Session ready for actions

---

### 2. Active Phase

**Actions**:
1. Query state via `get_screen_content` or `get_browser_context`
2. Execute actions via `execute_action` tool
3. Listen for events via Redis Pub/Sub
4. Process video frames from LiveKit

**State**: Session executing actions

---

### 3. Termination Phase

**Actions**:
1. Call `close_browser_session` tool
2. Unsubscribe from Redis channel
3. Disconnect from LiveKit

**State**: Session closed, resources cleaned up

---

## Authentication Patterns

### Recommended Login Flow

**Step 1: Detect Login Page**
- Query: `get_screen_content`
- Check: `dom_summary` contains "login", "sign in", "username", "password"

**Step 2: Find Form Fields**
- Use: `find_form_fields` tool (fast, intelligent detection)
- Returns: `{username_index, password_index, submit_index}`

**Step 3: Enter Credentials**
- Action: `type` with `username_index`
- Action: `type` with `password_index`
- Action: `click` with `submit_index`

**Step 4: Validate Success**
- Wait: 3 seconds
- Query: `get_browser_context`
- Check: URL changed from login page

---

## Code Organization

### Action Dispatcher Module Structure

The `ActionDispatcher` has been modularized into focused handler modules:

```
navigator/action/dispatcher/
├── __init__.py                          # Exports ActionDispatcher
├── dispatcher.py                        # Main ActionDispatcher class (routing & orchestration)
├── handlers/
│   ├── navigation.py                    # Navigate, go_back, go_forward, refresh
│   ├── interaction.py                  # Click, right_click, double_click, hover, drag_drop
│   ├── input.py                        # Type, send_keys, text_input_action, type_slowly
│   ├── scrolling.py                    # Scroll actions
│   └── utility.py                      # Wait, screenshot
└── utils.py                             # Shared utilities (JavaScript execution, element lookup)
```

**Benefits:**
- Clear separation by action type
- Easier to locate and modify specific action handlers
- Better testability - handlers can be tested independently
- All existing imports continue to work via `__init__.py` re-exports

---

## Error Handling

### Common Error Scenarios

#### 1. Element Not Found

**Error**: `"Element not found"`

**Recovery**:
1. Query: `get_screen_content` (refresh DOM state)
2. Find element again with new index
3. Retry action with correct index

---

#### 2. Page Load Timeout

**Error**: `"Navigation timeout"`

**Recovery**:
1. Wait additional time
2. Query: `get_browser_context` (check if partially loaded)
3. If URL matches target: Continue
4. If URL doesn't match: Retry `navigate` action

---

#### 3. Session Crashed

**Error**: `"Browser session not found"`

**Recovery**:
1. Call: `recover_browser_session`
2. If recovery succeeds: Retry action
3. If recovery fails: Call `start_browser_session` (new session)

---

#### 4. Action Stuck

**Detection**: No event received for 30+ seconds

**Recovery**:
1. Execute: `refresh` action (reload page)
2. Wait: 3 seconds
3. Query: `get_screen_content` (verify page loaded)
4. Retry original action

---

### Error Response Schema

All errors follow this schema:

```json
{
  "success": false,
  "error": "string (error message)",
  "error_type": "string (optional categorization)",
  "data": null
}
```

**Error Types**:
- `element_not_found`: Element index invalid
- `navigation_timeout`: Page load timeout
- `session_not_found`: Browser session doesn't exist
- `action_failed`: Action execution failed
- `network_error`: Network connectivity issue

---

## Next Steps

1. **Setup Environment**: See `dev-docs/QUICK_START.md`
2. **Knowledge Extraction**: See `dev-docs/KNOWLEDGE_EXTRACTION.md`
3. **API Reference**: Visit http://localhost:8000/docs

---

**Last Updated**: 2026-01-14  
**Version**: 1.0.0

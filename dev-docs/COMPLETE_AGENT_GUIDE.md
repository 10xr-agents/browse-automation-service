# Complete Agent Guide - Browser Automation Service

**Date**: 2026-01-13  
**Version**: 4.0.0

This is the **complete, single source of truth** for integrating with the Browser Automation Service. It covers all protocols, interfaces, tools, actions, and best practices for agent developers.

## Table of Contents

1. [Overview & Quick Start](#overview--quick-start)
2. [Communication Architecture](#communication-architecture)
3. [Complete MCP Tools Reference](#complete-mcp-tools-reference)
4. [Complete Browser Actions Reference](#complete-browser-actions-reference)
5. [Finding Element Indices](#finding-element-indices)
6. [Session Lifecycle & Coordination](#session-lifecycle--coordination)
7. [REST API Specifications](#rest-api-specifications)
8. [Redis & MongoDB Integration](#redis--mongodb-integration)
9. [Event Types](#event-types)
10. [Integration Examples](#integration-examples)
11. [Best Practices & Troubleshooting](#best-practices--troubleshooting)

---

## Overview & Quick Start

### What Is This Service?

The **Browser Automation Service** provides browser automation capabilities through two major flows:

1. **Presentation/Agent Flow**: Real-time browser automation with video streaming, controlled via MCP protocol for live demonstrations and presentations
2. **Knowledge Retrieval Flow**: Comprehensive website exploration, semantic understanding, and knowledge storage

### Key Features

- **52 tools available**: 45 browser actions + 7 session/state management tools
- **Real-time video streaming** via LiveKit WebRTC
- **Bidirectional event communication** via Redis Pub/Sub
- **Reliable job processing** via RQ for knowledge retrieval
- **Persistent state management** via MongoDB
- **MCP Protocol** for standardized tool access
- **REST API** for HTTP-based integration

### Quick Start

**1. Start the Server**

```bash
# Install dependencies
uv sync

# Start Redis (optional but recommended)
redis-server  # Or ensure Redis is running on localhost:6379

# Start MongoDB (optional but recommended)
# MongoDB runs on localhost:27017 by default

# Start the server
uv run python navigator/start_server.py
```

The server starts on `http://localhost:8000` with:
- **REST API**: `http://localhost:8000`
- **MCP Tools**: `POST http://localhost:8000/mcp/tools/call`
- **WebSocket**: `ws://localhost:8000/mcp/events/{room_name}`
- **Health Check**: `http://localhost:8000/health`
- **Swagger UI**: `http://localhost:8000/docs`

**2. Environment Variables**

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

# Optional: MongoDB (for persistent data storage)
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=browser_automation_service
```

**3. Basic Agent Integration**

```python
import httpx
from redis.asyncio import Redis
import json

# Initialize HTTP client for MCP tools
mcp_client = httpx.AsyncClient(base_url="http://localhost:8000")

# Initialize Redis for events
redis = Redis(host='localhost', port=6379)

# Start browser session
result = await mcp_client.post(
    "/mcp/tools/call",
    json={
        "tool": "start_browser_session",
        "arguments": {
            "room_name": "demo-room",
            "initial_url": "https://example.com"
        }
    }
)

# Execute action
result = await mcp_client.post(
    "/mcp/tools/call",
    json={
        "tool": "execute_action",
        "arguments": {
            "room_name": "demo-room",
            "action_type": "click",
            "params": {"index": 5}
        }
    }
)
```

---

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
          │          Redis (RQ + Pub/Sub)  │
          └────────────────────────────────────┘
              (Commands & Events)
          
          │          MongoDB (Persistence)      │
          └────────────────────────────────────┘
              (State, Sessions, Knowledge)
```

### Communication Channels

| Communication Type | Direction | Technology | Why? |
|-------------------|-----------|------------|------|
| **Browser Actions** | Agent → Browser | **MCP/REST API** | Direct, immediate execution |
| **Knowledge Retrieval Jobs** | API → Worker | **RQ** | Needs persistence & retry for long-running tasks |
| **Real-time Events** | Browser → Agent | **Redis Pub/Sub** | Needs <5ms latency, no persistence needed |
| **Video Streaming** | Browser → Agent | **LiveKit WebRTC** | Low-latency video streaming |
| **Persistent Data** | Service → Storage | **MongoDB** | Long-term storage with `brwsr_auto_svc_` prefix |

### Key Principles

- Browser Automation Service publishes video **directly to LiveKit** (no relay through agent)
- Both services connect to the **same LiveKit room**
- **Jobs** (API → Worker): Use **RQ** for reliable, persistent job processing
- **Events** (Browser → Agent): Use **Redis Pub/Sub** for high-frequency, real-time events
- **Persistence** (State, Sessions, Knowledge): Use **MongoDB** with `brwsr_auto_svc_` prefixed collections
- Video flows through LiveKit WebRTC, not between servers
- Bidirectional event communication via Redis Pub/Sub

---

## Complete MCP Tools Reference

The agent can call these MCP tools via `POST /mcp/tools/call`:

### Session Management Tools

#### 1. `start_browser_session`

Start a browser session for a LiveKit room with video streaming.

**Input Schema:**
```json
{
  "room_name": "string (required)",
  "livekit_url": "string (optional, if LIVEKIT_URL env var is set)",
  "livekit_api_key": "string (optional, if LIVEKIT_API_KEY env var is set)",
  "livekit_api_secret": "string (optional, if LIVEKIT_API_SECRET env var is set)",
  "livekit_token": "string (optional, pre-generated LiveKit access token)",
  "participant_identity": "string (optional, default: 'browser-automation')",
  "participant_name": "string (optional, default: 'Browser Automation Agent')",
  "initial_url": "string (optional)",
  "viewport_width": "integer (optional, default: 1920)",
  "viewport_height": "integer (optional, default: 1080)",
  "fps": "integer (optional, default: 10)"
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

#### 2. `pause_browser_session`

Pause video publishing (keep browser alive).

**Input Schema:**
```json
{
  "room_name": "string (required)"
}
```

---

#### 3. `resume_browser_session`

Resume video publishing.

**Input Schema:**
```json
{
  "room_name": "string (required)"
}
```

---

#### 4. `close_browser_session`

Close browser session and stop streaming.

**Input Schema:**
```json
{
  "room_name": "string (required)"
}
```

---

#### 5. `recover_browser_session`

Attempt to recover a failed browser session (reconnect LiveKit, restore state).

**Input Schema:**
```json
{
  "room_name": "string (required)"
}
```

---

### Browser State Tools

#### 6. `get_browser_context`

Get current browser state (URL, title, ready state, scroll position, cursor position).

**Input Schema:**
```json
{
  "room_name": "string (required)"
}
```

**Response:**
```json
{
  "success": true,
  "error": null,
  "data": {
    "url": "https://example.com",
    "title": "Example",
    "ready_state": "complete",
    "scroll_x": 0,
    "scroll_y": 0,
    "viewport_width": 1920,
    "viewport_height": 1080,
    "cursor_x": 500,
    "cursor_y": 300
  }
}
```

---

#### 7. `get_screen_content`

Get detailed screen content with DOM summary.

**Input Schema:**
```json
{
  "room_name": "string (required)"
}
```

**Response:**
```json
{
  "success": true,
  "error": null,
  "data": {
    "url": "https://example.com",
    "title": "Example",
    "dom_summary": "Page structure with element descriptions...",
    "visible_elements_count": 15,
    "scroll_x": 0,
    "scroll_y": 0,
    "viewport_width": 1920,
    "viewport_height": 1080,
    "cursor_x": 0,
    "cursor_y": 0
  }
}
```

---

#### 8. `find_form_fields` ⭐ **RECOMMENDED FOR LOGIN**

Intelligently find form field indices by analyzing element attributes (type, name, id, placeholder). **Much faster than brute-forcing through indices.**

**Input Schema:**
```json
{
  "room_name": "string (required)"
}
```

**Response:**
```json
{
  "success": true,
  "error": null,
  "data": {
    "username_index": 13,
    "password_index": 14,
    "submit_index": 15
  }
}
```

**What It Does:**
- Analyzes element attributes to find:
  - **Username/Email field**: `type="email"` or `type="text"` with semantic indicators (placeholder/name/id containing "email", "username", "user", "login", "account")
  - **Password field**: `type="password"`
  - **Submit button**: `type="submit"` or button with text containing "login", "sign in", "submit"

**Performance:**
- **Before (brute-forcing)**: ~10-15 seconds
- **After (using this tool)**: ~2-3 seconds
- **Speedup**: 3-5x faster

**Example Usage:**
```python
# Step 1: Find form fields automatically
result = await mcp_client.post("/mcp/tools/call", json={
    "tool": "find_form_fields",
    "arguments": {"room_name": "demo-room"}
})

# Step 2: Use found indices directly
if result["success"]:
    fields = result["data"]
    await execute_action("type", {
        "text": username,
        "index": fields["username_index"]  # Uses correct index immediately!
    })
```

---

### Action Execution Tool

#### 9. `execute_action`

Execute browser actions. Supports **45 action types** (see Complete Browser Actions Reference below).

**Input Schema:**
```json
{
  "room_name": "string (required)",
  "action_type": "string (required, see action types below)",
  "params": "object (required, action-specific parameters)"
}
```

**Response:**
```json
{
  "success": true,
  "error": null,
  "data": {}
}
```

---

### Knowledge Retrieval Tools

#### 10. `start_knowledge_exploration`

Start a knowledge retrieval job to explore and extract knowledge from a website.

**Input Schema:**
```json
{
  "start_url": "string (required)",
  "max_pages": "integer (optional)",
  "max_depth": "integer (optional, default: 3)",
  "strategy": "string (optional, enum: 'BFS', 'DFS', default: 'BFS')",
  "job_id": "string (optional, auto-generated if not provided)",
  "authentication": {
    "username": "string (optional)",
    "password": "string (optional)"
  }
}
```

**Response:**
```json
{
  "job_id": "generated-job-id",
  "status": "queued",
  "message": "Job queued via RQ"
}
```

---

#### 11. `get_exploration_status`

Get live status and progress for a knowledge retrieval job.

**Input Schema:**
```json
{
  "job_id": "string (required)"
}
```

---

#### 12. `pause_exploration`

Pause a running knowledge retrieval job.

**Input Schema:**
```json
{
  "job_id": "string (required)"
}
```

---

#### 13. `resume_exploration`

Resume a paused knowledge retrieval job.

**Input Schema:**
```json
{
  "job_id": "string (required)"
}
```

---

#### 14. `cancel_exploration`

Cancel a knowledge retrieval job.

**Input Schema:**
```json
{
  "job_id": "string (required)"
}
```

---

#### 15. `get_knowledge_results`

Get results from a knowledge retrieval job (partial or final).

**Input Schema:**
```json
{
  "job_id": "string (required)",
  "partial": "boolean (optional, default: false)"
}
```

---

#### 16. `query_knowledge`

Query stored knowledge (pages, semantic search, links, sitemaps).

**Input Schema:**
```json
{
  "query_type": "string (required, enum: 'page', 'search', 'links', 'sitemap_semantic', 'sitemap_functional')",
  "params": "object (optional, query-specific parameters)"
}
```

---

## Complete Browser Actions Reference

The agent can execute **45 browser actions** via the `execute_action` MCP tool. All actions return a standardized response format.

### Core Navigation Actions (9)

#### 1. `navigate` - Navigate to URL

**Parameters:**
```json
{
  "url": "string (required)",
  "new_tab": "boolean (optional, default: false)"
}
```

**Purpose**: Navigate browser to a specific URL.

---

#### 2. `click` - Click an Element

**Parameters** (choose one method):
- **By Index**: `{"index": integer}`
- **By Coordinates**: `{"coordinate_x": integer, "coordinate_y": integer}`
- **Optional**: `{"button": "left" | "right" | "middle"}` (default: "left")

**Purpose**: Click an element on the page by index (from screen content) or by pixel coordinates.

---

#### 3. `type` - Type Text into Input Field

**Parameters:**
```json
{
  "text": "string (required)",
  "index": "integer (optional, defaults to first input field)"
}
```

**Purpose**: Type text into an input field. Use `index` to specify which input field (from screen content).

---

#### 4. `scroll` - Scroll the Page

**Parameters:**
```json
{
  "direction": "string (required, enum: 'up', 'down', 'left', 'right')",
  "amount": "integer (optional, default: 500 pixels)"
}
```

**Purpose**: Scroll the page in a specific direction by a specified amount.

---

#### 5. `wait` - Wait for Specified Time

**Parameters:**
```json
{
  "seconds": "float (required)"
}
```

**Purpose**: Wait for a specified number of seconds before continuing. Useful for allowing pages to load or animations to complete.

---

#### 6. `go_back` - Navigate Back

**Parameters**: `{}` (no parameters)

**Purpose**: Navigate back in browser history (equivalent to browser back button).

---

#### 7. `go_forward` - Navigate Forward

**Parameters**: `{}` (no parameters)

**Purpose**: Navigate forward in browser history (equivalent to browser forward button).

---

#### 8. `refresh` - Refresh Current Page

**Parameters**: `{}` (no parameters)

**Purpose**: Refresh the current page (equivalent to F5 or browser refresh button).

---

#### 9. `send_keys` - Send Keyboard Events

**Parameters:**
```json
{
  "keys": "string (required)",
  "index": "integer (optional, element to send keys to)"
}
```

**Supported Keys**: `Enter`, `Escape`, `Tab`, `ArrowUp`, `ArrowDown`, `ArrowLeft`, `ArrowRight`, `Home`, `End`, `PageUp`, `PageDown`, `Backspace`, `Delete`, etc.

**Purpose**: Send keyboard events (special keys) to the page or a specific element. Useful for form submission, navigation, etc.

---

### Interaction Actions (4)

#### 10. `right_click` - Right-Click an Element

**Parameters** (choose one method):
- **By Index**: `{"index": integer}`
- **By Coordinates**: `{"coordinate_x": integer, "coordinate_y": integer}`

**Purpose**: Right-click an element to open context menu.

---

#### 11. `double_click` - Double-Click an Element

**Parameters** (choose one method):
- **By Index**: `{"index": integer}`
- **By Coordinates**: `{"coordinate_x": integer, "coordinate_y": integer}`

**Purpose**: Double-click an element (useful for file selection, word selection, etc.).

---

#### 12. `hover` - Hover Over an Element

**Parameters** (choose one method):
- **By Index**: `{"index": integer}`
- **By Coordinates**: `{"coordinate_x": integer, "coordinate_y": integer}`

**Purpose**: Hover over an element to trigger hover effects, tooltips, or dropdown menus.

---

#### 13. `drag_drop` - Drag and Drop Elements

**Parameters:**
```json
{
  "start_index": "integer (optional, element to drag from)",
  "start_coordinate_x": "integer (optional, start X coordinate)",
  "start_coordinate_y": "integer (optional, start Y coordinate)",
  "end_index": "integer (optional, element to drop to)",
  "end_coordinate_x": "integer (optional, end X coordinate)",
  "end_coordinate_y": "integer (optional, end Y coordinate)"
}
```

**Purpose**: Drag an element and drop it to another location.

---

### Text Input Actions (6)

#### 14. `type_slowly` - Type Text Slowly

**Parameters:**
```json
{
  "text": "string (required)",
  "index": "integer (optional, defaults to first input field)",
  "delay": "float (optional, delay between characters in seconds, default: 0.1)"
}
```

**Purpose**: Type text character by character with a delay (useful for triggering autocomplete or animations).

---

#### 15. `select_all` - Select All Text

**Parameters:**
```json
{
  "index": "integer (optional, element to select text in)"
}
```

**Purpose**: Select all text in an input field or element (equivalent to Ctrl+A).

---

#### 16. `copy` - Copy Selected Text

**Parameters**: `{}` (no parameters)

**Purpose**: Copy selected text to clipboard (equivalent to Ctrl+C).

---

#### 17. `paste` - Paste Text

**Parameters:**
```json
{
  "index": "integer (optional, element to paste into)"
}
```

**Purpose**: Paste text from clipboard (equivalent to Ctrl+V).

---

#### 18. `cut` - Cut Selected Text

**Parameters**: `{}` (no parameters)

**Purpose**: Cut selected text to clipboard (equivalent to Ctrl+X).

---

#### 19. `clear` - Clear Input Field

**Parameters:**
```json
{
  "index": "integer (optional, defaults to first input field)"
}
```

**Purpose**: Clear all text from an input field.

---

### Form Actions (6)

#### 20. `upload_file` - Upload a File

**Parameters:**
```json
{
  "file_path": "string (required, path to file to upload)",
  "index": "integer (optional, file input element index)"
}
```

**Purpose**: Upload a file to a file input element.

---

#### 21. `select_dropdown` - Select Dropdown Option

**Parameters:**
```json
{
  "index": "integer (required, dropdown element index)",
  "value": "string (optional, option value to select)",
  "text": "string (optional, option text to select)",
  "option_index": "integer (optional, option index to select)"
}
```

**Purpose**: Select an option from a dropdown menu.

---

#### 22. `fill_form` - Fill Multiple Form Fields

**Parameters:**
```json
{
  "fields": "array (required, array of {index: integer, value: string})"
}
```

**Purpose**: Fill multiple form fields at once.

---

#### 23. `select_multiple` - Select Multiple Options

**Parameters:**
```json
{
  "index": "integer (required, multi-select element index)",
  "values": "array (required, array of values to select)"
}
```

**Purpose**: Select multiple options in a multi-select element.

---

#### 24. `submit_form` - Submit a Form

**Parameters:**
```json
{
  "index": "integer (optional, form element index)"
}
```

**Purpose**: Submit a form (equivalent to clicking submit button or pressing Enter).

---

#### 25. `reset_form` - Reset a Form

**Parameters:**
```json
{
  "index": "integer (optional, form element index)"
}
```

**Purpose**: Reset a form to its initial state.

---

### Media Actions (6)

#### 26. `play_video` - Play a Video

**Parameters:**
```json
{
  "index": "integer (optional, video element index)"
}
```

**Purpose**: Play a video element on the page.

---

#### 27. `pause_video` - Pause a Video

**Parameters:**
```json
{
  "index": "integer (optional, video element index)"
}
```

**Purpose**: Pause a playing video element.

---

#### 28. `seek_video` - Seek to Time in Video

**Parameters:**
```json
{
  "index": "integer (optional, video element index)",
  "time": "float (required, time in seconds)"
}
```

**Purpose**: Seek to a specific time in a video.

---

#### 29. `adjust_volume` - Adjust Video Volume

**Parameters:**
```json
{
  "index": "integer (optional, video element index)",
  "volume": "float (required, volume level 0.0 to 1.0)"
}
```

**Purpose**: Adjust the volume of a video element.

---

#### 30. `toggle_fullscreen` - Toggle Fullscreen Mode

**Parameters:**
```json
{
  "index": "integer (optional, video/element index)"
}
```

**Purpose**: Toggle fullscreen mode for a video or element.

---

#### 31. `toggle_mute` - Toggle Mute

**Parameters:**
```json
{
  "index": "integer (optional, video element index)"
}
```

**Purpose**: Toggle mute for a video element.

---

### Advanced Actions (8)

#### 32. `take_screenshot` - Take a Screenshot

**Parameters**: `{}` (no parameters)

**Purpose**: Take a screenshot of the current page.

---

#### 33. `keyboard_shortcut` - Execute Keyboard Shortcut

**Parameters:**
```json
{
  "keys": "string (required, e.g., 'Control+KeyC', 'Control+KeyV', 'Meta+KeyA')",
  "index": "integer (optional, element to send shortcut to)"
}
```

**Purpose**: Execute keyboard shortcuts (Ctrl+C, Ctrl+V, Cmd+A, etc.).

---

#### 34. `multi_select` - Multi-Select Elements

**Parameters:**
```json
{
  "indices": "array (required, array of element indices to select)"
}
```

**Purpose**: Select multiple elements at once.

---

#### 35. `highlight_element` - Highlight an Element

**Parameters:**
```json
{
  "index": "integer (required, element index to highlight)",
  "duration": "float (optional, highlight duration in seconds, default: 2.0)",
  "color": "string (optional, highlight color, default: 'yellow')"
}
```

**Purpose**: Visually highlight an element on the page.

---

#### 36. `zoom_in` - Zoom In

**Parameters**: `{}` (no parameters)

**Purpose**: Zoom in on the page.

---

#### 37. `zoom_out` - Zoom Out

**Parameters**: `{}` (no parameters)

**Purpose**: Zoom out on the page.

---

#### 38. `zoom_reset` - Reset Zoom

**Parameters**: `{}` (no parameters)

**Purpose**: Reset zoom level to default (100%).

---

#### 39. `download_file` - Download a File

**Parameters:**
```json
{
  "url": "string (optional, URL of file to download)",
  "index": "integer (optional, link element index)"
}
```

**Purpose**: Trigger a file download from a link or URL.

---

### Presentation Actions (6)

#### 40. `presentation_mode` - Enter Presentation Mode

**Parameters**: `{}` (no parameters)

**Purpose**: Enter presentation mode (fullscreen with optimized display).

---

#### 41. `show_pointer` - Show Pointer/Cursor

**Parameters:**
```json
{
  "x": "integer (optional, X coordinate)",
  "y": "integer (optional, Y coordinate)",
  "visible": "boolean (optional, show/hide pointer, default: true)"
}
```

**Purpose**: Show or hide the pointer/cursor on the page.

---

#### 42. `animate_scroll` - Animate Scroll

**Parameters:**
```json
{
  "direction": "string (required, 'up' or 'down')",
  "amount": "integer (optional, pixels to scroll, default: 500)",
  "duration": "float (optional, animation duration in seconds, default: 1.0)"
}
```

**Purpose**: Smoothly animate scrolling on the page.

---

#### 43. `highlight_region` - Highlight a Region

**Parameters:**
```json
{
  "x": "integer (required, X coordinate of top-left corner)",
  "y": "integer (required, Y coordinate of top-left corner)",
  "width": "integer (required, width of region)",
  "height": "integer (required, height of region)",
  "duration": "float (optional, highlight duration in seconds, default: 2.0)",
  "color": "string (optional, highlight color, default: 'yellow')"
}
```

**Purpose**: Highlight a rectangular region on the page.

---

#### 44. `draw_on_page` - Draw on Page

**Parameters:**
```json
{
  "path": "array (required, array of {x: integer, y: integer} points)",
  "color": "string (optional, drawing color, default: 'red')",
  "width": "integer (optional, line width, default: 2)"
}
```

**Purpose**: Draw a path on the page (useful for annotations or demonstrations).

---

#### 45. `focus_element` - Focus an Element

**Parameters:**
```json
{
  "index": "integer (required, element index to focus)"
}
```

**Purpose**: Focus an element (bring it into view and set focus).

---

## Finding Element Indices

### What Are Element Indices?

Element indices are **sequential numbers** (0, 1, 2, 3, ...) assigned to **all visible, interactive elements** on the page by the Browser Automation Service. These indices are used to identify specific elements for actions like `click` and `type`.

**Important Notes:**
- Indices are **not stable** - they can change when the page updates or elements are added/removed
- Indices include **all interactive elements** (buttons, links, inputs, etc.), not just input fields
- The first visible element gets index 0, the second gets index 1, and so on
- A page with 15 visible elements will have indices 0-14

### ⭐ Recommended Approach: Use `find_form_fields` Tool

**✅ DO: Use `find_form_fields` for Login Forms**

The `find_form_fields` tool automatically finds form field indices by analyzing element attributes. This is **much faster** than brute-forcing or parsing DOM summaries.

```python
# Step 1: Find form fields automatically
result = await mcp_client.post("/mcp/tools/call", json={
    "tool": "find_form_fields",
    "arguments": {"room_name": "demo-room"}
})

# Step 2: Use found indices directly
if result["success"]:
    fields = result["data"]
    await execute_action("type", {
        "text": username,
        "index": fields["username_index"]  # Uses correct index immediately!
    })
    await execute_action("type", {
        "text": password,
        "index": fields["password_index"]
    })
```

**Performance:**
- **Before (brute-forcing)**: ~10-15 seconds
- **After (using find_form_fields)**: ~2-3 seconds
- **Speedup**: 3-5x faster

### Alternative: Parse DOM Summary Intelligently

If `find_form_fields` returns `None` for any field, fall back to parsing the DOM summary:

**Step 1: Call `get_screen_content`**
```python
screen = await get_screen_content(room_name)
dom_summary = screen["data"]["dom_summary"]
# dom_summary contains: "Element 13: <input type='email' placeholder='Email'>"
```

**Step 2: Parse with LLM to find input fields**
- Look for elements with `type="email"` or `type="text"` for username
- Look for elements with `type="password"` for password
- Match by placeholder text, labels, or position in the DOM

**Step 3: Use identified indices directly**
```python
username_index = 13  # From LLM analysis
await execute_action("type", {
    "text": username,
    "index": username_index
})
```

### ❌ DON'T: Brute-Force Through Indices

```python
# ❌ BAD: Trying indices 0-5 blindly
for i in range(6):
    result = await execute_action("type", {"text": username, "index": i})
    if result["success"]:
        break
```

**Why This Is Bad:**
- Wastes time trying wrong indices
- May fail if fields are beyond the range you're trying
- Inefficient and slow

---

## Session Lifecycle & Coordination

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

3. **Agent** calls MCP tool:
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
- ✅ Bidirectional communication via MCP/REST API + Redis Pub/Sub

---

### Phase 4: Pausing Screen Share

**When:** User requests to pause or agent determines browser not needed temporarily

**Flow:**
1. **Agent** sends pause command via MCP or REST API
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
1. **Agent** sends resume command via MCP or REST API
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
1. **Agent** sends close command via MCP or REST API
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

## REST API Specifications

### Base URL

**Default**: `http://localhost:8000`

### OpenAPI/Swagger Specification

The complete OpenAPI 3.0 specification is available. View interactive API documentation:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

### Browser Automation Endpoints

#### POST `/mcp/tools/call`

Execute MCP tools via HTTP.

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

List all available MCP tools.

**Response:**
```json
{
  "tools": [
    {
      "name": "start_browser_session",
      "description": "Start a browser session for a LiveKit room with video streaming"
    }
    // ... more tools
  ]
}
```

---

#### GET `/health`

Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "service": "browser-automation-websocket"
}
```

---

### Knowledge Retrieval Endpoints

#### POST `/api/knowledge/explore/start`

Start a knowledge retrieval job.

**Request:**
```json
{
  "start_url": "https://example.com",
  "max_pages": 100,
  "max_depth": 3,
  "strategy": "BFS",
  "job_id": "optional-job-id",
  "include_paths": ["/docs/*"],
  "exclude_paths": ["/admin/*", "/api/*"],
  "authentication": {
    "username": "demo@example.com",
    "password": "secure-password"
  }
}
```

**Request Fields:**
- `start_url` (string, required): Starting URL for exploration
- `max_pages` (integer, optional): Maximum number of pages to explore
- `max_depth` (integer, optional, default: 3): Maximum exploration depth
- `strategy` (string, optional, default: "BFS"): Exploration strategy ("BFS" or "DFS")
- `job_id` (string, optional): Optional job ID (auto-generated if not provided)
- `include_paths` (array of strings, optional): Path patterns to include
- `exclude_paths` (array of strings, optional): Path patterns to exclude
- `authentication` (object, optional): Authentication credentials for protected websites
  - `username` (string, required if authentication provided): Username or email for login
  - `password` (string, required if authentication provided): Password for login

**Authentication Flow:**
When `authentication` is provided, the service will:
1. Navigate to `start_url`
2. Detect login form (username/password fields)
3. Fill in credentials and submit form
4. Verify authentication success
5. Maintain session (cookies/headers) throughout exploration

**Security:**
- Passwords are never logged (only username is logged)
- Credentials are never persisted (not stored in MongoDB)
- Credentials are cleared from memory after job completion

**Response:**
```json
{
  "job_id": "generated-job-id",
  "status": "queued",
  "message": "Job queued via RQ. Use /api/knowledge/explore/status/{job_id} to check progress. Workers are automatically managed by JobManager (no manual worker startup needed)"
}
```

---

#### GET `/api/knowledge/explore/status/{job_id}`

Get live progress for a job.

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

Pause a running job.

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

Resume a paused job.

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

Cancel a job.

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

Get job results (partial or final).

**Query Parameters:**
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

List all jobs.

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

## Redis & MongoDB Integration

### Redis Configuration

**Default Connection**: `redis://localhost:6379`

**Environment Variables:**
```bash
REDIS_URL=redis://localhost:6379  # Optional: Custom Redis URL
```

**Critical Configuration for RQ:**
```python
# IMPORTANT: RQ requires decode_responses=False because it stores binary data (pickled objects) in Redis
# RQ handles encoding/decoding internally
redis_conn = Redis.from_url("redis://localhost:6379", decode_responses=False)
```

### Redis Pub/Sub Channels

#### Browser Events Channel

**Channel Pattern**: `browser:events:{room_name}`

**Purpose**: Real-time browser events (page navigation, action completion, errors, etc.)

**Example:**
```python
from redis.asyncio import Redis
import json

redis = Redis(host='localhost', port=6379)
pubsub = redis.pubsub()
channel = f"browser:events:{room_name}"
await pubsub.subscribe(channel)

async for message in pubsub.listen():
    if message['type'] == 'message':
        event = json.loads(message['data'])
        # Handle event
```

#### Knowledge Retrieval Progress Channel

**Channel Pattern**: `exploration:{job_id}:progress`

**Purpose**: Real-time progress updates for knowledge retrieval jobs

**Example:**
```python
channel = f"exploration:{job_id}:progress"
await pubsub.subscribe(channel)

async for message in pubsub.listen():
    if message['type'] == 'message':
        progress = json.loads(message['data'])
        print(f"Progress: {progress['completed']}/{progress['queued']}")
```

### RQ Queues

#### Knowledge Retrieval Queue

**Queue Name**: `knowledge-retrieval`

**Purpose**: Durable job queue for long-running knowledge retrieval tasks

**Job Data Format:**
```json
{
  "start_url": "https://example.com",
  "max_pages": 100,
  "max_depth": 3,
  "strategy": "BFS",
  "job_id": "string",
  "include_paths": ["/docs/*"],
  "exclude_paths": ["/admin/*", "/api/*"],
  "authentication": {
    "username": "demo@example.com",
    "password": "secure-password"
  }
}
```

**Job Options:**
- `retry`: Retry configuration (max=3, interval=60 seconds)
- `job_timeout`: Maximum job execution time (e.g., '1h' for 1 hour)
- `job_id`: Job ID for tracking
- `authentication`: Optional authentication credentials (username/password) - never logged or persisted

**Worker Management:**
- Workers are automatically managed by the JobManager (no manual startup needed)
- Auto-scaling: Workers scale up/down based on queue length
- Health monitoring: Dead workers are automatically restarted
- Worker logs are forwarded to the main console with `[Worker-{id}]` prefix
- Stuck job monitor: Jobs stuck in 'queued' status for >2 minutes are automatically marked as failed

---

### MongoDB Configuration

**Default Connection**: `mongodb://localhost:27017`  
**Default Database**: `browser_automation_service`

**Environment Variables:**
```bash
MONGODB_URL=mongodb://localhost:27017  # Optional: Custom MongoDB URL
MONGODB_DATABASE=browser_automation_service  # Optional: Database name
```

### MongoDB Collections

All collections use the standardized prefix `brwsr_auto_svc_`:

- **`brwsr_auto_svc_pages`**: Knowledge retrieval pages (content, metadata)
- **`brwsr_auto_svc_links`**: Link relationships between pages
- **`brwsr_auto_svc_embeddings`**: Vector embeddings for semantic search
- **`brwsr_auto_svc_sessions`**: Presentation flow session state
- **`brwsr_auto_svc_jobs`**: Knowledge retrieval job state and metadata

### Storage Components

All storage components use MongoDB with graceful in-memory fallback:

- **KnowledgeStorage**: Pages and links storage
- **VectorStore**: Embedding storage and similarity search
- **SessionStore**: Session persistence with TTL
- **JobRegistry**: Job state tracking

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

## Integration Examples

### Complete Browser Controller with Login

```python
import httpx
import asyncio
from redis.asyncio import Redis
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
    
    async def connect(self):
        """Connect to MCP server (HTTP) and Redis Pub/Sub"""
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
                    elif event_type == "action_completed":
                        await self._on_action_completed(event)
                    elif event_type == "action_error":
                        await self._on_action_error(event)
                    elif event_type == "browser_error":
                        await self._on_browser_error(event)
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
        """Start browser session via MCP"""
        return await self.call_tool("start_browser_session", {
            "room_name": self.room_name,
            **kwargs
        })
    
    async def execute_action(self, action_type: str, params: dict):
        """Execute browser action via MCP"""
        return await self.call_tool("execute_action", {
            "room_name": self.room_name,
            "action_type": action_type,
            "params": params
        })
    
    async def find_form_fields(self):
        """Find form fields using find_form_fields tool"""
        result = await self.call_tool("find_form_fields", {
            "room_name": self.room_name
        })
        
        if result.get("success"):
            return result["data"]
        return None
    
    async def login(self, username: str, password: str):
        """Login to website using find_form_fields tool (FAST!)"""
        
        # Step 1: Refresh page to ensure clean state
        await self.execute_action("refresh", {})
        await asyncio.sleep(2)
        
        # Step 2: Find form fields automatically
        fields = await self.find_form_fields()
        
        if not fields or fields["username_index"] is None:
            raise ValueError("Could not find login form fields")
        
        # Step 3: Type username
        username_result = await self.execute_action("type", {
            "text": username,
            "index": fields["username_index"]
        })
        
        if not username_result.get("success"):
            raise ValueError(f"Failed to enter username: {username_result.get('error')}")
        
        # Step 4: Type password
        password_result = await self.execute_action("type", {
            "text": password,
            "index": fields["password_index"]
        })
        
        if not password_result.get("success"):
            raise ValueError(f"Failed to enter password: {password_result.get('error')}")
        
        # Step 5: Submit form
        if fields["submit_index"] is not None:
            submit_result = await self.execute_action("click", {
                "index": fields["submit_index"]
            })
        else:
            # Fallback: Use Enter key
            submit_result = await self.execute_action("send_keys", {
                "keys": "Enter"
            })
        
        if not submit_result.get("success"):
            raise ValueError(f"Failed to submit form: {submit_result.get('error')}")
        
        # Step 6: Wait for navigation/response
        await asyncio.sleep(2)
        
        return {"success": True, "message": "Login completed"}
    
    async def get_screen_content(self):
        """Get screen content for agent communication"""
        return await self.call_tool("get_screen_content", {
            "room_name": self.room_name
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
```

---

### Knowledge Retrieval Coordinator

```python
import asyncio
from redis.asyncio import Redis
import json
import logging
import httpx

logger = logging.getLogger(__name__)

class KnowledgeRetrievalCoordinator:
    def __init__(self, api_url: str, job_id: str | None = None):
        self.api_url = api_url
        self.job_id = job_id
        self.redis = Redis(host='localhost', port=6379)
        self.pubsub = None
    
    async def start_exploration(self, start_url: str, authentication: dict | None = None, **kwargs):
        """Start knowledge retrieval and monitor progress
        
        Args:
            start_url: Starting URL for exploration
            authentication: Optional authentication dict with 'username' and 'password' (never logged or persisted)
            **kwargs: Additional exploration parameters (max_pages, max_depth, strategy, etc.)
        """
        request_data = {
            "start_url": start_url,
            **kwargs
        }
        if authentication:
            request_data["authentication"] = authentication
        
        async with httpx.AsyncClient(base_url=self.api_url) as client:
            response = await client.post(
                "/api/knowledge/explore/start",
                json=request_data
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
    
    async def pause(self):
        """Pause exploration"""
        async with httpx.AsyncClient(base_url=self.api_url) as client:
            response = await client.post(
                "/api/knowledge/explore/pause",
                json={"job_id": self.job_id}
            )
            return response.json()
    
    async def resume(self):
        """Resume exploration"""
        async with httpx.AsyncClient(base_url=self.api_url) as client:
            response = await client.post(
                "/api/knowledge/explore/resume",
                json={"job_id": self.job_id}
            )
            return response.json()
    
    async def cancel(self):
        """Cancel exploration"""
        async with httpx.AsyncClient(base_url=self.api_url) as client:
            response = await client.post(
                "/api/knowledge/explore/cancel",
                json={"job_id": self.job_id}
            )
            return response.json()
    
    async def get_results(self, partial: bool = False):
        """Get exploration results"""
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
    
    # Login using find_form_fields (FAST!)
    await browser.login(
        username="demo@example.com",
        password="secure-password"
    )
    
    # Start knowledge retrieval for the same site
    knowledge = KnowledgeRetrievalCoordinator(
        api_url="http://localhost:8000",
        job_id=None  # Auto-generated
    )
    
    # Start exploration with authentication (optional)
    result = await knowledge.start_exploration(
        start_url="https://example.com",
        max_pages=50,
        max_depth=3,
        strategy="BFS",
        authentication={
            "username": "demo@example.com",
            "password": "secure-password"
        }  # Optional: credentials never logged or persisted
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

## Best Practices & Troubleshooting

### 1. Use `find_form_fields` for Login Forms

**✅ DO:**
```python
# Find form fields automatically
fields = await find_form_fields(room_name)
await execute_action("type", {
    "text": username,
    "index": fields["username_index"]
})
```

**❌ DON'T:**
```python
# Brute-force through indices
for i in range(6):
    result = await execute_action("type", {"text": username, "index": i})
    if result["success"]:
        break
```

---

### 2. Use RQ for Knowledge Retrieval Jobs

**✅ DO:**
```python
# Knowledge retrieval jobs use RQ via REST API
response = await http_client.post(
    "/api/knowledge/explore/start",
    json={
        "start_url": "https://example.com",
        "max_pages": 100,
        "max_depth": 3,
        "strategy": "BFS",
        "authentication": {  # Optional: credentials never logged or persisted
            "username": "demo@example.com",
            "password": "secure-password"
        }
    }
)
# Job is queued in RQ with automatic retry (3 attempts)
```

**✅ For Browser Actions:**
```python
# Browser actions use MCP/REST API (handled directly)
response = await http_client.post(
    "/mcp/tools/call",
    json={
        "tool": "execute_action",
        "arguments": {
            "room_name": "room_123",
            "action_type": "click",
            "params": {"index": 5}
        }
    }
)
```

---

### 3. Use Redis Pub/Sub for Events

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

---

### 4. Connection Pooling

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

---

### 5. Error Handling

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

---

### 6. Session Lifecycle Management

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

### 7. Action Execution Best Practices

**✅ DO:**
- Always check `success` field in response before proceeding
- Wait after navigation - Use `wait` action or wait 2-3 seconds after `navigate` for page to load
- Use `get_screen_content` to verify page state after actions
- Handle errors gracefully - Check `error` field and retry or report to user
- Use `index` for reliability - Element indices are more stable than coordinates
- Use `send_keys` for special keys - Use `send_keys` with "Enter" for form submission instead of finding submit button
- **Use `find_form_fields` for login forms** - Much faster than brute-forcing

**❌ DON'T:**
- Ignore action responses
- Assume actions always succeed
- Use coordinates when element indices are available
- Skip waiting for page loads after navigation
- **Brute-force through indices** - Use `find_form_fields` instead

---

### 8. Performance Optimization

**Frame Rate Management:**
- **Static pages**: 1-2 FPS
- **Active interactions**: 10-15 FPS
- **Rapid changes**: 20-30 FPS (if needed)

**Latency Minimization:**
- Minimize screenshot capture time
- Use efficient encoding (H.264)
- Optimize frame conversion pipeline
- Keep MCP calls asynchronous
- Use Redis Pub/Sub for events (<5ms latency)

**Command Processing:**
- Use RQ for reliable knowledge retrieval job queuing
- Use MCP/REST API for browser action commands
- Batch commands when possible
- Implement rate limiting to prevent overload
- Use connection pooling for Redis

---

### 9. Security Considerations

**Access Control:**
- Validate room tokens before allowing browser connections
- Restrict browser automation to authorized domains
- Validate actions before execution
- Log all browser actions for audit

**Content Filtering:**
- Filter sensitive content before streaming
- Respect privacy settings
- Handle authentication pages carefully
- Don't stream passwords or sensitive form data

**Domain Restrictions:**
- Use `allowed_domains` to restrict navigation
- Use `prohibited_domains` to block specific sites
- Validate URLs before navigation
- Log domain violations for audit

---

### 10. Error Handling & Recovery

#### Browser Service Failures

**Scenario:** Browser crashes or becomes unresponsive

**Recovery:**
1. Browser service detects failure
2. Sends `browser_error` event via Redis Pub/Sub to agent
3. Agent receives event in Pub/Sub handler
4. Agent informs user and offers to restart
5. If user agrees, agent sends command via MCP/REST API: `start_browser_session`

---

#### Network Interruptions

**Scenario:** LiveKit connection lost

**Recovery:**
1. Both services implement reconnection logic
2. Browser service republishes video track on reconnect
3. Agent resubscribes to video track
4. MCP connection retries automatically

---

#### Action Failures

**Scenario:** Browser action fails (element not found, timeout, etc.)

**Recovery:**
1. Browser service sends `action_error` event via Redis Pub/Sub
2. Agent receives event in Pub/Sub handler
3. Agent uses vision to analyze current page state (latest video frame)
4. Agent generates corrective action and sends via MCP/REST API, or asks user for clarification

---

#### Knowledge Retrieval Job Failures

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

## Summary

**Total Available Tools**: **52 tools**

- **45 Browser Actions**: Core navigation (9), Interaction (4), Text input (6), Form (6), Media (6), Advanced (8), Presentation (6)
- **8 Session/State Management Tools**: `start_browser_session`, `pause_browser_session`, `resume_browser_session`, `close_browser_session`, `recover_browser_session`, `get_browser_context`, `get_screen_content`, `find_form_fields`
- **8 Knowledge Retrieval Tools**: `start_knowledge_exploration`, `get_exploration_status`, `pause_exploration`, `resume_exploration`, `cancel_exploration`, `get_knowledge_results`, `query_knowledge`

**Communication Channels:**
- **MCP/REST API**: Browser actions and session management
- **Redis Pub/Sub**: Real-time events and progress updates
- **RQ**: Reliable knowledge retrieval job processing
- **LiveKit WebRTC**: Video streaming
- **MongoDB**: Persistent state and knowledge storage

**Key Recommendations:**
1. **Use `find_form_fields` for login forms** - 3-5x faster than brute-forcing
2. **Use Redis Pub/Sub for events** - <5ms latency
3. **Use RQ for knowledge retrieval jobs** - Reliable with retry
4. **Always close browser sessions** - Prevent zombie processes
5. **Handle errors gracefully** - Check `success` field in all responses

---

**Last Updated**: 2026-01-13  
**Version**: 4.0.0

# Browser Automation Service - Architecture

**Date**: 2026-01-13  
**Version**: 1.0.0

---

## Table of Contents

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Core Foundation](#core-foundation)
4. [Two Major Service Flows](#two-major-service-flows)
5. [Component Architecture](#component-architecture)
6. [Data Persistence](#data-persistence)
7. [Communication Protocols](#communication-protocols)
8. [State Management](#state-management)
9. [Event-Driven Architecture](#event-driven-architecture)
10. [Data Schemas](#data-schemas)
11. [Integration Points](#integration-points)
12. [Scalability & Performance](#scalability--performance)

---

## Overview

**Browser Automation Service** is a production-ready server that provides browser automation capabilities through two major flows:

1. **Presentation/Agent Flow**: Real-time browser automation with video streaming, controlled via MCP protocol for live demonstrations and presentations
2. **Knowledge Retrieval Flow**: Comprehensive website exploration, semantic understanding, and knowledge storage

### Key Characteristics

- **Event-driven architecture** using `bubus` event bus
- **Type-safe** with Pydantic v2 models throughout
- **Async-first** design using Python asyncio
- **CDP-based** browser control via `cdp-use` wrapper
- **Modular** with clear separation of concerns
- **MCP Protocol** for external service integration
- **LiveKit Integration** for real-time video streaming
- **Room-based sessions** for multi-tenant support
- **Redis/RQ** for scalable communication
- **MongoDB** for persistent data storage (all collections prefixed with `brwsr_auto_svc_`)
- **Knowledge Graph** for website understanding

### Architecture Approach

**Embedded Source with Extension Boundaries:**
- **`browser_use/`**: Embedded source code of Browser-Use library (version 0.11.2)
- **`navigator/`**: Our extensions that import `browser_use` as a library
- **Import Pattern**: All `navigator/` code imports from `browser_use` like: `from browser_use import BrowserSession`

**Why This Approach:**
- Full source access for debugging and optimization
- Clear boundaries between upstream and custom code
- Performance benefits from direct access
- Flexibility to modify when needed (with documentation)
- Clear upgrade path via git merge/replace

---

## System Architecture

### High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    External Services                             │
│  (Voice Agent Service, CLI, Web UI, etc.)                       │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     │ Redis (RQ + Pub/Sub)
                     │ - Knowledge Jobs: RQ (Agent → Browser)
                     │ - Events: Redis Pub/Sub (Browser → Agent)
                     │
┌────────────────────▼────────────────────────────────────────────┐
│              Browser Automation Service                          │
│                                                                  │
│  ┌──────────────────────────────────────────────────────┐    │
│  │         MCP Server                                     │    │
│  │  - Exposes 15+ MCP tools                               │    │
│  │  - HTTP endpoint integration                           │    │
│  └──────────────┬───────────────────────────────────────┘    │
│                 │                                             │
│  ┌──────────────▼───────────────────────────────────────┐    │
│  │   Browser Session Manager                            │    │
│  │  - Per-room session management                       │    │
│  │  - Action execution interface                        │    │
│  │  - Browser context retrieval                         │    │
│  └──────┬────────────────────┬──────────────────────────┘    │
│         │                    │                                │
│  ┌──────▼──────────┐  ┌──────▼─────────────────────────┐    │
│  │ ActionDispatcher│  │ LiveKit Streaming Service      │    │
│  │ - ActionCommand │  │ - Video streaming to LiveKit   │    │
│  │   execution     │  │ - Frame capture & encoding     │    │
│  └──────┬──────────┘  └────────────────────────────────┘    │
│         │                                                    │
│  ┌──────▼───────────────────────────────────────────────┐    │
│  │         Browser-Use Library (Embedded)               │    │
│  │  - BrowserSession                                    │    │
│  │  - BrowserProfile                                    │    │
│  │  - Tools / Agent                                     │    │
│  │  - Watchdogs (DefaultAction, Security, DOM, etc.)   │    │
│  │  - Event System                                      │    │
│  │  - CDP Integration                                   │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────┐    │
│  │     Event Broadcaster                                │    │
│  │  - Redis Pub/Sub event streaming (primary)           │    │
│  │  - MongoDB persistence (brwsr_auto_svc_*)            │    │
│  │  - WebSocket event streaming (fallback)              │    │
│  │  - Room-based event routing                          │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────┐    │
│  │   WebSocket Server                                   │    │
│  │  - FastAPI application                               │    │
│  │  - WebSocket & HTTP endpoints                        │    │
│  │  - Knowledge retrieval REST API                      │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────┐    │
│  │   Knowledge Retrieval Flow                          │    │
│  │                                                      │    │
│  │  ┌──────────────────────────────────────────────┐  │    │
│  │  │  Exploration Engine                          │  │    │
│  │  │  - Link discovery                            │  │    │
│  │  │  - External link detection                   │  │    │
│  │  │  - BFS/DFS strategies                        │  │    │
│  │  └──────────────────────────────────────────────┘  │    │
│  │                                                      │    │
│  │  ┌──────────────────────────────────────────────┐  │    │
│  │  │  Semantic Analyzer                           │  │    │
│  │  │  - Content extraction                         │  │    │
│  │  │  - Entity recognition                         │  │    │
│  │  │  - Embedding generation                        │  │    │
│  │  └──────────────────────────────────────────────┘  │    │
│  │                                                      │    │
│  │  ┌──────────────────────────────────────────────┐  │    │
│  │  │  Knowledge Pipeline                          │  │    │
│  │  │  - Orchestration                             │  │    │
│  │  │  - Progress observer                         │  │    │
│  │  │  - Job management                            │  │    │
│  │  └──────────────────────────────────────────────┘  │    │
│  │                                                      │    │
│  │  ┌──────────────────────────────────────────────┐  │    │
│  │  │  Knowledge Storage                           │  │    │
│  │  │  - MongoDB storage (brwsr_auto_svc_*)       │  │    │
│  │  │  - Vector store (embeddings)                 │  │    │
│  │  └──────────────────────────────────────────────┘  │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

---

## Core Foundation

### Browser-Use Library Components

The service extends the existing **Browser-Use** library, which provides core browser automation capabilities:

#### BrowserSession
- **Purpose**: Manages browser lifecycle, CDP connections, and coordinates multiple watchdog services
- **Key Features**:
  - Browser instance management (start, stop, kill)
  - CDP client and session management
  - Event bus integration (`bubus` event-driven architecture)
  - Watchdog service coordination
  - DOM state management
  - Screenshot capture
  - Browser state summary generation

#### BrowserProfile
- **Purpose**: Browser configuration and launch arguments
- **Key Features**:
  - Browser launch arguments
  - Display configuration (headless, window size, viewport)
  - Extension management (uBlock Origin, cookie handlers)
  - Proxy settings
  - Security settings (domain allowlist/prohibited domains)
  - User data directory and profile management
  - Video recording configuration
  - Device emulation

#### Tools Registry
- **Purpose**: Maps LLM decisions to browser operations
- **Key Features**:
  - Action registry for browser operations
  - Built-in actions: `click`, `type`, `navigate`, `scroll`, `wait`, `send_keys`, `upload_file`, `extract`, `evaluate`, etc.
  - Custom action registration
  - Action result handling

#### Agent
- **Purpose**: Main orchestrator that executes tasks using LLMs
- **Key Features**:
  - Task execution with LLM-driven decision making
  - Browser session management
  - Tool integration
  - Action execution loop
  - Vision analysis support
  - Error handling and retries

#### DomService
- **Purpose**: DOM extraction and processing
- **Key Features**:
  - DOM tree building from CDP snapshots
  - Accessibility tree generation
  - Element highlighting
  - LLM-readable DOM representation
  - Selector map generation

#### Event System
- **Purpose**: Event-driven architecture for browser actions
- **Key Events**:
  - `ClickEvent`, `TypeEvent`, `NavigateToUrlEvent`, `ScrollEvent`, `WaitEvent`, `SendKeysEvent`
  - `BrowserStateRequestEvent`, `NavigationCompleteEvent`, `BrowserErrorEvent`
  - Element selection events, file upload events

#### Watchdog Services
- **Purpose**: Specialized services that monitor browser state and react to events
- **Key Watchdogs**:
  - `DefaultActionWatchdog`: Handles click, type, scroll, navigate, send_keys actions via CDP
  - `SecurityWatchdog`: Enforces domain restrictions (allowlist/prohibited domains)
  - `DOMWatchdog`: Processes DOM snapshots, screenshots, element highlighting
  - `RecordingWatchdog`: Handles video recording
  - `AboutBlankWatchdog`: Handles empty page redirects
  - `PopupsWatchdog`: Manages JavaScript dialogs and popups
  - `DownloadsWatchdog`: Handles file downloads

---

## Two Major Service Flows

### Flow 1: Presentation/Agent Flow

**Purpose**: Live browser automation for presentations and demonstrations

**Key Features**:
- Agent session management with room-based isolation
- Real-time screen streaming to LiveKit
- Job execution via RQ (reliable, persistent job queue)
- Event broadcasting via Redis Pub/Sub (high-frequency, real-time events)
- Extensive human-like presentation actions
- Session timeout (6 hours) or explicit close
- Scalable to thousands of concurrent sessions

**Session Lifecycle**:
1. **Start**: Agent calls `start_browser_session` → Browser starts, LiveKit streaming begins
2. **Active**: Agent executes actions via MCP → Browser performs operations → Video streams
3. **Pause/Resume**: Agent can pause/resume streaming without closing browser
4. **Close**: Agent calls `close_browser_session` or timeout (6 hours) → Cleanup

**Presentation Actions**:
- Navigation: navigate, go_back, go_forward, refresh
- Interaction: click, type, scroll, hover, drag_drop
- Forms: fill_form, select_dropdown, upload_file, submit_form
- Media: play_video, pause_video, seek_video, adjust_volume
- Advanced: right_click, double_click, keyboard_shortcuts, multi_select
- Presentation: highlight_element, zoom_in, zoom_out, fullscreen

**Presentation Flow Phases**:

1. **Session Initialization**: Agent joins LiveKit room, sets up voice AI pipeline, registers event handlers
2. **Conversational Introduction**: Agent introduces itself, asks for user's name, introduces product
3. **Browser Startup**: Agent calls `start_browser_session`, browser joins LiveKit room, video streaming begins
4. **Authentication Flow**: Agent detects login page, enters credentials, validates login success
5. **Feature Walkthrough**: Agent navigates through sections, describes features, explains functionality
6. **Interactive Q&A**: User asks questions, agent answers using visual context from video frames
7. **Session Termination**: Agent closes browser session, cleans up resources, disconnects from LiveKit

---

### Flow 2: Knowledge Retrieval & Storage Flow

**Purpose**: Comprehensive website exploration and knowledge extraction

**Key Features**:
- Complete website exploration (all links, all flows)
- Semantic understanding of content structure
- Functional understanding of navigation flows
- Site map generation (semantic + functional)
- Knowledge storage in structured format
- Link tracking and flow mapping
- **External link detection** (detected but NOT followed - CRITICAL)
- Real-time progress observability
- Long-running job support with pause/resume
- Authentication support for protected websites

**Exploration Process**:
1. **Initialization**: Start from root URL, configure exploration parameters
2. **Authentication** (if provided): Detect login page, enter credentials, validate success
3. **Crawling**: Discover all links, follow navigation paths (internal links only)
4. **Analysis**: Extract semantic content, understand page structure
5. **Flow Mapping**: Track navigation flows, understand user journeys
6. **Storage**: Store knowledge in appropriate format (MongoDB, vector DB, etc.)

**Knowledge Storage**:
- **Semantic Understanding**: Content structure, topics, entities
- **Functional Understanding**: Navigation flows, user journeys, action sequences
- **Site Map**: Hierarchical structure + flow diagrams
- **Content Index**: Searchable content with metadata

---

## Component Architecture

### Presentation Flow Components

#### ActionCommand Primitives
- **Purpose**: Standardized data structures for high-level browser actions
- **Components**:
  - `ActionType` enum: Defines all supported action types
  - `ActionCommand` base class: Abstract base for all action commands
  - Specific command classes: `ClickActionCommand`, `TypeActionCommand`, `NavigateActionCommand`, `ScrollActionCommand`, `WaitActionCommand`
  - `ActionResult`: Standardized result structure with success/error/data
  - `BrowserContext`: Browser state primitive (URL, title, ready state, scroll position, viewport, cursor position)
  - `ScreenContent`: Detailed screen information for agent communication

#### ActionDispatcher
- **Purpose**: Translates `ActionCommand` primitives into browser events and executes them
- **Key Functions**:
  - Action execution engine that converts `ActionCommand` objects into browser events
  - Handler methods for each action type
  - Browser context retrieval
  - Screen content retrieval
  - Cursor position tracking

#### LiveKit Streaming Service
- **Purpose**: Streams browser video to LiveKit rooms for real-time viewing
- **Key Functions**:
  - Connects to LiveKit rooms via WebSocket
  - Publishes browser screenshots as video tracks
  - Handles token generation from API key/secret
  - Frame capture loop (configurable FPS, default 10)
  - Screenshot-to-video-frame conversion
  - Video track management (start/stop publishing)

#### Browser Session Manager
- **Purpose**: Manages browser sessions per LiveKit room with streaming integration
- **Key Functions**:
  - Per-room session management
  - Session lifecycle management (start, pause, resume, close)
  - Integration with `LiveKitStreamingService` and `ActionDispatcher`
  - Action execution interface
  - Browser context retrieval
  - Screen content retrieval
  - Automatic event broadcasting setup

#### MCP Server
- **Purpose**: Exposes Browser Automation Service capabilities as MCP tools
- **MCP Tools Exposed**:
  1. `start_browser_session`: Initialize browser session and start LiveKit streaming
  2. `pause_browser_session`: Pause video publishing (keep browser alive)
  3. `resume_browser_session`: Resume video publishing
  4. `close_browser_session`: Close browser session and stop streaming
  5. `execute_action`: Execute browser actions
  6. `get_browser_context`: Retrieve current browser state
  7. `get_screen_content`: Retrieve detailed screen content with DOM summary
  8. `recover_browser_session`: Attempt to recover a failed browser session
  9. Knowledge retrieval tools (15+ tools for exploration, status, pause/resume, etc.)

#### Event Broadcaster
- **Purpose**: Broadcasts browser events to connected clients via Redis Pub/Sub and WebSocket
- **Key Functions**:
  - Redis Pub/Sub connection management (primary)
  - WebSocket connection management per room (fallback)
  - Event broadcasting methods for all browser events
  - Automatic cleanup of disconnected WebSocket clients
  - Room-based event routing

#### WebSocket Server
- **Purpose**: FastAPI application for WebSocket and HTTP endpoints
- **Endpoints**:
  - WebSocket: `/mcp/events/{room_name}` for real-time event streaming
  - HTTP: `POST /mcp/tools/call`, `GET /mcp/tools`, `GET /health`, etc.
  - Knowledge retrieval REST API endpoints

#### Presentation Flow Manager
- **Purpose**: Manages presentation session lifecycle with timeout and queue management
- **Key Functions**:
  - Session lifecycle management (start, pause, resume, close)
  - 6-hour timeout management (configurable)
  - RQ (Redis Queue) integration for action queue
  - Browser session integration
  - Background cleanup task for expired sessions

---

### Knowledge Retrieval Components

#### Exploration Engine
- **Purpose**: Comprehensive website exploration with configurable strategies
- **Key Functions**:
  - Link discovery from HTML pages
  - Visited URL tracking (prevents duplicate exploration)
  - Depth management (configurable max_depth)
  - BFS (Breadth-First Search) strategy
  - DFS (Depth-First Search) strategy
  - Form handling (GET forms and read-only forms)
  - Base URL filtering
  - Invalid URL filtering
  - **External link detection** (detected but NOT followed - CRITICAL)

#### Semantic Analyzer
- **Purpose**: Semantic content analysis and understanding
- **Key Functions**:
  - Content extraction (title, headings, paragraphs, text)
  - Entity recognition (emails, URLs, phone numbers)
  - Topic modeling (keyword extraction, main topics)
  - Embedding generation (hash-based feature vectors, extensible to sentence-transformers/OpenAI)

#### Functional Flow Mapper
- **Purpose**: Track navigation flows and user journeys
- **Key Functions**:
  - Navigation tracking (page transitions, referrers, visit counts)
  - Click path mapping (user journey sequences)
  - Entry/exit point identification
  - Popular path analysis (by frequency)
  - Popular page analysis (by visit count)
  - Flow statistics generation

#### Knowledge Storage
- **Purpose**: Store pages and links as graph structure
- **Key Functions**:
  - Page storage (MongoDB collection: `brwsr_auto_svc_pages`)
  - Link storage (MongoDB collection: `brwsr_auto_svc_links`)
  - MongoDB integration (primary, with graceful fallback to in-memory)
  - Graph queries (get_links_from, get_links_to)

#### Vector Store
- **Purpose**: Store embeddings for semantic search
- **Key Functions**:
  - Embedding storage (URL → embedding mapping)
  - Similarity search (cosine similarity, top-k results)
  - Vector DB integration (optional, with graceful fallback to in-memory)
  - Metadata support

#### Knowledge Pipeline
- **Purpose**: Orchestrate complete exploration → analysis → storage workflow
- **Key Functions**:
  - Integrated exploration engine
  - Integrated semantic analyzer
  - Batch processing of pages with error handling
  - Automatic link discovery and storage during exploration
  - Semantic search integration
  - Progress observer integration (real-time progress updates)
  - Job management (pause, resume, cancel, status tracking)
  - External link handling (detected but not explored)

#### Site Map Generator
- **Purpose**: Generate semantic and functional sitemaps
- **Key Functions**:
  - Semantic sitemap generation (hierarchical, topic-based structure)
  - Functional sitemap generation (navigation flows, user journeys)
  - Integration with KnowledgeStorage and FunctionalFlowMapper

#### Authentication Service
- **Purpose**: Handle authentication for protected websites during knowledge retrieval
- **Key Functions**:
  - Login page detection (URL patterns + DOM analysis)
  - Form field finding (username, password, submit button)
  - Login execution (form filling + submission)
  - Login validation (URL change + page analysis)
  - Secure credential handling (never logged or persisted)

#### Job Manager
- **Purpose**: Auto-scaling RQ worker manager for production-grade job processing
- **Key Functions**:
  - Manages RQ workers as subprocesses
  - Auto-scaling logic based on queue length
  - Worker lifecycle management (start, stop, restart, health checks)
  - Integration with FastAPI startup/shutdown lifecycle events
  - Graceful shutdown with timeout
  - Worker health monitoring
  - Automatic restart on failure

#### REST API
- **Purpose**: HTTP endpoints for knowledge retrieval control
- **Endpoints**:
  - `POST /api/knowledge/explore/start`: Start exploration job (supports optional authentication)
  - `GET /api/knowledge/explore/status/{job_id}`: Get job status
  - `POST /api/knowledge/explore/pause`: Pause job
  - `POST /api/knowledge/explore/resume`: Resume job
  - `POST /api/knowledge/explore/cancel`: Cancel job
  - `GET /api/knowledge/explore/results/{job_id}`: Get results
  - `GET /api/knowledge/explore/jobs`: List all jobs

---

## Data Persistence

### MongoDB as Primary Persistence Layer

**All stateful data and long-lived information** in the Browser Automation Service is stored in **MongoDB** using a standardized collection naming convention.

### Collection Naming Convention

**All MongoDB collections MUST be prefixed with:**
```
brwsr_auto_svc_
```

**Collections**:
- `brwsr_auto_svc_pages` - Knowledge retrieval pages (content, metadata, embeddings)
- `brwsr_auto_svc_links` - Knowledge retrieval links (relationships between pages)
- `brwsr_auto_svc_embeddings` - Vector embeddings for semantic search
- `brwsr_auto_svc_sessions` - Presentation flow session state (with TTL)
- `brwsr_auto_svc_jobs` - Knowledge retrieval job state and metadata

**Why This Convention**:
- **Namespace Safety**: Collections are clearly identified as belonging to Browser Automation Service
- **Environment Isolation**: Multiple environments can share the same MongoDB instance
- **Discoverability**: Easy to identify and manage service-specific collections

### Storage Components

#### KnowledgeStorage
- **Collections**: `brwsr_auto_svc_pages`, `brwsr_auto_svc_links`
- **Purpose**: Store extracted knowledge (pages, content, link relationships)
- **Schema**:
  - Pages: URL, title, content, metadata, embeddings, timestamps
  - Links: from_url, to_url, link_type, metadata, timestamps

#### VectorStore
- **Collection**: `brwsr_auto_svc_embeddings`
- **Purpose**: Store vector embeddings for semantic search
- **Schema**:
  - URL, embedding vector, metadata, timestamps

#### SessionStore
- **Collection**: `brwsr_auto_svc_sessions`
- **Purpose**: Store presentation flow session state with TTL
- **Schema**:
  - session_id, room_name, state, created_at, expires_at, session_data

#### JobRegistry
- **Collection**: `brwsr_auto_svc_jobs`
- **Purpose**: Store knowledge retrieval job state and metadata
- **Schema**:
  - job_id, start_url, status, created_at, updated_at, results, metadata

### Configuration

MongoDB connection is configured via environment variables:
- `MONGODB_URL` - MongoDB connection URL (default: `mongodb://localhost:27017`)
- `MONGODB_DATABASE` - Database name (default: `browser_automation_service`)

### Fallback Behavior

All storage components gracefully fall back to in-memory storage if:
- MongoDB is not available
- MongoDB connection fails
- Motor (MongoDB async driver) is not installed

This ensures the system continues to function during development or when MongoDB is unavailable.

---

## Communication Protocols

### MCP (Model Context Protocol)

**Server Name**: `browser-automation-service`

**Base URL**: Configured via `BROWSER_MCP_SERVER_URL` environment variable (default: `http://localhost:8000`)

**Protocol**: HTTP REST API (MCP over HTTP)

**Endpoint Pattern**: `POST {base_url}/mcp/tools/call`

**Request Format**:
```json
{
  "tool": "tool_name",
  "arguments": {
    "room_name": "room-name",
    ...
  }
}
```

**Response Format** (MCP TextContent):
```json
[
  {
    "type": "text",
    "text": "{\"status\": \"started\", \"room_name\": \"...\"}"
  }
]
```

**Available Tools**:
- `start_browser_session`: Start browser session
- `execute_action`: Execute browser action
- `get_screen_content`: Get screen content
- `close_browser_session`: Close browser session
- `pause_browser_session`: Pause video publishing
- `resume_browser_session`: Resume video publishing
- `get_browser_context`: Get browser context
- `recover_browser_session`: Recover failed session
- Knowledge retrieval tools (15+ tools)

### Redis Pub/Sub

**Purpose**: High-frequency, real-time event streaming

**Channels**:
- Room-based channels: `browser:events:{room_name}`
- Job-based channels: `knowledge:progress:{job_id}`
- Global channels: `browser:events:global`

**Event Types**:
- `page_navigation`: Page navigation events
- `action_completed`: Action completion events
- `action_error`: Action error events
- `dom_change`: DOM change events
- `page_load_complete`: Page load completion
- `browser_error`: Browser error events
- `screen_content_update`: Screen content updates
- `presentation_started`: Presentation session started
- `presentation_paused`: Presentation paused
- `presentation_resumed`: Presentation resumed
- `action_queued`: Action queued
- `action_processing`: Action processing

### RQ (Redis Queue)

**Purpose**: Durable job queue for long-running tasks

**Queues**:
- `knowledge_exploration`: Knowledge retrieval jobs
- `browser_actions`: Browser action jobs (if needed)

**Job Features**:
- Retry support (configurable max retries and intervals)
- Job timeout (configurable, default: 1 hour)
- Job status tracking (queued, started, finished, failed)
- Job cancellation support

### WebSocket

**Purpose**: Real-time bidirectional communication (fallback to Redis Pub/Sub)

**Endpoints**:
- `/mcp/events/{room_name}`: Real-time event streaming for a room
- `/api/knowledge/explore/ws/{job_id}`: Real-time progress updates for knowledge jobs

**Message Format**:
```json
{
  "type": "event_type",
  "data": {...}
}
```

---

## State Management

### Session State

**Presentation Sessions**:
- **State Values**: ACTIVE, PAUSED, CLOSED
- **Storage**: MongoDB (`brwsr_auto_svc_sessions`) with TTL
- **Lifecycle**: Start → Active → (Pause/Resume) → Close
- **Timeout**: 6 hours (configurable)

**Knowledge Retrieval Jobs**:
- **State Values**: queued, running, paused, completed, failed, cancelled
- **Storage**: MongoDB (`brwsr_auto_svc_jobs`) + in-memory pipeline registry
- **Lifecycle**: Queued → Running → (Pause/Resume) → Completed/Failed/Cancelled

### Browser State

**Browser Context**:
- URL, title, ready state
- Scroll position (x, y)
- Viewport dimensions (width, height)
- Cursor position (x, y)

**Screen Content**:
- URL, title
- DOM summary (text representation)
- Visible elements count
- Scroll position
- Viewport dimensions
- Cursor position

### State Transitions

**Presentation Flow**:
1. **Initialization**: Agent joins room, sets up handlers
2. **Introduction**: Conversational introduction completes
3. **Browser Start**: Browser session starts, video streaming begins
4. **Active**: Browser automation active, actions executing
5. **Paused**: Video streaming paused, browser alive
6. **Resumed**: Video streaming resumed
7. **Termination**: Browser closed, resources cleaned up

**Knowledge Retrieval Flow**:
1. **Queued**: Job added to RQ queue
2. **Running**: Worker picks up job, exploration begins
3. **Paused**: Job paused (can be resumed)
4. **Resumed**: Job resumed from pause point
5. **Completed**: Exploration finished successfully
6. **Failed**: Exploration failed with error
7. **Cancelled**: Job cancelled by user or timeout

---

## Event-Driven Architecture

### Event Bus Architecture

The event bus (`bubus`) coordinates all browser operations:

```
Agent/Tools → Events → Event Bus → Watchdogs → CDP → Browser
```

### Event Types

#### Agent/Tools → BrowserSession Events
- `NavigateToUrlEvent`: Navigate to URL
- `ClickElementEvent`: Click an element
- `TypeTextEvent`: Type text into element
- `ScrollEvent`: Scroll page
- `GoBackEvent`: Navigate back
- `SendKeysEvent`: Send keyboard events
- `UploadFileEvent`: Upload file
- And more...

#### BrowserSession → Watchdogs Events
- `BrowserConnectedEvent`: Browser connected
- `NavigationCompleteEvent`: Navigation completed
- `BrowserStateRequestEvent`: Request browser state
- `BrowserErrorEvent`: Browser error occurred
- And more...

### Watchdog Pattern

All watchdogs inherit from `BaseWatchdog` and:
- Automatically register event handlers via method naming (`on_EventName`)
- Listen to specific events via `LISTENS_TO` class variable
- Emit events via `EMITS` class variable
- Access browser session and event bus

### Event Flow

**Action Execution Flow**:
1. Agent/Tool dispatches action event (e.g., `ClickElementEvent`)
2. Event bus routes event to appropriate watchdog
3. Watchdog handles event and executes CDP command
4. Browser state changes
5. Watchdog emits state change events
6. Event broadcaster publishes events to Redis Pub/Sub
7. External services receive events

---

## Data Schemas

### MCP Tool Request Schema

**Endpoint**: `POST /mcp/tools/call`

**Request Body Schema**:
```json
{
  "type": "object",
  "properties": {
    "tool": {
      "type": "string",
      "enum": ["start_browser_session", "execute_action", "get_screen_content", "close_browser_session", "pause_browser_session", "resume_browser_session", "get_browser_context", "recover_browser_session"]
    },
    "arguments": {
      "type": "object",
      "description": "Tool-specific arguments"
    }
  },
  "required": ["tool", "arguments"]
}
```

### start_browser_session Tool

**Input Schema**:
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
    "participant_identity": {
      "type": "string",
      "description": "Participant identity for token generation (default: 'browser-automation')"
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

**Output Schema (Success)**:
```json
{
  "status": "started",
  "room_name": "demo-room-123"
}
```

**Output Schema (Error)**:
```json
{
  "success": false,
  "error": "LiveKit credentials not configured",
  "status": null
}
```

### execute_action Tool

**Input Schema**:
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

**Action Parameter Schemas**:

**navigate**:
```json
{
  "url": "string (required)",
  "new_tab": "boolean (optional, default: false)"
}
```

**click**:
```json
{
  "index": "integer (optional)",
  "coordinate_x": "integer (optional)",
  "coordinate_y": "integer (optional)"
}
```

**type**:
```json
{
  "text": "string (required)",
  "index": "integer (optional)"
}
```

**scroll**:
```json
{
  "direction": "string (enum: up, down, left, right)",
  "amount": "integer (optional, default: 500)"
}
```

**Output Schema (Success)**:
```json
{
  "success": true,
  "error": null,
  "data": {}
}
```

**Output Schema (Error)**:
```json
{
  "success": false,
  "error": "string",
  "data": null
}
```

### get_screen_content Tool

**Input Schema**:
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

**Output Schema (Success)**:
```json
{
  "success": true,
  "error": null,
  "data": {
    "url": "string",
    "title": "string",
    "dom_summary": "string",
    "visible_elements_count": "integer",
    "scroll_x": "integer",
    "scroll_y": "integer",
    "viewport_width": "integer",
    "viewport_height": "integer",
    "cursor_x": "integer",
    "cursor_y": "integer"
  }
}
```

**Output Schema (Error)**:
```json
{
  "success": false,
  "error": "Browser session not found",
  "data": null
}
```

### close_browser_session Tool

**Input Schema**:
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

**Output Schema (Success)**:
```json
{
  "status": "closed",
  "room_name": "demo-room-123"
}
```

**Output Schema (Error)**:
```json
{
  "success": false,
  "error": "Browser session not found",
  "status": null
}
```

### Knowledge Retrieval Job Schema

**Start Job Request**:
```json
{
  "start_url": "string (required)",
  "max_pages": "integer (optional)",
  "max_depth": "integer (optional, default: 3)",
  "strategy": "string (enum: BFS, DFS, default: BFS)",
  "job_id": "string (optional, auto-generated if not provided)",
  "include_paths": "array of strings (optional)",
  "exclude_paths": "array of strings (optional)",
  "authentication": {
    "username": "string (required)",
    "password": "string (required)"
  }
}
```

**Job Status Response**:
```json
{
  "job_id": "string",
  "status": "string (enum: queued, running, paused, completed, failed, cancelled)",
  "start_url": "string",
  "created_at": "timestamp",
  "updated_at": "timestamp",
  "pages_completed": "integer",
  "pages_total": "integer (optional)",
  "error": "string (optional)"
}
```

---

## Integration Points

### CDP Integration
- **Library**: `cdp-use`
- **Usage**: Typed CDP commands and events
- **Location**: `browser_use/browser/session.py`

### LLM Providers
- **Supported**: OpenAI, Anthropic, Google, Browser Use, Groq, Mistral, Azure, OCI, Ollama, Vercel
- **Location**: `browser_use/llm/`
- **Interface**: `BaseChatModel` protocol

### Event Bus
- **Library**: `bubus`
- **Usage**: Event-driven coordination between components

### MCP Protocol
- **Library**: `mcp` (Model Context Protocol)
- **Location**: `navigator/server/mcp.py`
- **Usage**: Integration with external services

### LiveKit
- **Library**: `livekit` Python SDK
- **Location**: `navigator/streaming/livekit.py`
- **Usage**: Real-time video streaming
- **Participant Identity**: Default `"browser-automation"` (configurable)

### Redis
- **Library**: `redis` (async)
- **Usage**: 
  - Redis Pub/Sub for high-frequency events
  - RQ backend for job queue
  - Progress observer channels

### RQ (Redis Queue)
- **Library**: `rq`
- **Usage**: Durable job queue for commands and knowledge retrieval jobs
- **Configuration**: `decode_responses=False` required for Redis client

### MongoDB
- **Library**: `motor` (async MongoDB driver)
- **Location**: `navigator/storage/mongodb.py` (utilities)
- **Usage**: Primary persistence layer for all stateful data
- **Collections**: All prefixed with `brwsr_auto_svc_`
- **Configuration**: Via `MONGODB_URL` and `MONGODB_DATABASE` environment variables

---

## Scalability & Performance

### Room-Based Isolation

**Multi-Tenancy**:
- Each LiveKit room has isolated browser session
- Sessions are independent and don't interfere
- Scalable to thousands of concurrent sessions

### Worker Management

**Auto-Scaling RQ Workers**:
- Workers spawn automatically when server starts
- Dynamic scaling based on queue length
- Configurable min/max workers per job type
- Health monitoring and automatic restart
- Graceful shutdown with timeout

### Event Broadcasting

**Multi-Channel Broadcasting**:
- **Primary**: Redis Pub/Sub (high-frequency, real-time events)
- **Fallback**: WebSocket (for clients without Redis access)
- **Storage**: MongoDB (persistent event storage)

### Resource Management

**Browser Session Management**:
- Per-room browser instance
- Automatic cleanup on session close
- Timeout-based cleanup (6 hours for presentation sessions)
- Memory-efficient browser profile configuration

### Performance Optimizations

**Video Streaming**:
- Configurable FPS (default: 10 FPS)
- Efficient frame capture and encoding
- Optimized video track publishing

**Knowledge Retrieval**:
- Batch processing of pages
- Parallel link discovery
- Efficient graph storage in MongoDB
- In-memory fallback for development

---

## File Organization

### Directory Structure

```
browser_use/              # Embedded Browser-Use library source (v0.11.2)
├── agent/                # Agent orchestration
├── browser/              # Browser session management
├── tools/                # Action registry
├── dom/                  # DOM processing
├── llm/                  # LLM integration
└── ...

navigator/                # Our extensions (imports browser_use as library)
├── action/               # Action system
│   ├── command.py       # ActionCommand primitives
│   └── dispatcher.py    # Action execution engine
├── knowledge/           # Knowledge Retrieval & Storage Flow
│   ├── exploration_engine.py  # Website exploration (BFS/DFS)
│   ├── semantic_analyzer.py   # Semantic content analysis
│   ├── flow_mapper.py         # Navigation flow tracking
│   ├── storage.py             # Knowledge storage (MongoDB/in-memory)
│   ├── vector_store.py         # Vector embeddings storage
│   ├── pipeline.py             # Knowledge pipeline orchestration
│   ├── sitemap_generator.py   # Site map generation
│   ├── auth_service.py         # Authentication service
│   ├── api.py                 # Knowledge API endpoints
│   ├── progress_observer.py   # Progress observer system
│   ├── job_queue.py           # RQ job queue
│   ├── worker_manager.py      # Auto-scaling RQ worker manager
│   └── rest_api.py            # REST API endpoints
├── presentation/        # Presentation flow management
│   ├── flow_manager.py  # Session lifecycle management
│   ├── action_registry.py  # Presentation actions
│   └── action_queue.py     # Action queue
├── server/              # Server components
│   ├── mcp.py          # MCP server
│   └── websocket.py    # WebSocket/HTTP server
├── session/             # Session management
│   └── manager.py      # Browser session manager
└── streaming/           # Streaming components
    ├── broadcaster.py  # Event broadcasting
    └── livekit.py      # LiveKit streaming
```

### Import Relationship

**Key Principle**: `navigator/` code treats `browser_use/` as an imported library, even though it's embedded source.

**Example Import Pattern**:
```
from browser_use import BrowserSession
from browser_use.browser.profile import BrowserProfile
```

**Why This Works**:
- Python's import system treats `browser_use/` as a package in the same repository
- No special configuration needed - standard Python imports
- `navigator/` code doesn't need to know `browser_use/` is embedded vs external
- Easy to switch to external library later if needed (just change imports)

---

## Key Architectural Patterns

### 1. Event-Driven Architecture
All browser operations go through events for decoupling and extensibility.

### 2. Watchdog Pattern
Specialized services monitor browser state and react to events.

### 3. ActionCommand Pattern
High-level action primitives abstract away event system complexity.

### 4. Room-Based Sessions
Multi-tenant support with per-room session isolation.

### 5. MCP Protocol
Standardized interface for external service integration.

### 6. Progress Observer Pattern
Flexible, multi-channel progress reporting for real-time observability.

### 7. Job Queue Pattern
Durable, scalable job processing for long-running tasks.

### 8. Storage Abstraction Pattern
MongoDB primary with in-memory fallback for development flexibility.

---

## Presentation Flow Architecture

### Agent-Server Communication

**Communication Channels**:
1. **MCP HTTP**: Agent → Server (action commands)
2. **LiveKit RTC**: Server → Agent (video frames)
3. **Redis Pub/Sub**: Server → Agent (event notifications)
4. **WebSocket**: Server → Agent (fallback event streaming)

### Video Frame Flow

**Frame Capture & Streaming**:
1. Browser automation service captures browser viewport (screenshot)
2. Screenshot converted to video frame (PNG → RGBA → LiveKit VideoFrame)
3. Video frame published to LiveKit room as video track
4. Agent subscribes to video track via LiveKit RTC
5. Agent receives frames via `VideoStream` async iterator
6. Latest frame stored in agent's `_latest_browser_frame`
7. Frame injected into LLM context on user turns

**Frame Rate**: 10 FPS (configurable via `fps` parameter)

**Frame Format**: LiveKit `rtc.VideoFrame` object with ARGB pixel data, compatible with GPT-4o vision API

### Action Execution Flow

**Temporal Alignment**:
1. Agent calls browser action (e.g., `click_element()`)
2. Action sent via MCP HTTP to browser automation service
3. Browser automation service executes action via ActionDispatcher
4. ActionDispatcher converts ActionCommand to browser event
5. Watchdog handles event and executes CDP command
6. Browser state changes (page navigates, element appears, etc.)
7. New video frame captured showing updated state
8. Frame flows through LiveKit to agent
9. Agent receives frame in background task
10. Frame stored in `_latest_browser_frame`
11. On next user turn, frame injected into LLM context

**Action Success/Failure**:
- Success: MCP tool response contains `"success": true`
- Failure: MCP tool response contains `"success": false` and `"error"` field
- Agent checks `success` field before proceeding

### State Synchronization

**How Agent Receives Updates**:

1. **Video Frame Updates (Push)**:
   - Source: Browser automation service publishes video track to LiveKit room
   - Protocol: LiveKit RTC video stream
   - Mechanism: `rtc.VideoStream` async iterator
   - Frequency: 10 FPS (configurable)
   - Agent Consumption: Background task continuously reads frames, stores latest frame

2. **Action Completion (Pull)**:
   - Source: MCP tool response
   - Protocol: HTTP response from `/mcp/tools/call`
   - Mechanism: Synchronous HTTP response
   - Agent Consumption: `BrowserController.call_tool()` returns response immediately

3. **Screen Content (Pull)**:
   - Source: `get_screen_content` MCP tool
   - Protocol: HTTP response
   - Mechanism: Explicit call when needed
   - Agent Consumption: Returns structured data (URL, title, DOM summary, element count)

**Navigation Completion Detection**:
- Implicit via video frames: Agent waits for video frames, analyzes frames to detect page change
- Explicit via screen content: Agent calls `get_screen_content()` after navigation, checks URL field
- Timing: Agent waits 2-3 seconds after navigation actions, relies on video frame updates

---

## Knowledge Retrieval Architecture

### Exploration Strategy

**BFS (Breadth-First Search)**:
- Explores all pages at current depth before moving to next depth
- Good for discovering all top-level pages first
- Better for understanding site structure

**DFS (Depth-First Search)**:
- Explores one path completely before backtracking
- Good for following specific flows
- Better for understanding user journeys

### External Link Detection

**Critical Requirement**: External links are **detected but NOT followed**.

**Detection Logic**:
- Compare URL domain against base_url domain
- If domains differ, link is external
- External links are stored in knowledge graph
- External links are NOT added to exploration queue
- Progress observer notified when external links detected

**Why**: Prevents exploration from leaving the target website and ensures focused knowledge extraction.

### Authentication Flow

**Login Detection**:
- URL pattern matching (common login URL patterns)
- DOM analysis (presence of password + username fields)

**Login Execution**:
- Form field identification (username, password, submit button)
- Form filling via ActionDispatcher
- Form submission (button click or Enter key)
- Login validation (URL change + page analysis)

**Session Persistence**:
- Browser session maintains cookies/authentication throughout exploration
- Credentials never logged (only username logged)
- Credentials never persisted

### Progress Observability

**Progress Events**:
- `on_progress()`: Page-by-page progress updates
- `on_page_completed()`: Page processing completion
- `on_external_link_detected()`: External link detection
- `on_error()`: Error notifications

**Progress Channels**:
- Logging observer (console logs)
- Redis Pub/Sub (real-time updates)
- WebSocket (UI updates)
- Composite observer (combines multiple observers)

### Job Management

**Job States**:
- `queued`: Job added to RQ queue, waiting for worker
- `running`: Worker processing job, exploration in progress
- `paused`: Job paused (can be resumed)
- `completed`: Exploration finished successfully
- `failed`: Exploration failed with error
- `cancelled`: Job cancelled by user or timeout

**Job Control**:
- Pause: Pause exploration at current page
- Resume: Resume from pause point
- Cancel: Stop exploration immediately
- Status: Query current job status and progress

**Stuck Job Monitoring**:
- Queued jobs timeout: 2 minutes (if not picked up by worker)
- Running jobs timeout: 30 minutes (if no progress updates)
- Automatic cancellation of stuck jobs

---

## Data Flow Diagrams

### Presentation Flow Data Flow

```
Agent
  ↓ (MCP HTTP)
Browser Automation Service
  ↓ (ActionCommand)
ActionDispatcher
  ↓ (Browser Event)
Event Bus
  ↓ (Event)
Watchdog
  ↓ (CDP Command)
Browser
  ↓ (State Change)
Browser Automation Service
  ↓ (Video Frame)
LiveKit Room
  ↓ (Video Stream)
Agent (receives frame)
  ↓ (Frame Injection)
LLM (GPT-4o Vision)
  ↓ (Analysis)
Agent (responds)
```

### Knowledge Retrieval Data Flow

```
REST API / MCP Tool
  ↓ (Job Request)
RQ Queue
  ↓ (Job Pickup)
RQ Worker
  ↓ (Pipeline Execution)
KnowledgePipeline
  ↓ (Exploration)
ExplorationEngine
  ↓ (Link Discovery)
BrowserSession
  ↓ (Page Content)
SemanticAnalyzer
  ↓ (Content Analysis)
KnowledgeStorage
  ↓ (Storage)
MongoDB (brwsr_auto_svc_pages, brwsr_auto_svc_links)
  ↓ (Progress Update)
ProgressObserver
  ↓ (Event Broadcast)
Redis Pub/Sub / WebSocket
  ↓ (Progress Event)
External Services (UI, Agent, etc.)
```

---

## Environment Configuration

### Required Environment Variables

**Browser Automation Service**:
- `BROWSER_MCP_SERVER_URL`: MCP server base URL (default: `http://localhost:8000`)

**LiveKit**:
- `LIVEKIT_URL`: LiveKit server URL (required)
- `LIVEKIT_API_KEY`: LiveKit API key (required)
- `LIVEKIT_API_SECRET`: LiveKit API secret (required)

**Redis**:
- `REDIS_URL`: Redis connection URL (required for RQ and Pub/Sub)

**MongoDB**:
- `MONGODB_URL`: MongoDB connection URL (default: `mongodb://localhost:27017`)
- `MONGODB_DATABASE`: Database name (default: `browser_automation_service`)

**LLM** (for agent):
- `OPENAI_API_KEY`: OpenAI API key (for GPT-4o vision)
- `DEEPGRAM_API_KEY`: Deepgram API key (for STT)
- `CARTESIA_API_KEY`: Cartesia API key (for TTS)

---

## Security Considerations

### Domain Restrictions

**SecurityWatchdog**:
- Enforces domain allowlist (if configured)
- Enforces domain prohibited list (if configured)
- Blocks navigation to unauthorized domains

**Pattern Formats**:
- `'example.com'` - Matches only `https://example.com/*`
- `'*.example.com'` - Matches `https://example.com/*` and any subdomain
- `'http*://example.com'` - Matches both `http://` and `https://` protocols
- Wildcards in TLD are **not allowed** for security

### Credential Handling

**Authentication Service**:
- Credentials never logged in plaintext (only username logged)
- Credentials never persisted to MongoDB or any storage
- Credentials cleared from memory after job completion
- Secure credential handling via transient `Credentials` dataclass

### Session Isolation

**Room-Based Isolation**:
- Each LiveKit room has isolated browser session
- Sessions cannot access each other's data
- Multi-tenant support with complete isolation

---

## Performance Characteristics

### Browser Session Startup
- **Target**: < 5 seconds
- **Factors**: Browser launch, CDP connection, LiveKit connection

### Action Execution
- **Target**: < 2 seconds per action
- **Factors**: Network latency, CDP command execution, page response

### Video Frame Latency
- **Target**: 100-300ms (network + encoding)
- **Frame Rate**: 10 FPS (configurable)
- **Agent Wait Time**: 2-3 seconds after actions (to account for latency)

### Knowledge Retrieval
- **Page Processing**: Varies by page complexity
- **Batch Processing**: Multiple pages processed in batches
- **Scalability**: Handles large websites (1000+ pages)

---

## Scalability Considerations

### Horizontal Scaling

**Browser Sessions**:
- Each session is independent
- No shared state between sessions
- Can scale to thousands of concurrent sessions

**Knowledge Retrieval Jobs**:
- RQ workers can be scaled horizontally
- Jobs are stateless (can be processed by any worker)
- Auto-scaling worker manager adjusts worker count based on queue length

### Vertical Scaling

**Resource Management**:
- Each browser session consumes memory
- Configurable limits per session
- Automatic cleanup of expired sessions

### Database Scaling

**MongoDB**:
- Collections prefixed for namespace safety
- Can use MongoDB sharding for large datasets
- Indexes on frequently queried fields (URL, job_id, etc.)

---

## Error Handling & Recovery

### Browser Errors

**Error Types**:
- Navigation failures
- Action execution failures
- Browser crashes
- CDP connection failures

**Recovery Mechanisms**:
- Automatic retry for transient errors
- Error events broadcast to external services
- Session recovery via `recover_browser_session` tool
- Graceful degradation (continues without streaming if LiveKit fails)

### Knowledge Retrieval Errors

**Error Types**:
- Page load failures
- Network timeouts
- DOM parsing errors
- Storage failures

**Recovery Mechanisms**:
- Per-page error handling (continues with next page)
- Retry support via RQ (configurable max retries)
- Error logging and progress observer notifications
- Graceful fallback to in-memory storage if MongoDB unavailable

### Job Timeout Handling

**Stuck Job Monitor**:
- Monitors jobs for inactivity
- Queued jobs: 2-minute timeout (if not picked up)
- Running jobs: 30-minute timeout (if no progress)
- Automatic cancellation and status update

---

## Monitoring & Observability

### Event Broadcasting

**Channels**:
- Redis Pub/Sub (primary, high-frequency)
- WebSocket (fallback, per-room)
- MongoDB (persistent storage)

**Event Types**:
- Browser events (navigation, actions, errors)
- Knowledge retrieval progress (page completion, external links, errors)
- Session lifecycle (start, pause, resume, close)

### Logging

**Log Levels**:
- DEBUG: Detailed execution flow
- INFO: Important state changes
- WARNING: Recoverable issues
- ERROR: Failures requiring attention

**Log Sources**:
- Browser automation service
- RQ workers (forwarded to main console)
- Knowledge retrieval pipeline
- MCP server

### Health Checks

**Endpoints**:
- `GET /health`: Service health check
- `GET /rooms/{room_name}/connections`: WebSocket connection count

---

## Conclusion

The Browser Automation Service architecture provides:

- **Production-Ready Infrastructure**: Complete server implementation with all required components
- **Scalable Design**: Room-based isolation, horizontal scaling, auto-scaling workers
- **Flexible Integration**: MCP protocol, REST API, WebSocket, Redis Pub/Sub
- **Robust Persistence**: MongoDB with standardized collection naming
- **Real-Time Communication**: LiveKit video streaming, Redis Pub/Sub events
- **Comprehensive Knowledge Retrieval**: Complete website exploration with semantic understanding
- **Secure Operation**: Domain restrictions, credential handling, session isolation

**The architecture is designed for production deployment with clear separation of concerns, extensible patterns, and comprehensive observability.**

---

**Last Updated**: 2026-01-13  
**Version**: 1.0.0

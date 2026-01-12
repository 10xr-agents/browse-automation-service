# How to Start the Browser Automation Service Server

## Quick Start

```bash
# 1. Install dependencies
uv sync

# 2. Start Redis (if using BullMQ/Redis Pub/Sub)
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

---

## Prerequisites

### 1. Python Environment

**Required**: Python >= 3.11

**Setup**:
```bash
# Create virtual environment with uv
uv venv --python 3.11
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv sync
```

### 2. Redis (Optional but Recommended)

Redis is used for:
- **BullMQ**: Reliable job queue for commands and knowledge retrieval
- **Redis Pub/Sub**: High-frequency event streaming

**Installation**:

**macOS**:
```bash
brew install redis
brew services start redis
```

**Linux**:
```bash
sudo apt-get install redis-server  # Debian/Ubuntu
sudo systemctl start redis
```

**Windows**:
- Download from: https://redis.io/download
- Or use WSL2 with Linux instructions

**Verify Redis is running**:
```bash
redis-cli ping
# Should return: PONG
```

**Default Configuration**:
- Host: `localhost`
- Port: `6379`
- No password required (default)

**Custom Redis URL**:
Set environment variable:
```bash
export REDIS_URL=redis://localhost:6379
```

### 3. Chromium Browser

The server uses Chromium for browser automation. Install it:

```bash
uvx browser-use install
```

This installs Chromium in the default location for your platform.

---

## Environment Variables

Create a `.env` file in the project root:

```bash
# .env file

# Optional: LLM API Keys (for knowledge retrieval semantic analysis)
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
GOOGLE_API_KEY=your_google_key

# Optional: Browser Use Cloud (for cloud browser automation)
BROWSER_USE_API_KEY=your_browser_use_key

# Optional: LiveKit (for video streaming)
LIVEKIT_URL=wss://livekit.example.com
LIVEKIT_API_KEY=your_livekit_key
LIVEKIT_API_SECRET=your_livekit_secret

# Optional: Redis (if not using default localhost:6379)
REDIS_URL=redis://localhost:6379

# Optional: Logging
BROWSER_USE_LOGGING_LEVEL=debug  # debug, info, warning, error
```

**Note**: Most environment variables are optional. The server will work with minimal configuration, but some features require specific keys:
- **LiveKit**: Required for video streaming
- **LLM API Keys**: Required for semantic analysis in knowledge retrieval
- **Redis**: Required for BullMQ and Redis Pub/Sub (falls back to in-memory if unavailable)

---

## Starting the Server

### Method 1: Direct Python Execution (Recommended)

```bash
# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Start server
uv run python navigator/start_server.py
```

**Output**:
```
======================================================================
Starting Browser Automation Service WebSocket Server
======================================================================
WebSocket endpoint: ws://localhost:8000/mcp/events/{room_name}
Health check: http://localhost:8000/health
Knowledge API: http://localhost:8000/api/knowledge/explore/start
======================================================================
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
✅ BullMQ knowledge retrieval worker started
```

### Method 2: Using uvicorn Directly

```bash
# Activate virtual environment
source .venv/bin/activate

# Start with uvicorn
uvicorn navigator.server.websocket:get_app --factory --host 0.0.0.0 --port 8000
```

### Method 3: Using Python Module

```bash
# Activate virtual environment
source .venv/bin/activate

# Run as module
python -m navigator.start_server
```

---

## Server Features

When the server starts, it automatically:

1. **Loads Environment Variables**: From `.env` file
2. **Starts FastAPI Application**: WebSocket and HTTP endpoints
3. **Starts BullMQ Worker**: For knowledge retrieval jobs (if Redis available)
4. **Registers Routes**:
   - Browser automation endpoints (`/mcp/tools/*`)
   - Knowledge retrieval endpoints (`/api/knowledge/*`)
   - Health check (`/health`)
   - WebSocket events (`/mcp/events/{room_name}`)

---

## Verifying the Server is Running

### 1. Health Check

```bash
curl http://localhost:8000/health
```

**Expected Response**:
```json
{
  "status": "ok",
  "service": "browser-automation-websocket"
}
```

### 2. List MCP Tools

```bash
curl http://localhost:8000/mcp/tools
```

**Expected Response**:
```json
{
  "tools": [
    {
      "name": "start_browser_session",
      "description": "Start a browser session for a LiveKit room with video streaming"
    },
    ...
  ]
}
```

### 3. View API Documentation

Open in browser:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 4. Check Knowledge API

```bash
curl http://localhost:8000/api/knowledge/explore/jobs
```

**Expected Response**:
```json
{
  "jobs": []
}
```

---

## Configuration Options

### Port Configuration

**Default**: Port `8000`

**Change Port**:
```bash
# Method 1: Environment variable
export PORT=8080
uv run python navigator/start_server.py

# Method 2: Modify start_server.py
# Change: uvicorn.run(app, host='0.0.0.0', port=8000, ...)
# To: uvicorn.run(app, host='0.0.0.0', port=8080, ...)
```

### Host Configuration

**Default**: `0.0.0.0` (all interfaces)

**Change Host**:
```bash
# Method 1: Environment variable
export HOST=127.0.0.1
uv run python navigator/start_server.py

# Method 2: Modify start_server.py
# Change: uvicorn.run(app, host='0.0.0.0', ...)
# To: uvicorn.run(app, host='127.0.0.1', ...)
```

### Logging Level

**Default**: `DEBUG` (comprehensive logging)

**Change Logging Level**:
```bash
# Set in .env file
BROWSER_USE_LOGGING_LEVEL=info  # or warning, error

# Or modify start_server.py
logging.basicConfig(level=logging.INFO)  # Instead of DEBUG
```

---

## Troubleshooting

### Issue: "uvicorn not installed"

**Error**:
```
Error: uvicorn not installed. Install with: uv pip install uvicorn
```

**Solution**:
```bash
uv sync
# Or
uv pip install uvicorn
```

---

### Issue: "Redis not available"

**Warning**:
```
Redis not available, BullMQ worker not started
```

**Solution**:
1. **Install Redis** (see Prerequisites section)
2. **Start Redis**:
   ```bash
   redis-server
   ```
3. **Verify Redis is running**:
   ```bash
   redis-cli ping
   ```

**Note**: Server will still work without Redis, but:
- BullMQ job queue won't be available (falls back to in-memory)
- Redis Pub/Sub events won't be available (falls back to WebSocket)

---

### Issue: "FastAPI not installed"

**Error**:
```
FastAPI not installed. Install with: pip install fastapi
```

**Solution**:
```bash
uv sync
# Or
uv pip install fastapi websockets
```

---

### Issue: "BullMQ not available"

**Warning**:
```
BullMQ not available, worker not started
```

**Solution**:
```bash
uv pip install bullmq redis
```

**Note**: Server will still work without BullMQ, but knowledge retrieval jobs will run in-memory (not persistent).

---

### Issue: Port Already in Use

**Error**:
```
ERROR: [Errno 48] Address already in use
```

**Solution**:
1. **Find process using port 8000**:
   ```bash
   lsof -i :8000  # macOS/Linux
   netstat -ano | findstr :8000  # Windows
   ```

2. **Kill the process** or **use a different port**:
   ```bash
   # Change port in start_server.py or use environment variable
   export PORT=8080
   ```

---

### Issue: Chromium Not Found

**Error**:
```
Browser executable not found
```

**Solution**:
```bash
# Install Chromium
uvx browser-use install

# Or specify custom path in BrowserProfile
```

---

## Running in Production

### Using Gunicorn (Recommended for Production)

```bash
# Install gunicorn
uv pip install gunicorn

# Run with gunicorn
gunicorn navigator.server.websocket:get_app \
  --factory \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120
```

### Using Docker

```bash
# Build image
docker build -t browser-automation-service .

# Run container
docker run -p 8000:8000 \
  -e REDIS_URL=redis://host.docker.internal:6379 \
  browser-automation-service
```

### Using Systemd (Linux)

Create `/etc/systemd/system/browser-automation.service`:

```ini
[Unit]
Description=Browser Automation Service
After=network.target redis.service

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/browse-automation-service
Environment="PATH=/path/to/.venv/bin"
ExecStart=/path/to/.venv/bin/python navigator/start_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Start service**:
```bash
sudo systemctl enable browser-automation
sudo systemctl start browser-automation
sudo systemctl status browser-automation
```

---

## Development Mode

For development with auto-reload:

```bash
# Install watchfiles
uv pip install watchfiles

# Run with reload
uvicorn navigator.server.websocket:get_app \
  --factory \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
```

---

## Testing the Server

### Test Browser Automation

```bash
# Start browser session
curl -X POST http://localhost:8000/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "start_browser_session",
    "arguments": {
      "room_name": "test-room",
      "initial_url": "https://www.google.com"
    }
  }'

# Execute action
curl -X POST http://localhost:8000/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "execute_action",
    "arguments": {
      "room_name": "test-room",
      "action_type": "navigate",
      "params": {"url": "https://example.com"}
    }
  }'
```

### Test Knowledge Retrieval

```bash
# Start exploration
curl -X POST http://localhost:8000/api/knowledge/explore/start \
  -H "Content-Type: application/json" \
  -d '{
    "start_url": "https://quotes.toscrape.com",
    "max_pages": 5,
    "max_depth": 2,
    "strategy": "BFS"
  }'

# Get job status (use job_id from previous response)
curl http://localhost:8000/api/knowledge/explore/status/{job_id}
```

---

## Next Steps

After starting the server:

1. **View API Documentation**: http://localhost:8000/docs
2. **Read Protocol Documentation**: `dev-docs/PROTOCOL_AND_INTERFACE.md`
3. **Read Architecture Documentation**: `dev-docs/COMPLETE_ARCHITECTURE.md`
4. **Test with MCP Client**: Connect via MCP protocol
5. **Test with REST API**: Use curl or Postman
6. **Test with WebSocket**: Connect to `ws://localhost:8000/mcp/events/{room_name}`

---

## Common Commands Reference

```bash
# Start server
uv run python navigator/start_server.py

# Start with custom port
PORT=8080 uv run python navigator/start_server.py

# Start with debug logging
BROWSER_USE_LOGGING_LEVEL=debug uv run python navigator/start_server.py

# Check health
curl http://localhost:8000/health

# List tools
curl http://localhost:8000/mcp/tools

# View Swagger UI
open http://localhost:8000/docs  # macOS
xdg-open http://localhost:8000/docs  # Linux
start http://localhost:8000/docs  # Windows
```

---

*Last Updated: 2025-01-12*
*Version: 1.0.0*

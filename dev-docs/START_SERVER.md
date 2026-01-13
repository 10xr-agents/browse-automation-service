# How to Start the Browser Automation Service Server

## Quick Start

### Development / Local

```bash
# 1. Install dependencies
uv sync

# 2. Start Redis via Docker (for RQ job queue and Pub/Sub)
docker run -d --name redis -p 6379:6379 redis:latest

# 3. Start MongoDB via Docker (for persistent data storage - optional)
docker run -d --name mongodb -p 27017:27017 mongo:latest

# 4. Start the API server
uv run python navigator/start_server.py

# Note: RQ workers are automatically managed by the JobManager!
# No need to start workers manually - they are spawned and scaled automatically.
# The server will start with 1 worker (minimum) and scale up to 5 workers (maximum)
# based on queue length.
```

The server will start on `http://localhost:8000` with:
- **REST API**: `http://localhost:8000`
- **WebSocket**: `ws://localhost:8000/mcp/events/{room_name}`
- **Health Check**: `http://localhost:8000/health`
- **API Documentation**: `http://localhost:8000/docs`

### Production

```bash
# Build and run with Docker Compose (recommended)
docker-compose up -d

# Or build and run individually
docker build -t browser-automation-service .
docker run -p 8000:8000 \
  --network host \
  -e REDIS_URL=redis://redis:6379 \
  browser-automation-service
```

---

## Prerequisites

### 1. Python Environment

**Required**: Python >= 3.11

```bash
# Create virtual environment
uv venv --python 3.11
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv sync
```

### 2. Redis (via Docker)

Redis is required for:
- **RQ (Redis Queue)**: Reliable job queue for knowledge retrieval
- **Redis Pub/Sub**: High-frequency event streaming

**Start Redis**:
```bash
docker run -d --name redis -p 6379:6379 redis:latest
```

**Verify Redis is running**:
```bash
docker ps | grep redis
# Or test connection
docker exec redis redis-cli ping
# Should return: PONG
```

**Default Configuration**:
- Host: `localhost` (from host) or `redis` (from Docker network)
- Port: `6379`
- No password required

**Custom Redis URL**:
Set environment variable in `.env`:
```bash
REDIS_URL=redis://localhost:6379
```

### 3. Chromium Browser

```bash
uvx browser-use install
```

---

## Environment Variables

Create a `.env` file in the project root:

```bash
# Optional: LLM API Keys (for knowledge retrieval semantic analysis)
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
GOOGLE_API_KEY=your_google_key

# Optional: Browser Use Cloud
BROWSER_USE_API_KEY=your_browser_use_key

# Optional: LiveKit (for video streaming)
LIVEKIT_URL=wss://livekit.example.com
LIVEKIT_API_KEY=your_livekit_key
LIVEKIT_API_SECRET=your_livekit_secret

# Optional: Redis (defaults to redis://localhost:6379)
REDIS_URL=redis://localhost:6379

# Optional: MongoDB (defaults to mongodb://localhost:27017)
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=browser_automation_service

# Optional: MongoDB Debug Logging (defaults to false - only errors shown)
MONGODB_DEBUG_LOGS=false  # Set to 'true' to enable MongoDB debug logs

# Optional: Logging
BROWSER_USE_LOGGING_LEVEL=info  # debug, info, warning, error
```

---

## Starting the Server

### Development / Local

**Single Command**:
```bash
uv run python navigator/start_server.py
```

**Expected Output**:
```
======================================================================
Starting Browser Automation Service WebSocket Server
======================================================================
WebSocket endpoint: ws://localhost:8000/mcp/events/{room_name}
Health check: http://localhost:8000/health
Knowledge API: http://localhost:8000/api/knowledge/explore/start
======================================================================
✅ Required environment variables found
======================================================================
Starting uvicorn server...
   RQ workers are automatically managed by JobManager
   Workers will be spawned and scaled automatically
======================================================================
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
======================================================================
🔧 [Startup] FastAPI startup event triggered
🔧 [Startup] RQ job queue setup
======================================================================
✅ [Startup] RQ queue available
   Queue name: knowledge-retrieval
   Workers run as separate processes
======================================================================
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Important**: RQ workers are automatically managed by the JobManager! No manual startup required.

Workers are spawned automatically when the server starts and scale based on queue length:
- Starts with 1 worker (minimum)
- Scales up to 5 workers (maximum) when queue length > 5 jobs
- Scales down when queue is empty
- Automatically restarts failed workers

Check worker status: `curl http://localhost:8000/api/knowledge/worker/status`

If jobs aren't being processed, check:
1. Redis is running and accessible
2. `REDIS_URL` is set correctly in `.env.local`
3. Check the error messages in the logs
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)

# In a separate terminal, start the RQ worker:
rq worker knowledge-retrieval
# Worker will process jobs from the queue
```

### Production

**Using Docker**:
```bash
# Build image
docker build -t browser-automation-service .

# Run container (with Redis on same network)
docker run -d \
  --name browser-automation \
  --network host \
  -e REDIS_URL=redis://localhost:6379 \
  -p 8000:8000 \
  browser-automation-service
```

**Using Docker Compose** (recommended):
```yaml
# docker-compose.yml
version: '3.8'
services:
  redis:
    image: redis:latest
    ports:
      - "6379:6379"
  
  mongodb:
    image: mongo:latest
    ports:
      - "27017:27017"
  
  server:
    build: .
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379
      - MONGODB_URL=mongodb://mongodb:27017
      - MONGODB_DATABASE=browser_automation_service
    depends_on:
      - redis
      - mongodb
```

```bash
docker-compose up -d
```

---

## Verifying the Server

### Health Check

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

### API Documentation

Open in browser:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### List Available Tools

```bash
curl http://localhost:8000/mcp/tools
```

---

## Auto-Scaling RQ Workers (JobManager)

RQ workers are **automatically managed** by the JobManager subsystem. Workers are spawned, scaled, and managed automatically - **no manual startup required**.

### Automatic Management

The JobManager automatically:
- **Spawns initial workers** when the server starts (1 worker minimum by default)
- **Scales workers up** when queue length increases (up to 5 workers maximum by default)
- **Scales workers down** when queues drain (back to minimum workers)
- **Monitors worker health** and restarts failed workers
- **Gracefully shuts down** all workers when the server stops

### Configuration

Default configuration (knowledge-retrieval queue):
- **Minimum workers**: 1
- **Maximum workers**: 5
- **Scale-up threshold**: 5 jobs in queue
- **Scale-down threshold**: 0 jobs in queue
- **Scale cooldown**: 30 seconds

### Monitoring

Check worker status via the health endpoint:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/knowledge/worker/status
```

The response includes:
- Job manager status (enabled/running)
- Worker counts per queue (total/active)
- Queue lengths
- Worker process details (PID, status, health)

### Manual Worker Management (Advanced)

**Note**: Manual worker startup is no longer required. The JobManager handles everything automatically.

For advanced use cases, you can still start workers manually if needed:
```bash
rq worker knowledge-retrieval
rq worker knowledge-retrieval
```

**Using Docker Compose** (recommended for production):
```yaml
# docker-compose.yml
services:
  # ... existing services ...
  
  worker:
    build: .
    command: rq worker knowledge-retrieval
    environment:
      - REDIS_URL=redis://redis:6379
      - MONGODB_URL=mongodb://mongodb:27017
    depends_on:
      - redis
      - mongodb
```

**Scaling workers**:
```bash
docker-compose up --scale worker=5  # Start 5 workers
```

### Worker Status

Check if workers are running:
```bash
# List active workers
rq info

# Check queue status
rq info --url redis://localhost:6379
```

### Why Separate Processes?

RQ workers must run in separate processes because:
1. **Process isolation**: Jobs can take hours - worker process can be managed independently
2. **Crash resilience**: Worker crash doesn't bring down the API server
3. **Resource limits**: Workers can run with different resource constraints
4. **Horizontal scaling**: Easy to add/remove workers based on load

---

## Troubleshooting

### Redis Connection Issues

**Error**: `Redis not available, RQ queue not available`

**Solution**:
1. Ensure Redis is running: `docker ps | grep redis`
2. If not running, start it: `docker run -d --name redis -p 6379:6379 redis:latest`
3. Verify connection: `docker exec redis redis-cli ping`

**Note**: Server will still work without Redis, but:
- RQ job queue won't be available (falls back to in-memory)
- Redis Pub/Sub events won't be available (falls back to WebSocket)

### Port Already in Use

**Error**: `ERROR: [Errno 48] Address already in use`

**Solution**:
```bash
# Find process using port 8000
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# Kill the process or use a different port
PORT=8080 uv run python navigator/start_server.py
```

### Chromium Not Found

**Error**: `Browser executable not found`

**Solution**:
```bash
uvx browser-use install
```

---

## Development Mode

For development with auto-reload:

```bash
uv run uvicorn navigator.server.websocket:get_app \
  --factory \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
```

---

## Next Steps

1. **View API Documentation**: http://localhost:8000/docs
2. **Read Protocol Documentation**: `dev-docs/PROTOCOL_AND_INTERFACE.md`
3. **Read Architecture Documentation**: `dev-docs/COMPLETE_ARCHITECTURE.md`

---

*Last Updated: 2025-01-13*
*Version: 2.0.0*

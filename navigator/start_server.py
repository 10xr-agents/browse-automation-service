"""
Startup script for Browser Automation Service

Starts:
1. WebSocket server for event broadcasting
2. Temporal worker for knowledge extraction workflows

The MCP server runs separately via stdio when connected to MCP clients.
"""

import asyncio
import logging
import os
import signal
import sys

# macOS fork safety: Disable Objective-C runtime fork safety check
# This prevents crashes when spawning subprocesses on macOS
if sys.platform == 'darwin':
	os.environ.setdefault('OBJC_DISABLE_INITIALIZE_FORK_SAFETY', 'YES')

from dotenv import load_dotenv

try:
	import uvicorn
except ImportError:
	print('Error: uvicorn not installed. Install with: uv pip install uvicorn')
	sys.exit(1)

# Load environment variables from .env.local first, then .env
# .env.local takes precedence (for local development overrides)
load_dotenv(dotenv_path='.env.local', override=False)  # Load .env.local first
load_dotenv(override=True)  # Then load .env (or system env) with override

from navigator.server.websocket import get_app

# Note: Temporal worker runs as separate async task within the same process
# This allows better resource management and graceful shutdown

# Configure logging with DEBUG level for comprehensive debugging
logging.basicConfig(
	level=logging.DEBUG,
	format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
	force=True,  # Override any existing configuration
)
logger = logging.getLogger(__name__)

# Set specific loggers to appropriate levels
logging.getLogger('uvicorn').setLevel(logging.INFO)
logging.getLogger('uvicorn.access').setLevel(logging.INFO)
logging.getLogger('fastapi').setLevel(logging.INFO)

# Ensure knowledge extraction loggers are at INFO level
logging.getLogger('navigator.knowledge').setLevel(logging.INFO)
logging.getLogger('navigator.knowledge.pipeline').setLevel(logging.INFO)
logging.getLogger('navigator.knowledge.rest_api').setLevel(logging.INFO)
logging.getLogger('navigator.knowledge.exploration_engine').setLevel(logging.INFO)

# Configure MongoDB loggers - only show errors by default
# Set MONGODB_DEBUG_LOGS=true to enable debug logging for MongoDB
mongodb_debug = os.getenv('MONGODB_DEBUG_LOGS', 'false').lower() == 'true'
mongodb_log_level = logging.DEBUG if mongodb_debug else logging.ERROR

# Motor and pymongo loggers
logging.getLogger('motor').setLevel(mongodb_log_level)
logging.getLogger('motor.motor_asyncio').setLevel(mongodb_log_level)
logging.getLogger('pymongo').setLevel(mongodb_log_level)
logging.getLogger('pymongo.serverSelection').setLevel(mongodb_log_level)
logging.getLogger('pymongo.connection').setLevel(mongodb_log_level)
logging.getLogger('pymongo.network').setLevel(mongodb_log_level)
logging.getLogger('pymongo.topology').setLevel(mongodb_log_level)
logging.getLogger('pymongo.pool').setLevel(mongodb_log_level)

# Our MongoDB utility logger - keep at INFO for connection status
logging.getLogger('navigator.storage.mongodb').setLevel(logging.INFO)

# Global worker service reference
_worker_service = None


async def start_temporal_worker():
	"""Start the Temporal worker service."""
	global _worker_service
	
	try:
		from navigator.temporal.worker import start_worker
		from navigator.temporal.config import TemporalConfig
		
		config = TemporalConfig.from_env()
		logger.info('=' * 70)
		logger.info('🚀 Starting Temporal Worker')
		logger.info(f'   Temporal URL: {config.url}')
		logger.info(f'   Namespace: {config.namespace}')
		logger.info(f'   Task Queue: {config.knowledge_task_queue}')
		logger.info('=' * 70)
		
		_worker_service = await start_worker(config=config)
		
		logger.info('✅ Temporal worker started successfully')
		logger.info('=' * 70)
	except Exception as e:
		logger.error(f'❌ Failed to start Temporal worker: {e}', exc_info=True)
		logger.warning('   Service will continue without Temporal worker')
		logger.warning('   Knowledge extraction workflows will NOT work')
		logger.info('=' * 70)


async def stop_temporal_worker():
	"""Stop the Temporal worker service."""
	global _worker_service
	
	if _worker_service is not None:
		try:
			from navigator.temporal.worker import stop_worker
			
			logger.info('🛑 Stopping Temporal worker...')
			await stop_worker()
			_worker_service = None
			logger.info('✅ Temporal worker stopped')
		except Exception as e:
			logger.error(f'❌ Error stopping Temporal worker: {e}', exc_info=True)


def handle_shutdown(signum, frame):
	"""Handle shutdown signals."""
	logger.info(f'Received signal {signum}, initiating shutdown...')
	asyncio.create_task(stop_temporal_worker())


if __name__ == '__main__':
	logger.info('=' * 70)
	logger.info('Starting Browser Automation Service')
	logger.info('=' * 70)
	logger.info('WebSocket endpoint: ws://localhost:8000/mcp/events/{room_name}')
	logger.info('Health check: http://localhost:8000/health')
	logger.info('Knowledge API: http://localhost:8000/api/knowledge/explore/start')
	logger.info('=' * 70)
	
	# Verify required environment variables before starting
	required_vars = {
		'REDIS_URL': os.getenv('REDIS_URL'),
		'MONGODB_URI': os.getenv('MONGODB_URI') or os.getenv('MONGODB_URL'),
		'TEMPORAL_URL': os.getenv('TEMPORAL_URL', 'localhost:7233'),
	}
	
	missing_vars = [var for var, value in required_vars.items() if not value]
	if missing_vars:
		logger.error('=' * 70)
		logger.error('❌ Missing required environment variables:')
		for var in missing_vars:
			logger.error(f'   - {var}')
		logger.error('   Please set these in your .env.local file')
		logger.error('=' * 70)
		sys.exit(1)
	
	logger.info('✅ Required environment variables found')
	logger.info('=' * 70)
	
	# Setup signal handlers for graceful shutdown
	signal.signal(signal.SIGINT, handle_shutdown)
	signal.signal(signal.SIGTERM, handle_shutdown)
	
	# Start Temporal worker in background
	async def startup():
		await start_temporal_worker()
	
	async def shutdown():
		await stop_temporal_worker()
	
	app = get_app()
	
	# Register startup and shutdown events
	@app.on_event("startup")
	async def on_startup():
		await startup()
	
	@app.on_event("shutdown")
	async def on_shutdown():
		await shutdown()
	
	logger.info('Starting uvicorn server...')
	logger.info('   Temporal worker will start with FastAPI')
	logger.info('=' * 70)
	
	# Run with uvicorn
	# Note: We configure logging above, so we use log_config=None to avoid uvicorn overriding it
	uvicorn.run(
		app,
		host='0.0.0.0',
		port=8000,
		log_config=None,  # Use our logging configuration instead of uvicorn's default
	)

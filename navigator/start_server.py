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


# Note: Temporal worker runs as separate async task within the same process
# This allows better resource management and graceful shutdown

# Configure logging - use DEBUG level only if explicitly requested via env var
# Set NAVIGATOR_DEBUG=true to enable debug logging
debug_mode = os.getenv('NAVIGATOR_DEBUG', 'false').lower() == 'true'
root_log_level = logging.DEBUG if debug_mode else logging.INFO

logging.basicConfig(
	level=root_log_level,
	format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
	force=True,  # Override any existing configuration
)
logger = logging.getLogger(__name__)

# Set specific loggers to appropriate levels
logging.getLogger('uvicorn').setLevel(logging.INFO)
logging.getLogger('uvicorn.access').setLevel(logging.INFO)
logging.getLogger('fastapi').setLevel(logging.INFO)

# Suppress Temporal SDK warnings (SDK/server version mismatch warnings are harmless)
# The heartbeat warning indicates server doesn't support this feature, which is fine
logging.getLogger('temporalio').setLevel(logging.ERROR)

# Suppress botocore/boto3 verbosity (S3 operations are very verbose at DEBUG)
# These logs show every S3 API call, request signing, etc. - not useful for normal operation
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)  # boto3 uses urllib3

# Suppress HTTP client debug logs (httpcore, httpx, etc.)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('httpcore.connection').setLevel(logging.WARNING)
logging.getLogger('httpcore.http11').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)

# Suppress LiteLLM debug logs
logging.getLogger('LiteLLM').setLevel(logging.WARNING)
logging.getLogger('litellm').setLevel(logging.WARNING)

# Suppress browser_use verbose debug logs (keep INFO for important events)
logging.getLogger('browser_use.utils').setLevel(logging.INFO)
logging.getLogger('browser_use.browser').setLevel(logging.INFO)

# Suppress Temporal config connection debug messages (connection failures are handled gracefully)
logging.getLogger('navigator.temporal.config').setLevel(logging.INFO)

# Suppress navigator streaming debug logs (keep INFO for important events)
logging.getLogger('navigator.streaming.broadcaster').setLevel(logging.INFO)

# Ensure knowledge extraction loggers follow root log level (DEBUG if NAVIGATOR_DEBUG=true, else INFO)
knowledge_log_level = logging.DEBUG if debug_mode else logging.INFO
logging.getLogger('navigator.knowledge').setLevel(knowledge_log_level)
logging.getLogger('navigator.knowledge.pipeline').setLevel(knowledge_log_level)
logging.getLogger('navigator.knowledge.rest_api').setLevel(knowledge_log_level)
logging.getLogger('navigator.knowledge.exploration_engine').setLevel(knowledge_log_level)
logging.getLogger('navigator.temporal.workflows_extraction').setLevel(knowledge_log_level)
logging.getLogger('navigator.temporal.activities_extraction').setLevel(knowledge_log_level)

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
		from navigator.temporal.config import TemporalConfig
		from navigator.temporal.worker import start_worker

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
		# Log at info level since Temporal is optional and server continues without it
		logger.info('ℹ️  Temporal worker not available (optional service)')
		logger.info('   Service will continue without Temporal worker')
		logger.info('   Knowledge extraction workflows will NOT work until Temporal is started')
		logger.info('=' * 70)


async def stop_temporal_worker():
	"""Stop the Temporal worker service."""
	global _worker_service

	if _worker_service is not None:
		try:
			from navigator.temporal.worker import stop_worker

			logger.info('🛑 Stopping Temporal worker...')
			# Add timeout to prevent hanging
			await asyncio.wait_for(stop_worker(), timeout=10.0)
			_worker_service = None
			logger.info('✅ Temporal worker stopped')
		except asyncio.TimeoutError:
			logger.warning('⚠️  Temporal worker shutdown timed out (forced)')
			_worker_service = None
		except Exception as e:
			logger.error(f'❌ Error stopping Temporal worker: {e}', exc_info=True)
			_worker_service = None


if __name__ == '__main__':
	logger.info('=' * 70)
	logger.info('Starting Browser Automation Service')
	logger.info('=' * 70)
	logger.info('WebSocket endpoint: ws://localhost:8000/mcp/events/{room_name}')
	logger.info('Health check: http://localhost:8000/health')
	logger.info('Knowledge API: http://localhost:8000/api/knowledge/explore/start')
	logger.info('=' * 70)

	# Verify required environment variables before starting
	# Note: TEMPORAL_URL is optional (defaults to localhost:7233, but Temporal is not required)
	required_vars = {
		'REDIS_URL': os.getenv('REDIS_URL'),
		'MONGODB_URI': os.getenv('MONGODB_URI') or os.getenv('MONGODB_URL'),
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

	# Create app with lifespan context manager
	from contextlib import asynccontextmanager

	from fastapi import FastAPI

	@asynccontextmanager
	async def lifespan(app: FastAPI):
		"""Lifespan context manager for startup and shutdown."""
		# Startup - start Temporal worker
		await start_temporal_worker()

		yield  # Server is running

		# Shutdown - stop Temporal worker
		await stop_temporal_worker()

	# Get app and inject lifespan
	from navigator.server.websocket import create_app_with_lifespan
	app = create_app_with_lifespan(lifespan)

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

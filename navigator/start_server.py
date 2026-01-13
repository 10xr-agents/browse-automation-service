"""
Startup script for Browser Automation Service

Starts the WebSocket server for event broadcasting.
The MCP server runs separately via stdio when connected to MCP clients.
"""

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

from navigator.server.websocket import get_app

# Note: RQ workers run as separate processes (not inline with the API server)
# Start RQ worker with: rq worker knowledge-retrieval
# See navigator/server/websocket.py for RQ setup information

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
logging.getLogger('navigator.knowledge.job_queue').setLevel(logging.INFO)
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

if __name__ == '__main__':
	logger.info('=' * 70)
	logger.info('Starting Browser Automation Service WebSocket Server')
	logger.info('=' * 70)
	logger.info('WebSocket endpoint: ws://localhost:8000/mcp/events/{room_name}')
	logger.info('Health check: http://localhost:8000/health')
	logger.info('Knowledge API: http://localhost:8000/api/knowledge/explore/start')
	logger.info('=' * 70)
	
	# Verify required environment variables before starting
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
	
	app = get_app()
	
	# RQ workers run as separate processes (not started by FastAPI)
	# Start RQ worker with: rq worker knowledge-retrieval
	# Or use: uv run python navigator/knowledge/worker.py
	
	logger.info('Starting uvicorn server...')
	logger.info('   RQ workers run as separate processes')
	logger.info('   Start RQ worker with: rq worker knowledge-retrieval')
	logger.info('=' * 70)
	
	# Run with uvicorn
	# Note: We configure logging above, so we use log_config=None to avoid uvicorn overriding it
	uvicorn.run(
		app,
		host='0.0.0.0',
		port=8000,
		log_config=None,  # Use our logging configuration instead of uvicorn's default
	)

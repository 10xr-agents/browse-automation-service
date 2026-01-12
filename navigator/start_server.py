"""
Startup script for Browser Automation Service

Starts the WebSocket server for event broadcasting.
The MCP server runs separately via stdio when connected to MCP clients.
"""

import logging
import sys

from dotenv import load_dotenv

try:
	import uvicorn
except ImportError:
	print('Error: uvicorn not installed. Install with: uv pip install uvicorn')
	sys.exit(1)

# Load environment variables
load_dotenv()

from navigator.server.websocket import get_app

# Start BullMQ worker for knowledge retrieval (if available)
async def start_knowledge_worker():
	"""Start BullMQ worker for knowledge retrieval jobs."""
	try:
		from navigator.knowledge.job_queue import start_knowledge_worker, get_redis_client
		from browser_use import BrowserSession
		from browser_use.browser.profile import BrowserProfile
		from navigator.knowledge.pipeline import KnowledgePipeline
		from navigator.knowledge.progress_observer import (
			CompositeProgressObserver,
			LoggingProgressObserver,
		)
		
		# Check Redis availability
		redis_client = await get_redis_client()
		if redis_client is None:
			logger.info("Redis not available, BullMQ worker not started")
			return
		
		# Create pipeline factory
		def create_pipeline_factory():
			observers = [LoggingProgressObserver()]
			
			try:
				import redis.asyncio as redis
				from navigator.knowledge.progress_observer import RedisProgressObserver
				redis_observer = RedisProgressObserver(redis_client=redis_client)
				observers.append(redis_observer)
			except Exception:
				pass
			
			progress_observer = CompositeProgressObserver(observers)
			
			async def create_pipeline():
				profile = BrowserProfile(headless=True, user_data_dir=None, keep_alive=True)
				browser_session = BrowserSession(browser_profile=profile)
				await browser_session.start()
				await browser_session.attach_all_watchdogs()
				
				return KnowledgePipeline(
					browser_session=browser_session,
					progress_observer=progress_observer,
				)
			
			return create_pipeline
		
		# Start worker
		worker = await start_knowledge_worker(create_pipeline_factory())
		if worker:
			logger.info("✅ BullMQ knowledge retrieval worker started")
	except ImportError:
		logger.debug("BullMQ not available, worker not started")
	except Exception as e:
		logger.warning(f"Failed to start BullMQ worker: {e}")

# Configure logging with DEBUG level for comprehensive debugging
logging.basicConfig(
	level=logging.DEBUG,
	format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
)
logger = logging.getLogger(__name__)

# Set specific loggers to appropriate levels
logging.getLogger('uvicorn').setLevel(logging.INFO)
logging.getLogger('uvicorn.access').setLevel(logging.INFO)
logging.getLogger('fastapi').setLevel(logging.INFO)

if __name__ == '__main__':
	logger.info('=' * 70)
	logger.info('Starting Browser Automation Service WebSocket Server')
	logger.info('=' * 70)
	logger.info('WebSocket endpoint: ws://localhost:8000/mcp/events/{room_name}')
	logger.info('Health check: http://localhost:8000/health')
	logger.info('Knowledge API: http://localhost:8000/api/knowledge/explore/start')
	logger.info('=' * 70)
	
	app = get_app()
	
	# Start BullMQ worker in background
	import asyncio
	try:
		loop = asyncio.get_event_loop()
		if loop.is_running():
			asyncio.create_task(start_knowledge_worker())
		else:
			loop.run_until_complete(start_knowledge_worker())
	except RuntimeError:
		# No event loop, will start when uvicorn starts
		pass
	
	# Run with uvicorn
	uvicorn.run(
		app,
		host='0.0.0.0',
		port=8000,
		log_level='info',
	)

"""
RQ Worker Script for Knowledge Retrieval

Start RQ workers to process knowledge retrieval jobs.

Usage:
    rq worker knowledge-retrieval
    # Or with this script:
    python navigator/knowledge/worker.py

This worker runs in a separate process from the API server.
Multiple workers can be started for horizontal scaling.
"""

import logging
import os
import sys

# Add project root to path for imports
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
	sys.path.insert(0, project_root)

# Load environment variables FIRST before any other imports
from dotenv import load_dotenv
load_dotenv(dotenv_path='.env.local', override=False)
load_dotenv(override=True)

# Configure logging for worker process
logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
	force=True,
)

logger = logging.getLogger(__name__)

# Set specific loggers to appropriate levels
logging.getLogger('uvicorn').setLevel(logging.WARNING)
logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
logging.getLogger('fastapi').setLevel(logging.WARNING)

# Ensure knowledge extraction loggers are at INFO level
logging.getLogger('navigator.knowledge').setLevel(logging.INFO)
logging.getLogger('navigator.knowledge.pipeline').setLevel(logging.INFO)
logging.getLogger('navigator.knowledge.job_queue').setLevel(logging.INFO)
logging.getLogger('navigator.knowledge.exploration_engine').setLevel(logging.INFO)

# Configure MongoDB loggers - only show errors by default
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

try:
	from rq import Worker, Queue
	from redis import Redis
except ImportError:
	logger.error("Error: RQ not installed. Install with: pip install rq redis")
	sys.exit(1)

def main():
	"""Start RQ worker for knowledge retrieval queue."""
	redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
	
	if not redis_url:
		logger.error("REDIS_URL not set. Please set REDIS_URL in your .env.local file.")
		sys.exit(1)
	
	logger.info("=" * 80)
	logger.info("Starting RQ worker for knowledge retrieval")
	logger.info("=" * 80)
	logger.info(f"Redis URL: {redis_url}")
	logger.info(f"Queue: knowledge-retrieval")
	logger.info("=" * 80)
	logger.info("Worker will process jobs from the queue")
	logger.info("Press CTRL+C to stop")
	logger.info("=" * 80)
	
	try:
		# RQ requires decode_responses=False because it stores binary data (pickled objects) in Redis
		# RQ handles encoding/decoding internally
		redis_conn = Redis.from_url(redis_url, decode_responses=False)
		
		# Test Redis connection
		try:
			redis_conn.ping()
			logger.info("✓ Redis connection successful")
		except Exception as e:
			logger.error(f"✗ Redis connection failed: {e}")
			logger.error("   Check that Redis is running and REDIS_URL is correct")
			sys.exit(1)
		
		queue = Queue("knowledge-retrieval", connection=redis_conn)
		
		# RQ 2.0+ requires passing connection directly to Worker (Connection context manager removed)
		worker = Worker([queue], connection=redis_conn)
		logger.info("✓ RQ worker started, listening for jobs...")
		worker.work()
	except KeyboardInterrupt:
		logger.info("\n" + "=" * 80)
		logger.info("Worker stopped by user")
		logger.info("=" * 80)
	except Exception as e:
		logger.error(f"Error: {e}", exc_info=True)
		sys.exit(1)

if __name__ == "__main__":
	main()

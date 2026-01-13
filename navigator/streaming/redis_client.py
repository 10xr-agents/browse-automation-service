"""
Redis Client Helper for Streams

Provides helper function to get Redis async client for Redis Streams.
Note: Redis Streams can use decode_responses=False (manual encoding) or True (auto-decode).
We use decode_responses=False for consistency with manual JSON encoding.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Global Redis async client for streams
_redis_streams_client: Any | None = None


def get_redis_url() -> str:
	"""
	Get Redis URL from environment variable.
	
	Returns:
		Redis URL string (raises ValueError if not set)
	
	Raises:
		ValueError: If REDIS_URL is not set
	"""
	redis_url = os.getenv("REDIS_URL")
	if not redis_url:
		raise ValueError(
			"Redis connection URL not found. "
			"Please set REDIS_URL in your .env.local file."
		)
	return redis_url


async def get_redis_streams_client() -> Any | None:
	"""
	Get or create Redis async client for Redis Streams.
	
	Note: Redis Streams uses decode_responses=False for manual encoding control.
	We encode JSON strings manually when publishing to streams.
	
	Returns:
		Redis async client instance or None if Redis not available
	"""
	global _redis_streams_client
	
	if _redis_streams_client is None:
		try:
			import redis.asyncio as redis
			
			redis_url = get_redis_url()
			# Use decode_responses=False for manual encoding control
			_redis_streams_client = redis.from_url(redis_url, decode_responses=False)
			await _redis_streams_client.ping()
			logger.info(f"Redis streams client connected to {redis_url}")
			return _redis_streams_client
		except ImportError:
			logger.warning("redis.asyncio not installed. Install with: pip install redis")
			return None
		except Exception as e:
			logger.warning(f"Redis streams client not available: {e}")
			return None
	
	return _redis_streams_client

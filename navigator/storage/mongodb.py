"""
MongoDB Storage Utility for Browser Automation Service

Provides centralized MongoDB connection and collection naming with standardized prefix.
All collections must use the 'brwsr_auto_svc_' prefix for namespace safety.
"""

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# MongoDB connection
_mongodb_client: Any | None = None
_mongodb_db: Any | None = None

# Collection name prefix - REQUIRED for all collections
COLLECTION_PREFIX = "brwsr_auto_svc_"


def get_collection_name(base_name: str) -> str:
	"""
	Get a properly prefixed MongoDB collection name.
	
	This function ensures all collections use the standardized prefix.
	
	Args:
		base_name: Base collection name (e.g., 'pages', 'sessions', 'jobs')
	
	Returns:
		Prefixed collection name (e.g., 'brwsr_auto_svc_pages')
	
	Examples:
		>>> get_collection_name('pages')
		'brwsr_auto_svc_pages'
		>>> get_collection_name('sessions')
		'brwsr_auto_svc_sessions'
	"""
	if base_name.startswith(COLLECTION_PREFIX):
		# Already prefixed, return as-is
		return base_name
	return f"{COLLECTION_PREFIX}{base_name}"


def get_mongodb_url() -> str:
	"""
	Get MongoDB connection URL from environment variable.
	
	Supports both MONGODB_URI and MONGODB_URL for compatibility.
	
	Returns:
		MongoDB URL string (raises ValueError if not set)
	
	Raises:
		ValueError: If neither MONGODB_URI nor MONGODB_URL is set
	"""
	# Try MONGODB_URI first (common convention), then MONGODB_URL
	mongodb_url = os.getenv("MONGODB_URI") or os.getenv("MONGODB_URL")
	if not mongodb_url:
		raise ValueError(
			"MongoDB connection string not found. "
			"Please set MONGODB_URI or MONGODB_URL in your .env.local file."
		)
	return mongodb_url


def get_mongodb_database_name() -> str:
	"""
	Get MongoDB database name from environment variable or extract from URI.
	
	If MONGODB_DATABASE is set, use it. Otherwise, try to extract from MONGODB_URI/MONGODB_URL.
	
	Returns:
		Database name (raises ValueError if not set and cannot be extracted)
	
	Raises:
		ValueError: If MONGODB_DATABASE is not set and cannot be extracted from URI
	"""
	# First, try explicit MONGODB_DATABASE environment variable
	database_name = os.getenv("MONGODB_DATABASE")
	if database_name:
		return database_name
	
	# Try to extract from MongoDB URI (format: mongodb://.../database_name?options)
	mongodb_uri = os.getenv("MONGODB_URI") or os.getenv("MONGODB_URL")
	if mongodb_uri:
		try:
			from urllib.parse import urlparse
			parsed = urlparse(mongodb_uri)
			# Extract database name from path (e.g., /spadeworks_local?tls=true -> spadeworks_local)
			if parsed.path and len(parsed.path) > 1:
				db_name = parsed.path.lstrip('/').split('?')[0]  # Remove leading / and query params
				if db_name:
					return db_name
		except Exception:
			pass  # If parsing fails, continue to error
	
	raise ValueError(
		"MongoDB database name not found. "
		"Please set MONGODB_DATABASE in your .env.local file, "
		"or include the database name in your MONGODB_URI (e.g., mongodb://.../database_name)."
	)


async def get_mongodb_client():
	"""
	Get or create MongoDB client.
	
	Returns:
		MongoDB client instance or None if MongoDB not available
	"""
	global _mongodb_client
	
	if _mongodb_client is None:
		try:
			from motor.motor_asyncio import AsyncIOMotorClient
			
			mongodb_url = get_mongodb_url()
			
			# Configure connection with reasonable timeouts
			# serverSelectionTimeoutMS: How long to wait for server selection (default 30s is too long)
			# connectTimeoutMS: How long to wait for initial connection (default 20s)
			# socketTimeoutMS: How long to wait for socket operations (default 20s)
			_mongodb_client = AsyncIOMotorClient(
				mongodb_url,
				serverSelectionTimeoutMS=5000,  # 5 seconds for server selection
				connectTimeoutMS=5000,  # 5 seconds for initial connection
				socketTimeoutMS=10000,  # 10 seconds for socket operations
			)
			
			# Test connection with shorter timeout
			await asyncio.wait_for(
				_mongodb_client.admin.command('ping'),
				timeout=5.0  # 5 second timeout for ping
			)
			logger.info(f"MongoDB client connected to {mongodb_url}")
			return _mongodb_client
		except ImportError:
			logger.warning("Motor (MongoDB async driver) not installed. Install with: pip install motor")
			return None
		except asyncio.TimeoutError:
			logger.error(f"MongoDB connection timeout: {mongodb_url}")
			logger.error("   Check that MongoDB is running and accessible")
			_mongodb_client = None
			return None
		except ValueError as e:
			# Configuration error - re-raise
			logger.error(str(e))
			raise
		except Exception as e:
			logger.error(f"MongoDB connection failed: {e}")
			logger.error(f"   Connection string: {mongodb_url}")
			_mongodb_client = None
			return None
	
	return _mongodb_client


async def get_mongodb_database():
	"""
	Get or create MongoDB database instance.
	
	Returns:
		MongoDB database instance or None if MongoDB not available
	"""
	global _mongodb_db
	
	if _mongodb_db is None:
		client = await get_mongodb_client()
		if client is None:
			return None
		
		database_name = get_mongodb_database_name()
		_mongodb_db = client[database_name]
		logger.info(f"MongoDB database '{database_name}' initialized")
	
	return _mongodb_db


async def get_collection(collection_name: str):
	"""
	Get a MongoDB collection with proper prefix.
	
	Args:
		collection_name: Base collection name (will be prefixed automatically)
	
	Returns:
		MongoDB collection instance or None if MongoDB not available
	"""
	db = await get_mongodb_database()
	if db is None:
		return None
	
	prefixed_name = get_collection_name(collection_name)
	return db[prefixed_name]


async def close_mongodb_connection():
	"""Close MongoDB connection."""
	global _mongodb_client, _mongodb_db
	
	if _mongodb_client:
		_mongodb_client.close()
		_mongodb_client = None
		_mongodb_db = None
		logger.info("MongoDB connection closed")

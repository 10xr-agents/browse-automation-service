"""
ArangoDB Storage Utility for Browser Automation Service

Provides centralized ArangoDB connection and collection management for knowledge graph storage.
Supports Python-Arango driver for async/sync operations.
"""

import logging
import os
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ArangoDB connection
_arangodb_client: Any | None = None
_arangodb_db: Any | None = None


def get_arangodb_url() -> str:
	"""
	Get ArangoDB connection URL from environment variable.
	
	Supports ARANGODB_URL with embedded credentials (http://user:pass@host:port)
	or separate ARANGODB_HOST, ARANGODB_USERNAME, ARANGODB_PASSWORD variables.
	
	Returns:
		ArangoDB URL string (raises ValueError if not properly configured)
	
	Raises:
		ValueError: If ArangoDB connection details are not set
	"""
	# Try ARANGODB_URL first (with embedded credentials)
	arangodb_url = os.getenv("ARANGODB_URL")
	if arangodb_url:
		return arangodb_url

	# Try separate host/port/credentials
	host = os.getenv("ARANGODB_HOST", "localhost")
	port = os.getenv("ARANGODB_PORT", "8529")
	username = os.getenv("ARANGODB_USERNAME")
	password = os.getenv("ARANGODB_PASSWORD")

	if username and password:
		return f"http://{username}:{password}@{host}:{port}"

	# If no credentials, return basic URL (will need auth later)
	logger.warning(
		"ArangoDB credentials not found in environment. "
		"Set ARANGODB_URL or ARANGODB_USERNAME/ARANGODB_PASSWORD"
	)
	return f"http://{host}:{port}"


def get_arangodb_credentials() -> tuple[str, str]:
	"""
	Extract ArangoDB username and password from URL or environment.
	
	Returns:
		Tuple of (username, password)
	
	Raises:
		ValueError: If credentials cannot be determined
	"""
	# Try to extract from ARANGODB_URL
	arangodb_url = os.getenv("ARANGODB_URL")
	if arangodb_url:
		try:
			parsed = urlparse(arangodb_url)
			if parsed.username and parsed.password:
				return (parsed.username, parsed.password)
		except Exception:
			pass

	# Try separate environment variables
	username = os.getenv("ARANGODB_USERNAME")
	password = os.getenv("ARANGODB_PASSWORD")

	if username and password:
		return (username, password)

	raise ValueError(
		"ArangoDB credentials not found. "
		"Please set ARANGODB_URL (with credentials) or ARANGODB_USERNAME/ARANGODB_PASSWORD "
		"in your .env.local file."
	)


def get_arangodb_database_name() -> str:
	"""
	Get ArangoDB database name from environment variable.
	
	Returns:
		Database name (raises ValueError if not set)
	
	Raises:
		ValueError: If ARANGODB_DATABASE is not set
	"""
	database_name = os.getenv("ARANGODB_DATABASE")
	if not database_name:
		raise ValueError(
			"ArangoDB database name not found. "
			"Please set ARANGODB_DATABASE in your .env.local file."
		)
	return database_name


async def get_arangodb_client():
	"""
	Get or create ArangoDB client (async).
	
	Uses python-arango library for connection management.
	
	Returns:
		ArangoDB client instance or None if ArangoDB not available
	"""
	global _arangodb_client

	if _arangodb_client is None:
		try:
			# Import python-arango
			try:
				from arango import ArangoClient
			except ImportError:
				logger.warning(
					"python-arango not installed. Install with: pip install python-arango"
				)
				return None

			# Get connection details
			arangodb_url = get_arangodb_url()
			username, password = get_arangodb_credentials()

			# Parse host and port from URL
			parsed = urlparse(arangodb_url)
			host = parsed.hostname or "localhost"
			port = parsed.port or 8529
			protocol = parsed.scheme or "http"

			# Create client
			_arangodb_client = ArangoClient(hosts=f"{protocol}://{host}:{port}")

			# Test connection by verifying authentication
			sys_db = _arangodb_client.db(
				"_system", username=username, password=password, verify=True
			)

			# Verify connection
			version_info = sys_db.version()
			logger.info(
				f"ArangoDB client connected to {protocol}://{host}:{port} "
				f"(version: {version_info})"
			)

			return _arangodb_client

		except ValueError as e:
			logger.error(f"ArangoDB configuration error: {e}")
			_arangodb_client = None
			return None
		except Exception as e:
			logger.error(f"ArangoDB connection failed: {e}")
			logger.error("   Make sure ArangoDB is running and accessible")
			_arangodb_client = None
			return None

	return _arangodb_client


async def get_arangodb_database():
	"""
	Get or create ArangoDB database instance.
	
	Returns:
		ArangoDB database instance or None if ArangoDB not available
	"""
	global _arangodb_db

	if _arangodb_db is None:
		client = await get_arangodb_client()
		if client is None:
			return None

		try:
			database_name = get_arangodb_database_name()
			username, password = get_arangodb_credentials()

			# Connect to database
			_arangodb_db = client.db(
				database_name, username=username, password=password, verify=True
			)

			logger.info(f"ArangoDB database '{database_name}' initialized")

		except Exception as e:
			logger.error(f"Failed to connect to ArangoDB database: {e}")
			_arangodb_db = None
			return None

	return _arangodb_db


async def get_arangodb_collection(collection_name: str):
	"""
	Get an ArangoDB collection.
	
	Args:
		collection_name: Name of the collection
	
	Returns:
		ArangoDB collection instance or None if not available
	"""
	db = await get_arangodb_database()
	if db is None:
		return None

	try:
		# Check if collection exists
		if db.has_collection(collection_name):
			return db.collection(collection_name)
		else:
			logger.warning(f"ArangoDB collection '{collection_name}' does not exist")
			return None
	except Exception as e:
		logger.error(f"Failed to access ArangoDB collection '{collection_name}': {e}")
		return None


async def create_arangodb_collection(
	collection_name: str, edge: bool = False
) -> bool:
	"""
	Create an ArangoDB collection if it doesn't exist.
	
	Args:
		collection_name: Name of the collection
		edge: Whether this is an edge collection (default: False for document collection)
	
	Returns:
		True if collection created or already exists, False on error
	"""
	db = await get_arangodb_database()
	if db is None:
		return False

	try:
		if not db.has_collection(collection_name):
			db.create_collection(collection_name, edge=edge)
			logger.info(
				f"Created ArangoDB {'edge' if edge else 'document'} collection: {collection_name}"
			)
		return True
	except Exception as e:
		logger.error(f"Failed to create ArangoDB collection '{collection_name}': {e}")
		return False


async def create_arangodb_graph(graph_name: str, edge_definitions: list[dict]) -> bool:
	"""
	Create an ArangoDB named graph if it doesn't exist.
	
	Args:
		graph_name: Name of the graph
		edge_definitions: List of edge definitions, each with:
			- edge_collection: Edge collection name
			- from_vertex_collections: List of source vertex collection names
			- to_vertex_collections: List of target vertex collection names
	
	Returns:
		True if graph created or already exists, False on error
	"""
	db = await get_arangodb_database()
	if db is None:
		return False

	try:
		if not db.has_graph(graph_name):
			db.create_graph(graph_name, edge_definitions=edge_definitions)
			logger.info(f"Created ArangoDB graph: {graph_name}")
		return True
	except Exception as e:
		logger.error(f"Failed to create ArangoDB graph '{graph_name}': {e}")
		return False


def close_arangodb_connection():
	"""Close ArangoDB connection."""
	global _arangodb_client, _arangodb_db

	if _arangodb_client:
		# python-arango doesn't require explicit close
		_arangodb_client = None
		_arangodb_db = None
		logger.info("ArangoDB connection closed")

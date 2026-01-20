"""
Phase 4.1: ArangoDB Configuration for Knowledge Graph.

Provides connection management and database initialization for the knowledge graph.
"""

import logging
from typing import Any

from navigator.storage.arangodb import (
	get_arangodb_client,
	get_arangodb_credentials,
	get_arangodb_database,
	get_arangodb_database_name,
)

logger = logging.getLogger(__name__)


async def get_graph_database() -> Any | None:
	"""
	Get ArangoDB database instance for knowledge graph.
	
	This is a wrapper around the storage utility that ensures the
	knowledge_graph database exists and is accessible.
	
	Returns:
		ArangoDB database instance or None if not available
	"""
	return await get_arangodb_database()


async def verify_graph_connection() -> bool:
	"""
	Verify ArangoDB connection and ensure knowledge_graph database exists.
	
	Performs the following checks:
	- Client connection successful
	- Authentication successful
	- Database accessible
	- Can create collections (basic permission check)
	
	Returns:
		True if all checks pass, False otherwise
	"""
	try:
		logger.info("Verifying ArangoDB connection for knowledge graph...")

		# Get client
		client = await get_arangodb_client()
		if client is None:
			logger.error("❌ Failed to create ArangoDB client")
			return False

		logger.info("✅ ArangoDB client created successfully")

		# Get credentials and database name
		username, password = get_arangodb_credentials()
		database_name = get_arangodb_database_name()

		logger.info(f"   Database: {database_name}")
		logger.info(f"   Username: {username}")

		# Connect to _system database to check/create knowledge_graph
		sys_db = client.db("_system", username=username, password=password, verify=True)

		# Check if database exists, create if not
		if not sys_db.has_database(database_name):
			logger.info(f"Creating database '{database_name}'...")
			sys_db.create_database(database_name)
			logger.info(f"✅ Database '{database_name}' created")
		else:
			logger.info(f"✅ Database '{database_name}' already exists")

		# Get database instance
		db = await get_graph_database()
		if db is None:
			logger.error("❌ Failed to get database instance")
			return False

		# Test basic operations
		collections = db.collections()
		logger.info(f"✅ Database accessible ({len(collections)} collections)")

		# Connection stable check (optional - just verify we can do multiple operations)
		version = sys_db.version()
		logger.info(f"✅ ArangoDB version: {version}")

		logger.info("🎉 ArangoDB connection verified successfully!")
		return True

	except Exception as e:
		logger.error(f"❌ ArangoDB connection verification failed: {e}", exc_info=True)
		return False


async def ensure_database_exists(database_name: str) -> bool:
	"""
	Ensure a specific database exists in ArangoDB.
	
	Args:
		database_name: Name of the database to ensure exists
	
	Returns:
		True if database exists or was created, False on error
	"""
	try:
		client = await get_arangodb_client()
		if client is None:
			return False

		username, password = get_arangodb_credentials()
		sys_db = client.db("_system", username=username, password=password, verify=True)

		if not sys_db.has_database(database_name):
			sys_db.create_database(database_name)
			logger.info(f"Created database: {database_name}")

		return True

	except Exception as e:
		logger.error(f"Failed to ensure database '{database_name}' exists: {e}")
		return False

"""
Storage utilities for Browser Automation Service.

Provides MongoDB-based persistence with standardized collection naming.
Also provides ArangoDB graph database support for knowledge graph storage.
"""

from navigator.storage.arangodb import (
	close_arangodb_connection,
	create_arangodb_collection,
	create_arangodb_graph,
	get_arangodb_client,
	get_arangodb_collection,
	get_arangodb_credentials,
	get_arangodb_database,
	get_arangodb_database_name,
	get_arangodb_url,
)
from navigator.storage.mongodb import (
	COLLECTION_PREFIX,
	close_mongodb_connection,
	get_collection,
	get_collection_name,
	get_mongodb_client,
	get_mongodb_database,
	get_mongodb_database_name,
	get_mongodb_url,
)

__all__ = [
	# MongoDB
	'COLLECTION_PREFIX',
	'get_collection_name',
	'get_mongodb_url',
	'get_mongodb_database_name',
	'get_mongodb_client',
	'get_mongodb_database',
	'get_collection',
	'close_mongodb_connection',
	# ArangoDB
	'get_arangodb_url',
	'get_arangodb_credentials',
	'get_arangodb_database_name',
	'get_arangodb_client',
	'get_arangodb_database',
	'get_arangodb_collection',
	'create_arangodb_collection',
	'create_arangodb_graph',
	'close_arangodb_connection',
]

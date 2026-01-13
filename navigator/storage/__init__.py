"""
Storage utilities for Browser Automation Service.

Provides MongoDB-based persistence with standardized collection naming.
"""

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
	'COLLECTION_PREFIX',
	'get_collection_name',
	'get_mongodb_url',
	'get_mongodb_database_name',
	'get_mongodb_client',
	'get_mongodb_database',
	'get_collection',
	'close_mongodb_connection',
]

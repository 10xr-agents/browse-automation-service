"""
Ingestion Deduplication

Implements Phase 5.4: Ingestion Deduplication

Provides functions to:
- Check if source already ingested (by content hash)
- Skip re-ingestion if content unchanged
- Update metadata if source modified
- Compute content hashes (SHA-256)

Prevents duplicate work and enables incremental updates.
"""

import hashlib
import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from navigator.knowledge.persist.collections import (
	SourceType,
	IngestionMetadataCollection,
	get_ingestion_metadata_collection,
)

logger = logging.getLogger(__name__)


class IngestionMetadata(BaseModel):
	"""
	Ingestion metadata model for persistence.
	
	Maps to IngestionMetadataCollection schema.
	"""
	source_id: str = Field(default_factory=lambda: f"src-{uuid4()}", description="Unique source identifier")
	source_type: SourceType = Field(..., description="Source type")
	source_url: str | None = Field(None, description="Original URL (if applicable)")
	source_path: str | None = Field(None, description="File path (if applicable)")
	content_hash: str = Field(..., description="SHA-256 hash of content")
	ingested_at: datetime = Field(default_factory=datetime.utcnow, description="Ingestion timestamp")
	last_updated: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
	metadata: dict[str, Any] = Field(default_factory=dict, description="Source-specific metadata")
	
	class Config:
		json_encoders = {
			datetime: lambda v: v.isoformat(),
		}


def compute_content_hash(content: str | bytes) -> str:
	"""
	Compute SHA-256 hash of content.
	
	Args:
		content: Content to hash (string or bytes)
	
	Returns:
		Hex-encoded SHA-256 hash
	
	Examples:
		>>> compute_content_hash("Hello, World!")
		'dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f'
	"""
	if isinstance(content, str):
		content = content.encode('utf-8')
	
	hasher = hashlib.sha256()
	hasher.update(content)
	return hasher.hexdigest()


async def check_already_ingested(
	source_url: str | None = None,
	source_path: str | None = None,
	content_hash: str | None = None
) -> IngestionMetadata | None:
	"""
	Check if source already ingested.
	
	Searches by:
	1. content_hash (most reliable, checks for exact content match)
	2. source_url (if no hash provided)
	3. source_path (if no hash or URL provided)
	
	Args:
		source_url: Source URL to check
		source_path: Source file path to check
		content_hash: SHA-256 hash of content
	
	Returns:
		IngestionMetadata if found, None otherwise
	"""
	try:
		collection = await get_ingestion_metadata_collection()
		if not collection:
			logger.warning("MongoDB unavailable, cannot check ingestion")
			return None
		
		# Build query (prefer content_hash, fallback to source_url or source_path)
		query = {}
		if content_hash:
			query['content_hash'] = content_hash
		elif source_url:
			query['source_url'] = source_url
		elif source_path:
			query['source_path'] = source_path
		else:
			logger.warning("No identifier provided for ingestion check")
			return None
		
		# Find existing ingestion
		metadata_dict = await collection.find_one(query)
		if not metadata_dict:
			logger.debug(f"Source not yet ingested: query={query}")
			return None
		
		# Remove MongoDB _id field
		metadata_dict.pop('_id', None)
		
		metadata = IngestionMetadata(**metadata_dict)
		logger.info(
			f"Source already ingested: source_id={metadata.source_id}, "
			f"ingested_at={metadata.ingested_at}, content_hash={metadata.content_hash[:16]}..."
		)
		return metadata
	
	except Exception as e:
		logger.error(f"Failed to check if already ingested: {e}")
		return None


async def save_ingestion_metadata(metadata: IngestionMetadata) -> bool:
	"""
	Save ingestion metadata to MongoDB.
	
	Creates or updates ingestion metadata document.
	
	Args:
		metadata: Ingestion metadata to save
	
	Returns:
		True if saved successfully, False otherwise
	"""
	try:
		collection = await get_ingestion_metadata_collection()
		if not collection:
			logger.warning("MongoDB unavailable, ingestion metadata not persisted")
			return False
		
		# Update timestamp
		metadata.last_updated = datetime.utcnow()
		
		# Upsert by source_id
		metadata_dict = metadata.dict()
		await collection.update_one(
			{'source_id': metadata.source_id},
			{'$set': metadata_dict},
			upsert=True
		)
		
		logger.info(
			f"Saved ingestion metadata: source_id={metadata.source_id}, "
			f"type={metadata.source_type}, content_hash={metadata.content_hash[:16]}..."
		)
		return True
	
	except Exception as e:
		logger.error(f"Failed to save ingestion metadata: {e}")
		return False


async def update_ingestion_metadata(
	source_id: str,
	content_hash: str,
	metadata_updates: dict[str, Any] | None = None
) -> bool:
	"""
	Update ingestion metadata (for modified sources).
	
	Updates content_hash, last_updated, and any additional metadata.
	
	Args:
		source_id: Source identifier
		content_hash: New SHA-256 hash
		metadata_updates: Additional metadata fields to update
	
	Returns:
		True if updated successfully, False otherwise
	"""
	try:
		collection = await get_ingestion_metadata_collection()
		if not collection:
			logger.warning("MongoDB unavailable, cannot update ingestion metadata")
			return False
		
		# Build update document
		update_doc = {
			'content_hash': content_hash,
			'last_updated': datetime.utcnow(),
		}
		
		if metadata_updates:
			update_doc['metadata'] = metadata_updates
		
		# Update ingestion metadata
		result = await collection.update_one(
			{'source_id': source_id},
			{'$set': update_doc}
		)
		
		if result.matched_count > 0:
			logger.info(f"Updated ingestion metadata: source_id={source_id}, content_hash={content_hash[:16]}...")
			return True
		else:
			logger.warning(f"Ingestion metadata not found for update: source_id={source_id}")
			return False
	
	except Exception as e:
		logger.error(f"Failed to update ingestion metadata: {e}")
		return False


async def get_ingestion_metadata(source_id: str) -> IngestionMetadata | None:
	"""
	Get ingestion metadata by source_id.
	
	Args:
		source_id: Source identifier
	
	Returns:
		IngestionMetadata if found, None otherwise
	"""
	try:
		collection = await get_ingestion_metadata_collection()
		if not collection:
			logger.warning("MongoDB unavailable, cannot get ingestion metadata")
			return None
		
		metadata_dict = await collection.find_one({'source_id': source_id})
		if not metadata_dict:
			logger.debug(f"Ingestion metadata not found: source_id={source_id}")
			return None
		
		# Remove MongoDB _id field
		metadata_dict.pop('_id', None)
		
		metadata = IngestionMetadata(**metadata_dict)
		logger.debug(f"Retrieved ingestion metadata: source_id={source_id}")
		return metadata
	
	except Exception as e:
		logger.error(f"Failed to get ingestion metadata: {e}")
		return None


async def list_ingested_sources(
	source_type: SourceType | None = None,
	limit: int = 100
) -> list[IngestionMetadata]:
	"""
	List ingested sources (optionally filtered by type).
	
	Args:
		source_type: Optional source type filter
		limit: Maximum number of results (default: 100)
	
	Returns:
		List of IngestionMetadata objects (sorted by ingested_at descending)
	"""
	try:
		collection = await get_ingestion_metadata_collection()
		if not collection:
			logger.warning("MongoDB unavailable, cannot list ingested sources")
			return []
		
		# Build query
		query = {}
		if source_type:
			query['source_type'] = source_type.value
		
		# Find and sort sources
		cursor = collection.find(query).sort('ingested_at', -1).limit(limit)
		
		sources = []
		async for metadata_dict in cursor:
			metadata_dict.pop('_id', None)
			sources.append(IngestionMetadata(**metadata_dict))
		
		logger.debug(f"Listed {len(sources)} ingested sources (type={source_type or 'all'})")
		return sources
	
	except Exception as e:
		logger.error(f"Failed to list ingested sources: {e}")
		return []


async def delete_ingestion_metadata(source_id: str) -> bool:
	"""
	Delete ingestion metadata (for cleanup).
	
	Args:
		source_id: Source identifier
	
	Returns:
		True if deleted successfully, False otherwise
	"""
	try:
		collection = await get_ingestion_metadata_collection()
		if not collection:
			logger.warning("MongoDB unavailable, cannot delete ingestion metadata")
			return False
		
		result = await collection.delete_one({'source_id': source_id})
		
		if result.deleted_count > 0:
			logger.info(f"Deleted ingestion metadata: source_id={source_id}")
			return True
		else:
			logger.warning(f"Ingestion metadata not found for deletion: source_id={source_id}")
			return False
	
	except Exception as e:
		logger.error(f"Failed to delete ingestion metadata: {e}")
		return False


async def is_content_changed(
	source_url: str | None,
	source_path: str | None,
	new_content_hash: str
) -> bool:
	"""
	Check if source content has changed since last ingestion.
	
	Args:
		source_url: Source URL
		source_path: Source file path
		new_content_hash: SHA-256 hash of current content
	
	Returns:
		True if content changed (or never ingested), False if unchanged
	"""
	try:
		# Check if source already ingested
		existing = await check_already_ingested(
			source_url=source_url,
			source_path=source_path
		)
		
		if not existing:
			# Never ingested, content is "changed" (needs ingestion)
			logger.info("Source never ingested, content considered changed")
			return True
		
		# Compare hashes
		if existing.content_hash == new_content_hash:
			logger.info(f"Source content unchanged: hash={new_content_hash[:16]}...")
			return False
		else:
			logger.info(
				f"Source content changed: "
				f"old_hash={existing.content_hash[:16]}..., "
				f"new_hash={new_content_hash[:16]}..."
			)
			return True
	
	except Exception as e:
		logger.error(f"Failed to check if content changed: {e}")
		# In case of error, assume content changed (safer to re-ingest)
		return True

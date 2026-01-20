"""
Ingestion Result Storage

Persists complete ingestion results including content chunks to MongoDB.
This is critical for downstream extraction activities to access the ingested content.
"""

import logging

from navigator.knowledge.persist.collections import get_ingestion_metadata_collection
from navigator.schemas import ContentChunk, IngestionResult

logger = logging.getLogger(__name__)


async def save_ingestion_result(result: IngestionResult) -> bool:
	"""
	Save complete ingestion result to MongoDB.
	
	This saves:
	- Ingestion metadata (ingestion_id, source info, stats)
	- All content chunks
	
	Args:
		result: IngestionResult to save
	
	Returns:
		True if saved successfully, False otherwise
	"""
	try:
		collection = await get_ingestion_metadata_collection()
		if collection is None:
			logger.error("❌ MongoDB unavailable, ingestion result not persisted")
			return False

		# Convert to dict for MongoDB storage
		# Calculate processing time from timestamps
		processing_time = 0.0
		if result.completed_at and result.started_at:
			processing_time = (result.completed_at - result.started_at).total_seconds()

		result_dict = {
			'ingestion_id': result.ingestion_id,
			'source_type': result.source_type.value,
			'metadata': result.metadata.dict(exclude_none=True) if result.metadata else {},
			'content_chunks': [chunk.dict(exclude_none=True) for chunk in result.content_chunks],
			'total_chunks': result.total_chunks,
			'total_tokens': result.total_tokens,
			'success': result.success,
			'errors': [
				{
					'error_type': e.error_type,
					'error_message': e.error_message,
					'context': e.context  # Fixed: was 'error_context', should be 'context'
				}
				for e in result.errors
			],
			'processing_time': processing_time,
			'started_at': result.started_at.isoformat() if result.started_at else None,
			'completed_at': result.completed_at.isoformat() if result.completed_at else None,
		}

		# Upsert by ingestion_id
		await collection.update_one(
			{'ingestion_id': result.ingestion_id},
			{'$set': result_dict},
			upsert=True
		)

		logger.info(
			f"✅ Saved ingestion result: "
			f"ingestion_id={result.ingestion_id}, "
			f"chunks={result.total_chunks}, "
			f"tokens={result.total_tokens}"
		)
		return True

	except Exception as e:
		logger.error(f"❌ Failed to save ingestion result: {e}", exc_info=True)
		return False


async def get_ingestion_result(ingestion_id: str) -> IngestionResult | None:
	"""
	Get complete ingestion result by ingestion_id.
	
	Args:
		ingestion_id: Ingestion identifier
	
	Returns:
		IngestionResult if found, None otherwise
	"""
	try:
		collection = await get_ingestion_metadata_collection()
		if collection is None:
			logger.error("❌ MongoDB unavailable, cannot get ingestion result")
			return None

		result_dict = await collection.find_one({'ingestion_id': ingestion_id})
		if not result_dict:
			logger.warning(f"⚠️ Ingestion result not found: ingestion_id={ingestion_id}")
			return None

		# Remove MongoDB _id field
		result_dict.pop('_id', None)

		# Reconstruct IngestionResult from dict
		from navigator.schemas import ContentChunk, IngestionError, IngestionResult, SourceMetadata, SourceType

		# Reconstruct content chunks
		content_chunks = [
			ContentChunk(**chunk_dict)
			for chunk_dict in result_dict.get('content_chunks', [])
		]

		# Reconstruct metadata
		metadata_dict = result_dict.get('metadata', {})
		metadata = SourceMetadata(**metadata_dict) if metadata_dict else None

		# Reconstruct errors
		errors = [
			IngestionError(**error_dict)
			for error_dict in result_dict.get('errors', [])
		]

		# Reconstruct timestamps
		from datetime import datetime
		started_at = None
		completed_at = None
		if result_dict.get('started_at'):
			started_at = datetime.fromisoformat(result_dict['started_at'])
		if result_dict.get('completed_at'):
			completed_at = datetime.fromisoformat(result_dict['completed_at'])

		# Create IngestionResult
		result = IngestionResult(
			ingestion_id=result_dict['ingestion_id'],
			source_type=SourceType(result_dict['source_type']),
			metadata=metadata,
			content_chunks=content_chunks,
			total_chunks=result_dict.get('total_chunks', 0),
			total_tokens=result_dict.get('total_tokens', 0),
			success=result_dict.get('success', True),
			errors=errors,
			started_at=started_at or datetime.utcnow(),
			completed_at=completed_at,
		)

		logger.info(
			f"✅ Retrieved ingestion result: "
			f"ingestion_id={ingestion_id}, "
			f"chunks={result.total_chunks}"
		)
		return result

	except Exception as e:
		logger.error(f"❌ Failed to get ingestion result: {e}", exc_info=True)
		return None


async def get_ingestion_chunks(ingestion_id: str) -> list[ContentChunk]:
	"""
	Get content chunks for an ingestion.
	
	This is a convenience function that extracts just the chunks.
	
	Args:
		ingestion_id: Ingestion identifier
	
	Returns:
		List of ContentChunk objects (empty list if not found)
	"""
	result = await get_ingestion_result(ingestion_id)
	if not result:
		logger.warning(f"⚠️ No chunks found for ingestion: ingestion_id={ingestion_id}")
		return []

	logger.info(
		f"✅ Loaded {len(result.content_chunks)} chunks for ingestion: {ingestion_id}"
	)
	return result.content_chunks


async def delete_ingestion_result(ingestion_id: str) -> bool:
	"""
	Delete ingestion result and all its content chunks.
	
	Args:
		ingestion_id: Ingestion identifier
	
	Returns:
		True if deleted successfully, False otherwise
	"""
	try:
		collection = await get_ingestion_metadata_collection()
		if collection is None:
			logger.error("❌ MongoDB unavailable, cannot delete ingestion result")
			return False

		result = await collection.delete_one({'ingestion_id': ingestion_id})

		if result.deleted_count > 0:
			logger.info(f"✅ Deleted ingestion result: ingestion_id={ingestion_id}")
			return True
		else:
			logger.warning(f"⚠️ Ingestion result not found for deletion: ingestion_id={ingestion_id}")
			return False

	except Exception as e:
		logger.error(f"❌ Failed to delete ingestion result: {e}", exc_info=True)
		return False

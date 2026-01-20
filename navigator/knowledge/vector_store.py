"""
Vector Store for Knowledge Retrieval

Stores embeddings for semantic search in MongoDB (with in-memory fallback).
All collections use the 'brwsr_auto_svc_' prefix.
"""

import logging
from typing import Any

from navigator.storage.mongodb import get_collection

logger = logging.getLogger(__name__)


class VectorStore:
	"""
	Vector store for storing and searching embeddings.
	
	Supports:
	- MongoDB storage (production)
	- In-memory storage (development/testing fallback)
	- Embedding storage and retrieval
	- Similarity search
	"""

	def __init__(self, use_mongodb: bool = True):
		"""
		Initialize vector store.
		
		Args:
			use_mongodb: Whether to use MongoDB (True by default, falls back to in-memory if unavailable)
		"""
		self.use_mongodb = use_mongodb
		self.embedding_dimension = 128  # Default dimension (matches SemanticAnalyzer)

		if use_mongodb:
			logger.info("VectorStore initialized with MongoDB")
		else:
			self._init_in_memory()
			logger.debug("VectorStore initialized with in-memory storage")

	def _init_in_memory(self) -> None:
		"""Initialize in-memory storage."""
		self.embeddings: dict[str, dict[str, Any]] = {}  # id -> {embedding, metadata}

	def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
		"""
		Calculate cosine similarity between two vectors.
		
		Args:
			vec1: First vector
			vec2: Second vector
		
		Returns:
			Cosine similarity score (0.0 to 1.0)
		"""
		if len(vec1) != len(vec2):
			return 0.0

		dot_product = sum(a * b for a, b in zip(vec1, vec2))
		magnitude1 = sum(a * a for a in vec1) ** 0.5
		magnitude2 = sum(b * b for b in vec2) ** 0.5

		if magnitude1 == 0.0 or magnitude2 == 0.0:
			return 0.0

		return dot_product / (magnitude1 * magnitude2)

	async def store_embedding(self, id: str, embedding: list[float], metadata: dict[str, Any] | None = None) -> None:
		"""
		Store an embedding with metadata.
		
		Args:
			id: Unique identifier for the embedding
			embedding: Embedding vector (list of floats)
			metadata: Optional metadata dictionary
		"""
		metadata = metadata or {}
		embedding_document = {
			'id': id,
			'embedding': embedding,
			'metadata': metadata,
		}

		if self.use_mongodb:
			try:
				collection = await get_collection('embeddings')
				if collection is None:
					# Fallback to in-memory
					self.embeddings[id] = embedding_document
					logger.debug(f"Stored embedding in-memory (MongoDB unavailable): {id}")
					return

				# Upsert by id
				await collection.update_one(
					{'id': id},
					{'$set': embedding_document},
					upsert=True
				)
				logger.debug(f"Stored embedding in MongoDB: {id}")
			except Exception as e:
				logger.error(f"Failed to store embedding in MongoDB: {e}")
				# Fallback to in-memory
				self.embeddings[id] = embedding_document
				logger.debug(f"Stored embedding in-memory (fallback): {id}")
		else:
			self.embeddings[id] = embedding_document
			logger.debug(f"Stored embedding in-memory: {id}")

	async def search_similar(self, query_embedding: list[float], top_k: int = 5, metadata_filter: dict[str, Any] | None = None) -> list[dict[str, Any]]:
		"""
		Search for similar embeddings.
		
		Args:
			query_embedding: Query embedding vector
			top_k: Number of results to return
			metadata_filter: Optional metadata filter
		
		Returns:
			List of similar embeddings with scores (sorted by similarity)
		"""
		if self.use_mongodb:
			try:
				collection = await get_collection('embeddings')
				if collection is None:
					# Fallback to in-memory search
					return self._search_in_memory(query_embedding, top_k, metadata_filter)

				# Get all embeddings (for now - can be optimized with vector search indexes later)
				cursor = collection.find(metadata_filter or {})
				results = []

				async for doc in cursor:
					embedding = doc.get('embedding', [])
					if not embedding:
						continue

					similarity = self._cosine_similarity(query_embedding, embedding)
					results.append({
						'id': doc.get('id'),
						'score': similarity,
						'metadata': doc.get('metadata', {}),
					})

				# Sort by similarity (descending) and return top_k
				results.sort(key=lambda x: x['score'], reverse=True)
				return results[:top_k]
			except Exception as e:
				logger.error(f"Failed to search embeddings in MongoDB: {e}")
				# Fallback to in-memory
				return self._search_in_memory(query_embedding, top_k, metadata_filter)
		else:
			return self._search_in_memory(query_embedding, top_k, metadata_filter)

	def _search_in_memory(self, query_embedding: list[float], top_k: int, metadata_filter: dict[str, Any] | None) -> list[dict[str, Any]]:
		"""Search in-memory embeddings."""
		results = []

		for id, data in self.embeddings.items():
			# Apply metadata filter if provided
			if metadata_filter:
				metadata = data.get('metadata', {})
				if not all(metadata.get(k) == v for k, v in metadata_filter.items()):
					continue

			embedding = data.get('embedding', [])
			if not embedding:
				continue

			similarity = self._cosine_similarity(query_embedding, embedding)
			results.append({
				'id': id,
				'score': similarity,
				'metadata': data.get('metadata', {}),
			})

		# Sort by similarity (descending) and return top_k
		results.sort(key=lambda x: x['score'], reverse=True)
		return results[:top_k]

	async def get_embedding(self, id: str) -> dict[str, Any] | None:
		"""
		Get an embedding by ID.
		
		Args:
			id: Embedding ID
		
		Returns:
			Embedding data dictionary or None if not found
		"""
		if self.use_mongodb:
			try:
				collection = await get_collection('embeddings')
				if collection is None:
					# Fallback to in-memory
					return self.embeddings.get(id)

				doc = await collection.find_one({'id': id})
				if doc:
					doc.pop('_id', None)  # Remove MongoDB _id
					return doc
				return None
			except Exception as e:
				logger.error(f"Failed to get embedding from MongoDB: {e}")
				# Fallback to in-memory
				return self.embeddings.get(id)
		else:
			return self.embeddings.get(id)

	async def update_embedding(self, id: str, embedding: list[float] | None = None, metadata: dict[str, Any] | None = None) -> None:
		"""
		Update an existing embedding.
		
		Args:
			id: Embedding ID
			embedding: New embedding vector (optional)
			metadata: New metadata (optional)
		"""
		update_data: dict[str, Any] = {}
		if embedding is not None:
			update_data['embedding'] = embedding
		if metadata is not None:
			update_data['metadata'] = metadata

		if not update_data:
			return

		if self.use_mongodb:
			try:
				collection = await get_collection('embeddings')
				if collection is None:
					# Fallback to in-memory
					if id in self.embeddings:
						if embedding is not None:
							self.embeddings[id]['embedding'] = embedding
						if metadata is not None:
							self.embeddings[id]['metadata'] = metadata
					logger.debug(f"Updated embedding in-memory (MongoDB unavailable): {id}")
					return

				await collection.update_one(
					{'id': id},
					{'$set': update_data}
				)
				logger.debug(f"Updated embedding in MongoDB: {id}")
			except Exception as e:
				logger.error(f"Failed to update embedding in MongoDB: {e}")
				# Fallback to in-memory
				if id in self.embeddings:
					if embedding is not None:
						self.embeddings[id]['embedding'] = embedding
					if metadata is not None:
						self.embeddings[id]['metadata'] = metadata
				logger.debug(f"Updated embedding in-memory (fallback): {id}")
		else:
			if id in self.embeddings:
				if embedding is not None:
					self.embeddings[id]['embedding'] = embedding
				if metadata is not None:
					self.embeddings[id]['metadata'] = metadata
			logger.debug(f"Updated embedding in-memory: {id}")

	async def delete_embedding(self, id: str) -> None:
		"""
		Delete an embedding.
		
		Args:
			id: Embedding ID
		"""
		if self.use_mongodb:
			try:
				collection = await get_collection('embeddings')
				if collection is None:
					# Fallback to in-memory
					self.embeddings.pop(id, None)
					logger.debug(f"Deleted embedding from in-memory (MongoDB unavailable): {id}")
					return

				await collection.delete_one({'id': id})
				logger.debug(f"Deleted embedding from MongoDB: {id}")
			except Exception as e:
				logger.error(f"Failed to delete embedding from MongoDB: {e}")
				# Fallback to in-memory
				self.embeddings.pop(id, None)
				logger.debug(f"Deleted embedding from in-memory (fallback): {id}")
		else:
			self.embeddings.pop(id, None)
			logger.debug(f"Deleted embedding from in-memory: {id}")

	async def clear(self) -> None:
		"""
		Clear all embeddings (for testing).
		"""
		if self.use_mongodb:
			try:
				collection = await get_collection('embeddings')
				if collection:
					await collection.delete_many({})
				logger.debug("Cleared MongoDB embeddings collection")
			except Exception as e:
				logger.error(f"Failed to clear MongoDB embeddings: {e}")

		# Also clear in-memory storage
		self.embeddings.clear()
		logger.debug("Cleared in-memory embeddings")

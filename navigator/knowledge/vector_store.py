"""
Vector Store for Knowledge Retrieval

Stores embeddings for semantic search (with in-memory fallback).
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class VectorStore:
	"""
	Vector store for storing and searching embeddings.
	
	Supports:
	- Vector database storage (production - Pinecone, Weaviate, Qdrant, Chroma)
	- In-memory storage (development/testing)
	- Embedding storage and retrieval
	- Similarity search
	"""
	
	def __init__(self, use_vector_db: bool = False, vector_db_config: dict[str, Any] | None = None):
		"""
		Initialize vector store.
		
		Args:
			use_vector_db: Whether to use vector database (False for in-memory storage)
			vector_db_config: Vector database configuration dict (type, api_key, endpoint, etc.)
		"""
		self.use_vector_db = use_vector_db
		self.vector_db_config = vector_db_config or {}
		
		if use_vector_db:
			try:
				# Try to initialize vector database
				# Note: For production, integrate with Pinecone, Weaviate, Qdrant, or Chroma
				vector_db_type = self.vector_db_config.get('type', 'pinecone')
				
				if vector_db_type == 'pinecone':
					# Placeholder for Pinecone integration
					# from pinecone import Pinecone, ServerlessSpec
					# self.pinecone = Pinecone(api_key=vector_db_config.get('api_key'))
					# self.index = self.pinecone.Index(vector_db_config.get('index_name', 'knowledge'))
					logger.warning("Pinecone integration not implemented, falling back to in-memory storage")
					self.use_vector_db = False
					self._init_in_memory()
				elif vector_db_type == 'chroma':
					# Placeholder for Chroma integration
					# import chromadb
					# self.chroma_client = chromadb.Client()
					# self.collection = self.chroma_client.get_or_create_collection('knowledge')
					logger.warning("Chroma integration not implemented, falling back to in-memory storage")
					self.use_vector_db = False
					self._init_in_memory()
				else:
					logger.warning(f"Vector database type '{vector_db_type}' not supported, falling back to in-memory storage")
					self.use_vector_db = False
					self._init_in_memory()
			except ImportError:
				logger.warning("Vector database libraries not available, falling back to in-memory storage")
				self.use_vector_db = False
				self._init_in_memory()
			except Exception as e:
				logger.error(f"Failed to initialize vector database: {e}, falling back to in-memory storage")
				self.use_vector_db = False
				self._init_in_memory()
		else:
			self._init_in_memory()
			logger.debug("VectorStore initialized with in-memory storage")
	
	def _init_in_memory(self) -> None:
		"""Initialize in-memory storage."""
		self.embeddings: dict[str, dict[str, Any]] = {}  # id -> {embedding, metadata}
		self.embedding_dimension = 128  # Default dimension (matches SemanticAnalyzer)
	
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
		
		if self.use_vector_db:
			try:
				# For production: use vector database API
				# Example for Pinecone:
				# self.index.upsert(vectors=[(id, embedding, metadata)])
				logger.debug(f"Stored embedding in vector database: {id}")
				# Fallback to in-memory for now
				self.embeddings[id] = {
					'embedding': embedding,
					'metadata': metadata,
				}
			except Exception as e:
				logger.error(f"Failed to store embedding in vector database: {e}")
				raise
		else:
			self.embeddings[id] = {
				'embedding': embedding,
				'metadata': metadata,
			}
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
		if self.use_vector_db:
			try:
				# For production: use vector database similarity search
				# Example for Pinecone:
				# results = self.index.query(vector=query_embedding, top_k=top_k, filter=metadata_filter, include_metadata=True)
				# return [{'id': r.id, 'score': r.score, 'metadata': r.metadata} for r in results.matches]
				# Fallback to in-memory for now
				pass
			except Exception as e:
				logger.error(f"Failed to search embeddings in vector database: {e}")
				return []
		
		# In-memory similarity search using cosine similarity
		results: list[dict[str, Any]] = []
		
		for embedding_id, embedding_data in self.embeddings.items():
			embedding = embedding_data['embedding']
			metadata = embedding_data['metadata']
			
			# Apply metadata filter if provided
			if metadata_filter:
				if not all(metadata.get(k) == v for k, v in metadata_filter.items()):
					continue
			
			# Calculate cosine similarity
			similarity = self._cosine_similarity(query_embedding, embedding)
			
			results.append({
				'id': embedding_id,
				'score': similarity,
				'metadata': metadata,
			})
		
		# Sort by similarity (descending)
		results.sort(key=lambda x: x['score'], reverse=True)
		
		# Return top_k results
		return results[:top_k]
	
	async def get_embedding(self, id: str) -> dict[str, Any] | None:
		"""
		Get an embedding by ID.
		
		Args:
			id: Embedding identifier
		
		Returns:
			Embedding data dictionary or None if not found
		"""
		if self.use_vector_db:
			try:
				# For production: use vector database API
				# Example for Pinecone:
				# result = self.index.fetch(ids=[id])
				# return result.vectors.get(id)
				# Fallback to in-memory for now
				return self.embeddings.get(id)
			except Exception as e:
				logger.error(f"Failed to get embedding from vector database: {e}")
				return None
		else:
			return self.embeddings.get(id)
	
	async def update_embedding(self, id: str, embedding: list[float] | None = None, metadata: dict[str, Any] | None = None) -> None:
		"""
		Update an existing embedding.
		
		Args:
			id: Embedding identifier
			embedding: New embedding vector (optional)
			metadata: New metadata (optional, merged with existing)
		"""
		if self.use_vector_db:
			try:
				# For production: use vector database API
				# Example for Pinecone:
				# self.index.upsert(vectors=[(id, embedding, metadata)])
				logger.debug(f"Updated embedding in vector database: {id}")
				# Fallback to in-memory for now
				if id in self.embeddings:
					if embedding is not None:
						self.embeddings[id]['embedding'] = embedding
					if metadata is not None:
						self.embeddings[id]['metadata'].update(metadata)
			except Exception as e:
				logger.error(f"Failed to update embedding in vector database: {e}")
				raise
		else:
			if id in self.embeddings:
				if embedding is not None:
					self.embeddings[id]['embedding'] = embedding
				if metadata is not None:
					self.embeddings[id]['metadata'].update(metadata)
				logger.debug(f"Updated embedding in-memory: {id}")
	
	async def delete_embedding(self, id: str) -> None:
		"""
		Delete an embedding.
		
		Args:
			id: Embedding identifier
		"""
		if self.use_vector_db:
			try:
				# For production: use vector database API
				# Example for Pinecone:
				# self.index.delete(ids=[id])
				logger.debug(f"Deleted embedding from vector database: {id}")
				# Fallback to in-memory for now
				if id in self.embeddings:
					del self.embeddings[id]
			except Exception as e:
				logger.error(f"Failed to delete embedding from vector database: {e}")
				raise
		else:
			if id in self.embeddings:
				del self.embeddings[id]
				logger.debug(f"Deleted embedding from in-memory storage: {id}")
	
	async def clear(self) -> None:
		"""
		Clear all embeddings (for testing).
		"""
		if self.use_vector_db:
			try:
				# For production: use vector database API
				# Example for Pinecone:
				# self.index.delete(delete_all=True)
				logger.debug("Cleared vector database")
				# Fallback to in-memory for now
				self.embeddings.clear()
			except Exception as e:
				logger.error(f"Failed to clear vector database: {e}")
		else:
			self.embeddings.clear()
			logger.debug("Cleared in-memory storage")

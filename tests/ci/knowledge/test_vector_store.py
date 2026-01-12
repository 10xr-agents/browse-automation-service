"""
Tests for Vector Store (Step 2.16).

Tests cover:
- Vector Store for Embeddings (Step 2.16)
"""

import pytest

from navigator.knowledge.vector_store import VectorStore


class TestVectorStoreInitialization:
	"""Tests for vector store initialization (Step 2.16)."""

	def test_in_memory_storage_init(self):
		"""Test in-memory storage initialization."""
		store = VectorStore(use_vector_db=False)
		
		assert store.use_vector_db is False
		assert hasattr(store, 'embeddings')
		assert store.embedding_dimension == 128

	def test_vector_db_storage_init_without_vector_db(self):
		"""Test vector database storage initialization falls back to in-memory if vector DB unavailable."""
		# This will fall back to in-memory since vector DB libraries are not installed
		store = VectorStore(use_vector_db=True)
		
		# Should fall back to in-memory
		assert store.use_vector_db is False
		assert hasattr(store, 'embeddings')


class TestVectorStoreOperations:
	"""Tests for vector store operations (Step 2.16)."""

	@pytest.mark.asyncio
	async def test_store_embedding(self):
		"""Test storing an embedding."""
		store = VectorStore(use_vector_db=False)
		
		embedding = [0.1, 0.2, 0.3] * 43  # 129 values, will be truncated or used as-is
		# Use 128 dimensions to match default
		embedding = [0.1, 0.2, 0.3, 0.4] * 32  # 128 dimensions
		
		await store.store_embedding("page1", embedding, {"url": "https://example.com/page1"})
		
		# Check stored embedding
		stored = await store.get_embedding("page1")
		assert stored is not None
		assert stored["embedding"] == embedding
		assert stored["metadata"]["url"] == "https://example.com/page1"

	@pytest.mark.asyncio
	async def test_get_embedding_not_found(self):
		"""Test getting a non-existent embedding."""
		store = VectorStore(use_vector_db=False)
		
		embedding = await store.get_embedding("notfound")
		assert embedding is None

	@pytest.mark.asyncio
	async def test_search_similar(self):
		"""Test similarity search."""
		store = VectorStore(use_vector_db=False)
		
		# Store multiple embeddings
		embedding1 = [1.0, 0.0, 0.0] * 32 + [0.0] * 32  # 128 dimensions
		embedding2 = [0.0, 1.0, 0.0] * 32 + [0.0] * 32  # 128 dimensions
		embedding3 = [0.0, 0.0, 1.0] * 32 + [0.0] * 32  # 128 dimensions
		
		# Normalize embeddings (roughly)
		def normalize(v):
			mag = sum(x*x for x in v) ** 0.5
			return [x/mag if mag > 0 else x for x in v]
		
		embedding1 = normalize(embedding1[:128])
		embedding2 = normalize(embedding2[:128])
		embedding3 = normalize(embedding3[:128])
		
		await store.store_embedding("page1", embedding1, {"title": "Page 1"})
		await store.store_embedding("page2", embedding2, {"title": "Page 2"})
		await store.store_embedding("page3", embedding3, {"title": "Page 3"})
		
		# Search with query similar to embedding1
		query_embedding = embedding1[:]  # Same as embedding1
		results = await store.search_similar(query_embedding, top_k=2)
		
		assert len(results) > 0
		assert results[0]["id"] == "page1"  # Should match page1
		assert results[0]["score"] > 0.9  # High similarity

	@pytest.mark.asyncio
	async def test_update_embedding(self):
		"""Test updating an embedding."""
		store = VectorStore(use_vector_db=False)
		
		embedding1 = [0.1, 0.2, 0.3] * 32 + [0.0] * 32  # 128 dimensions
		await store.store_embedding("page1", embedding1, {"title": "Original"})
		
		embedding2 = [0.4, 0.5, 0.6] * 32 + [0.0] * 32  # 128 dimensions
		await store.update_embedding("page1", embedding=embedding2, metadata={"title": "Updated"})
		
		stored = await store.get_embedding("page1")
		assert stored is not None
		assert stored["embedding"] == embedding2
		assert stored["metadata"]["title"] == "Updated"

	@pytest.mark.asyncio
	async def test_delete_embedding(self):
		"""Test deleting an embedding."""
		store = VectorStore(use_vector_db=False)
		
		embedding = [0.1, 0.2, 0.3] * 32 + [0.0] * 32  # 128 dimensions
		await store.store_embedding("page1", embedding)
		
		await store.delete_embedding("page1")
		
		stored = await store.get_embedding("page1")
		assert stored is None

	@pytest.mark.asyncio
	async def test_clear(self):
		"""Test clearing all embeddings."""
		store = VectorStore(use_vector_db=False)
		
		embedding = [0.1, 0.2, 0.3] * 32 + [0.0] * 32  # 128 dimensions
		await store.store_embedding("page1", embedding)
		await store.store_embedding("page2", embedding)
		
		await store.clear()
		
		stored1 = await store.get_embedding("page1")
		stored2 = await store.get_embedding("page2")
		assert stored1 is None
		assert stored2 is None

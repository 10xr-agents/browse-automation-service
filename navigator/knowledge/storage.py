"""
Knowledge Storage for Knowledge Retrieval

Stores extracted knowledge in MongoDB (with in-memory fallback for development).
All collections use the 'brwsr_auto_svc_' prefix.
"""

import logging
from typing import Any

from navigator.storage.mongodb import get_collection

logger = logging.getLogger(__name__)


class KnowledgeStorage:
	"""
	Knowledge storage for persisting extracted knowledge.
	
	Supports:
	- MongoDB storage (production)
	- In-memory storage (development/testing fallback)
	- Page storage (content, metadata, embeddings)
	- Link storage (links, relationships)
	"""
	
	def __init__(self, use_mongodb: bool = True):
		"""
		Initialize knowledge storage.
		
		Args:
			use_mongodb: Whether to use MongoDB (True by default, falls back to in-memory if unavailable)
		"""
		self.use_mongodb = use_mongodb
		
		if use_mongodb:
			# MongoDB connection will be tested on first use (async)
			logger.info("KnowledgeStorage initialized (will use MongoDB if available)")
		else:
			self._init_in_memory()
			logger.debug("KnowledgeStorage initialized with in-memory storage")
	
	def _init_in_memory(self) -> None:
		"""Initialize in-memory storage."""
		self.pages: dict[str, dict[str, Any]] = {}  # url -> page_data
		self.links: list[dict[str, Any]] = []  # List of link records
	
	async def store_page(self, url: str, page_data: dict[str, Any]) -> None:
		"""
		Store a page (content, metadata, embeddings).
		
		Args:
			url: URL of the page
			page_data: Dictionary with page data (content, metadata, embeddings, etc.)
		"""
		page_document = {
			'url': url,
			**page_data,
		}
		
		if self.use_mongodb:
			try:
				collection = await get_collection('pages')
				if collection is None:
					# Fallback to in-memory if MongoDB unavailable
					self.pages[url] = page_document
					logger.debug(f"Stored page in-memory (MongoDB unavailable): {url}")
					return
				
				# Upsert by URL
				await collection.update_one(
					{'url': url},
					{'$set': page_document},
					upsert=True
				)
				logger.debug(f"Stored page in MongoDB: {url}")
			except Exception as e:
				logger.error(f"Failed to store page in MongoDB: {e}")
				# Fallback to in-memory
				self.pages[url] = page_document
				logger.debug(f"Stored page in-memory (fallback): {url}")
		else:
			self.pages[url] = page_document
			logger.debug(f"Stored page in-memory: {url}")
	
	async def get_page(self, url: str) -> dict[str, Any] | None:
		"""
		Get a stored page.
		
		Args:
			url: URL of the page to retrieve
		
		Returns:
			Page data dictionary or None if not found
		"""
		if self.use_mongodb:
			try:
				collection = await get_collection('pages')
				if collection is None:
					# Fallback to in-memory
					return self.pages.get(url)
				
				page = await collection.find_one({'url': url})
				if page:
					# Remove MongoDB _id field for consistency
					page.pop('_id', None)
					return page
				return None
			except Exception as e:
				logger.error(f"Failed to get page from MongoDB: {e}")
				# Fallback to in-memory
				return self.pages.get(url)
		else:
			return self.pages.get(url)
	
	async def store_link(self, from_url: str, to_url: str, link_data: dict[str, Any] | None = None) -> None:
		"""
		Store a link (relationship between pages).
		
		Args:
			from_url: Source URL
			to_url: Target URL
			link_data: Additional link metadata (optional)
		"""
		link_data = link_data or {}
		link_document = {
			'from_url': from_url,
			'to_url': to_url,
			**link_data,
		}
		
		if self.use_mongodb:
			try:
				collection = await get_collection('links')
				if collection is None:
					# Fallback to in-memory
					self.links.append(link_document)
					logger.debug(f"Stored link in-memory (MongoDB unavailable): {from_url} -> {to_url}")
					return
				
				# Upsert by from_url and to_url combination
				await collection.update_one(
					{'from_url': from_url, 'to_url': to_url},
					{'$set': link_document},
					upsert=True
				)
				logger.debug(f"Stored link in MongoDB: {from_url} -> {to_url}")
			except Exception as e:
				logger.error(f"Failed to store link in MongoDB: {e}")
				# Fallback to in-memory
				self.links.append(link_document)
				logger.debug(f"Stored link in-memory (fallback): {from_url} -> {to_url}")
		else:
			self.links.append(link_document)
			logger.debug(f"Stored link in-memory: {from_url} -> {to_url}")
	
	async def get_links_from(self, url: str) -> list[dict[str, Any]]:
		"""
		Get all links from a page.
		
		Args:
			url: Source URL
		
		Returns:
			List of link records
		"""
		if self.use_mongodb:
			try:
				collection = await get_collection('links')
				if collection is None:
					# Fallback to in-memory
					return [link for link in self.links if link.get('from_url') == url]
				
				cursor = collection.find({'from_url': url})
				links = []
				async for link in cursor:
					link.pop('_id', None)  # Remove MongoDB _id
					links.append(link)
				return links
			except Exception as e:
				logger.error(f"Failed to get links from MongoDB: {e}")
				# Fallback to in-memory
				return [link for link in self.links if link.get('from_url') == url]
		else:
			return [link for link in self.links if link.get('from_url') == url]
	
	async def get_links_to(self, url: str) -> list[dict[str, Any]]:
		"""
		Get all links to a page.
		
		Args:
			url: Target URL
		
		Returns:
			List of link records
		"""
		if self.use_mongodb:
			try:
				collection = await get_collection('links')
				if collection is None:
					# Fallback to in-memory
					return [link for link in self.links if link.get('to_url') == url]
				
				cursor = collection.find({'to_url': url})
				links = []
				async for link in cursor:
					link.pop('_id', None)  # Remove MongoDB _id
					links.append(link)
				return links
			except Exception as e:
				logger.error(f"Failed to get links to from MongoDB: {e}")
				# Fallback to in-memory
				return [link for link in self.links if link.get('to_url') == url]
		else:
			return [link for link in self.links if link.get('to_url') == url]
	
	async def clear(self) -> None:
		"""
		Clear all stored data (for testing).
		"""
		if self.use_mongodb:
			try:
				pages_collection = await get_collection('pages')
				links_collection = await get_collection('links')
				
				if pages_collection:
					await pages_collection.delete_many({})
				if links_collection:
					await links_collection.delete_many({})
				
				logger.debug("Cleared MongoDB collections")
			except Exception as e:
				logger.error(f"Failed to clear MongoDB: {e}")
		
		# Also clear in-memory storage
		self.pages.clear()
		self.links.clear()
		logger.debug("Cleared in-memory storage")

"""
Knowledge Storage for Knowledge Retrieval

Stores extracted knowledge in ArangoDB (or in-memory for development).
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class KnowledgeStorage:
	"""
	Knowledge storage for persisting extracted knowledge.
	
	Supports:
	- ArangoDB storage (production)
	- In-memory storage (development/testing)
	- Page storage (content, metadata, embeddings)
	- Link storage (links, relationships)
	"""
	
	def __init__(self, use_arangodb: bool = False, arangodb_config: dict[str, Any] | None = None):
		"""
		Initialize knowledge storage.
		
		Args:
			use_arangodb: Whether to use ArangoDB (False for in-memory storage)
			arangodb_config: ArangoDB configuration dict (hosts, database, username, password)
		"""
		self.use_arangodb = use_arangodb
		self.arangodb_config = arangodb_config or {}
		
		if use_arangodb:
			try:
				from arango import ArangoClient
				self.arangodb_client = ArangoClient(hosts=self.arangodb_config.get('hosts', 'http://localhost:8529'))
				self.arangodb_db = self.arangodb_client.db(
					name=self.arangodb_config.get('database', 'knowledge'),
					username=self.arangodb_config.get('username', 'root'),
					password=self.arangodb_config.get('password', ''),
				)
				
				# Initialize collections if they don't exist
				self._init_collections()
				
				logger.info("KnowledgeStorage initialized with ArangoDB")
			except ImportError:
				logger.warning("ArangoDB not available, falling back to in-memory storage")
				self.use_arangodb = False
				self._init_in_memory()
			except Exception as e:
				logger.error(f"Failed to initialize ArangoDB: {e}, falling back to in-memory storage")
				self.use_arangodb = False
				self._init_in_memory()
		else:
			self._init_in_memory()
			logger.debug("KnowledgeStorage initialized with in-memory storage")
	
	def _init_collections(self) -> None:
		"""Initialize ArangoDB collections."""
		if not self.use_arangodb:
			return
		
		try:
			# Pages collection
			if not self.arangodb_db.has_collection('pages'):
				self.arangodb_db.create_collection('pages')
				logger.debug("Created 'pages' collection")
			
			# Links collection (edges for relationships)
			if not self.arangodb_db.has_collection('links'):
				self.arangodb_db.create_collection('links', edge=True)
				logger.debug("Created 'links' collection")
		except Exception as e:
			logger.error(f"Failed to initialize collections: {e}")
			raise
	
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
			'_key': self._url_to_key(url),
			'url': url,
			**page_data,
		}
		
		if self.use_arangodb:
			try:
				collection = self.arangodb_db.collection('pages')
				if collection.has(page_document['_key']):
					collection.update(page_document)
				else:
					collection.insert(page_document)
				logger.debug(f"Stored page in ArangoDB: {url}")
			except Exception as e:
				logger.error(f"Failed to store page in ArangoDB: {e}")
				raise
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
		if self.use_arangodb:
			try:
				collection = self.arangodb_db.collection('pages')
				key = self._url_to_key(url)
				if collection.has(key):
					return collection.get(key)
				return None
			except Exception as e:
				logger.error(f"Failed to get page from ArangoDB: {e}")
				return None
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
			'_from': f"pages/{self._url_to_key(from_url)}",
			'_to': f"pages/{self._url_to_key(to_url)}",
			**link_data,
		}
		
		if self.use_arangodb:
			try:
				collection = self.arangodb_db.collection('links')
				# Create edge document
				link_document['_key'] = f"{self._url_to_key(from_url)}_{self._url_to_key(to_url)}"
				if collection.has(link_document['_key']):
					collection.update(link_document)
				else:
					collection.insert(link_document)
				logger.debug(f"Stored link in ArangoDB: {from_url} -> {to_url}")
			except Exception as e:
				logger.error(f"Failed to store link in ArangoDB: {e}")
				raise
		else:
			# Store as dictionary for in-memory
			link_record = {
				'from_url': from_url,
				'to_url': to_url,
				**link_data,
			}
			self.links.append(link_record)
			logger.debug(f"Stored link in-memory: {from_url} -> {to_url}")
	
	async def get_links_from(self, url: str) -> list[dict[str, Any]]:
		"""
		Get all links from a page.
		
		Args:
			url: Source URL
		
		Returns:
			List of link records
		"""
		if self.use_arangodb:
			try:
				collection = self.arangodb_db.collection('links')
				from_key = self._url_to_key(url)
				cursor = self.arangodb_db.aql.execute(
					"""
					FOR link IN links
						FILTER link._from == @from_key
						RETURN link
					""",
					bind_vars={'from_key': f"pages/{from_key}"},
				)
				return list(cursor)
			except Exception as e:
				logger.error(f"Failed to get links from ArangoDB: {e}")
				return []
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
		if self.use_arangodb:
			try:
				collection = self.arangodb_db.collection('links')
				to_key = self._url_to_key(url)
				cursor = self.arangodb_db.aql.execute(
					"""
					FOR link IN links
						FILTER link._to == @to_key
						RETURN link
					""",
					bind_vars={'to_key': f"pages/{to_key}"},
				)
				return list(cursor)
			except Exception as e:
				logger.error(f"Failed to get links to from ArangoDB: {e}")
				return []
		else:
			return [link for link in self.links if link.get('to_url') == url]
	
	def _url_to_key(self, url: str) -> str:
		"""
		Convert URL to ArangoDB document key (safe for _key field).
		
		Args:
			url: URL to convert
		
		Returns:
			Safe key string
		"""
		# Replace unsafe characters
		import re
		key = re.sub(r'[^a-zA-Z0-9_-]', '_', url)
		# Limit length (ArangoDB key max length is 254)
		if len(key) > 200:
			key = key[:200]
		return key
	
	async def clear(self) -> None:
		"""
		Clear all stored data (for testing).
		"""
		if self.use_arangodb:
			try:
				# Clear collections
				if self.arangodb_db.has_collection('pages'):
					self.arangodb_db.collection('pages').truncate()
				if self.arangodb_db.has_collection('links'):
					self.arangodb_db.collection('links').truncate()
				logger.debug("Cleared ArangoDB collections")
			except Exception as e:
				logger.error(f"Failed to clear ArangoDB: {e}")
		else:
			self.pages.clear()
			self.links.clear()
			logger.debug("Cleared in-memory storage")

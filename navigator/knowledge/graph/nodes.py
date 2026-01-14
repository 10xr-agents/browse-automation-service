"""
Phase 4.4: Graph Node Creation.

Transforms extracted screens to graph nodes and inserts them into ArangoDB.
"""

import logging
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from navigator.knowledge.extract.screens import ScreenDefinition
from navigator.knowledge.graph.collections import SCREENS_COLLECTION, get_screen_collection

logger = logging.getLogger(__name__)


# =============================================================================
# Node Models
# =============================================================================

class ScreenNode(BaseModel):
	"""Screen node for ArangoDB (lightweight reference)."""
	model_config = {'populate_by_name': True}
	
	key: str = Field(..., alias="_key", description="Screen ID (ArangoDB document key)")
	name: str = Field(..., description="Screen name")
	website_id: str = Field(..., description="Website identifier")
	url_patterns: list[str] = Field(default_factory=list, description="URL regex patterns")
	metadata: dict[str, Any] = Field(default_factory=dict, description="Lightweight metadata")


class NodeCreationResult(BaseModel):
	"""Result of node creation operation."""
	creation_id: str = Field(default_factory=lambda: str(uuid4()), description="Operation ID")
	nodes_created: int = Field(default=0, description="Number of nodes created")
	nodes_updated: int = Field(default=0, description="Number of nodes updated")
	errors: list[dict[str, Any]] = Field(default_factory=list, description="Errors encountered")
	node_ids: list[str] = Field(default_factory=list, description="Created/updated node IDs")
	
	def add_error(self, error_type: str, message: str, context: dict[str, Any] | None = None) -> None:
		"""Add an error to the result."""
		self.errors.append({
			'type': error_type,
			'message': message,
			'context': context or {}
		})


# =============================================================================
# Node Creation Functions
# =============================================================================

async def upsert_screen_node(screen: ScreenDefinition) -> str | None:
	"""
	Insert or update a single screen node.
	
	Args:
		screen: Screen definition to convert to node
	
	Returns:
		Node ID (screens/{screen_id}) or None on error
	"""
	try:
		collection = await get_screen_collection()
		if collection is None:
			return None
		
		# Create lightweight node
		node = ScreenNode(
			key=screen.screen_id,
			name=screen.name,
			website_id=screen.website_id,
			url_patterns=screen.url_patterns,
			metadata={
				'state_signature_indicators': len(screen.state_signature.required_indicators),
				'ui_elements_count': len(screen.ui_elements),
			}
		)
		
		# Upsert (insert or update)
		node_dict = node.dict(by_alias=True, exclude_none=True)
		collection.insert(node_dict, overwrite=True)  # overwrite=True enables upsert
		
		node_id = f"{SCREENS_COLLECTION}/{screen.screen_id}"
		logger.debug(f"Upserted screen node: {node_id}")
		
		return node_id
		
	except Exception as e:
		logger.error(f"Failed to upsert screen node '{screen.screen_id}': {e}")
		return None


async def create_screen_nodes(screens: list[ScreenDefinition]) -> NodeCreationResult:
	"""
	Create or update screen nodes from extracted screens.
	
	Args:
		screens: List of screen definitions
	
	Returns:
		NodeCreationResult with statistics
	"""
	result = NodeCreationResult()
	
	try:
		logger.info(f"Creating screen nodes for {len(screens)} screens...")
		
		collection = await get_screen_collection()
		if collection is None:
			result.add_error("CollectionError", "Failed to get screen collection")
			return result
		
		for screen in screens:
			try:
				# Check if node already exists
				existing = collection.get(screen.screen_id)
				
				# Upsert node
				node_id = await upsert_screen_node(screen)
				
				if node_id:
					result.node_ids.append(node_id)
					if existing:
						result.nodes_updated += 1
					else:
						result.nodes_created += 1
				
			except Exception as e:
				result.add_error(
					"NodeCreationError",
					f"Failed to create node for screen '{screen.screen_id}': {e}",
					{'screen_id': screen.screen_id}
				)
		
		logger.info(
			f"✅ Created {result.nodes_created} nodes, "
			f"updated {result.nodes_updated} nodes"
		)
		
	except Exception as e:
		logger.error(f"❌ Failed to create screen nodes: {e}", exc_info=True)
		result.add_error("BatchCreationError", str(e))
	
	return result


async def get_screen_node(screen_id: str) -> dict | None:
	"""
	Get a screen node by ID.
	
	Args:
		screen_id: Screen ID (key)
	
	Returns:
		Screen node document or None if not found
	"""
	try:
		collection = await get_screen_collection()
		if collection is None:
			return None
		
		return collection.get(screen_id)
		
	except Exception as e:
		logger.error(f"Failed to get screen node '{screen_id}': {e}")
		return None


async def delete_screen_node(screen_id: str) -> bool:
	"""
	Delete a screen node.
	
	Args:
		screen_id: Screen ID (key)
	
	Returns:
		True if deleted, False otherwise
	"""
	try:
		collection = await get_screen_collection()
		if collection is None:
			return False
		
		collection.delete(screen_id)
		logger.info(f"Deleted screen node: {screen_id}")
		return True
		
	except Exception as e:
		logger.error(f"Failed to delete screen node '{screen_id}': {e}")
		return False


async def count_screen_nodes(website_id: str | None = None) -> int:
	"""
	Count screen nodes, optionally filtered by website.
	
	Args:
		website_id: Optional website ID to filter by
	
	Returns:
		Number of screen nodes
	"""
	try:
		collection = await get_screen_collection()
		if collection is None:
			return 0
		
		if website_id:
			# Count with filter
			from navigator.knowledge.graph.config import get_graph_database
			db = await get_graph_database()
			if db is None:
				return 0
			
			aql = """
			FOR screen IN screens
			    FILTER screen.website_id == @website_id
			    COLLECT WITH COUNT INTO count
			    RETURN count
			"""
			cursor = db.aql.execute(aql, bind_vars={'website_id': website_id})
			return next(cursor, 0)
		else:
			# Count all
			return collection.count()
		
	except Exception as e:
		logger.error(f"Failed to count screen nodes: {e}")
		return 0

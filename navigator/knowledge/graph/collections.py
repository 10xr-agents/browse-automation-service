"""
Phase 4.2: ArangoDB Collection Management.

Creates and manages document and edge collections for the knowledge graph.
"""

import logging
from typing import Any

from navigator.knowledge.graph.config import get_graph_database

logger = logging.getLogger(__name__)


# Collection names
SCREENS_COLLECTION = "screens"
SCREEN_GROUPS_COLLECTION = "screen_groups"
TRANSITIONS_COLLECTION = "transitions"
GROUP_MEMBERSHIP_COLLECTION = "group_membership"
GLOBAL_RECOVERY_COLLECTION = "global_recovery"


async def create_all_collections() -> bool:
	"""
	Create all required collections for the knowledge graph.
	
	Document collections:
	- screens: Lightweight screen references
	- screen_groups: Logical screen groupings
	
	Edge collections:
	- transitions: Screen state transitions
	- group_membership: Screen → ScreenGroup edges
	- global_recovery: ScreenGroup → Screen recovery edges
	
	Returns:
		True if all collections created/exist, False on error
	"""
	try:
		logger.info("Creating ArangoDB collections for knowledge graph...")

		db = await get_graph_database()
		if db is None:
			return False

		# Document collections
		doc_collections = [SCREENS_COLLECTION, SCREEN_GROUPS_COLLECTION]

		for coll_name in doc_collections:
			if not db.has_collection(coll_name):
				db.create_collection(coll_name, edge=False)
				logger.info(f"✅ Created document collection: {coll_name}")
			else:
				logger.info(f"   Document collection exists: {coll_name}")

		# Edge collections
		edge_collections = [
			TRANSITIONS_COLLECTION,
			GROUP_MEMBERSHIP_COLLECTION,
			GLOBAL_RECOVERY_COLLECTION,
		]

		for coll_name in edge_collections:
			if not db.has_collection(coll_name):
				db.create_collection(coll_name, edge=True)
				logger.info(f"✅ Created edge collection: {coll_name}")
			else:
				logger.info(f"   Edge collection exists: {coll_name}")

		# Create indexes for performance
		await _create_collection_indexes(db)

		logger.info("🎉 All collections created successfully!")
		return True

	except Exception as e:
		logger.error(f"❌ Failed to create collections: {e}", exc_info=True)
		return False


async def _create_collection_indexes(db: Any) -> None:
	"""Create indexes on collections for query performance."""
	try:
		# Index on screens.website_id for filtering by website
		screens = db.collection(SCREENS_COLLECTION)
		if not screens.has_index("website_id"):
			screens.add_hash_index(fields=["website_id"], unique=False)
			logger.info("✅ Created index: screens.website_id")

		# Index on screen_groups.website_id
		screen_groups = db.collection(SCREEN_GROUPS_COLLECTION)
		if not screen_groups.has_index("website_id"):
			screen_groups.add_hash_index(fields=["website_id"], unique=False)
			logger.info("✅ Created index: screen_groups.website_id")

		# Index on transitions for from/to queries
		transitions = db.collection(TRANSITIONS_COLLECTION)
		# ArangoDB automatically indexes _from and _to for edge collections

		logger.info("   Indexes created successfully")

	except Exception as e:
		logger.warning(f"Failed to create some indexes: {e}")


async def get_screen_collection() -> Any | None:
	"""Get the screens collection."""
	db = await get_graph_database()
	if db is None:
		return None
	return db.collection(SCREENS_COLLECTION)


async def get_screen_group_collection() -> Any | None:
	"""Get the screen_groups collection."""
	db = await get_graph_database()
	if db is None:
		return None
	return db.collection(SCREEN_GROUPS_COLLECTION)


async def get_transition_collection() -> Any | None:
	"""Get the transitions edge collection."""
	db = await get_graph_database()
	if db is None:
		return None
	return db.collection(TRANSITIONS_COLLECTION)


async def get_group_membership_collection() -> Any | None:
	"""Get the group_membership edge collection."""
	db = await get_graph_database()
	if db is None:
		return None
	return db.collection(GROUP_MEMBERSHIP_COLLECTION)


async def get_global_recovery_collection() -> Any | None:
	"""Get the global_recovery edge collection."""
	db = await get_graph_database()
	if db is None:
		return None
	return db.collection(GLOBAL_RECOVERY_COLLECTION)


async def clear_all_collections() -> bool:
	"""
	Clear all data from knowledge graph collections (for testing).
	
	Returns:
		True if successful, False on error
	"""
	try:
		logger.warning("⚠️ Clearing all knowledge graph collections...")

		db = await get_graph_database()
		if db is None:
			return False

		collections = [
			SCREENS_COLLECTION,
			SCREEN_GROUPS_COLLECTION,
			TRANSITIONS_COLLECTION,
			GROUP_MEMBERSHIP_COLLECTION,
			GLOBAL_RECOVERY_COLLECTION,
		]

		for coll_name in collections:
			if db.has_collection(coll_name):
				db.collection(coll_name).truncate()
				logger.info(f"   Cleared: {coll_name}")

		logger.info("✅ All collections cleared")
		return True

	except Exception as e:
		logger.error(f"❌ Failed to clear collections: {e}")
		return False

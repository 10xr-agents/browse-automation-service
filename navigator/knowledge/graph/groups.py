"""
Phase 4.6: Screen Group Creation with Recovery Paths.

Implements screen grouping and global recovery (Agent-Killer #4).
"""

import logging
import re
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from navigator.knowledge.extract.screens import ScreenDefinition
from navigator.knowledge.graph.collections import get_screen_group_collection
from navigator.knowledge.graph.edges import create_membership_edges, create_recovery_edges

logger = logging.getLogger(__name__)


# =============================================================================
# Group Models
# =============================================================================

class ScreenGroup(BaseModel):
	"""Screen group node."""
	model_config = {'populate_by_name': True}
	
	key: str = Field(..., alias="_key", description="Group ID (ArangoDB document key)")
	name: str = Field(..., description="Group name")
	website_id: str = Field(..., description="Website identifier")
	pattern_prefix: str | None = Field(None, description="URL pattern prefix")
	functional_area: str | None = Field(None, description="Functional area (login, dashboard, etc.)")
	metadata: dict[str, Any] = Field(default_factory=dict, description="Group metadata")


class GroupCreationResult(BaseModel):
	"""Result of group creation operation."""
	creation_id: str = Field(default_factory=lambda: str(uuid4()), description="Operation ID")
	groups_created: int = Field(default=0, description="Number of groups created")
	screens_grouped: int = Field(default=0, description="Number of screens grouped")
	recovery_paths_created: int = Field(default=0, description="Number of recovery paths")
	errors: list[dict[str, Any]] = Field(default_factory=list, description="Errors encountered")
	
	def add_error(self, error_type: str, message: str, context: dict[str, Any] | None = None) -> None:
		"""Add an error to the result."""
		self.errors.append({
			'type': error_type,
			'message': message,
			'context': context or {}
		})


# =============================================================================
# Grouping Logic
# =============================================================================

def group_screens_by_pattern(screens: list[ScreenDefinition]) -> dict[str, list[ScreenDefinition]]:
	"""
	Group screens by URL pattern prefix.
	
	Args:
		screens: List of screen definitions
	
	Returns:
		Dictionary mapping group name to screens
	"""
	groups: dict[str, list[ScreenDefinition]] = {}
	
	for screen in screens:
		# Extract common prefix from URL patterns
		if screen.url_patterns:
			# Take first pattern and extract prefix
			pattern = screen.url_patterns[0]
			
			# Try to find common path prefix (e.g., /dashboard/, /settings/)
			match = re.search(r'^[^/]*/([^/]+)/', pattern)
			if match:
				prefix = match.group(1)
				group_name = f"{prefix}_group"
			else:
				group_name = "root_group"
		else:
			group_name = "ungrouped"
		
		if group_name not in groups:
			groups[group_name] = []
		
		groups[group_name].append(screen)
	
	return groups


def identify_functional_area(screen: ScreenDefinition) -> str:
	"""
	Identify functional area from screen name/URL patterns.
	
	Args:
		screen: Screen definition
	
	Returns:
		Functional area (login, dashboard, settings, etc.)
	"""
	name_lower = screen.name.lower()
	patterns_lower = ' '.join(screen.url_patterns).lower()
	
	# Check for common patterns
	if any(keyword in name_lower or keyword in patterns_lower for keyword in ['login', 'signin', 'auth']):
		return 'login'
	elif any(keyword in name_lower or keyword in patterns_lower for keyword in ['dashboard', 'home', 'main']):
		return 'dashboard'
	elif any(keyword in name_lower or keyword in patterns_lower for keyword in ['settings', 'preferences', 'config']):
		return 'settings'
	elif any(keyword in name_lower or keyword in patterns_lower for keyword in ['profile', 'account']):
		return 'profile'
	elif any(keyword in name_lower or keyword in patterns_lower for keyword in ['admin', 'management']):
		return 'admin'
	else:
		return 'general'


def identify_recovery_screens(screens: list[ScreenDefinition]) -> list[dict[str, Any]]:
	"""
	Identify recovery screens with priority (Agent-Killer #4).
	
	Priority 1 (safest): Dashboard/Home links
	Priority 2+ (fastest): Back buttons, Cancel actions
	
	Args:
		screens: List of screen definitions
	
	Returns:
		List of recovery screen configs with priority and reliability
	"""
	recovery_screens = []
	
	for screen in screens:
		functional_area = identify_functional_area(screen)
		
		# Priority 1: Dashboard/Home (safest)
		if functional_area in ['dashboard', 'home']:
			recovery_screens.append({
				'screen_id': screen.screen_id,
				'priority': 1,  # Highest priority = safest
				'reliability': 1.0,  # Hard-coded nav links = 1.0
				'recovery_type': 'dashboard',
			})
		
		# Priority 2: Settings/Profile (reliable fallback)
		elif functional_area in ['settings', 'profile']:
			recovery_screens.append({
				'screen_id': screen.screen_id,
				'priority': 2,
				'reliability': 0.9,
				'recovery_type': 'settings',
			})
	
	# Sort by priority (lower = higher priority)
	recovery_screens.sort(key=lambda x: x['priority'])
	
	return recovery_screens


# =============================================================================
# Group Creation Functions
# =============================================================================

async def create_screen_groups(screens: list[ScreenDefinition], website_id: str) -> GroupCreationResult:
	"""
	Create screen groups with recovery paths (Agent-Killer #4).
	
	Grouping strategies:
	1. Group by URL pattern prefix
	2. Group by functional area
	3. Create recovery paths with priority
	
	Args:
		screens: List of screen definitions
		website_id: Website identifier
	
	Returns:
		GroupCreationResult with statistics
	"""
	result = GroupCreationResult()
	
	try:
		logger.info(f"Creating screen groups for {len(screens)} screens...")
		
		collection = await get_screen_group_collection()
		if collection is None:
			result.add_error("CollectionError", "Failed to get screen group collection")
			return result
		
		# Group by URL pattern
		pattern_groups = group_screens_by_pattern(screens)
		
		# Also group by functional area
		functional_groups: dict[str, list[ScreenDefinition]] = {}
		for screen in screens:
			area = identify_functional_area(screen)
			if area not in functional_groups:
				functional_groups[area] = []
			functional_groups[area].append(screen)
		
		# Create groups (prefer functional grouping)
		all_groups = functional_groups
		
		for group_name, group_screens in all_groups.items():
			try:
				# Create group node
				group_id = f"{website_id}_{group_name}"
				
				group = ScreenGroup(
					key=group_id,
					name=group_name.replace('_', ' ').title(),
					website_id=website_id,
					functional_area=group_name,
					metadata={
						'screen_count': len(group_screens),
					}
				)
				
				# Insert group
				group_dict = group.dict(by_alias=True, exclude_none=True)
				collection.insert(group_dict, overwrite=True)
				
				result.groups_created += 1
				logger.info(f"✅ Created group: {group_name} ({len(group_screens)} screens)")
				
				# Create membership edges (screen → group)
				screen_ids = [s.screen_id for s in group_screens]
				membership_result = await create_membership_edges(screen_ids, group_id)
				result.screens_grouped += membership_result.edges_created
				
				# Identify recovery screens for this group (Agent-Killer #4)
				recovery_screens = identify_recovery_screens(screens)  # All screens, not just group
				
				if recovery_screens:
					# Create recovery edges (group → recovery screens)
					recovery_result = await create_recovery_edges(group_id, recovery_screens)
					result.recovery_paths_created += recovery_result.edges_created
					
					logger.info(
						f"   Recovery paths: {len(recovery_screens)} screens "
						f"(Priority 1: {sum(1 for r in recovery_screens if r['priority'] == 1)})"
					)
			
			except Exception as e:
				result.add_error(
					"GroupCreationError",
					f"Failed to create group '{group_name}': {e}",
					{'group_name': group_name}
				)
		
		logger.info(
			f"🎉 Created {result.groups_created} groups, "
			f"grouped {result.screens_grouped} screens, "
			f"{result.recovery_paths_created} recovery paths"
		)
		
	except Exception as e:
		logger.error(f"❌ Failed to create screen groups: {e}", exc_info=True)
		result.add_error("BatchCreationError", str(e))
	
	return result


async def get_screen_group(group_id: str) -> dict | None:
	"""
	Get a screen group by ID.
	
	Args:
		group_id: Group ID (key)
	
	Returns:
		Screen group document or None if not found
	"""
	try:
		collection = await get_screen_group_collection()
		if collection is None:
			return None
		
		return collection.get(group_id)
		
	except Exception as e:
		logger.error(f"Failed to get screen group '{group_id}': {e}")
		return None


async def list_groups_for_website(website_id: str) -> list[dict]:
	"""
	List all groups for a website.
	
	Args:
		website_id: Website identifier
	
	Returns:
		List of screen group documents
	"""
	try:
		from navigator.knowledge.graph.config import get_graph_database
		
		db = await get_graph_database()
		if db is None:
			return []
		
		aql = """
		FOR group IN screen_groups
		    FILTER group.website_id == @website_id
		    RETURN group
		"""
		
		cursor = db.aql.execute(aql, bind_vars={'website_id': website_id})
		return list(cursor)
		
	except Exception as e:
		logger.error(f"Failed to list groups for website '{website_id}': {e}")
		return []

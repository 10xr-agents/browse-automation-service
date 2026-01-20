"""
Phase 4.5: Graph Edge Creation.

Transforms extracted transitions to graph edges and inserts them into ArangoDB.
"""

import logging
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from navigator.knowledge.extract.transitions import TransitionDefinition
from navigator.knowledge.graph.collections import (
	GLOBAL_RECOVERY_COLLECTION,
	GROUP_MEMBERSHIP_COLLECTION,
	SCREENS_COLLECTION,
	TRANSITIONS_COLLECTION,
	get_global_recovery_collection,
	get_group_membership_collection,
	get_transition_collection,
)
from navigator.knowledge.graph.nodes import get_screen_node

logger = logging.getLogger(__name__)


# =============================================================================
# Edge Models
# =============================================================================

class TransitionEdge(BaseModel):
	"""Transition edge schema (deprecated - all knowledge stored in MongoDB)."""
	model_config = {'populate_by_name': True}

	key: str | None = Field(None, alias="_key", description="Edge key (auto-generated if None)")
	from_: str = Field(..., alias="_from", description="Source node ID (screens/{screen_id})")
	to: str = Field(..., alias="_to", description="Target node ID (screens/{screen_id})")
	trigger_action_id: str | None = Field(None, description="Action that triggers transition")
	trigger_action_type: str = Field(..., description="Action type (click, submit, etc.)")
	trigger_element_id: str | None = Field(None, description="Element ID that triggers transition")
	conditions: dict[str, list[dict]] = Field(
		default_factory=lambda: {"required": [], "optional": []},
		description="Transition conditions"
	)
	effects: list[dict] = Field(default_factory=list, description="Side effects")
	cost: dict[str, Any] = Field(
		default_factory=lambda: {"estimated_ms": 2000, "complexity_score": 0.5},
		description="Transition cost"
	)
	reliability: float = Field(default=0.95, description="Success rate (0.0-1.0)")


class EdgeCreationResult(BaseModel):
	"""Result of edge creation operation."""
	creation_id: str = Field(default_factory=lambda: str(uuid4()), description="Operation ID")
	edges_created: int = Field(default=0, description="Number of edges created")
	edges_updated: int = Field(default=0, description="Number of edges updated")
	errors: list[dict[str, Any]] = Field(default_factory=list, description="Errors encountered")
	edge_ids: list[str] = Field(default_factory=list, description="Created/updated edge IDs")

	def add_error(self, error_type: str, message: str, context: dict[str, Any] | None = None) -> None:
		"""Add an error to the result."""
		self.errors.append({
			'type': error_type,
			'message': message,
			'context': context or {}
		})


# =============================================================================
# Edge Creation Functions
# =============================================================================

async def create_transition_edge(transition: TransitionDefinition) -> str | None:
	"""
	Create a single transition edge.
	
	Args:
		transition: Transition definition
	
	Returns:
		Edge ID (transitions/{edge_key}) or None on error
	"""
	try:
		collection = await get_transition_collection()
		if collection is None:
			return None

		# Validate source and target nodes exist
		from_node = await get_screen_node(transition.from_screen_id)
		to_node = await get_screen_node(transition.to_screen_id)

		if not from_node:
			logger.error(f"Source screen not found: {transition.from_screen_id}")
			return None

		if not to_node:
			logger.error(f"Target screen not found: {transition.to_screen_id}")
			return None

		# Create edge
		edge = TransitionEdge(
			from_=f"{SCREENS_COLLECTION}/{transition.from_screen_id}",
			to=f"{SCREENS_COLLECTION}/{transition.to_screen_id}",
			trigger_action_type=transition.triggered_by.action_type,
			trigger_element_id=transition.triggered_by.element_id,
			conditions={
				'required': [c.dict() for c in transition.conditions.get('required', [])],
				'optional': [c.dict() for c in transition.conditions.get('optional', [])],
			},
			effects=[e.dict() for e in transition.effects],
			cost=transition.cost,
			reliability=transition.reliability_score,
		)

		# Insert edge
		edge_dict = edge.dict(by_alias=True, exclude_none=True)
		result = collection.insert(edge_dict)

		edge_id = f"{TRANSITIONS_COLLECTION}/{result['_key']}"
		logger.debug(f"Created transition edge: {edge_id}")

		return edge_id

	except Exception as e:
		logger.error(f"Failed to create transition edge: {e}")
		return None


async def create_transition_edges(transitions: list[TransitionDefinition]) -> EdgeCreationResult:
	"""
	Create transition edges from extracted transitions.
	
	Args:
		transitions: List of transition definitions
	
	Returns:
		EdgeCreationResult with statistics
	"""
	result = EdgeCreationResult()

	try:
		logger.info(f"Creating transition edges for {len(transitions)} transitions...")

		for transition in transitions:
			try:
				edge_id = await create_transition_edge(transition)

				if edge_id:
					result.edge_ids.append(edge_id)
					result.edges_created += 1

			except Exception as e:
				result.add_error(
					"EdgeCreationError",
					f"Failed to create edge for transition '{transition.transition_id}': {e}",
					{'transition_id': transition.transition_id}
				)

		logger.info(f"✅ Created {result.edges_created} transition edges")

	except Exception as e:
		logger.error(f"❌ Failed to create transition edges: {e}", exc_info=True)
		result.add_error("BatchCreationError", str(e))

	return result


async def create_membership_edges(
	screen_ids: list[str],
	group_id: str
) -> EdgeCreationResult:
	"""
	Create group membership edges (screen → group).
	
	Args:
		screen_ids: List of screen IDs
		group_id: Screen group ID
	
	Returns:
		EdgeCreationResult with statistics
	"""
	result = EdgeCreationResult()

	try:
		collection = await get_group_membership_collection()
		if collection is None:
			result.add_error("CollectionError", "Failed to get membership collection")
			return result

		logger.info(f"Creating membership edges: {len(screen_ids)} screens → group {group_id}")

		for screen_id in screen_ids:
			try:
				edge = {
					'_from': f"{SCREENS_COLLECTION}/{screen_id}",
					'_to': f"screen_groups/{group_id}",
				}

				edge_result = collection.insert(edge)
				result.edge_ids.append(f"{GROUP_MEMBERSHIP_COLLECTION}/{edge_result['_key']}")
				result.edges_created += 1

			except Exception as e:
				result.add_error(
					"MembershipError",
					f"Failed to create membership edge for screen '{screen_id}': {e}",
					{'screen_id': screen_id, 'group_id': group_id}
				)

		logger.info(f"✅ Created {result.edges_created} membership edges")

	except Exception as e:
		logger.error(f"❌ Failed to create membership edges: {e}", exc_info=True)
		result.add_error("BatchCreationError", str(e))

	return result


async def create_recovery_edges(
	group_id: str,
	recovery_screens: list[dict[str, Any]]
) -> EdgeCreationResult:
	"""
	Create global recovery edges (group → recovery screens).
	
	Agent-Killer #4: Implements priority-based recovery paths.
	
	Args:
		group_id: Screen group ID
		recovery_screens: List of recovery screen configs with:
			- screen_id: Screen ID
			- priority: Recovery priority (1 = safest, 2+ = fastest)
			- reliability: Reliability score (0.0-1.0)
	
	Returns:
		EdgeCreationResult with statistics
	"""
	result = EdgeCreationResult()

	try:
		collection = await get_global_recovery_collection()
		if collection is None:
			result.add_error("CollectionError", "Failed to get recovery collection")
			return result

		logger.info(f"Creating recovery edges: group {group_id} → {len(recovery_screens)} recovery screens")

		for recovery in recovery_screens:
			try:
				screen_id = recovery['screen_id']
				priority = recovery.get('priority', 1)
				reliability = recovery.get('reliability', 1.0)

				edge = {
					'_from': f"screen_groups/{group_id}",
					'_to': f"{SCREENS_COLLECTION}/{screen_id}",
					'priority': priority,  # Agent-Killer #4
					'reliability': reliability,  # Agent-Killer #4
					'recovery_type': 'dashboard' if priority == 1 else 'back_button',
				}

				edge_result = collection.insert(edge)
				result.edge_ids.append(f"{GLOBAL_RECOVERY_COLLECTION}/{edge_result['_key']}")
				result.edges_created += 1

			except Exception as e:
				result.add_error(
					"RecoveryError",
					f"Failed to create recovery edge for screen '{screen_id}': {e}",
					{'screen_id': screen_id, 'group_id': group_id}
				)

		logger.info(f"✅ Created {result.edges_created} recovery edges")

	except Exception as e:
		logger.error(f"❌ Failed to create recovery edges: {e}", exc_info=True)
		result.add_error("BatchCreationError", str(e))

	return result


async def count_transition_edges(from_screen_id: str | None = None) -> int:
	"""
	Count transition edges, optionally filtered by source screen.
	
	Args:
		from_screen_id: Optional source screen ID to filter by
	
	Returns:
		Number of transition edges
	"""
	try:
		collection = await get_transition_collection()
		if collection is None:
			return 0

		if from_screen_id:
			# Count with filter
			from navigator.knowledge.graph.config import get_graph_database
			db = await get_graph_database()
			if db is None:
				return 0

			aql = """
			FOR edge IN transitions
			    FILTER edge._from == @from_screen
			    COLLECT WITH COUNT INTO count
			    RETURN count
			"""
			from_screen = f"{SCREENS_COLLECTION}/{from_screen_id}"
			cursor = db.aql.execute(aql, bind_vars={'from_screen': from_screen})
			return next(cursor, 0)
		else:
			# Count all
			return collection.count()

	except Exception as e:
		logger.error(f"Failed to count transition edges: {e}")
		return 0

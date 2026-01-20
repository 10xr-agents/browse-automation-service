"""
Phase 4.7: Graph Structure Validation.

Validates graph against KNOWLEDGE_SCHEMA_DESIGN.md requirements.
"""

import logging
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from navigator.knowledge.graph.config import get_graph_database

logger = logging.getLogger(__name__)


# =============================================================================
# Validation Models
# =============================================================================

class ValidationResult(BaseModel):
	"""Result of graph validation."""
	validation_id: str = Field(default_factory=lambda: str(uuid4()), description="Validation ID")
	is_valid: bool = Field(default=True, description="Whether graph is valid")

	# Validation checks
	nodes_valid: bool = Field(default=False, description="All nodes have required fields")
	edges_valid: bool = Field(default=False, description="All edges reference valid nodes")
	connectivity_valid: bool = Field(default=False, description="Graph is connected")
	acyclicity_valid: bool = Field(default=False, description="Graph is acyclic (DAG)")
	recovery_paths_valid: bool = Field(default=False, description="All groups have recovery paths")

	# Statistics
	total_nodes: int = Field(default=0, description="Total screen nodes")
	total_edges: int = Field(default=0, description="Total transition edges")
	total_groups: int = Field(default=0, description="Total screen groups")
	orphaned_nodes: int = Field(default=0, description="Nodes with no edges")
	cyclic_paths: int = Field(default=0, description="Number of cycles detected")

	# Errors
	errors: list[dict[str, Any]] = Field(default_factory=list, description="Validation errors")
	warnings: list[dict[str, Any]] = Field(default_factory=list, description="Validation warnings")

	def add_error(self, error_type: str, message: str, context: dict[str, Any] | None = None) -> None:
		"""Add an error to the result."""
		self.errors.append({
			'type': error_type,
			'message': message,
			'context': context or {}
		})
		self.is_valid = False

	def add_warning(self, warning_type: str, message: str, context: dict[str, Any] | None = None) -> None:
		"""Add a warning to the result."""
		self.warnings.append({
			'type': warning_type,
			'message': message,
			'context': context or {}
		})


# =============================================================================
# Validation Functions
# =============================================================================

async def validate_graph_structure(website_id: str | None = None) -> ValidationResult:
	"""
	Validate complete graph structure.
	
	Checks:
	1. All nodes have required fields
	2. All edges reference valid nodes
	3. Graph connectivity
	4. Graph acyclicity (DAG requirement)
	5. All groups have recovery paths
	
	Args:
		website_id: Optional website ID to validate specific website
	
	Returns:
		ValidationResult with detailed results
	"""
	result = ValidationResult()

	try:
		logger.info("Validating knowledge graph structure...")

		db = await get_graph_database()
		if db is None:
			result.add_error("DatabaseError", "Failed to get graph database")
			return result

		# Validate nodes
		await _validate_nodes(db, result, website_id)

		# Validate edges
		await _validate_edges(db, result, website_id)

		# Validate connectivity
		await _validate_connectivity(db, result, website_id)

		# Validate acyclicity (Agent-Killer #1)
		await _validate_acyclicity(db, result, website_id)

		# Validate recovery paths (Agent-Killer #4)
		await _validate_recovery_paths(db, result, website_id)

		# Calculate final validity
		result.is_valid = (
			result.nodes_valid and
			result.edges_valid and
			result.connectivity_valid and
			result.acyclicity_valid and
			result.recovery_paths_valid
		)

		if result.is_valid:
			logger.info("🎉 Graph validation passed!")
		else:
			logger.error(f"❌ Graph validation failed: {len(result.errors)} errors")

	except Exception as e:
		logger.error(f"❌ Graph validation failed: {e}", exc_info=True)
		result.add_error("ValidationError", str(e))

	return result


async def _validate_nodes(db: Any, result: ValidationResult, website_id: str | None) -> None:
	"""Validate all screen nodes have required fields."""
	try:
		# Query all screens
		aql = """
		FOR screen IN screens
		    FILTER @website_id == null OR screen.website_id == @website_id
		    RETURN screen
		"""

		cursor = db.aql.execute(aql, bind_vars={'website_id': website_id})
		screens = list(cursor)

		result.total_nodes = len(screens)

		# Validate required fields
		required_fields = ['_key', 'name', 'website_id', 'url_patterns']

		for screen in screens:
			for field in required_fields:
				if field not in screen or screen[field] is None:
					result.add_error(
						"NodeValidationError",
						f"Screen '{screen.get('_key', 'unknown')}' missing required field: {field}",
						{'screen_id': screen.get('_key'), 'field': field}
					)

		if len(result.errors) == 0:
			result.nodes_valid = True
			logger.info(f"✅ Node validation passed ({result.total_nodes} nodes)")

	except Exception as e:
		result.add_error("NodeValidationError", str(e))


async def _validate_edges(db: Any, result: ValidationResult, website_id: str | None) -> None:
	"""Validate all edges reference valid nodes."""
	try:
		# Query all transitions
		aql = """
		FOR edge IN transitions
		    LET from_node = DOCUMENT(edge._from)
		    LET to_node = DOCUMENT(edge._to)
		    FILTER @website_id == null OR from_node.website_id == @website_id
		    RETURN {
		        edge: edge,
		        from_exists: from_node != null,
		        to_exists: to_node != null
		    }
		"""

		cursor = db.aql.execute(aql, bind_vars={'website_id': website_id})
		edges = list(cursor)

		result.total_edges = len(edges)

		# Validate edge references
		for edge_data in edges:
			edge = edge_data['edge']

			if not edge_data['from_exists']:
				result.add_error(
					"EdgeValidationError",
					f"Edge references non-existent source node: {edge['_from']}",
					{'edge_from': edge['_from']}
				)

			if not edge_data['to_exists']:
				result.add_error(
					"EdgeValidationError",
					f"Edge references non-existent target node: {edge['_to']}",
					{'edge_to': edge['_to']}
				)

		if len(result.errors) == 0:
			result.edges_valid = True
			logger.info(f"✅ Edge validation passed ({result.total_edges} edges)")

	except Exception as e:
		result.add_error("EdgeValidationError", str(e))


async def _validate_connectivity(db: Any, result: ValidationResult, website_id: str | None) -> None:
	"""Validate graph connectivity (no orphaned nodes)."""
	try:
		# Find orphaned nodes (no incoming or outgoing edges)
		aql = """
		FOR screen IN screens
		    FILTER @website_id == null OR screen.website_id == @website_id
		    LET outgoing = (
		        FOR v, e IN 1..1 OUTBOUND screen transitions
		        RETURN 1
		    )
		    LET incoming = (
		        FOR v, e IN 1..1 INBOUND screen transitions
		        RETURN 1
		    )
		    FILTER LENGTH(outgoing) == 0 AND LENGTH(incoming) == 0
		    RETURN screen._key
		"""

		cursor = db.aql.execute(aql, bind_vars={'website_id': website_id})
		orphaned = list(cursor)

		result.orphaned_nodes = len(orphaned)

		if result.orphaned_nodes > 0:
			result.add_warning(
				"ConnectivityWarning",
				f"{result.orphaned_nodes} orphaned nodes (no incoming/outgoing edges)",
				{'orphaned_nodes': orphaned}
			)

		# Connectivity is valid if less than 10% orphaned
		result.connectivity_valid = (result.orphaned_nodes / max(result.total_nodes, 1)) < 0.1

		if result.connectivity_valid:
			logger.info(f"✅ Connectivity validation passed ({result.orphaned_nodes} orphaned)")

	except Exception as e:
		result.add_error("ConnectivityError", str(e))


async def _validate_acyclicity(db: Any, result: ValidationResult, website_id: str | None) -> None:
	"""
	Validate graph is acyclic (DAG requirement - Agent-Killer #1).
	
	Uses DFS cycle detection algorithm.
	"""
	try:
		# Find cycles using AQL traversal
		aql = """
		FOR screen IN screens
		    FILTER @website_id == null OR screen.website_id == @website_id
		    FOR v, e, p IN 1..10 OUTBOUND screen transitions
		        FILTER v._id == screen._id
		        RETURN {
		            start: screen._key,
		            cycle: p.vertices[*]._key
		        }
		"""

		cursor = db.aql.execute(aql, bind_vars={'website_id': website_id})
		cycles = list(cursor)

		result.cyclic_paths = len(cycles)

		if result.cyclic_paths > 0:
			for cycle in cycles[:5]:  # Limit to first 5
				result.add_error(
					"CycleDetected",
					f"Cycle detected starting at {cycle['start']}",
					{'cycle': cycle['cycle']}
				)

			if result.cyclic_paths > 5:
				result.add_error(
					"CycleDetected",
					f"...and {result.cyclic_paths - 5} more cycles",
					{}
				)

		result.acyclicity_valid = result.cyclic_paths == 0

		if result.acyclicity_valid:
			logger.info("✅ Acyclicity validation passed (DAG confirmed)")
		else:
			logger.error(f"❌ Acyclicity validation failed ({result.cyclic_paths} cycles)")

	except Exception as e:
		result.add_error("AcyclicityError", str(e))


async def _validate_recovery_paths(db: Any, result: ValidationResult, website_id: str | None) -> None:
	"""
	Validate all groups have recovery paths (Agent-Killer #4).
	"""
	try:
		# Query all groups and check recovery edges
		aql = """
		FOR group IN screen_groups
		    FILTER @website_id == null OR group.website_id == @website_id
		    LET recovery_paths = (
		        FOR screen IN 1..1 OUTBOUND group global_recovery
		        RETURN 1
		    )
		    RETURN {
		        group_id: group._key,
		        has_recovery: LENGTH(recovery_paths) > 0,
		        recovery_count: LENGTH(recovery_paths)
		    }
		"""

		cursor = db.aql.execute(aql, bind_vars={'website_id': website_id})
		groups = list(cursor)

		result.total_groups = len(groups)

		groups_without_recovery = [g for g in groups if not g['has_recovery']]

		if groups_without_recovery:
			for group in groups_without_recovery:
				result.add_error(
					"RecoveryPathMissing",
					f"Group '{group['group_id']}' has no recovery paths",
					{'group_id': group['group_id']}
				)

		result.recovery_paths_valid = len(groups_without_recovery) == 0

		if result.recovery_paths_valid:
			logger.info(f"✅ Recovery path validation passed ({result.total_groups} groups)")

	except Exception as e:
		result.add_error("RecoveryPathError", str(e))


async def validate_screen_node(screen_id: str) -> bool:
	"""
	Validate a single screen node.
	
	Args:
		screen_id: Screen ID (key)
	
	Returns:
		True if valid, False otherwise
	"""
	try:
		db = await get_graph_database()
		if db is None:
			return False

		# Check node exists
		aql = """
		FOR screen IN screens
		    FILTER screen._key == @screen_id
		    RETURN screen
		"""

		cursor = db.aql.execute(aql, bind_vars={'screen_id': screen_id})
		screen = next(cursor, None)

		if not screen:
			return False

		# Validate required fields
		required_fields = ['_key', 'name', 'website_id', 'url_patterns']
		for field in required_fields:
			if field not in screen or screen[field] is None:
				return False

		return True

	except Exception as e:
		logger.error(f"Failed to validate screen node '{screen_id}': {e}")
		return False

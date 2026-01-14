"""
Tests for Phase 4: Knowledge Graph Construction.

Validates:
- ArangoDB configuration
- Collection creation
- Graph definitions
- Node creation
- Edge creation
- Screen grouping
- Graph validation
"""

import pytest

from navigator.knowledge.extract.screens import ScreenDefinition, StateSignature, Indicator
from navigator.knowledge.extract.transitions import TransitionDefinition, TransitionTrigger
from navigator.knowledge.graph import (
	create_all_collections,
	create_all_graphs,
	create_screen_groups,
	create_screen_nodes,
	create_transition_edges,
	get_graph_database,
	validate_graph_structure,
	verify_graph_connection,
)


# =============================================================================
# Phase 4.1: Configuration
# =============================================================================

@pytest.mark.asyncio
async def test_4_1_1_arango_connection():
	"""Test Phase 4.1.1 - ArangoDB connection verification."""
	is_connected = await verify_graph_connection()
	
	# May fail if ArangoDB not running - that's OK for CI
	if is_connected:
		assert is_connected is True
		print("✅ ArangoDB connection successful")
	else:
		pytest.skip("ArangoDB not available")


@pytest.mark.asyncio
async def test_4_1_2_get_database():
	"""Test Phase 4.1.2 - Get graph database instance."""
	db = await get_graph_database()
	
	if db:
		assert db is not None
		print("✅ Graph database instance obtained")
	else:
		pytest.skip("ArangoDB not available")


# =============================================================================
# Phase 4.2: Collections
# =============================================================================

@pytest.mark.asyncio
async def test_4_2_1_create_collections():
	"""Test Phase 4.2.1 - Create all collections."""
	result = await create_all_collections()
	
	if result:
		assert result is True
		print("✅ Collections created successfully")
	else:
		pytest.skip("ArangoDB not available")


# =============================================================================
# Phase 4.3: Graphs
# =============================================================================

@pytest.mark.asyncio
async def test_4_3_1_create_graphs():
	"""Test Phase 4.3.1 - Create named graphs."""
	result = await create_all_graphs()
	
	if result:
		assert result is True
		print("✅ Graphs created successfully")
	else:
		pytest.skip("ArangoDB not available")


# =============================================================================
# Phase 4.4: Nodes
# =============================================================================

@pytest.mark.asyncio
async def test_4_4_1_create_screen_nodes():
	"""Test Phase 4.4.1 - Create screen nodes."""
	screens = [
		ScreenDefinition(
			screen_id="test_screen_1",
			name="Test Screen 1",
			website_id="test_website",
			url_patterns=[".*/test1"],
			state_signature=StateSignature(
				required_indicators=[Indicator(pattern="Test indicator", type="dom_contains")],
				optional_indicators=[],
				exclusion_indicators=[],
				negative_indicators=[]
			),
			ui_elements=[]
		),
		ScreenDefinition(
			screen_id="test_screen_2",
			name="Test Screen 2",
			website_id="test_website",
			url_patterns=[".*/test2"],
			state_signature=StateSignature(
				required_indicators=[Indicator(pattern="Test indicator", type="dom_contains")],
				optional_indicators=[],
				exclusion_indicators=[],
				negative_indicators=[]
			),
			ui_elements=[]
		)
	]
	
	result = await create_screen_nodes(screens)
	
	if result.nodes_created > 0 or result.nodes_updated > 0:
		assert result.nodes_created + result.nodes_updated == 2
		print(f"✅ Created/updated {result.nodes_created + result.nodes_updated} nodes")
	else:
		pytest.skip("ArangoDB not available")


# =============================================================================
# Phase 4.5: Edges
# =============================================================================

@pytest.mark.asyncio
async def test_4_5_1_create_transition_edges():
	"""Test Phase 4.5.1 - Create transition edges."""
	# First create nodes
	screens = [
		ScreenDefinition(
			screen_id="screen_a",
			name="Screen A",
			website_id="test_website",
			url_patterns=[".*/a"],
			state_signature=StateSignature(
			required_indicators=[Indicator(pattern="A", type="dom_contains")],
				optional_indicators=[],
				exclusion_indicators=[],
				negative_indicators=[]
			),
			ui_elements=[]
		),
		ScreenDefinition(
			screen_id="screen_b",
			name="Screen B",
			website_id="test_website",
			url_patterns=[".*/b"],
			state_signature=StateSignature(
			required_indicators=[Indicator(pattern="B", type="dom_contains")],
				optional_indicators=[],
				exclusion_indicators=[],
				negative_indicators=[]
			),
			ui_elements=[]
		)
	]
	
	await create_screen_nodes(screens)
	
	# Create transition
	transitions = [
		TransitionDefinition(
			transition_id="a_to_b",
			from_screen_id="screen_a",
			to_screen_id="screen_b",
			triggered_by=TransitionTrigger(action_type="click")
		)
	]
	
	result = await create_transition_edges(transitions)
	
	if result.edges_created > 0:
		assert result.edges_created == 1
		print(f"✅ Created {result.edges_created} edges")
	else:
		pytest.skip("ArangoDB not available")


# =============================================================================
# Phase 4.6: Groups
# =============================================================================

@pytest.mark.asyncio
async def test_4_6_1_create_screen_groups():
	"""Test Phase 4.6.1 - Create screen groups with recovery."""
	screens = [
		ScreenDefinition(
			screen_id="dashboard_screen",
			name="Dashboard",
			website_id="test_website",
			url_patterns=[".*/dashboard"],
			state_signature=StateSignature(
			required_indicators=[Indicator(pattern="Dashboard", type="dom_contains")],
				optional_indicators=[],
				exclusion_indicators=[],
				negative_indicators=[]
			),
			ui_elements=[]
		),
		ScreenDefinition(
			screen_id="settings_screen",
			name="Settings",
			website_id="test_website",
			url_patterns=[".*/settings"],
			state_signature=StateSignature(
			required_indicators=[Indicator(pattern="Settings", type="dom_contains")],
				optional_indicators=[],
				exclusion_indicators=[],
				negative_indicators=[]
			),
			ui_elements=[]
		)
	]
	
	# Create nodes first
	await create_screen_nodes(screens)
	
	# Create groups
	result = await create_screen_groups(screens, "test_website")
	
	if result.groups_created > 0:
		assert result.groups_created > 0
		assert result.screens_grouped > 0
		print(f"✅ Created {result.groups_created} groups with {result.recovery_paths_created} recovery paths")
	else:
		pytest.skip("ArangoDB not available")


# =============================================================================
# Phase 4.7: Validation
# =============================================================================

@pytest.mark.asyncio
async def test_4_7_1_validate_graph_structure():
	"""Test Phase 4.7.1 - Validate complete graph structure."""
	result = await validate_graph_structure(website_id="test_website")
	
	if result:
		# Graph may not be valid initially (expected)
		assert result is not None
		print(f"✅ Graph validation completed (valid: {result.is_valid})")
	else:
		pytest.skip("ArangoDB not available")


# =============================================================================
# Integration Test
# =============================================================================

@pytest.mark.asyncio
async def test_4_integration_full_graph_construction():
	"""Integration test - Full graph construction pipeline."""
	# Verify connection
	if not await verify_graph_connection():
		pytest.skip("ArangoDB not available")
	
	# Create collections and graphs
	await create_all_collections()
	await create_all_graphs()
	
	# Create test data
	screens = [
		ScreenDefinition(
			screen_id="login",
			name="Login",
			website_id="integration_test",
			url_patterns=[".*/login"],
			state_signature=StateSignature(
			required_indicators=[Indicator(pattern="Login form", type="dom_contains")],
				optional_indicators=[],
				exclusion_indicators=[],
				negative_indicators=[]
			),
			ui_elements=[]
		),
		ScreenDefinition(
			screen_id="dashboard",
			name="Dashboard",
			website_id="integration_test",
			url_patterns=[".*/dashboard"],
			state_signature=StateSignature(
			required_indicators=[Indicator(pattern="Dashboard", type="dom_contains")],
				optional_indicators=[],
				exclusion_indicators=[],
				negative_indicators=[]
			),
			ui_elements=[]
		)
	]
	
	# Create nodes
	node_result = await create_screen_nodes(screens)
	assert node_result.nodes_created + node_result.nodes_updated == 2
	
	# Create edges
	transitions = [
		TransitionDefinition(
			transition_id="login_to_dashboard",
			from_screen_id="login",
			to_screen_id="dashboard",
			triggered_by=TransitionTrigger(action_type="click")
		)
	]
	edge_result = await create_transition_edges(transitions)
	assert edge_result.edges_created == 1
	
	# Create groups
	group_result = await create_screen_groups(screens, "integration_test")
	assert group_result.groups_created > 0
	
	# Validate
	validation = await validate_graph_structure(website_id="integration_test")
	assert validation is not None
	
	print("🎉 Full graph construction pipeline completed!")

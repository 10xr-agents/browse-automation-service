"""
Tests for Phase 3.6: Entity and Relationship Extraction.

Validates:
- UI element entity extraction
- Parameter entity extraction
- Relationship extraction (CONTAINS, REQUIRES, TRIGGERS, EXECUTES)
- Graph-ready format
"""

import pytest

from navigator.knowledge.extract import EntityExtractor
from navigator.knowledge.extract.actions import ActionDefinition
from navigator.knowledge.extract.entities import UIElementEntity, ParameterEntity
from navigator.knowledge.extract.screens import (
	ScreenDefinition, StateSignature, UIElement, ElementSelector, SelectorStrategy
)
from navigator.knowledge.extract.tasks import TaskDefinition, IOSpec, IOInput, IOOutput, IteratorSpec
from navigator.knowledge.extract.transitions import TransitionDefinition, TransitionTrigger
from navigator.schemas import ContentChunk


# =============================================================================
# Phase 3.6.1: UI Element Entity Extraction
# =============================================================================

def test_3_6_1_entity_extractor_initialization():
	"""Test Phase 3.6.1 - EntityExtractor initialization."""
	extractor = EntityExtractor()
	
	assert extractor is not None


def test_3_6_2_extract_ui_elements_from_screens():
	"""Test Phase 3.6.2 - Extract UI element entities from screens."""
	extractor = EntityExtractor()
	
	screens = [
		ScreenDefinition(
			screen_id="login_screen",
			name="Login Screen",
			website_id="test_site",
			url_patterns=[".*/login"],
			state_signature=StateSignature(
				required_indicators=[],
				optional_indicators=[],
				exclusion_indicators=[],
				negative_indicators=[]
			),
			ui_elements=[
				UIElement(
					element_id="email_input",
					type="input",
					selector=ElementSelector(
						strategies=[
							SelectorStrategy(type="css", css="#email")
						]
					)
				),
				UIElement(
					element_id="submit_button",
					type="button",
					selector=ElementSelector(
						strategies=[
							SelectorStrategy(type="css", css=".submit-btn")
						]
					)
				)
			]
		)
	]
	
	result = extractor.extract_entities_and_relationships(
		screens=screens,
		tasks=[],
		actions=[],
		transitions=[]
	)
	
	assert result.success is True
	assert len(result.ui_elements) == 2
	assert result.statistics['ui_elements'] == 2


# =============================================================================
# Phase 3.6.2: Parameter Entity Extraction
# =============================================================================

def test_3_6_3_extract_parameters_from_tasks():
	"""Test Phase 3.6.3 - Extract parameter entities from tasks."""
	extractor = EntityExtractor()
	
	tasks = [
		TaskDefinition(
			task_id="login_task",
			name="Login Task",
			website_id="test_site",
			description="Login to site",
			io_spec=IOSpec(
				inputs=[
					IOInput(
						name="email",
						type="string",
						required=True,
						description="User email",
						source="user_input",
						volatility="low"
					),
					IOInput(
						name="password",
						type="string",
						required=True,
						description="User password",
						source="user_input",
						volatility="high"
					)
				],
				outputs=[
					IOOutput(
						name="auth_token",
						type="string",
						description="Authentication token",
						extraction={"method": "cookie", "name": "auth_token"}
					)
				]
			),
			iterator_spec=IteratorSpec(type='none'),
			steps=[]
		)
	]
	
	result = extractor.extract_entities_and_relationships(
		screens=[],
		tasks=tasks,
		actions=[],
		transitions=[]
	)
	
	assert result.success is True
	assert len(result.parameters) == 3  # 2 inputs + 1 output
	assert result.statistics['parameters'] == 3


# =============================================================================
# Phase 3.6.3: Relationship Extraction
# =============================================================================

def test_3_6_4_extract_contains_relationships():
	"""Test Phase 3.6.4 - Extract CONTAINS relationships."""
	extractor = EntityExtractor()
	
	screens = [
		ScreenDefinition(
			screen_id="test_screen",
			name="Test Screen",
			website_id="test_site",
			url_patterns=[".*/test"],
			state_signature=StateSignature(
				required_indicators=[],
				optional_indicators=[],
				exclusion_indicators=[],
				negative_indicators=[]
			),
			ui_elements=[
				UIElement(
					element_id="button_1",
					type="button",
					selector=ElementSelector(
						strategies=[
							SelectorStrategy(type="css", css=".btn1")
						]
					)
				)
			]
		)
	]
	
	result = extractor.extract_entities_and_relationships(
		screens=screens,
		tasks=[],
		actions=[],
		transitions=[]
	)
	
	assert result.success is True
	
	# Should have CONTAINS relationship: screen → ui_element
	contains_rels = [r for r in result.relationships if r.relationship_type == 'CONTAINS']
	assert len(contains_rels) == 1
	assert contains_rels[0].from_entity_id == "test_screen"
	assert contains_rels[0].to_entity_id == "button_1"


def test_3_6_5_extract_triggers_relationships():
	"""Test Phase 3.6.5 - Extract TRIGGERS relationships."""
	extractor = EntityExtractor()
	
	actions = [
		ActionDefinition(
			action_id="click_submit",
			name="Click Submit",
			website_id="test_site",
			action_type="click",
			target_selector=".submit-btn"
		)
	]
	
	transitions = [
		TransitionDefinition(
			transition_id="login_to_dashboard",
			from_screen_id="login",
			to_screen_id="dashboard",
			triggered_by=TransitionTrigger(
				action_type="click",
				element_id="submit_button"
			)
		)
	]
	
	result = extractor.extract_entities_and_relationships(
		screens=[],
		tasks=[],
		actions=actions,
		transitions=transitions
	)
	
	assert result.success is True
	
	# Should have TRIGGERS relationship: action → transition
	triggers_rels = [r for r in result.relationships if r.relationship_type == 'TRIGGERS']
	assert len(triggers_rels) == 1


# =============================================================================
# Phase 3.6.4: Validation
# =============================================================================

def test_3_6_6_validate_unique_entity_ids():
	"""Test Phase 3.6.6 - Validate unique entity IDs."""
	extractor = EntityExtractor()
	
	# Should deduplicate entities with same ID
	screens = [
		ScreenDefinition(
			screen_id="screen1",
			name="Screen 1",
			website_id="test_site",
			url_patterns=[".*/screen1"],
			state_signature=StateSignature(
				required_indicators=[],
				optional_indicators=[],
				exclusion_indicators=[],
				negative_indicators=[]
			),
			ui_elements=[
				UIElement(
					element_id="elem1",
					type="button",
					selector=ElementSelector(
						strategies=[
							SelectorStrategy(type="css", css=".elem1")
						]
					)
				),
				# Duplicate ID (should be deduplicated)
				UIElement(
					element_id="elem1",
					type="button",
					selector=ElementSelector(
						strategies=[
							SelectorStrategy(type="css", css=".elem1-dup")
						]
					)
				)
			]
		)
	]
	
	result = extractor.extract_entities_and_relationships(
		screens=screens,
		tasks=[],
		actions=[],
		transitions=[]
	)
	
	assert result.success is True
	# Should deduplicate
	assert len(result.ui_elements) == 1


def test_3_6_7_calculate_orphaned_entities():
	"""Test Phase 3.6.7 - Calculate orphaned entities."""
	extractor = EntityExtractor()
	
	# UI element with no relationships (but CONTAINS relationship will be created)
	# So let's use parameters instead which won't have relationships
	tasks = [
		TaskDefinition(
			task_id="task1",
			name="Task 1",
			website_id="test_site",
			description="Test task",
			io_spec=IOSpec(
				inputs=[
					IOInput(
						name="test_input",
						type="string",
						required=True,
						description="Test",
						source="user_input",
						volatility="low"
					)
				],
				outputs=[]
			),
			iterator_spec=IteratorSpec(type='none'),
			steps=[]
		)
	]
	
	result = extractor.extract_entities_and_relationships(
		screens=[],
		tasks=tasks,
		actions=[],
		transitions=[]
	)
	
	assert result.success is True
	# Parameter entity with no relationships
	assert result.statistics['orphaned_entities'] >= 1


# =============================================================================
# Integration Tests
# =============================================================================

def test_3_6_integration_full_extraction():
	"""Integration test - Full entity and relationship extraction."""
	extractor = EntityExtractor()
	
	screens = [
		ScreenDefinition(
			screen_id="login_screen",
			name="Login Screen",
			website_id="test_site",
			url_patterns=[".*/login"],
			state_signature=StateSignature(
				required_indicators=[],
				optional_indicators=[],
				exclusion_indicators=[],
				negative_indicators=[]
			),
			ui_elements=[
				UIElement(
					element_id="email_input",
					type="input",
					selector=ElementSelector(
						strategies=[
							SelectorStrategy(type="css", css="#email")
						]
					)
				),
				UIElement(
					element_id="submit_btn",
					type="button",
					selector=ElementSelector(
						strategies=[
							SelectorStrategy(type="css", css=".submit")
						]
					)
				)
			]
		)
	]
	
	tasks = [
		TaskDefinition(
			task_id="login_task",
			name="Login",
			website_id="test_site",
			description="Login",
			io_spec=IOSpec(
				inputs=[
					IOInput(
						name="email",
						type="string",
						required=True,
						description="Email",
						source="user_input",
						volatility="low"
					)
				],
				outputs=[]
			),
			iterator_spec=IteratorSpec(type='none'),
			steps=[]
		)
	]
	
	actions = [
		ActionDefinition(
			action_id="click_submit",
			name="Click Submit",
			website_id="test_site",
			action_type="click",
			target_selector=".submit"
		)
	]
	
	transitions = [
		TransitionDefinition(
			transition_id="login_to_dashboard",
			from_screen_id="login_screen",
			to_screen_id="dashboard_screen",
			triggered_by=TransitionTrigger(
				action_type="click",
				element_id="submit_btn"
			)
		)
	]
	
	result = extractor.extract_entities_and_relationships(
		screens=screens,
		tasks=tasks,
		actions=actions,
		transitions=transitions
	)
	
	# Verify results
	assert result.success is True
	assert result.statistics['total_entities'] >= 3
	assert result.statistics['total_relationships'] >= 2
	assert result.statistics['ui_elements'] == 2
	assert result.statistics['parameters'] == 1
	
	# Verify relationship types
	rel_types = result.statistics['relationship_types']
	assert 'CONTAINS' in rel_types
	assert 'TRIGGERS' in rel_types

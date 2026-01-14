"""
Tests for Phase 3.7: Reference Resolution.

Validates:
- Cross-reference resolution between entities
- Exact ID matching
- Fuzzy name matching
- Ambiguous reference detection
- Dangling reference detection
"""

import pytest

from navigator.knowledge.extract import ReferenceResolver
from navigator.knowledge.extract.actions import ActionDefinition
from navigator.knowledge.extract.screens import (
	ScreenDefinition, StateSignature, UIElement, ElementSelector, SelectorStrategy
)
from navigator.knowledge.extract.tasks import TaskDefinition, IOSpec, IteratorSpec, TaskStep
from navigator.knowledge.extract.transitions import TransitionDefinition, TransitionTrigger


# =============================================================================
# Phase 3.7.1: Basic Resolution
# =============================================================================

def test_3_7_1_reference_resolver_initialization():
	"""Test Phase 3.7.1 - ReferenceResolver initialization."""
	resolver = ReferenceResolver(min_confidence=0.7)
	
	assert resolver.min_confidence == 0.7


def test_3_7_2_resolve_exact_id_match():
	"""Test Phase 3.7.2 - Resolve exact ID match."""
	resolver = ReferenceResolver()
	
	screens = [
		ScreenDefinition(
			screen_id="login_screen",
			name="Login",
			website_id="test",
			url_patterns=[".*/login"],
			state_signature=StateSignature(
				required_indicators=[],
				optional_indicators=[],
				exclusion_indicators=[],
				negative_indicators=[]
			),
			ui_elements=[]
		),
		ScreenDefinition(
			screen_id="dashboard_screen",
			name="Dashboard",
			website_id="test",
			url_patterns=[".*/dashboard"],
			state_signature=StateSignature(
				required_indicators=[],
				optional_indicators=[],
				exclusion_indicators=[],
				negative_indicators=[]
			),
			ui_elements=[]
		)
	]
	
	transitions = [
		TransitionDefinition(
			transition_id="login_to_dashboard",
			from_screen_id="login_screen",  # Exact match
			to_screen_id="dashboard_screen",  # Exact match
			triggered_by=TransitionTrigger(action_type="click")
		)
	]
	
	result = resolver.resolve_references(
		screens=screens,
		tasks=[],
		actions=[],
		transitions=transitions
	)
	
	assert result.success is True
	assert result.statistics['resolution_rate'] == 1.0  # 100% resolution
	assert len(result.resolved) == 2  # Both from and to
	assert len(result.dangling) == 0


def test_3_7_3_detect_dangling_reference():
	"""Test Phase 3.7.3 - Detect dangling references."""
	resolver = ReferenceResolver()
	
	screens = [
		ScreenDefinition(
			screen_id="login_screen",
			name="Login",
			website_id="test",
			url_patterns=[".*/login"],
			state_signature=StateSignature(
				required_indicators=[],
				optional_indicators=[],
				exclusion_indicators=[],
				negative_indicators=[]
			),
			ui_elements=[]
		)
	]
	
	transitions = [
		TransitionDefinition(
			transition_id="login_to_missing",
			from_screen_id="login_screen",  # Exists
			to_screen_id="nonexistent_screen",  # MISSING!
			triggered_by=TransitionTrigger(action_type="click")
		)
	]
	
	result = resolver.resolve_references(
		screens=screens,
		tasks=[],
		actions=[],
		transitions=transitions
	)
	
	assert result.success is True
	assert len(result.resolved) == 1  # Only from_screen
	assert len(result.dangling) == 1  # to_screen is dangling
	assert result.statistics['resolution_rate'] < 1.0


# =============================================================================
# Phase 3.7.2: Task Action Resolution
# =============================================================================

def test_3_7_4_resolve_task_action_references():
	"""Test Phase 3.7.4 - Resolve task→action references."""
	resolver = ReferenceResolver()
	
	tasks = [
		TaskDefinition(
			task_id="login_task",
			name="Login",
			website_id="test",
			description="Login",
			io_spec=IOSpec(),
			iterator_spec=IteratorSpec(type='none'),
			steps=[
				TaskStep(
					step_id="step_1",
					order=1,
					type="click",  # Action type
					action={}
				)
			]
		)
	]
	
	actions = [
		ActionDefinition(
			action_id="click_submit",
			name="Click Submit",
			website_id="test",
			action_type="click"  # Matches step type
		)
	]
	
	result = resolver.resolve_references(
		screens=[],
		tasks=tasks,
		actions=actions,
		transitions=[]
	)
	
	assert result.success is True
	assert len(result.resolved) >= 1


def test_3_7_5_detect_ambiguous_action_references():
	"""Test Phase 3.7.5 - Detect ambiguous action references."""
	resolver = ReferenceResolver()
	
	tasks = [
		TaskDefinition(
			task_id="login_task",
			name="Login",
			website_id="test",
			description="Login",
			io_spec=IOSpec(),
			iterator_spec=IteratorSpec(type='none'),
			steps=[
				TaskStep(
					step_id="step_1",
					order=1,
					type="click",  # Ambiguous!
					action={}
				)
			]
		)
	]
	
	actions = [
		ActionDefinition(
			action_id="click_submit",
			name="Click Submit",
			website_id="test",
			action_type="click"
		),
		ActionDefinition(
			action_id="click_cancel",
			name="Click Cancel",
			website_id="test",
			action_type="click"  # Same type!
		)
	]
	
	result = resolver.resolve_references(
		screens=[],
		tasks=tasks,
		actions=actions,
		transitions=[]
	)
	
	assert result.success is True
	assert len(result.ambiguous) >= 1  # Ambiguous references detected


# =============================================================================
# Integration Tests
# =============================================================================

def test_3_7_integration_full_resolution():
	"""Integration test - Full reference resolution."""
	resolver = ReferenceResolver(min_confidence=0.7)
	
	screens = [
		ScreenDefinition(
			screen_id="login",
			name="Login",
			website_id="test",
			url_patterns=[".*/login"],
			state_signature=StateSignature(
				required_indicators=[],
				optional_indicators=[],
				exclusion_indicators=[],
				negative_indicators=[]
			),
			ui_elements=[
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
		),
		ScreenDefinition(
			screen_id="dashboard",
			name="Dashboard",
			website_id="test",
			url_patterns=[".*/dashboard"],
			state_signature=StateSignature(
				required_indicators=[],
				optional_indicators=[],
				exclusion_indicators=[],
				negative_indicators=[]
			),
			ui_elements=[]
		)
	]
	
	tasks = [
		TaskDefinition(
			task_id="login_task",
			name="Login",
			website_id="test",
			description="Login",
			io_spec=IOSpec(),
			iterator_spec=IteratorSpec(type='none'),
			steps=[
				TaskStep(
					step_id="step_1",
					order=1,
					type="click",
					action={}
				)
			]
		)
	]
	
	actions = [
		ActionDefinition(
			action_id="click_submit",
			name="Click Submit",
			website_id="test",
			action_type="click",
			target_selector=".submit"  # Matches UI element
		)
	]
	
	transitions = [
		TransitionDefinition(
			transition_id="login_to_dashboard",
			from_screen_id="login",  # Matches screen
			to_screen_id="dashboard",  # Matches screen
			triggered_by=TransitionTrigger(action_type="click")
		)
	]
	
	result = resolver.resolve_references(
		screens=screens,
		tasks=tasks,
		actions=actions,
		transitions=transitions
	)
	
	# Verify results
	assert result.success is True
	assert result.statistics['total_references'] > 0
	assert result.statistics['resolution_rate'] >= 0.95  # >95% resolved
	assert len(result.resolved) > 0


def test_3_7_calculate_statistics():
	"""Test statistics calculation."""
	resolver = ReferenceResolver()
	
	screens = [
		ScreenDefinition(
			screen_id="screen1",
			name="Screen 1",
			website_id="test",
			url_patterns=[".*/screen1"],
			state_signature=StateSignature(
				required_indicators=[],
				optional_indicators=[],
				exclusion_indicators=[],
				negative_indicators=[]
			),
			ui_elements=[]
		)
	]
	
	transitions = [
		TransitionDefinition(
			transition_id="trans1",
			from_screen_id="screen1",
			to_screen_id="screen1",  # Self-transition
			triggered_by=TransitionTrigger(action_type="click")
		)
	]
	
	result = resolver.resolve_references(
		screens=screens,
		tasks=[],
		actions=[],
		transitions=transitions
	)
	
	assert 'total_references' in result.statistics
	assert 'resolved_count' in result.statistics
	assert 'resolution_rate' in result.statistics
	assert 'confidence_avg' in result.statistics

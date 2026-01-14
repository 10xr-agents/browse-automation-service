"""
Tests for Phase 3.4: Transition Extraction.

Validates:
- Transition extraction from documentation
- Source/target screen identification
- Trigger action extraction
- Condition extraction
- Schema validation
"""

import pytest

from navigator.knowledge.extract import TransitionExtractor
from navigator.knowledge.extract.transitions import (
	TransitionDefinition,
	TransitionTrigger,
	validate_transition_definition,
)
from navigator.schemas import ContentChunk


# =============================================================================
# Phase 3.4.1: Basic Transition Extraction
# =============================================================================

def test_3_4_1_transition_extractor_initialization():
	"""Test Phase 3.4.1 - TransitionExtractor initialization."""
	extractor = TransitionExtractor(website_id="test_site")
	
	assert extractor.website_id == "test_site"


def test_3_4_2_extract_basic_transition():
	"""Test Phase 3.4.2 - Extract basic transition."""
	extractor = TransitionExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			After clicking Submit, the system navigates to the Dashboard.
			""",
			chunk_index=0,
			token_count=15,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_transitions(chunks)
	
	assert result.success is True
	assert result.statistics['total_transitions'] > 0


def test_3_4_3_extract_source_target_screens():
	"""Test Phase 3.4.3 - Extract source and target screens."""
	extractor = TransitionExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			From the Login Page, clicking Sign In navigates to the Dashboard.
			""",
			chunk_index=0,
			token_count=15,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_transitions(chunks)
	
	assert result.success is True
	transition = result.transitions[0]
	assert transition.from_screen_id is not None
	assert transition.to_screen_id is not None
	assert 'login' in transition.from_screen_id.lower()
	assert 'dashboard' in transition.to_screen_id.lower()


# =============================================================================
# Phase 3.4.2: Trigger Action Extraction
# =============================================================================

def test_3_4_4_extract_trigger_actions():
	"""Test Phase 3.4.4 - Extract trigger actions."""
	extractor = TransitionExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			Clicking the Save button navigates to the list page.
			Submitting the form redirects to the confirmation page.
			""",
			chunk_index=0,
			token_count=20,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_transitions(chunks)
	
	assert result.success is True
	assert result.statistics['total_transitions'] >= 2
	
	# Check trigger types
	trigger_types = result.statistics['trigger_types']
	assert 'click' in trigger_types or 'submit' in trigger_types


# =============================================================================
# Phase 3.4.3: Condition Extraction
# =============================================================================

def test_3_4_5_extract_transition_conditions():
	"""Test Phase 3.4.5 - Extract transition conditions."""
	extractor = TransitionExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			From Login to Dashboard:
			- Must be authenticated
			- Requires valid credentials
			""",
			chunk_index=0,
			token_count=20,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_transitions(chunks)
	
	assert result.success is True
	assert result.statistics['transitions_with_conditions'] > 0


# =============================================================================
# Phase 3.4.4: Schema Validation
# =============================================================================

def test_3_4_6_validate_transition_definition():
	"""Test Phase 3.4.6 - Validate transition definition."""
	transition = TransitionDefinition(
		transition_id="test_transition",
		from_screen_id="screen_a",
		to_screen_id="screen_b",
		triggered_by=TransitionTrigger(
			action_type='click',
			element_id='submit_button'
		)
	)
	
	is_valid = validate_transition_definition(transition)
	assert is_valid is True


def test_3_4_7_invalid_reliability_score_fails():
	"""Test Phase 3.4.7 - Invalid reliability score fails validation."""
	transition = TransitionDefinition(
		transition_id="test_transition",
		from_screen_id="screen_a",
		to_screen_id="screen_b",
		triggered_by=TransitionTrigger(action_type='click'),
		reliability_score=1.5  # Invalid: > 1
	)
	
	is_valid = validate_transition_definition(transition)
	assert is_valid is False


# =============================================================================
# Integration Tests
# =============================================================================

def test_3_4_integration_full_extraction():
	"""Integration test - Full transition extraction pipeline."""
	extractor = TransitionExtractor(website_id="example_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			## Login Flow
			
			From the Login Screen, clicking Sign In navigates to the Dashboard.
			The transition requires valid credentials.
			The system shows a welcome message after successful login.
			""",
			chunk_index=0,
			token_count=40,
			chunk_type="documentation"
		),
		ContentChunk(
			chunk_id="chunk_2",
			content="""
			## Navigation Flow
			
			After clicking Settings, the user goes to the Settings Page.
			Submitting the form redirects to the Confirmation Page.
			""",
			chunk_index=1,
			token_count=30,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_transitions(chunks)
	
	# Verify results
	assert result.success is True
	assert result.statistics['total_transitions'] >= 2
	assert result.statistics['transitions_with_conditions'] >= 1
	assert result.statistics['transitions_with_effects'] >= 1
	
	# Verify trigger types
	assert len(result.statistics['trigger_types']) > 0
	
	# Verify reliability scores are valid
	for transition in result.transitions:
		assert 0 <= transition.reliability_score <= 1


def test_3_4_deduplication():
	"""Test transition deduplication."""
	extractor = TransitionExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="From Login to Dashboard by clicking Sign In.",
			chunk_index=0,
			token_count=10,
			chunk_type="documentation"
		),
		ContentChunk(
			chunk_id="chunk_2",
			content="From Login to Dashboard when clicking Sign In.",
			chunk_index=1,
			token_count=10,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_transitions(chunks)
	
	# Should deduplicate transitions with same ID
	assert result.success is True
	transition_ids = [t.transition_id for t in result.transitions]
	assert len(transition_ids) == len(set(transition_ids)), "Duplicate transition IDs found"

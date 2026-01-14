"""
Tests for Phase 3.3: Action Extraction.

Validates:
- Action extraction from documentation
- Action type detection
- Selector generation
- Idempotency detection
- Precondition and postcondition extraction
- Schema validation
"""

import pytest

from navigator.knowledge.extract import ActionExtractor
from navigator.knowledge.extract.actions import (
	ActionDefinition,
	ActionPrecondition,
	ActionPostcondition,
	validate_action_definition,
)
from navigator.schemas import ContentChunk


# =============================================================================
# Phase 3.3.1: Basic Action Extraction
# =============================================================================

def test_3_3_1_action_extractor_initialization():
	"""Test Phase 3.3.1 - ActionExtractor initialization."""
	extractor = ActionExtractor(website_id="test_site")
	
	assert extractor.website_id == "test_site"


def test_3_3_2_extract_click_actions():
	"""Test Phase 3.3.2 - Extract click actions."""
	extractor = ActionExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			Click the Submit button to save your changes.
			Click the Cancel link to abort.
			""",
			chunk_index=0,
			token_count=20,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_actions(chunks)
	
	assert result.success is True
	assert result.statistics['total_actions'] >= 2
	
	# Check action types
	action_types = result.statistics['action_types']
	assert 'click' in action_types
	assert action_types['click'] >= 2


def test_3_3_3_extract_type_actions():
	"""Test Phase 3.3.3 - Extract type actions."""
	extractor = ActionExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			Type your username in the field.
			Type the password carefully.
			""",
			chunk_index=0,
			token_count=15,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_actions(chunks)
	
	assert result.success is True
	assert 'type' in result.statistics['action_types']


def test_3_3_4_extract_navigate_actions():
	"""Test Phase 3.3.4 - Extract navigate actions."""
	extractor = ActionExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			Navigate to the settings page.
			Navigate to /dashboard to see your stats.
			""",
			chunk_index=0,
			token_count=20,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_actions(chunks)
	
	assert result.success is True
	assert 'navigate' in result.statistics['action_types']


# =============================================================================
# Phase 3.3.2: Idempotency Detection
# =============================================================================

def test_3_3_5_detect_idempotent_actions():
	"""Test Phase 3.3.5 - Detect idempotent actions."""
	extractor = ActionExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			Type the username (can be repeated safely).
			Navigate to the page (safe to repeat).
			""",
			chunk_index=0,
			token_count=20,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_actions(chunks)
	
	assert result.success is True
	
	# Type and navigate are idempotent
	for action in result.actions:
		if action.action_type in ['type', 'navigate']:
			assert action.idempotent is True


def test_3_3_6_detect_non_idempotent_actions():
	"""Test Phase 3.3.6 - Detect non-idempotent actions."""
	extractor = ActionExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			Click the Submit button to create the record.
			Click the Delete button to remove the item.
			""",
			chunk_index=0,
			token_count=20,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_actions(chunks)
	
	assert result.success is True
	
	# Submit and delete are NOT idempotent
	non_idempotent_found = False
	for action in result.actions:
		if 'submit' in action.name.lower() or 'delete' in action.name.lower():
			assert action.idempotent is False
			non_idempotent_found = True
	
	assert non_idempotent_found


# =============================================================================
# Phase 3.3.3: Selector Generation
# =============================================================================

def test_3_3_7_generate_selectors():
	"""Test Phase 3.3.7 - Generate selectors from targets."""
	extractor = ActionExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			Click the Save Changes button.
			""",
			chunk_index=0,
			token_count=10,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_actions(chunks)
	
	assert result.success is True
	action = result.actions[0]
	assert action.target_selector is not None
	assert action.target_selector.startswith('.')  # CSS selector


# =============================================================================
# Phase 3.3.4: Schema Validation
# =============================================================================

def test_3_3_8_validate_action_definition():
	"""Test Phase 3.3.8 - Validate action definition."""
	action = ActionDefinition(
		action_id="click_submit",
		name="Click Submit",
		website_id="test_site",
		action_type="click",
		target_selector=".submit-button"
	)
	
	is_valid = validate_action_definition(action)
	assert is_valid is True


def test_3_3_9_invalid_action_type_fails():
	"""Test Phase 3.3.9 - Invalid action type fails validation."""
	action = ActionDefinition(
		action_id="invalid_action",
		name="Invalid Action",
		website_id="test_site",
		action_type="invalid_type",
	)
	
	is_valid = validate_action_definition(action)
	assert is_valid is False


# =============================================================================
# Integration Tests
# =============================================================================

def test_3_3_integration_full_extraction():
	"""Integration test - Full action extraction pipeline."""
	extractor = ActionExtractor(website_id="example_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="""
			## User Actions
			
			Navigate to the login page.
			Type your email in the email field.
			Type your password in the password field.
			Click the Sign In button to submit.
			Wait for the dashboard to load.
			""",
			chunk_index=0,
			token_count=50,
			chunk_type="documentation"
		),
		ContentChunk(
			chunk_id="chunk_2",
			content="""
			## Form Actions
			
			Select your country from the dropdown.
			Scroll to the bottom of the page.
			Click the Save button.
			""",
			chunk_index=1,
			token_count=30,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_actions(chunks)
	
	# Verify results
	assert result.success is True
	assert result.statistics['total_actions'] >= 6
	assert result.statistics['idempotent_actions'] >= 3
	
	# Verify action types
	action_types = result.statistics['action_types']
	assert 'navigate' in action_types
	assert 'type' in action_types
	assert 'click' in action_types
	assert 'select_option' in action_types
	assert 'scroll' in action_types
	assert 'wait' in action_types
	
	# Verify no critical errors
	critical_errors = [e for e in result.errors if 'ValidationError' in e.get('type', '')]
	assert len(critical_errors) == 0


def test_3_3_deduplication():
	"""Test action deduplication."""
	extractor = ActionExtractor(website_id="test_site")
	
	chunks = [
		ContentChunk(
			chunk_id="chunk_1",
			content="Click the Save button.",
			chunk_index=0,
			token_count=5,
			chunk_type="documentation"
		),
		ContentChunk(
			chunk_id="chunk_2",
			content="Click the Save button again.",
			chunk_index=1,
			token_count=5,
			chunk_type="documentation"
		)
	]
	
	result = extractor.extract_actions(chunks)
	
	# Should deduplicate actions with same ID
	assert result.success is True
	action_ids = [a.action_id for a in result.actions]
	assert len(action_ids) == len(set(action_ids)), "Duplicate action IDs found"

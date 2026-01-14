"""
Tests for Phase 3.5: Iterator and Logic Extraction.

Validates:
- Loop detection in text
- Step linearity validation (Agent-Killer #1)
- Iterator spec validation
- Graph acyclicity validation
"""

import pytest

from navigator.knowledge.extract import IteratorExtractor
from navigator.knowledge.extract.iterators import (
	validate_step_linearity,
	validate_iterator_spec,
)
from navigator.knowledge.extract.tasks import IteratorSpec, TaskStep


# =============================================================================
# Phase 3.5.1: Loop Detection
# =============================================================================

def test_3_5_1_iterator_extractor_initialization():
	"""Test Phase 3.5.1 - IteratorExtractor initialization."""
	extractor = IteratorExtractor()
	
	assert extractor is not None


def test_3_5_2_detect_for_each_loops():
	"""Test Phase 3.5.2 - Detect 'for each' loops."""
	extractor = IteratorExtractor()
	
	text = """
	For each email in the inbox:
	1. Open the email
	2. Mark as read
	3. Archive
	"""
	
	loops = extractor.detect_loops_in_text(text)
	
	assert len(loops) > 0
	assert any('for each' in loop.lower() for loop in loops)


def test_3_5_3_detect_repeat_until_loops():
	"""Test Phase 3.5.3 - Detect 'repeat until' loops."""
	extractor = IteratorExtractor()
	
	text = """
	Repeat until all pages are processed:
	1. Process current page
	2. Click next
	"""
	
	loops = extractor.detect_loops_in_text(text)
	
	assert len(loops) > 0
	assert any('repeat until' in loop.lower() for loop in loops)


def test_3_5_4_detect_delete_all_loops():
	"""Test Phase 3.5.4 - Detect 'delete all' loops."""
	extractor = IteratorExtractor()
	
	text = "Delete all items from the list."
	
	loops = extractor.detect_loops_in_text(text)
	
	assert len(loops) > 0
	assert any('delete all' in loop.lower() for loop in loops)


# =============================================================================
# Phase 3.5.2: Step Linearity Validation (Agent-Killer #1)
# =============================================================================

def test_3_5_5_validate_linear_steps():
	"""Test Phase 3.5.5 - Validate linear steps pass."""
	steps = [
		TaskStep(
			step_id="step_1",
			order=1,
			type="navigation",
			action={"description": "Navigate to page"}
		),
		TaskStep(
			step_id="step_2",
			order=2,
			type="form_fill",
			action={"description": "Fill form"}
		),
		TaskStep(
			step_id="step_3",
			order=3,
			type="submit",
			action={"description": "Submit"}
		),
	]
	
	result = validate_step_linearity(steps)
	
	assert result.is_linear is True
	assert len(result.backward_references) == 0
	assert len(result.validation_errors) == 0


def test_3_5_6_detect_backward_reference_in_steps():
	"""Test Phase 3.5.6 - Detect backward reference (Agent-Killer #1)."""
	steps = [
		TaskStep(
			step_id="step_1",
			order=1,
			type="action",
			action={"description": "Do action A"}
		),
		TaskStep(
			step_id="step_2",
			order=2,
			type="action",
			action={"description": "Do action B"}
		),
		TaskStep(
			step_id="step_3",
			order=3,
			type="action",
			action={"description": "Go back to step 1"}  # LOOP!
		),
	]
	
	result = validate_step_linearity(steps)
	
	assert result.is_linear is False
	assert len(result.backward_references) > 0
	assert len(result.validation_errors) > 0
	
	# Verify backward reference was detected
	backward_ref = result.backward_references[0]
	assert backward_ref['from_step'] == 3
	assert backward_ref['to_step'] == 1


def test_3_5_7_detect_repeat_step_loop():
	"""Test Phase 3.5.7 - Detect 'repeat step X' loop."""
	steps = [
		TaskStep(
			step_id="step_1",
			order=1,
			type="action",
			action={"description": "Process item"}
		),
		TaskStep(
			step_id="step_2",
			order=2,
			type="action",
			action={"description": "Repeat step 1 again"}  # LOOP!
		),
	]
	
	result = validate_step_linearity(steps)
	
	assert result.is_linear is False
	assert len(result.backward_references) > 0


# =============================================================================
# Phase 3.5.3: Iterator Spec Validation
# =============================================================================

def test_3_5_8_validate_collection_processing_iterator():
	"""Test Phase 3.5.8 - Validate collection_processing iterator."""
	iterator_spec = IteratorSpec(
		type='collection_processing',
		collection_selector='.item-row',
		item_action={'task_id': 'process_item'},
		termination_condition={
			'type': 'element_disappears',
			'selector': '.item-row'
		}
	)
	
	result = validate_iterator_spec(iterator_spec)
	
	assert result.is_valid is True
	assert result.iterator_type == 'collection_processing'


def test_3_5_9_invalid_collection_iterator_missing_selector():
	"""Test Phase 3.5.9 - Invalid collection iterator (missing selector)."""
	iterator_spec = IteratorSpec(
		type='collection_processing',
		collection_selector=None,  # Missing!
		item_action={'task_id': 'process_item'}
	)
	
	result = validate_iterator_spec(iterator_spec)
	
	assert result.is_valid is False
	assert len(result.suggestions) > 0


def test_3_5_10_validate_pagination_iterator():
	"""Test Phase 3.5.10 - Validate pagination iterator."""
	iterator_spec = IteratorSpec(
		type='pagination',
		item_action={'task_id': 'process_page'},
		termination_condition={
			'type': 'no_next_button',
			'selector': '.next-page'
		}
	)
	
	result = validate_iterator_spec(iterator_spec)
	
	assert result.is_valid is True
	assert result.iterator_type == 'pagination'


def test_3_5_11_validate_none_iterator():
	"""Test Phase 3.5.11 - Validate none iterator (no iteration)."""
	iterator_spec = IteratorSpec(type='none')
	
	result = validate_iterator_spec(iterator_spec)
	
	assert result.is_valid is True
	assert result.iterator_type == 'none'


# =============================================================================
# Phase 3.5.4: Graph Acyclicity Validation
# =============================================================================

def test_3_5_12_validate_acyclic_graph():
	"""Test Phase 3.5.12 - Validate acyclic graph."""
	extractor = IteratorExtractor()
	
	transitions = [
		('screen_a', 'screen_b'),
		('screen_b', 'screen_c'),
		('screen_c', 'screen_d'),
	]
	
	result = extractor.validate_graph_acyclicity(transitions)
	
	assert result.is_acyclic is True
	assert len(result.cycles_detected) == 0


def test_3_5_13_detect_graph_cycle():
	"""Test Phase 3.5.13 - Detect cycle in graph."""
	extractor = IteratorExtractor()
	
	transitions = [
		('screen_a', 'screen_b'),
		('screen_b', 'screen_c'),
		('screen_c', 'screen_a'),  # CYCLE!
	]
	
	result = extractor.validate_graph_acyclicity(transitions)
	
	assert result.is_acyclic is False
	assert len(result.cycles_detected) > 0
	assert len(result.validation_errors) > 0


def test_3_5_14_detect_self_loop():
	"""Test Phase 3.5.14 - Detect self-loop."""
	extractor = IteratorExtractor()
	
	transitions = [
		('screen_a', 'screen_b'),
		('screen_b', 'screen_b'),  # SELF-LOOP!
	]
	
	result = extractor.validate_graph_acyclicity(transitions)
	
	assert result.is_acyclic is False
	assert len(result.cycles_detected) > 0


# =============================================================================
# Integration Tests
# =============================================================================

def test_3_5_integration_full_validation():
	"""Integration test - Full iterator validation pipeline."""
	extractor = IteratorExtractor()
	
	# Test 1: Linear steps (valid)
	linear_steps = [
		TaskStep(step_id=f"step_{i}", order=i, type="action", action={})
		for i in range(1, 6)
	]
	
	linearity_result = extractor.validate_step_linearity(linear_steps)
	assert linearity_result.is_linear is True
	
	# Test 2: Iterator spec (valid)
	valid_iterator = IteratorSpec(
		type='collection_processing',
		collection_selector='.item',
		item_action={'task_id': 'process'},
		termination_condition={'type': 'none_left'}
	)
	
	iterator_result = extractor.validate_iterator_spec(valid_iterator)
	assert iterator_result.is_valid is True
	
	# Test 3: Graph acyclicity (valid)
	acyclic_graph = [
		('a', 'b'),
		('b', 'c'),
		('c', 'd'),
	]
	
	graph_result = extractor.validate_graph_acyclicity(acyclic_graph)
	assert graph_result.is_acyclic is True
	
	# Test 4: Detect loops in text
	loop_text = "For each item in the list, delete it and repeat."
	detected_loops = extractor.detect_loops_in_text(loop_text)
	assert len(detected_loops) > 0

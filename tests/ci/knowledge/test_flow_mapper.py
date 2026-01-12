"""
Tests for Functional Flow Mapper (Steps 2.11-2.12).

Tests cover:
- Navigation Tracking (Step 2.11)
- Click Path Mapping (Step 2.12)
"""

import pytest

from navigator.knowledge.flow_mapper import FunctionalFlowMapper


class TestNavigationTracking:
	"""Tests for navigation tracking (Step 2.11)."""

	def test_track_navigation(self):
		"""Test tracking navigation events."""
		mapper = FunctionalFlowMapper()
		
		mapper.track_navigation("https://example.com/page1")
		mapper.track_navigation("https://example.com/page2", referrer="https://example.com/page1")
		
		assert mapper.get_visit_count("https://example.com/page1") == 1
		assert mapper.get_visit_count("https://example.com/page2") == 1
		assert mapper.is_entry_point("https://example.com/page1") is True
		assert mapper.is_entry_point("https://example.com/page2") is False

	def test_track_navigation_with_referrer(self):
		"""Test tracking navigation with referrer."""
		mapper = FunctionalFlowMapper()
		
		mapper.track_navigation("https://example.com/page1")
		mapper.track_navigation("https://example.com/page2", referrer="https://example.com/page1")
		mapper.track_navigation("https://example.com/page3", referrer="https://example.com/page2")
		
		assert mapper.get_referrer("https://example.com/page2") == "https://example.com/page1"
		assert mapper.get_referrer("https://example.com/page3") == "https://example.com/page2"
		assert mapper.get_referrer("https://example.com/page1") is None

	def test_get_referrers(self):
		"""Test getting all referrers for a page."""
		mapper = FunctionalFlowMapper()
		
		# Multiple paths to same page
		mapper.track_navigation("https://example.com/page1")
		mapper.track_navigation("https://example.com/page2")
		mapper.track_navigation("https://example.com/target", referrer="https://example.com/page1")
		mapper.track_navigation("https://example.com/target", referrer="https://example.com/page2")
		
		referrers = mapper.get_referrers("https://example.com/target")
		assert len(referrers) == 2
		assert "https://example.com/page1" in referrers
		assert "https://example.com/page2" in referrers

	def test_visit_count(self):
		"""Test visit count tracking."""
		mapper = FunctionalFlowMapper()
		
		mapper.track_navigation("https://example.com/page1")
		mapper.track_navigation("https://example.com/page1")
		mapper.track_navigation("https://example.com/page1")
		
		assert mapper.get_visit_count("https://example.com/page1") == 3

	def test_entry_points(self):
		"""Test entry point tracking."""
		mapper = FunctionalFlowMapper()
		
		mapper.track_navigation("https://example.com/page1")
		mapper.track_navigation("https://example.com/page2", referrer="https://example.com/page1")
		
		entry_points = mapper.get_entry_points()
		assert "https://example.com/page1" in entry_points
		assert "https://example.com/page2" not in entry_points

	def test_is_entry_point(self):
		"""Test checking if URL is entry point."""
		mapper = FunctionalFlowMapper()
		
		mapper.track_navigation("https://example.com/page1")
		mapper.track_navigation("https://example.com/page2", referrer="https://example.com/page1")
		
		assert mapper.is_entry_point("https://example.com/page1") is True
		assert mapper.is_entry_point("https://example.com/page2") is False


class TestClickPathMapping:
	"""Tests for click path mapping (Step 2.12)."""

	def test_start_click_path(self):
		"""Test starting a click path."""
		mapper = FunctionalFlowMapper()
		
		mapper.start_click_path("https://example.com/page1")
		
		current_path = mapper.get_current_path()
		assert len(current_path) == 1
		assert current_path[0] == "https://example.com/page1"

	def test_add_to_click_path(self):
		"""Test adding URLs to click path."""
		mapper = FunctionalFlowMapper()
		
		mapper.start_click_path("https://example.com/page1")
		mapper.add_to_click_path("https://example.com/page2")
		mapper.add_to_click_path("https://example.com/page3")
		
		current_path = mapper.get_current_path()
		assert len(current_path) == 3
		assert current_path[0] == "https://example.com/page1"
		assert current_path[1] == "https://example.com/page2"
		assert current_path[2] == "https://example.com/page3"

	def test_end_click_path(self):
		"""Test ending a click path."""
		mapper = FunctionalFlowMapper()
		
		mapper.start_click_path("https://example.com/page1")
		mapper.add_to_click_path("https://example.com/page2")
		mapper.end_click_path()
		
		all_paths = mapper.get_all_paths()
		assert len(all_paths) == 1
		assert len(all_paths[0]) == 2
		
		# Current path should be cleared
		current_path = mapper.get_current_path()
		assert len(current_path) == 0

	def test_multiple_click_paths(self):
		"""Test tracking multiple click paths."""
		mapper = FunctionalFlowMapper()
		
		# First path
		mapper.start_click_path("https://example.com/page1")
		mapper.add_to_click_path("https://example.com/page2")
		mapper.end_click_path()
		
		# Second path
		mapper.start_click_path("https://example.com/page3")
		mapper.add_to_click_path("https://example.com/page4")
		mapper.end_click_path()
		
		all_paths = mapper.get_all_paths()
		assert len(all_paths) == 2

	def test_add_to_click_path_without_start(self):
		"""Test adding to click path without explicitly starting."""
		mapper = FunctionalFlowMapper()
		
		# Add without start should create new path
		mapper.add_to_click_path("https://example.com/page1")
		
		current_path = mapper.get_current_path()
		assert len(current_path) == 1
		assert current_path[0] == "https://example.com/page1"


class TestFlowAnalysis:
	"""Tests for flow analysis."""

	def test_analyze_flows(self):
		"""Test flow analysis."""
		mapper = FunctionalFlowMapper()
		
		# Create some navigation and paths
		mapper.track_navigation("https://example.com/page1")
		mapper.track_navigation("https://example.com/page2", referrer="https://example.com/page1")
		mapper.track_navigation("https://example.com/page3", referrer="https://example.com/page2")
		
		mapper.start_click_path("https://example.com/page1")
		mapper.add_to_click_path("https://example.com/page2")
		mapper.end_click_path()
		
		analysis = mapper.analyze_flows()
		
		assert "entry_points" in analysis
		assert "exit_points" in analysis
		assert "popular_paths" in analysis
		assert "popular_pages" in analysis
		assert "avg_path_length" in analysis
		assert "total_paths" in analysis
		assert "total_pages" in analysis

	def test_analyze_flows_exit_points(self):
		"""Test exit point identification."""
		mapper = FunctionalFlowMapper()
		
		# Page 1 -> Page 2, but Page 3 has no outgoing links
		mapper.track_navigation("https://example.com/page1")
		mapper.track_navigation("https://example.com/page2", referrer="https://example.com/page1")
		mapper.track_navigation("https://example.com/page3", referrer="https://example.com/page2")
		
		analysis = mapper.analyze_flows()
		exit_points = analysis["exit_points"]
		
		# Page 3 should be an exit point (no pages refer to it)
		assert "https://example.com/page3" in exit_points

	def test_analyze_flows_popular_paths(self):
		"""Test popular path identification."""
		mapper = FunctionalFlowMapper()
		
		# Create multiple identical paths
		for _ in range(3):
			mapper.start_click_path("https://example.com/page1")
			mapper.add_to_click_path("https://example.com/page2")
			mapper.end_click_path()
		
		analysis = mapper.analyze_flows()
		popular_paths = analysis["popular_paths"]
		
		# Should identify the repeated path
		assert len(popular_paths) > 0

	def test_get_flow_stats(self):
		"""Test getting flow statistics."""
		mapper = FunctionalFlowMapper()
		
		mapper.track_navigation("https://example.com/page1")
		mapper.track_navigation("https://example.com/page2", referrer="https://example.com/page1")
		
		mapper.start_click_path("https://example.com/page1")
		mapper.add_to_click_path("https://example.com/page2")
		mapper.end_click_path()
		
		stats = mapper.get_flow_stats()
		
		assert "total_pages" in stats
		assert "total_paths" in stats
		assert "entry_points" in stats
		assert "exit_points" in stats
		assert "total_visits" in stats
		
		assert stats["total_pages"] == 2
		assert stats["total_paths"] == 1
		assert stats["entry_points"] == 1
		assert stats["total_visits"] == 2

	def test_reset(self):
		"""Test resetting flow mapper."""
		mapper = FunctionalFlowMapper()
		
		mapper.track_navigation("https://example.com/page1")
		mapper.start_click_path("https://example.com/page1")
		mapper.end_click_path()
		
		mapper.reset()
		
		assert mapper.get_visit_count("https://example.com/page1") == 0
		assert len(mapper.get_all_paths()) == 0
		assert len(mapper.get_entry_points()) == 0

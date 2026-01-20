"""
Functional Flow Mapper for Knowledge Retrieval

Tracks navigation flows and click paths during website exploration.
"""

import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)


class FunctionalFlowMapper:
	"""
	Functional flow mapper for tracking navigation flows and click paths.
	
	Supports:
	- Navigation tracking (page transitions, referrers)
	- Click path mapping (user flows, common paths)
	- Flow analysis (popular paths, entry/exit points)
	"""

	def __init__(self):
		"""
		Initialize the functional flow mapper.
		"""
		# Navigation tracking
		self.page_transitions: dict[str, list[str]] = defaultdict(list)  # page_url -> [referrer_urls]
		self.referrers: dict[str, str] = {}  # page_url -> referrer_url
		self.visit_counts: dict[str, int] = defaultdict(int)  # page_url -> visit_count

		# Click path tracking
		self.click_paths: list[list[str]] = []  # List of click paths (sequences of URLs)
		self.current_path: list[str] = []  # Current click path being tracked

		# Flow analysis
		self.entry_points: set[str] = set()  # Entry URLs (no referrer)
		self.exit_points: set[str] = set()  # Exit URLs (pages that lead nowhere)

		logger.debug("FunctionalFlowMapper initialized")

	def track_navigation(self, url: str, referrer: str | None = None) -> None:
		"""
		Track a navigation event (page visit).
		
		Args:
			url: URL of the page being visited
			referrer: URL of the referring page (None if entry point)
		"""
		# Track page transition
		if referrer:
			self.page_transitions[url].append(referrer)
			self.referrers[url] = referrer
		else:
			# Entry point (no referrer)
			self.entry_points.add(url)

		# Update visit count
		self.visit_counts[url] += 1

		logger.debug(f"Tracked navigation: {url} (referrer: {referrer})")

	def get_referrer(self, url: str) -> str | None:
		"""
		Get the referrer URL for a page.
		
		Args:
			url: URL to get referrer for
		
		Returns:
			Referrer URL or None if entry point
		"""
		return self.referrers.get(url)

	def get_referrers(self, url: str) -> list[str]:
		"""
		Get all referrer URLs for a page (multiple paths can lead to same page).
		
		Args:
			url: URL to get referrers for
		
		Returns:
			List of referrer URLs
		"""
		return self.page_transitions.get(url, [])

	def get_visit_count(self, url: str) -> int:
		"""
		Get visit count for a page.
		
		Args:
			url: URL to get visit count for
		
		Returns:
			Number of times the page was visited
		"""
		return self.visit_counts.get(url, 0)

	def is_entry_point(self, url: str) -> bool:
		"""
		Check if URL is an entry point (no referrer).
		
		Args:
			url: URL to check
		
		Returns:
			True if URL is an entry point, False otherwise
		"""
		return url in self.entry_points

	def get_entry_points(self) -> list[str]:
		"""
		Get all entry points.
		
		Returns:
			List of entry point URLs
		"""
		return list(self.entry_points)

	def start_click_path(self, start_url: str) -> None:
		"""
		Start tracking a new click path.
		
		Args:
			start_url: Starting URL for the click path
		"""
		self.current_path = [start_url]
		logger.debug(f"Started click path: {start_url}")

	def add_to_click_path(self, url: str) -> None:
		"""
		Add URL to current click path.
		
		Args:
			url: URL to add to current click path
		"""
		if not self.current_path:
			# If no current path, start a new one
			self.current_path = [url]
		else:
			# Add to existing path
			self.current_path.append(url)

		logger.debug(f"Added to click path: {url} (path length: {len(self.current_path)})")

	def end_click_path(self) -> None:
		"""
		End current click path and save it.
		"""
		if self.current_path:
			self.click_paths.append(self.current_path.copy())
			logger.debug(f"Ended click path: {len(self.current_path)} steps")
			self.current_path = []

	def get_current_path(self) -> list[str]:
		"""
		Get current click path.
		
		Returns:
			Current click path as list of URLs
		"""
		return self.current_path.copy()

	def get_all_paths(self) -> list[list[str]]:
		"""
		Get all recorded click paths.
		
		Returns:
			List of all click paths
		"""
		return [path.copy() for path in self.click_paths]

	def analyze_flows(self) -> dict[str, Any]:
		"""
		Analyze navigation flows and click paths.
		
		Returns:
			Dictionary with flow analysis results:
			- entry_points: List of entry point URLs
			- exit_points: List of exit point URLs (pages with no outgoing links)
			- popular_paths: List of most common click paths
			- popular_pages: List of most visited pages
			- avg_path_length: Average click path length
		"""
		# Identify exit points (pages with no outgoing transitions)
		# Note: This is a simplified analysis - exit points are pages that don't appear as referrers
		all_referrers = set()
		for referrers in self.page_transitions.values():
			all_referrers.update(referrers)

		all_pages = set(self.visit_counts.keys())
		exit_points = all_pages - all_referrers
		self.exit_points = exit_points

		# Find popular paths (paths that appear multiple times)
		path_counts: dict[tuple[str, ...], int] = defaultdict(int)
		for path in self.click_paths:
			if len(path) >= 2:  # Only consider paths with at least 2 steps
				path_tuple = tuple(path)
				path_counts[path_tuple] += 1

		# Sort by frequency
		sorted_paths = sorted(path_counts.items(), key=lambda x: x[1], reverse=True)
		popular_paths = [list(path) for path, count in sorted_paths[:10]]  # Top 10 paths

		# Find popular pages (most visited)
		sorted_pages = sorted(self.visit_counts.items(), key=lambda x: x[1], reverse=True)
		popular_pages = [url for url, count in sorted_pages[:10]]  # Top 10 pages

		# Calculate average path length
		if self.click_paths:
			avg_path_length = sum(len(path) for path in self.click_paths) / len(self.click_paths)
		else:
			avg_path_length = 0.0

		return {
			"entry_points": list(self.entry_points),
			"exit_points": list(exit_points),
			"popular_paths": popular_paths,
			"popular_pages": popular_pages,
			"avg_path_length": avg_path_length,
			"total_paths": len(self.click_paths),
			"total_pages": len(self.visit_counts),
		}

	def get_flow_stats(self) -> dict[str, Any]:
		"""
		Get flow statistics.
		
		Returns:
			Dictionary with flow statistics
		"""
		return {
			"total_pages": len(self.visit_counts),
			"total_paths": len(self.click_paths),
			"entry_points": len(self.entry_points),
			"exit_points": len(self.exit_points),
			"total_visits": sum(self.visit_counts.values()),
		}

	def reset(self) -> None:
		"""
		Reset all tracking data.
		"""
		self.page_transitions.clear()
		self.referrers.clear()
		self.visit_counts.clear()
		self.click_paths.clear()
		self.current_path.clear()
		self.entry_points.clear()
		self.exit_points.clear()
		logger.debug("FunctionalFlowMapper reset")

"""
Knowledge Pipeline Helper Functions

Utility functions for URL filtering, error categorization, and metrics calculation.
"""

import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def categorize_error(error_msg: str, url: str) -> str:
	"""
	Categorize error type for better error handling.
	
	Args:
		error_msg: Error message
		url: URL that failed
	
	Returns:
		Error category: 'network', 'timeout', 'http_4xx', 'http_5xx', 'parsing', 'other'
	"""
	error_lower = error_msg.lower()

	# Network errors
	if any(keyword in error_lower for keyword in ['connection', 'network', 'dns', 'resolve', 'refused']):
		return 'network'

	# Timeout errors
	if any(keyword in error_lower for keyword in ['timeout', 'timed out', 'exceeded']):
		return 'timeout'

	# HTTP 4xx errors
	if any(keyword in error_lower for keyword in ['404', '403', '401', '400', 'not found', 'forbidden', 'unauthorized']):
		return 'http_4xx'

	# HTTP 5xx errors
	if any(keyword in error_lower for keyword in ['500', '502', '503', '504', 'server error', 'bad gateway', 'service unavailable']):
		return 'http_5xx'

	# Parsing errors
	if any(keyword in error_lower for keyword in ['parse', 'parsing', 'invalid', 'malformed', 'syntax']):
		return 'parsing'

	# Default to 'other'
	return 'other'


def should_explore_url(url: str, include_paths: list[str], exclude_paths: list[str]) -> bool:
	"""
	Check if URL should be explored based on include/exclude path patterns.
	
	Args:
		url: URL to check
		include_paths: List of path patterns to include
		exclude_paths: List of path patterns to exclude
	
	Returns:
		True if URL should be explored, False otherwise
	"""
	parsed = urlparse(url)
	path = parsed.path

	# If include_paths specified, URL must match at least one pattern
	if include_paths:
		matches_include = False
		for pattern in include_paths:
			if match_path_pattern(path, pattern):
				matches_include = True
				break
		if not matches_include:
			return False

	# If exclude_paths specified, URL must not match any pattern
	if exclude_paths:
		for pattern in exclude_paths:
			if match_path_pattern(path, pattern):
				return False

	return True


def match_path_pattern(path: str, pattern: str) -> bool:
	"""
	Match path against pattern (supports * wildcard).
	
	Args:
		path: URL path to match
		pattern: Pattern with * wildcard support (e.g., '/docs/*', '/api/v1/*')
	
	Returns:
		True if path matches pattern
	"""
	# Convert pattern to regex
	pattern_regex = pattern.replace('*', '.*')
	return bool(re.match(pattern_regex, path))


def calculate_estimated_time_remaining(
	pages_completed: int,
	pages_queued: int,
	processing_times: list[float],
) -> float | None:
	"""
	Calculate estimated time remaining based on average processing time.
	
	Args:
		pages_completed: Number of pages completed
		pages_queued: Number of pages remaining
		processing_times: List of page processing times in seconds
	
	Returns:
		Estimated time remaining in seconds, or None if cannot calculate
	"""
	if not processing_times or pages_queued == 0:
		return None

	# Calculate average processing time
	avg_time = sum(processing_times) / len(processing_times)

	# Estimate remaining time
	estimated = avg_time * pages_queued
	return estimated


def calculate_processing_rate(processing_times: list[float]) -> float | None:
	"""
	Calculate processing rate (pages per minute).
	
	Args:
		processing_times: List of page processing times in seconds
	
	Returns:
		Processing rate in pages per minute, or None if cannot calculate
	"""
	if not processing_times:
		return None

	# Calculate average processing time per page
	avg_time = sum(processing_times) / len(processing_times)

	if avg_time == 0:
		return None

	# Convert to pages per minute
	pages_per_minute = 60.0 / avg_time
	return pages_per_minute

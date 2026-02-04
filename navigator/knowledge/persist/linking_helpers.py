"""
Helper functions for entity linking matching logic.

Priority 2: Post-Extraction Entity Linking Phase
"""

import logging
import re
from difflib import SequenceMatcher
from typing import Any

from navigator.knowledge.extract.actions import ActionDefinition
from navigator.knowledge.extract.screens import ScreenDefinition
from navigator.knowledge.extract.tasks import TaskDefinition

logger = logging.getLogger(__name__)


def find_screens_by_url(url: str, screens: list[ScreenDefinition]) -> list[ScreenDefinition]:
	"""
	Find screens that match a URL by checking URL patterns.
	
	URL patterns can be:
	- Full regex patterns (e.g., ".*/dashboard(?:\\?.*)?(?:#.*)?$")
	- Partial patterns that should match anywhere in the URL
	
	Uses re.search() to match patterns anywhere in the URL, not just from the start.
	
	Args:
		url: URL to match
		screens: List of screens to search
	
	Returns:
		List of matching screens
	"""
	matched = []
	
	for screen in screens:
		for pattern in screen.url_patterns:
			try:
				# Use re.search() to match patterns anywhere in the URL
				# This handles patterns like ".*/dashboard" which should match
				# "https://app.spadeworks.co/dashboard"
				if re.search(pattern, url):
					matched.append(screen)
					break
			except re.error:
				logger.debug(f"Invalid regex pattern in screen {screen.screen_id}: {pattern}")
				continue
	
	return matched


def find_screens_by_name(
	screen_name: str,
	screens: list[ScreenDefinition],
	fuzzy: bool = False,
	threshold: float = 0.6
) -> list[ScreenDefinition]:
	"""
	Find screens by name matching.
	
	Args:
		screen_name: Screen name to match
		screens: List of screens to search
		fuzzy: Whether to use fuzzy matching
		threshold: Similarity threshold for fuzzy matching (0-1)
	
	Returns:
		List of matching screens
	"""
	matched = []
	screen_name_lower = screen_name.lower()

	for screen in screens:
		screen_name_match = screen.name.lower()
		
		# Exact match
		if screen_name_lower == screen_name_match:
			matched.append(screen)
			continue
		
		# Substring match
		if screen_name_lower in screen_name_match or screen_name_match in screen_name_lower:
			matched.append(screen)
			continue
		
		# Fuzzy match
		if fuzzy:
			similarity = SequenceMatcher(None, screen_name_lower, screen_name_match).ratio()
			if similarity >= threshold:
				matched.append(screen)

	return matched


def find_actions_by_name(action_name: str, actions: list[ActionDefinition]) -> list[ActionDefinition]:
	"""Find actions by name matching."""
	matched = []
	action_name_lower = action_name.lower()

	for action in actions:
		if action_name_lower in action.name.lower() or action.name.lower() in action_name_lower:
			matched.append(action)

	return matched


def find_tasks_by_name(task_name: str, tasks: list[TaskDefinition]) -> list[TaskDefinition]:
	"""Find tasks by name matching."""
	matched = []
	task_name_lower = task_name.lower()

	for task in tasks:
		if task_name_lower in task.name.lower() or task.name.lower() in task_name_lower:
			matched.append(task)

	return matched

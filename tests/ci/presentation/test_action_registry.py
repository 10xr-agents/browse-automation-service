"""
Tests for Presentation Action Registry (Steps 1.5-1.12).

Tests cover:
- Basic actions (Step 1.5)
- Navigation actions (Step 1.6)
- Extended actions (Steps 1.7-1.12)
"""

import asyncio

import pytest

from navigator.action.command import ActionResult
from navigator.presentation.action_registry import PresentationActionRegistry


class TestActionRegistryBasic:
	"""Tests for PresentationActionRegistry basic functionality (Steps 1.5-1.6)."""

	async def test_create_action_registry(self, action_registry):
		"""Test creating a PresentationActionRegistry instance."""
		assert action_registry is not None
		assert action_registry.action_dispatcher is not None

	async def test_execute_navigate_action(self, action_registry, base_url):
		"""Test executing a navigate action."""
		result = await action_registry.execute_action(
			"navigate",
			{"url": f"{base_url}/test2"}
		)
		assert isinstance(result, ActionResult)
		assert result.success is True

	async def test_execute_click_action(self, action_registry, base_url):
		"""Test executing a click action."""
		# First navigate to a page with clickable elements
		await action_registry.execute_action("navigate", {"url": f"{base_url}/test"})
		await asyncio.sleep(0.5)  # Wait for navigation
		
		# Click first interactive element
		result = await action_registry.execute_action("click", {"index": 0})
		assert isinstance(result, ActionResult)

	async def test_execute_type_action(self, action_registry, base_url):
		"""Test executing a type action."""
		# Navigate to page with input
		await action_registry.execute_action("navigate", {"url": f"{base_url}/test"})
		await asyncio.sleep(0.5)
		
		# Type into input field (assuming index 1 is input)
		result = await action_registry.execute_action("type", {"index": 1, "text": "Hello World"})
		assert isinstance(result, ActionResult)

	async def test_execute_scroll_action(self, action_registry):
		"""Test executing a scroll action."""
		result = await action_registry.execute_action("scroll", {"direction": "down", "amount": 500})
		assert isinstance(result, ActionResult)

	async def test_execute_wait_action(self, action_registry):
		"""Test executing a wait action."""
		result = await action_registry.execute_action("wait", {"seconds": 0.1})
		assert isinstance(result, ActionResult)
		assert result.success is True

	async def test_execute_go_back_action(self, action_registry, base_url):
		"""Test executing a go_back action."""
		# Navigate to two pages
		await action_registry.execute_action("navigate", {"url": f"{base_url}/test"})
		await asyncio.sleep(0.3)
		await action_registry.execute_action("navigate", {"url": f"{base_url}/test2"})
		await asyncio.sleep(0.3)
		
		# Go back
		result = await action_registry.execute_action("go_back", {})
		assert isinstance(result, ActionResult)

	async def test_execute_refresh_action(self, action_registry, base_url):
		"""Test executing a refresh action."""
		await action_registry.execute_action("navigate", {"url": f"{base_url}/test"})
		await asyncio.sleep(0.3)
		
		result = await action_registry.execute_action("refresh", {})
		assert isinstance(result, ActionResult)

	async def test_unknown_action_type(self, action_registry):
		"""Test that unknown action type returns error."""
		result = await action_registry.execute_action("unknown_action", {})
		assert isinstance(result, ActionResult)
		assert result.success is False
		assert result.error is not None
		assert "Unknown action type" in result.error


class TestActionRegistryExtended:
	"""Tests for extended action registry (Steps 1.7-1.12)."""

	async def test_execute_right_click(self, action_registry, base_url):
		"""Test executing a right_click action."""
		await action_registry.execute_action("navigate", {"url": f"{base_url}/test"})
		await asyncio.sleep(0.5)
		
		result = await action_registry.execute_action("right_click", {"index": 0})
		assert isinstance(result, ActionResult)

	async def test_execute_keyboard_shortcut(self, action_registry):
		"""Test executing a keyboard_shortcut action."""
		result = await action_registry.execute_action(
			"keyboard_shortcut",
			{"keys": ["Control", "s"]}
		)
		assert isinstance(result, ActionResult)

	async def test_execute_take_screenshot(self, action_registry, base_url, tmp_path):
		"""Test executing a take_screenshot action."""
		await action_registry.execute_action("navigate", {"url": f"{base_url}/test"})
		await asyncio.sleep(0.5)
		
		screenshot_path = str(tmp_path / "screenshot.png")
		result = await action_registry.execute_action(
			"take_screenshot",
			{"path": screenshot_path}
		)
		assert isinstance(result, ActionResult)
		if result.success:
			# Screenshot file should exist
			import os
			assert os.path.exists(screenshot_path)

	async def test_execute_zoom_actions(self, action_registry, base_url):
		"""Test executing zoom actions."""
		await action_registry.execute_action("navigate", {"url": f"{base_url}/test"})
		await asyncio.sleep(0.5)
		
		# Test zoom_in
		result1 = await action_registry.execute_action("zoom_in", {})
		assert isinstance(result1, ActionResult)
		
		# Test zoom_reset
		result2 = await action_registry.execute_action("zoom_reset", {})
		assert isinstance(result2, ActionResult)

	async def test_execute_presentation_mode(self, action_registry, base_url):
		"""Test executing presentation_mode action."""
		await action_registry.execute_action("navigate", {"url": f"{base_url}/test"})
		await asyncio.sleep(0.5)
		
		result = await action_registry.execute_action("presentation_mode", {"enabled": True})
		assert isinstance(result, ActionResult)
		
		# Disable presentation mode
		result2 = await action_registry.execute_action("presentation_mode", {"enabled": False})
		assert isinstance(result2, ActionResult)

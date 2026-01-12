"""
Presentation Action Registry

Wrapper around ActionDispatcher for presentation-specific actions.
Provides a unified interface for executing browser actions in presentation flows.
"""

import logging
from typing import Any

from navigator.action.command import (
	ActionCommand,
	ActionResult,
	ClickActionCommand,
	NavigateActionCommand,
	ScrollActionCommand,
	TypeActionCommand,
	WaitActionCommand,
	ActionType,
)
from navigator.action.dispatcher import ActionDispatcher

logger = logging.getLogger(__name__)


class PresentationActionRegistry:
	"""
	Action registry for presentation flows.
	
	Wrapper around ActionDispatcher that provides presentation-specific action execution.
	"""
	
	def __init__(self, action_dispatcher: ActionDispatcher):
		"""
		Initialize the presentation action registry.
		
		Args:
			action_dispatcher: ActionDispatcher instance to use for action execution
		"""
		self.action_dispatcher = action_dispatcher
		logger.debug("PresentationActionRegistry initialized")
	
	async def execute_action(self, action_type: str, params: dict[str, Any]) -> ActionResult:
		"""
		Execute an action.
		
		Args:
			action_type: Action type (e.g., "navigate", "click", "type", "scroll", "wait")
			params: Action parameters
		
		Returns:
			ActionResult with execution result
		"""
		# Map action type to ActionCommand
		action = self._create_action_command(action_type, params)
		if action is None:
			return ActionResult(
				success=False,
				error=f"Unknown action type: {action_type}",
			)
		
		# Execute action via dispatcher
		logger.debug(f"Executing action: {action_type} with params: {params}")
		result = await self.action_dispatcher.execute_action(action)
		logger.debug(f"Action result: success={result.success}, error={result.error}")
		return result
	
	def _create_action_command(self, action_type: str, params: dict[str, Any]) -> ActionCommand | None:
		"""
		Create an ActionCommand from action type and params.
		
		Args:
			action_type: Action type string
			params: Action parameters
		
		Returns:
			ActionCommand or None if action type is unknown
		"""
		# Basic actions (Steps 1.5-1.6)
		if action_type == "navigate":
			return NavigateActionCommand(params=params)
		elif action_type == "click":
			return ClickActionCommand(params=params)
		elif action_type == "type":
			return TypeActionCommand(params=params)
		elif action_type == "scroll":
			return ScrollActionCommand(params=params)
		elif action_type == "wait":
			return WaitActionCommand(params=params)
		elif action_type == "go_back":
			return ActionCommand(action_type=ActionType.GO_BACK, params=params)
		elif action_type == "go_forward":
			return ActionCommand(action_type=ActionType.GO_FORWARD, params=params)
		elif action_type == "refresh":
			return ActionCommand(action_type=ActionType.REFRESH, params=params)
		elif action_type == "reload":
			# Reload is typically the same as refresh
			return ActionCommand(action_type=ActionType.REFRESH, params=params)
		
		# Step 1.7: Interaction Actions
		elif action_type in ("right_click", "double_click", "hover", "drag_drop"):
			return ActionCommand(action_type=ActionType.CLICK, params=params)  # Use CLICK as base type
		
		# Step 1.8: Text Input Actions
		elif action_type in ("type_slowly", "clear", "select_all", "copy", "paste", "cut"):
			if action_type == "type_slowly" or action_type == "clear":
				return TypeActionCommand(params=params)
			else:
				return ActionCommand(action_type=ActionType.SEND_KEYS, params=params)
		
		# Step 1.9: Form Actions
		elif action_type in ("fill_form", "select_dropdown", "select_multiple", "upload_file", "submit_form", "reset_form"):
			return ActionCommand(action_type=ActionType.CLICK, params=params)  # Use CLICK as base type, handlers will distinguish
		
		# Step 1.10: Media Actions (require JavaScript)
		elif action_type in ("play_video", "pause_video", "seek_video", "adjust_volume", "toggle_fullscreen", "toggle_mute"):
			return ActionCommand(action_type=ActionType.SEND_KEYS, params=params)  # Use SEND_KEYS as base type
		
		# Step 1.11: Advanced Actions
		elif action_type in ("keyboard_shortcut", "multi_select", "highlight_element", "zoom_in", "zoom_out", "zoom_reset", "take_screenshot", "download_file"):
			if action_type == "keyboard_shortcut":
				return ActionCommand(action_type=ActionType.SEND_KEYS, params=params)
			else:
				return ActionCommand(action_type=ActionType.CLICK, params=params)  # Use CLICK as base type
		
		# Step 1.12: Presentation-Specific Actions (require JavaScript)
		elif action_type in ("presentation_mode", "show_pointer", "animate_scroll", "highlight_region", "draw_on_page", "focus_element"):
			return ActionCommand(action_type=ActionType.SEND_KEYS, params=params)  # Use SEND_KEYS as base type
		
		else:
			return None

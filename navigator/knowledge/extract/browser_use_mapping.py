"""
Browser-Use Action Mapping (Phase 2).

Translates knowledge ActionDefinition to browser-use compatible actions.
"""

import logging
from typing import Any

from pydantic import BaseModel, Field

from navigator.knowledge.extract.actions import ActionDefinition

logger = logging.getLogger(__name__)


# =============================================================================
# Browser-Use Action Schema
# =============================================================================

class BrowserUseAction(BaseModel):
	"""
	Action directly mappable to browser-use tools.
	
	This schema represents an action that can be executed by browser-use agents
	using their standard tool interface (navigate, click, input, etc.).
	"""
	tool_name: str = Field(..., description="Browser-use tool name (navigate, click, input, etc.)")
	parameters: dict[str, Any] = Field(..., description="Tool parameters")
	description: str = Field(..., description="Human-readable description")
	
	# Optional metadata
	confidence: float | None = Field(
		default=None,
		ge=0.0,
		le=1.0,
		description="Confidence score for inferred actions (0-1)"
	)
	screen_id: str | None = Field(
		default=None,
		description="Screen ID where this action should be performed"
	)


# =============================================================================
# Action Translator
# =============================================================================

class ActionTranslator:
	"""
	Translates knowledge ActionDefinition to browser-use actions.
	
	Maps knowledge action types to browser-use tool names and converts
	parameters to the format expected by browser-use tools.
	"""
	
	# Mapping from knowledge action types to browser-use tool names
	ACTION_TYPE_TO_TOOL: dict[str, str] = {
		# Navigation actions
		"navigate": "navigate",
		"go_back": "go_back",
		"go_forward": "go_forward",
		"refresh": "refresh",
		
		# Interaction actions
		"click": "click",
		"right_click": "right_click",
		"double_click": "double_click",
		"hover": "hover",
		"drag_drop": "drag_drop",
		
		# Input actions
		"type": "input",  # browser-use uses 'input' not 'type'
		"type_slowly": "type_slowly",
		"send_keys": "send_keys",
		"select_all": "select_all",
		"copy": "copy",
		"paste": "paste",
		"cut": "cut",
		"clear": "clear",
		
		# Scrolling
		"scroll": "scroll",
		
		# Form actions
		"upload_file": "upload_file",
		"select_dropdown": "select_dropdown",
		"fill_form": "fill_form",
		"submit_form": "submit_form",
		"reset_form": "reset_form",
		
		# Media actions
		"play_video": "play_video",
		"pause_video": "pause_video",
		"seek_video": "seek_video",
		"adjust_volume": "adjust_volume",
		"toggle_mute": "toggle_mute",
		
		# Advanced actions
		"screenshot": "screenshot",
		"wait": "wait",
		"evaluate": "evaluate",  # JavaScript execution
		"extract": "extract",  # Content extraction
		
		# Tab management
		"switch": "switch",
		"close": "close",
	}
	
	def translate_action(
		self,
		action: ActionDefinition,
		screen_id: str | None = None
	) -> BrowserUseAction:
		"""
		Convert ActionDefinition to BrowserUseAction.
		
		Args:
			action: Knowledge action definition
			screen_id: Optional screen ID where action occurs
		
		Returns:
			BrowserUseAction ready for browser-use execution
		"""
		# Get browser-use tool name
		tool_name = self.ACTION_TYPE_TO_TOOL.get(
			action.action_type,
			action.action_type  # Fallback to original if not in mapping
		)
		
		# Convert parameters based on action type
		parameters = self._convert_parameters(action)
		
		# Generate description
		description = action.name or f"{action.action_type} on {action.target_selector or 'element'}"
		
		return BrowserUseAction(
			tool_name=tool_name,
			parameters=parameters,
			description=description,
			screen_id=screen_id or (action.screen_ids[0] if action.screen_ids else None)
		)
	
	def _convert_parameters(self, action: ActionDefinition) -> dict[str, Any]:
		"""
		Convert action parameters to browser-use tool parameters.
		
		Args:
			action: Action definition
		
		Returns:
			Dictionary of parameters for browser-use tool
		"""
		params: dict[str, Any] = {}
		
		# Handle action-specific parameter conversion
		if action.action_type == "navigate":
			# Navigate action: target_selector should be URL
			if action.target_selector:
				params["url"] = action.target_selector
			elif "url" in action.parameters:
				params["url"] = action.parameters["url"]
			if "new_tab" in action.parameters:
				params["new_tab"] = action.parameters["new_tab"]
		
		elif action.action_type == "click":
			# Click action: target_selector should be element index or selector
			if action.target_selector:
				# Try to parse as integer (element index)
				try:
					params["index"] = int(action.target_selector)
				except ValueError:
					# If not integer, use as selector (browser-use will need to resolve)
					params["selector"] = action.target_selector
			if "button" in action.parameters:
				params["button"] = action.parameters["button"]  # left, right, middle
			if "new_tab" in action.parameters:
				params["new_tab"] = action.parameters["new_tab"]
		
		elif action.action_type in ("type", "input"):
			# Type/input action: target_selector is element, parameters contain text
			if action.target_selector:
				try:
					params["index"] = int(action.target_selector)
				except ValueError:
					params["selector"] = action.target_selector
			if "text" in action.parameters:
				params["text"] = action.parameters["text"]
			elif "value" in action.parameters:
				params["text"] = action.parameters["value"]
		
		elif action.action_type == "scroll":
			# Scroll action
			if "direction" in action.parameters:
				params["direction"] = action.parameters["direction"]  # up, down, left, right
			if "amount" in action.parameters:
				params["amount"] = action.parameters["amount"]
		
		elif action.action_type == "wait":
			# Wait action
			if "seconds" in action.parameters:
				params["seconds"] = action.parameters["seconds"]
			elif "duration" in action.parameters:
				params["seconds"] = action.parameters["duration"]
		
		elif action.action_type == "send_keys":
			# Send keys action
			if "keys" in action.parameters:
				params["keys"] = action.parameters["keys"]
			if action.target_selector:
				try:
					params["index"] = int(action.target_selector)
				except ValueError:
					params["selector"] = action.target_selector
		
		elif action.action_type == "upload_file":
			# Upload file action
			if "file_path" in action.parameters:
				params["file_path"] = action.parameters["file_path"]
			if action.target_selector:
				try:
					params["index"] = int(action.target_selector)
				except ValueError:
					params["selector"] = action.target_selector
		
		elif action.action_type == "select_dropdown":
			# Select dropdown action
			if action.target_selector:
				try:
					params["index"] = int(action.target_selector)
				except ValueError:
					params["selector"] = action.target_selector
			if "value" in action.parameters:
				params["value"] = action.parameters["value"]
			elif "text" in action.parameters:
				params["text"] = action.parameters["text"]
			elif "option_index" in action.parameters:
				params["option_index"] = action.parameters["option_index"]
		
		elif action.action_type == "fill_form":
			# Fill form action: expects array of {index, value} pairs
			if "fields" in action.parameters:
				params["fields"] = action.parameters["fields"]
		
		elif action.action_type == "drag_drop":
			# Drag and drop action
			if "start_index" in action.parameters:
				params["start_index"] = action.parameters["start_index"]
			elif action.target_selector:
				try:
					params["start_index"] = int(action.target_selector)
				except ValueError:
					params["start_selector"] = action.target_selector
			if "end_index" in action.parameters:
				params["end_index"] = action.parameters["end_index"]
			if "end_selector" in action.parameters:
				params["end_selector"] = action.parameters["end_selector"]
		
		elif action.action_type == "evaluate":
			# JavaScript evaluation
			if "code" in action.parameters:
				params["code"] = action.parameters["code"]
			elif "javascript" in action.parameters:
				params["code"] = action.parameters["javascript"]
		
		elif action.action_type == "extract":
			# Content extraction
			if "query" in action.parameters:
				params["query"] = action.parameters["query"]
			elif "prompt" in action.parameters:
				params["query"] = action.parameters["prompt"]
		
		else:
			# For other action types, pass through parameters as-is
			params.update(action.parameters)
			if action.target_selector:
				params["target"] = action.target_selector
		
		return params
	
	def translate_action_list(
		self,
		actions: list[ActionDefinition],
		screen_id: str | None = None
	) -> list[BrowserUseAction]:
		"""
		Translate a list of actions to browser-use actions.
		
		Args:
			actions: List of action definitions
			screen_id: Optional screen ID for all actions
		
		Returns:
			List of BrowserUseAction objects
		"""
		return [
			self.translate_action(action, screen_id=screen_id)
			for action in actions
		]


# =============================================================================
# Convenience Functions
# =============================================================================

def translate_to_browser_use(
	action: ActionDefinition,
	screen_id: str | None = None
) -> BrowserUseAction:
	"""
	Convenience function to translate a single action.
	
	Args:
		action: Action definition to translate
		screen_id: Optional screen ID
	
	Returns:
		BrowserUseAction
	"""
	translator = ActionTranslator()
	return translator.translate_action(action, screen_id=screen_id)


def translate_actions_to_browser_use(
	actions: list[ActionDefinition],
	screen_id: str | None = None
) -> list[BrowserUseAction]:
	"""
	Convenience function to translate a list of actions.
	
	Args:
		actions: List of action definitions
		screen_id: Optional screen ID
	
	Returns:
		List of BrowserUseAction objects
	"""
	translator = ActionTranslator()
	return translator.translate_action_list(actions, screen_id=screen_id)

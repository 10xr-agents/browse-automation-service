"""
ActionCommand Primitives for MVP

This module defines the ActionCommand primitives used for communication
between Voice Agent Service and Browser Automation Service.

These primitives wrap the existing event-driven system for MVP purposes.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ActionType(str, Enum):
	"""Types of actions that can be executed."""

	CLICK = 'click'
	TYPE = 'type'
	NAVIGATE = 'navigate'
	SCROLL = 'scroll'
	WAIT = 'wait'
	GO_BACK = 'go_back'
	GO_FORWARD = 'go_forward'
	REFRESH = 'refresh'
	UPLOAD_FILE = 'upload_file'
	SEND_KEYS = 'send_keys'


class ActionCommand(BaseModel):
	"""Base action command primitive.

	This is the unified interface for all browser actions.
	"""

	action_type: ActionType = Field(..., description='Type of action to execute')
	params: dict[str, Any] = Field(default_factory=dict, description='Action-specific parameters')

	class Config:
		use_enum_values = True


class ClickActionCommand(ActionCommand):
	"""Click action command."""

	action_type: ActionType = ActionType.CLICK
	params: dict[str, Any] = Field(
		default_factory=lambda: {},
		description='Click parameters: index (int) or coordinate_x/coordinate_y (int)',
	)


class TypeActionCommand(ActionCommand):
	"""Type action command."""

	action_type: ActionType = ActionType.TYPE
	params: dict[str, Any] = Field(
		default_factory=lambda: {},
		description='Type parameters: text (str), index (int, optional)',
	)


class NavigateActionCommand(ActionCommand):
	"""Navigate action command."""

	action_type: ActionType = ActionType.NAVIGATE
	params: dict[str, Any] = Field(
		default_factory=lambda: {},
		description='Navigate parameters: url (str), new_tab (bool, optional)',
	)


class ScrollActionCommand(ActionCommand):
	"""Scroll action command."""

	action_type: ActionType = ActionType.SCROLL
	params: dict[str, Any] = Field(
		default_factory=lambda: {},
		description='Scroll parameters: direction (str: "up"/"down"/"left"/"right"), amount (int, optional)',
	)


class WaitActionCommand(ActionCommand):
	"""Wait action command."""

	action_type: ActionType = ActionType.WAIT
	params: dict[str, Any] = Field(
		default_factory=lambda: {},
		description='Wait parameters: seconds (float)',
	)


class ActionResult(BaseModel):
	"""Result of executing an action command."""

	success: bool = Field(..., description='Whether the action succeeded')
	error: str | None = Field(default=None, description='Error message if action failed')
	data: dict[str, Any] = Field(default_factory=dict, description='Action-specific result data')
	timestamp: float = Field(default_factory=lambda: __import__('time').time(), description='Timestamp of result')


class BrowserContext(BaseModel):
	"""Browser context primitive representing current browser state."""

	url: str = Field(..., description='Current page URL')
	title: str = Field(..., description='Current page title')
	ready_state: str = Field(default='unknown', description='Page ready state (loading, interactive, complete)')
	scroll_x: int = Field(default=0, description='Current horizontal scroll position in pixels')
	scroll_y: int = Field(default=0, description='Current vertical scroll position in pixels')
	viewport_width: int = Field(default=1920, description='Viewport width in pixels')
	viewport_height: int = Field(default=1080, description='Viewport height in pixels')
	cursor_x: int | None = Field(default=None, description='Current cursor X position relative to viewport')
	cursor_y: int | None = Field(default=None, description='Current cursor Y position relative to viewport')
	timestamp: float = Field(default_factory=lambda: __import__('time').time(), description='Timestamp of context')


class ScreenContent(BaseModel):
	"""Screen content description for agent communication."""

	url: str = Field(..., description='Current page URL')
	title: str = Field(..., description='Current page title')
	dom_summary: str = Field(..., description='DOM tree summary (LLM-readable representation)')
	visible_elements_count: int = Field(default=0, description='Number of visible interactive elements')
	scroll_x: int = Field(default=0, description='Current horizontal scroll position')
	scroll_y: int = Field(default=0, description='Current vertical scroll position')
	viewport_width: int = Field(default=1920, description='Viewport width')
	viewport_height: int = Field(default=1080, description='Viewport height')
	cursor_x: int | None = Field(default=None, description='Current cursor X position')
	cursor_y: int | None = Field(default=None, description='Current cursor Y position')
	timestamp: float = Field(default_factory=lambda: __import__('time').time(), description='Timestamp')


class BrowserStateChange(BaseModel):
	"""Browser state change notification."""

	change_type: str = Field(..., description='Type of change (url, title, dom, loading)')
	old_value: str | None = Field(default=None, description='Previous value')
	new_value: str = Field(..., description='New value')
	timestamp: float = Field(default_factory=lambda: __import__('time').time(), description='Timestamp of change')

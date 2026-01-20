"""
Navigator - Browser Automation Service

This package contains the Navigator implementation of the Browser Automation Service.
"""

from navigator.action.command import (
	ActionCommand,
	ActionResult,
	ActionType,
	BrowserContext,
	BrowserStateChange,
	ClickActionCommand,
	NavigateActionCommand,
	ScrollActionCommand,
	TypeActionCommand,
	WaitActionCommand,
)
from navigator.action.dispatcher import ActionDispatcher

__all__ = [
	'ActionCommand',
	'ActionType',
	'ActionResult',
	'BrowserContext',
	'BrowserStateChange',
	'ClickActionCommand',
	'NavigateActionCommand',
	'ScrollActionCommand',
	'TypeActionCommand',
	'WaitActionCommand',
	'ActionDispatcher',
]

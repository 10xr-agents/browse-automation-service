"""
Presentation Flow Components

This module provides presentation flow management and action registry
for browser automation in presentation/agent flows.
"""

from navigator.presentation.action_queue import ActionQueue
from navigator.presentation.action_registry import PresentationActionRegistry
from navigator.presentation.flow_manager import (
	PresentationFlowManager,
	PresentationSession,
	SessionState,
)
from navigator.presentation.session_store import SessionStore

__all__ = [
	"PresentationFlowManager",
	"PresentationSession",
	"SessionState",
	"PresentationActionRegistry",
	"ActionQueue",
	"SessionStore",
]

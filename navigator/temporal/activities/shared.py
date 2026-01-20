"""
Shared dependencies and utilities for extraction activities.

This module provides the global idempotency manager and initialization function
that all activities depend on.
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
	pass

logger = logging.getLogger(__name__)

# Global dependencies (initialized by worker)
_idempotency_manager: Any = None


def init_activity_dependencies(idempotency_manager: Any):
	"""
	Initialize dependencies for V2 activities.
	
	Args:
		idempotency_manager: Idempotency manager for activity deduplication
	"""
	global _idempotency_manager
	_idempotency_manager = idempotency_manager
	logger.info("✅ V2 activity dependencies initialized")


def get_idempotency_manager() -> Any:
	"""Get the global idempotency manager."""
	return _idempotency_manager

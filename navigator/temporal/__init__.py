"""
Temporal workflow integration for Browser Automation Service.

Provides Temporal-based durable workflows for:
- Knowledge extraction (long-running website exploration)
- Session management (future)
- Background tasks (future)
"""

from navigator.temporal.config import TemporalConfig, get_temporal_client

__all__ = [
	'TemporalConfig',
	'get_temporal_client',
]

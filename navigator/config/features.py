"""
Feature Flags Configuration

Centralized feature flag management for optional features.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class FeatureFlags:
	"""
	Feature flag manager for optional functionality.
	
	Features can be enabled/disabled via environment variables:
	- FEATURE_BROWSER_VERIFICATION=true
	- FEATURE_KNOWLEDGE_ENRICHMENT=true
	- etc.
	"""
	
	def __init__(self):
		"""Initialize feature flags from environment variables."""
		# Phase 7: Browser-Based Verification & Enrichment
		self.browser_verification_enabled = self._get_flag('FEATURE_BROWSER_VERIFICATION', default=False)
		self.knowledge_enrichment_enabled = self._get_flag('FEATURE_KNOWLEDGE_ENRICHMENT', default=False)
		
		# Log enabled features
		self._log_enabled_features()
	
	def _get_flag(self, env_var: str, default: bool = False) -> bool:
		"""
		Get feature flag from environment variable.
		
		Args:
			env_var: Environment variable name
			default: Default value if not set
		
		Returns:
			True if enabled, False otherwise
		"""
		value = os.getenv(env_var, str(default)).lower()
		return value in ('true', '1', 'yes', 'on', 'enabled')
	
	def _log_enabled_features(self):
		"""Log enabled features for debugging."""
		enabled_features = []
		
		if self.browser_verification_enabled:
			enabled_features.append('BrowserVerification')
		if self.knowledge_enrichment_enabled:
			enabled_features.append('KnowledgeEnrichment')
		
		if enabled_features:
			logger.info(f"✅ Enabled features: {', '.join(enabled_features)}")
		else:
			logger.info("ℹ️  No optional features enabled (all features disabled by default)")
	
	def is_verification_enabled(self) -> bool:
		"""Check if browser verification is enabled."""
		return self.browser_verification_enabled
	
	def is_enrichment_enabled(self) -> bool:
		"""Check if knowledge enrichment is enabled."""
		return self.knowledge_enrichment_enabled
	
	def to_dict(self) -> dict[str, Any]:
		"""Export feature flags as dictionary."""
		return {
			'browser_verification': self.browser_verification_enabled,
			'knowledge_enrichment': self.knowledge_enrichment_enabled,
		}


# Global feature flags instance
_feature_flags: FeatureFlags | None = None


def get_feature_flags() -> FeatureFlags:
	"""
	Get global feature flags instance.
	
	Returns:
		FeatureFlags instance
	"""
	global _feature_flags
	if _feature_flags is None:
		_feature_flags = FeatureFlags()
	return _feature_flags


def reload_feature_flags():
	"""Reload feature flags from environment (useful for testing)."""
	global _feature_flags
	_feature_flags = FeatureFlags()

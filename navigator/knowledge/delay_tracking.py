"""
Delay Intelligence Tracking System

Captures and stores delay information from UI transitions to provide intelligence
about website performance characteristics for AI agents.
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =============================================================================
# Delay Intelligence Schemas
# =============================================================================

class DelayMetrics(BaseModel):
	"""Delay metrics for a specific action/transition/screen."""
	
	# Timing information
	average_delay_ms: float = Field(..., description="Average delay in milliseconds", ge=0.0)
	min_delay_ms: float = Field(..., description="Minimum delay observed", ge=0.0)
	max_delay_ms: float = Field(..., description="Maximum delay observed", ge=0.0)
	median_delay_ms: float | None = Field(None, description="Median delay", ge=0.0)
	
	# Sample information
	sample_count: int = Field(..., description="Number of samples collected", ge=1)
	last_observed_ms: float = Field(..., description="Most recent delay observed", ge=0.0)
	
	# Context information
	url_changed: bool = Field(default=False, description="Whether URL changed during transition")
	dom_stable: bool = Field(default=False, description="Whether DOM stabilized")
	network_idle: bool = Field(default=False, description="Whether network was idle")
	
	# Metadata
	context: dict[str, Any] = Field(default_factory=dict, description="Additional context (screen_id, action_type, etc.)")


class DelayIntelligence(BaseModel):
	"""Complete delay intelligence for an entity (action, transition, screen)."""
	
	entity_id: str = Field(..., description="Entity identifier (action_id, transition_id, screen_id)")
	entity_type: str = Field(..., description="Entity type: 'action' | 'transition' | 'screen'")
	
	# Delay metrics
	metrics: DelayMetrics = Field(..., description="Delay metrics")
	
	# Performance characteristics
	is_slow: bool = Field(default=False, description="Whether this entity is considered slow (>3s average)")
	is_fast: bool = Field(default=False, description="Whether this entity is considered fast (<1s average)")
	variability: str = Field(default="medium", description="Delay variability: 'low' | 'medium' | 'high'")
	
	# Recommendations
	recommended_wait_time_ms: float = Field(..., description="Recommended wait time in milliseconds")
	confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence in delay estimate (0-1)")
	
	# Metadata
	metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


# =============================================================================
# Delay Tracker
# =============================================================================

@dataclass
class DelaySample:
	"""Single delay sample."""
	delay_ms: float
	url_changed: bool
	dom_stable: bool
	network_idle: bool
	timestamp: float = field(default_factory=time.time)
	context: dict[str, Any] = field(default_factory=dict)


class DelayTracker:
	"""
	Tracks delay information for actions, transitions, and screens.
	
	Collects delay samples and provides intelligence about website performance.
	"""
	
	def __init__(self):
		"""Initialize the delay tracker."""
		# Store samples by entity (action_id, transition_id, screen_id)
		self._samples: dict[str, list[DelaySample]] = defaultdict(list)
		# Store entity types
		self._entity_types: dict[str, str] = {}
		# Store entity metadata
		self._entity_metadata: dict[str, dict[str, Any]] = defaultdict(dict)
	
	def record_delay(
		self,
		entity_id: str,
		entity_type: str,
		delay_ms: float,
		url_changed: bool = False,
		dom_stable: bool = False,
		network_idle: bool = False,
		context: dict[str, Any] | None = None,
	) -> None:
		"""
		Record a delay sample for an entity.
		
		Args:
			entity_id: Entity identifier (action_id, transition_id, screen_id)
			entity_type: Entity type ('action', 'transition', 'screen')
			delay_ms: Delay in milliseconds
			url_changed: Whether URL changed during transition
			dom_stable: Whether DOM stabilized
			network_idle: Whether network was idle
			context: Additional context (screen_id, action_type, etc.)
		"""
		sample = DelaySample(
			delay_ms=delay_ms,
			url_changed=url_changed,
			dom_stable=dom_stable,
			network_idle=network_idle,
			context=context or {},
		)
		
		self._samples[entity_id].append(sample)
		self._entity_types[entity_id] = entity_type
		
		# Update metadata if provided
		if context:
			self._entity_metadata[entity_id].update(context)
		
		logger.debug(
			f"📊 Recorded delay for {entity_type} {entity_id}: "
			f"{delay_ms:.0f}ms (samples: {len(self._samples[entity_id])})"
		)
	
	def get_intelligence(
		self,
		entity_id: str,
		min_samples: int = 1,
	) -> DelayIntelligence | None:
		"""
		Get delay intelligence for an entity.
		
		Args:
			entity_id: Entity identifier
			min_samples: Minimum number of samples required (default: 1)
		
		Returns:
			DelayIntelligence if enough samples, None otherwise
		"""
		samples = self._samples.get(entity_id, [])
		if len(samples) < min_samples:
			return None
		
		entity_type = self._entity_types.get(entity_id, "unknown")
		
		# Calculate statistics
		delays = [s.delay_ms for s in samples]
		delays.sort()
		
		avg_delay = sum(delays) / len(delays)
		min_delay = delays[0]
		max_delay = delays[-1]
		median_delay = delays[len(delays) // 2] if delays else None
		
		# Calculate variability
		if len(delays) > 1:
			variance = sum((d - avg_delay) ** 2 for d in delays) / len(delays)
			std_dev = variance ** 0.5
			coefficient_of_variation = std_dev / avg_delay if avg_delay > 0 else 0
			
			if coefficient_of_variation < 0.2:
				variability = "low"
			elif coefficient_of_variation < 0.5:
				variability = "medium"
			else:
				variability = "high"
		else:
			variability = "medium"
		
		# Aggregate context flags
		url_changed_ratio = sum(1 for s in samples if s.url_changed) / len(samples)
		dom_stable_ratio = sum(1 for s in samples if s.dom_stable) / len(samples)
		network_idle_ratio = sum(1 for s in samples if s.network_idle) / len(samples)
		
		# Create metrics
		metrics = DelayMetrics(
			average_delay_ms=avg_delay,
			min_delay_ms=min_delay,
			max_delay_ms=max_delay,
			median_delay_ms=median_delay,
			sample_count=len(samples),
			last_observed_ms=delays[-1],
			url_changed=url_changed_ratio > 0.5,
			dom_stable=dom_stable_ratio > 0.5,
			network_idle=network_idle_ratio > 0.5,
			context=self._entity_metadata.get(entity_id, {}),
		)
		
		# Determine performance characteristics
		is_slow = avg_delay > 3000  # >3 seconds
		is_fast = avg_delay < 1000  # <1 second
		
		# Calculate recommended wait time (average + 1 standard deviation for safety)
		if len(delays) > 1:
			std_dev = (sum((d - avg_delay) ** 2 for d in delays) / len(delays)) ** 0.5
			recommended_wait = avg_delay + std_dev
		else:
			recommended_wait = avg_delay * 1.5  # 50% buffer for single sample
		
		# Calculate confidence (more samples = higher confidence)
		confidence = min(1.0, 0.5 + (len(samples) - 1) * 0.1)  # 0.5 base, +0.1 per additional sample
		
		return DelayIntelligence(
			entity_id=entity_id,
			entity_type=entity_type,
			metrics=metrics,
			is_slow=is_slow,
			is_fast=is_fast,
			variability=variability,
			recommended_wait_time_ms=recommended_wait,
			confidence=confidence,
			metadata=self._entity_metadata.get(entity_id, {}),
		)
	
	def get_all_intelligence(self, min_samples: int = 1) -> dict[str, DelayIntelligence]:
		"""Get delay intelligence for all entities with enough samples."""
		intelligence = {}
		for entity_id in self._samples.keys():
			intel = self.get_intelligence(entity_id, min_samples=min_samples)
			if intel:
				intelligence[entity_id] = intel
		return intelligence
	
	def clear(self) -> None:
		"""Clear all tracked samples."""
		self._samples.clear()
		self._entity_types.clear()
		self._entity_metadata.clear()
	
	def record_transition_delay(
		self,
		from_url: str,
		to_url: str,
		delay_ms: float,
		url_changed: bool = True,
		dom_stable: bool = False,
		network_idle: bool = False,
		context: dict[str, Any] | None = None,
	) -> None:
		"""
		Record delay for a screen transition (by URL pattern).
		
		Creates a transition_id from URL patterns that can later be matched to
		actual TransitionDefinition objects during the linking phase.
		
		Args:
			from_url: Source URL
			to_url: Target URL
			delay_ms: Delay in milliseconds
			url_changed: Whether URL changed (default: True for transitions)
			dom_stable: Whether DOM stabilized
			network_idle: Whether network was idle
			context: Additional context (action_id, screen_id, etc.)
		"""
		# Create transition_id from URL patterns
		# This will be matched to actual transitions during linking phase
		import hashlib
		transition_key = f"{from_url}->{to_url}"
		transition_id = f"transition_{hashlib.md5(transition_key.encode()).hexdigest()[:12]}"
		
		transition_context = {
			'from_url': from_url,
			'to_url': to_url,
			'transition_key': transition_key,
			**(context or {}),
		}
		
		self.record_delay(
			entity_id=transition_id,
			entity_type='transition',
			delay_ms=delay_ms,
			url_changed=url_changed,
			dom_stable=dom_stable,
			network_idle=network_idle,
			context=transition_context,
		)


# Global delay tracker instance
_delay_tracker: DelayTracker | None = None


def get_delay_tracker() -> DelayTracker:
	"""Get the global delay tracker instance."""
	global _delay_tracker
	if _delay_tracker is None:
		_delay_tracker = DelayTracker()
	return _delay_tracker

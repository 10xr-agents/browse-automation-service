"""
Delay Intelligence Synchronization

Syncs captured delay intelligence from DelayTracker into knowledge entities
(ActionDefinition, TransitionDefinition) for storage and retrieval.
"""

import logging
from typing import Any

from navigator.knowledge.delay_tracking import DelayIntelligence, get_delay_tracker
from navigator.knowledge.extract.actions import ActionDefinition
from navigator.knowledge.extract.transitions import TransitionDefinition
from navigator.knowledge.persist.documents.actions import get_action
from navigator.knowledge.persist.documents.transitions import get_transition

logger = logging.getLogger(__name__)


def delay_intelligence_to_dict(intelligence: DelayIntelligence) -> dict[str, Any]:
	"""
	Convert DelayIntelligence to dictionary for storage in metadata.
	
	Args:
		intelligence: DelayIntelligence object
	
	Returns:
		Dictionary representation suitable for storage
	"""
	return {
		'average_delay_ms': intelligence.metrics.average_delay_ms,
		'min_delay_ms': intelligence.metrics.min_delay_ms,
		'max_delay_ms': intelligence.metrics.max_delay_ms,
		'median_delay_ms': intelligence.metrics.median_delay_ms,
		'sample_count': intelligence.metrics.sample_count,
		'last_observed_ms': intelligence.metrics.last_observed_ms,
		'url_changed': intelligence.metrics.url_changed,
		'dom_stable': intelligence.metrics.dom_stable,
		'network_idle': intelligence.metrics.network_idle,
		'is_slow': intelligence.is_slow,
		'is_fast': intelligence.is_fast,
		'variability': intelligence.variability,
		'recommended_wait_time_ms': intelligence.recommended_wait_time_ms,
		'confidence': intelligence.confidence,
		'context': intelligence.metrics.context,
		'metadata': intelligence.metadata,
	}


def get_delay_intelligence_for_action(
	action_id: str,
	min_samples: int = 1,
) -> dict[str, Any] | None:
	"""
	Get delay intelligence for an action (without saving).
	
	Args:
		action_id: Action ID to get intelligence for
		min_samples: Minimum samples required (default: 1)
	
	Returns:
		Delay intelligence dict if available, None otherwise
	"""
	try:
		delay_tracker = get_delay_tracker()
		intelligence = delay_tracker.get_intelligence(action_id, min_samples=min_samples)
		
		if not intelligence:
			return None
		
		return delay_intelligence_to_dict(intelligence)
	except Exception as e:
		logger.debug(f"Could not get delay intelligence for action {action_id}: {e}")
		return None


async def sync_delay_intelligence_to_action(
	action_id: str,
	min_samples: int = 1,
) -> bool:
	"""
	Sync delay intelligence to an ActionDefinition in the database.
	
	Retrieves the action, updates it with delay intelligence, and saves it back.
	Use this for updating existing actions in the database.
	
	Args:
		action_id: Action ID to update
		min_samples: Minimum samples required (default: 1)
	
	Returns:
		True if updated successfully, False otherwise
	"""
	try:
		delay_intel = get_delay_intelligence_for_action(action_id, min_samples=min_samples)
		if not delay_intel:
			return False
		
		# Get existing action
		action = await get_action(action_id)
		if not action:
			logger.debug(f"Action {action_id} not found in DB, delay intelligence will be synced when action is saved")
			return False
		
		# Update action with delay intelligence
		action.delay_intelligence = delay_intel
		
		# Also update cost in metadata if available
		if 'cost' not in action.metadata:
			action.metadata['cost'] = {}
		action.metadata['cost']['estimated_ms'] = delay_intel['recommended_wait_time_ms']
		action.metadata['cost']['actual_avg_ms'] = delay_intel['average_delay_ms']
		action.metadata['cost']['confidence'] = delay_intel['confidence']
		
		# Save updated action (pass knowledge_id and job_id if available in metadata)
		from navigator.knowledge.persist.documents.actions import save_action
		knowledge_id = action.metadata.get('knowledge_id')
		job_id = action.metadata.get('job_id')
		# Set delay_intelligence to prevent re-sync in save_action
		action.delay_intelligence = delay_intel
		success = await save_action(action, knowledge_id=knowledge_id, job_id=job_id)
		
		if success:
			logger.info(
				f"✅ Synced delay intelligence to action {action_id}: "
				f"avg={delay_intel['average_delay_ms']:.0f}ms, "
				f"recommended={delay_intel['recommended_wait_time_ms']:.0f}ms, "
				f"confidence={delay_intel['confidence']:.2f}"
			)
		
		return success
		
	except Exception as e:
		logger.error(f"Failed to sync delay intelligence to action {action_id}: {e}")
		return False


def get_delay_intelligence_for_transition(
	transition_id: str,
	min_samples: int = 1,
) -> dict[str, Any] | None:
	"""
	Get delay intelligence for a transition (without saving).
	
	Args:
		transition_id: Transition ID to get intelligence for
		min_samples: Minimum samples required (default: 1)
	
	Returns:
		Delay intelligence dict if available, None otherwise
	"""
	try:
		delay_tracker = get_delay_tracker()
		intelligence = delay_tracker.get_intelligence(transition_id, min_samples=min_samples)
		
		if not intelligence:
			return None
		
		return delay_intelligence_to_dict(intelligence)
	except Exception as e:
		logger.debug(f"Could not get delay intelligence for transition {transition_id}: {e}")
		return None


async def sync_delay_intelligence_to_transition(
	transition_id: str,
	min_samples: int = 1,
) -> bool:
	"""
	Sync delay intelligence to a TransitionDefinition in the database.
	
	Retrieves the transition, updates it with delay intelligence, and saves it back.
	Use this for updating existing transitions in the database.
	
	Args:
		transition_id: Transition ID to update
		min_samples: Minimum samples required (default: 1)
	
	Returns:
		True if updated successfully, False otherwise
	"""
	try:
		delay_intel = get_delay_intelligence_for_transition(transition_id, min_samples=min_samples)
		if not delay_intel:
			return False
		
		# Get existing transition
		transition = await get_transition(transition_id)
		if not transition:
			logger.debug(f"Transition {transition_id} not found in DB, delay intelligence will be synced when transition is saved")
			return False
		
		# Update transition with delay intelligence
		transition.delay_intelligence = delay_intel
		
		# Update cost.estimated_ms with actual delay
		transition.cost['estimated_ms'] = delay_intel['recommended_wait_time_ms']
		transition.cost['actual_avg_ms'] = delay_intel['average_delay_ms']
		transition.cost['confidence'] = delay_intel['confidence']
		
		# Save updated transition (pass knowledge_id and job_id if available in metadata)
		# Set delay_intelligence to prevent re-sync in save_transition
		from navigator.knowledge.persist.documents.transitions import save_transition
		knowledge_id = transition.metadata.get('knowledge_id')
		job_id = transition.metadata.get('job_id')
		success = await save_transition(transition, knowledge_id=knowledge_id, job_id=job_id)
		
		if success:
			logger.info(
				f"✅ Synced delay intelligence to transition {transition_id}: "
				f"avg={delay_intel['average_delay_ms']:.0f}ms, "
				f"recommended={delay_intel['recommended_wait_time_ms']:.0f}ms, "
				f"confidence={delay_intel['confidence']:.2f}"
			)
		
		return success
		
	except Exception as e:
		logger.error(f"Failed to sync delay intelligence to transition {transition_id}: {e}")
		return False


async def sync_all_delay_intelligence(
	min_samples: int = 1,
	knowledge_id: str | None = None,
) -> dict[str, Any]:
	"""
	Sync delay intelligence for all tracked entities.
	
	Args:
		min_samples: Minimum samples required per entity
		knowledge_id: Optional knowledge_id filter (if provided, only sync entities for this knowledge)
	
	Returns:
		Dictionary with sync results: {'actions': {'synced': 5, 'failed': 1}, 'transitions': {...}}
	"""
	delay_tracker = get_delay_tracker()
	all_intelligence = delay_tracker.get_all_intelligence(min_samples=min_samples)
	
	results = {
		'actions': {'synced': 0, 'failed': 0},
		'transitions': {'synced': 0, 'failed': 0},
		'total_entities': len(all_intelligence),
	}
	
	for entity_id, intelligence in all_intelligence.items():
		if intelligence.entity_type == 'action':
			success = await sync_delay_intelligence_to_action(entity_id, min_samples=min_samples)
			if success:
				results['actions']['synced'] += 1
			else:
				results['actions']['failed'] += 1
		elif intelligence.entity_type == 'transition':
			success = await sync_delay_intelligence_to_transition(entity_id, min_samples=min_samples)
			if success:
				results['transitions']['synced'] += 1
			else:
				results['transitions']['failed'] += 1
	
	logger.info(
		f"✅ Synced delay intelligence: {results['actions']['synced']} actions, "
		f"{results['transitions']['synced']} transitions "
		f"({results['actions']['failed'] + results['transitions']['failed']} failed)"
	)
	
	return results

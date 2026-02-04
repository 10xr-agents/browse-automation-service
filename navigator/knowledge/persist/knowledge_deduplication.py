"""
Phase 4.3: Knowledge Entity Deduplication

Comprehensive deduplication for knowledge entities:
- Screen deduplication (by name similarity, URL patterns, state signatures)
- Action deduplication (by name, action_type, selector similarity)
- Task deduplication (by name, description, step similarity)
- Merge duplicate entities with proper relationship updates
- Clean up orphaned entities
"""

import logging
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from navigator.knowledge.persist.collections import (
	get_actions_collection,
	get_screens_collection,
	get_tasks_collection,
	get_transitions_collection,
)
from navigator.knowledge.persist.cross_references import get_cross_reference_manager

logger = logging.getLogger(__name__)


@dataclass
class DeduplicationResult:
	"""Result of knowledge deduplication."""
	knowledge_id: str | None = None
	
	# Statistics
	screens_merged: int = 0
	actions_merged: int = 0
	tasks_merged: int = 0
	orphaned_entities_removed: int = 0
	
	# Details
	merged_screens: list[dict[str, Any]] = field(default_factory=list)
	merged_actions: list[dict[str, Any]] = field(default_factory=list)
	merged_tasks: list[dict[str, Any]] = field(default_factory=list)
	orphaned_entities: list[dict[str, Any]] = field(default_factory=list)
	
	# Errors
	errors: list[str] = field(default_factory=list)
	
	def to_dict(self) -> dict[str, Any]:
		"""Convert to dictionary for serialization."""
		return {
			'knowledge_id': self.knowledge_id,
			'screens_merged': self.screens_merged,
			'actions_merged': self.actions_merged,
			'tasks_merged': self.tasks_merged,
			'orphaned_entities_removed': self.orphaned_entities_removed,
			'merged_screens': self.merged_screens,
			'merged_actions': self.merged_actions,
			'merged_tasks': self.merged_tasks,
			'orphaned_entities': self.orphaned_entities,
			'errors': self.errors,
		}


class KnowledgeDeduplicator:
	"""
	Phase 4.3: Comprehensive knowledge deduplicator.
	
	Detects and merges duplicate entities:
	1. Screens (by name similarity, URL patterns, state signatures)
	2. Actions (by name, action_type, selector similarity)
	3. Tasks (by name, description, step similarity)
	
	Also cleans up orphaned entities (entities with no relationships).
	"""
	
	def __init__(self, knowledge_id: str | None = None, similarity_threshold: float = 0.85):
		"""
		Initialize knowledge deduplicator.
		
		Args:
			knowledge_id: Optional knowledge ID to deduplicate specific knowledge set
			similarity_threshold: Similarity threshold for duplicate detection (0-1, default: 0.85)
		"""
		self.knowledge_id = knowledge_id
		self.similarity_threshold = similarity_threshold
		self.cross_ref_manager = get_cross_reference_manager()
	
	async def deduplicate_all(self) -> DeduplicationResult:
		"""
		Run all deduplication checks and merge duplicates.
		
		Returns:
			DeduplicationResult with statistics
		"""
		result = DeduplicationResult(knowledge_id=self.knowledge_id)
		
		logger.info(f"Starting knowledge deduplication (knowledge_id={self.knowledge_id}, threshold={self.similarity_threshold})")
		
		try:
			# Filter artifacts first (video artifacts, duplicate form tasks)
			artifacts_removed = await self._filter_artifacts(result)
			result.orphaned_entities_removed += artifacts_removed
			
			# Deduplicate screens
			screens_merged = await self._deduplicate_screens(result)
			result.screens_merged = screens_merged
			
			# Deduplicate actions
			actions_merged = await self._deduplicate_actions(result)
			result.actions_merged = actions_merged
			
			# Deduplicate tasks
			tasks_merged = await self._deduplicate_tasks(result)
			result.tasks_merged = tasks_merged
			
			# Clean up orphaned entities
			orphaned_removed = await self._cleanup_orphaned_entities(result)
			result.orphaned_entities_removed += orphaned_removed
			
			logger.info(
				f"✅ Deduplication complete: "
				f"{screens_merged} screens merged, "
				f"{actions_merged} actions merged, "
				f"{tasks_merged} tasks merged, "
				f"{artifacts_removed} artifacts filtered, "
				f"{orphaned_removed} orphaned entities removed"
			)
			
		except Exception as e:
			logger.error(f"❌ Deduplication failed: {e}", exc_info=True)
			result.errors.append(f"Deduplication exception: {str(e)}")
		
		return result
	
	async def _deduplicate_screens(self, result: DeduplicationResult) -> int:
		"""Phase 4.3: Deduplicate screens by similarity."""
		logger.info("Deduplicating screens...")
		
		screens_collection = await get_screens_collection()
		if not screens_collection:
			logger.warning("MongoDB unavailable, cannot deduplicate screens")
			return 0
		
		# Load all screens
		query_filter: dict[str, Any] = {}
		if self.knowledge_id:
			query_filter['knowledge_id'] = self.knowledge_id
		
		screens = []
		async for doc in screens_collection.find(query_filter):
			screens.append(doc)
		
		if len(screens) < 2:
			return 0
		
		# Find duplicates
		duplicate_groups = []
		processed = set()
		
		for i, screen1 in enumerate(screens):
			if screen1['screen_id'] in processed:
				continue
			
			group = [screen1]
			for j, screen2 in enumerate(screens[i+1:], start=i+1):
				if screen2['screen_id'] in processed:
					continue
				
				similarity = self._calculate_screen_similarity(screen1, screen2)
				if similarity >= self.similarity_threshold:
					group.append(screen2)
					processed.add(screen2['screen_id'])
			
			if len(group) > 1:
				duplicate_groups.append(group)
				processed.add(screen1['screen_id'])
		
		# Merge duplicates
		merged_count = 0
		for group in duplicate_groups:
			try:
				merged = await self._merge_screens(group)
				if merged:
					merged_count += len(group) - 1  # Number of screens merged into one
					result.merged_screens.append({
						'kept_screen_id': merged['screen_id'],
						'merged_screen_ids': [s['screen_id'] for s in group if s['screen_id'] != merged['screen_id']],
						'similarity_scores': [self._calculate_screen_similarity(group[0], s) for s in group[1:]]
					})
			except Exception as e:
				logger.error(f"Failed to merge screen group: {e}")
				result.errors.append(f"Screen merge error: {str(e)}")
		
		return merged_count
	
	def _calculate_screen_similarity(self, screen1: dict[str, Any], screen2: dict[str, Any]) -> float:
		"""Calculate similarity between two screens (0-1)."""
		scores = []
		
		# Name similarity
		name1 = screen1.get('name', '').lower().strip()
		name2 = screen2.get('name', '').lower().strip()
		if name1 and name2:
			name_sim = SequenceMatcher(None, name1, name2).ratio()
			scores.append(('name', name_sim, 0.3))
		
		# URL pattern similarity
		urls1 = set(screen1.get('url_patterns', []))
		urls2 = set(screen2.get('url_patterns', []))
		if urls1 and urls2:
			url_sim = len(urls1 & urls2) / max(len(urls1 | urls2), 1)
			scores.append(('url_patterns', url_sim, 0.3))
		
		# State signature similarity (required indicators)
		sig1 = screen1.get('state_signature', {}).get('required_indicators', [])
		sig2 = screen2.get('state_signature', {}).get('required_indicators', [])
		if sig1 and sig2:
			# Compare indicator values
			values1 = {ind.get('value', '') for ind in sig1 if ind.get('value')}
			values2 = {ind.get('value', '') for ind in sig2 if ind.get('value')}
			if values1 and values2:
				sig_sim = len(values1 & values2) / max(len(values1 | values2), 1)
				scores.append(('state_signature', sig_sim, 0.4))
		
		# Weighted average
		if scores:
			total_weight = sum(weight for _, _, weight in scores)
			if total_weight > 0:
				weighted_sum = sum(score * weight for _, score, weight in scores)
				return weighted_sum / total_weight
		
		return 0.0
	
	async def _merge_screens(self, screens: list[dict[str, Any]]) -> dict[str, Any] | None:
		"""Merge duplicate screens into one, preserving all relationships."""
		if not screens:
			return None
		
		# Keep the first screen as the primary (or the one with most relationships)
		primary = max(screens, key=lambda s: (
			len(s.get('business_function_ids', [])) +
			len(s.get('user_flow_ids', [])) +
			len(s.get('task_ids', [])) +
			len(s.get('action_ids', []))
		))
		
		# Merge data from other screens
		for screen in screens:
			if screen['screen_id'] == primary['screen_id']:
				continue
			
			# Merge URL patterns
			primary_urls = set(primary.get('url_patterns', []))
			primary_urls.update(screen.get('url_patterns', []))
			primary['url_patterns'] = list(primary_urls)
			
			# Merge UI elements (deduplicate by element_id)
			primary_elements = {el.get('element_id'): el for el in primary.get('ui_elements', [])}
			for el in screen.get('ui_elements', []):
				el_id = el.get('element_id')
				if el_id and el_id not in primary_elements:
					primary_elements[el_id] = el
			primary['ui_elements'] = list(primary_elements.values())
			
			# Merge state signature indicators (combine unique indicators)
			primary_sig = primary.get('state_signature', {})
			screen_sig = screen.get('state_signature', {})
			
			# Merge required indicators
			primary_req = {ind.get('value', ''): ind for ind in primary_sig.get('required_indicators', []) if ind.get('value')}
			for ind in screen_sig.get('required_indicators', []):
				val = ind.get('value', '')
				if val and val not in primary_req:
					primary_req[val] = ind
			primary_sig['required_indicators'] = list(primary_req.values())
			
			# Merge optional indicators
			primary_opt = {ind.get('value', ''): ind for ind in primary_sig.get('optional_indicators', []) if ind.get('value')}
			for ind in screen_sig.get('optional_indicators', []):
				val = ind.get('value', '')
				if val and val not in primary_opt:
					primary_opt[val] = ind
			primary_sig['optional_indicators'] = list(primary_opt.values())
			
			primary['state_signature'] = primary_sig
			
			# Merge cross-references (union of all IDs)
			primary['business_function_ids'] = list(set(primary.get('business_function_ids', []) + screen.get('business_function_ids', [])))
			primary['user_flow_ids'] = list(set(primary.get('user_flow_ids', []) + screen.get('user_flow_ids', [])))
			primary['task_ids'] = list(set(primary.get('task_ids', []) + screen.get('task_ids', [])))
			primary['action_ids'] = list(set(primary.get('action_ids', []) + screen.get('action_ids', [])))
			
			# Update all references to point to primary screen
			await self._update_screen_references(screen['screen_id'], primary['screen_id'])
			
			# Delete duplicate screen
			screens_collection = await get_screens_collection()
			if screens_collection:
				await screens_collection.delete_one({'screen_id': screen['screen_id']})
		
		# Save merged screen
		screens_collection = await get_screens_collection()
		if screens_collection:
			await screens_collection.update_one(
				{'screen_id': primary['screen_id']},
				{'$set': primary},
				upsert=True
			)
		
		return primary
	
	async def _update_screen_references(self, old_screen_id: str, new_screen_id: str) -> None:
		"""Update all references from old_screen_id to new_screen_id."""
		# Update transitions
		transitions_collection = await get_transitions_collection()
		if transitions_collection:
			await transitions_collection.update_many(
				{'from_screen_id': old_screen_id},
				{'$set': {'from_screen_id': new_screen_id}}
			)
			await transitions_collection.update_many(
				{'to_screen_id': old_screen_id},
				{'$set': {'to_screen_id': new_screen_id}}
			)
		
		# Update tasks
		tasks_collection = await get_tasks_collection()
		if tasks_collection:
			await tasks_collection.update_many(
				{'screen_ids': old_screen_id},
				{'$pull': {'screen_ids': old_screen_id}, '$addToSet': {'screen_ids': new_screen_id}}
			)
		
		# Update actions
		actions_collection = await get_actions_collection()
		if actions_collection:
			await actions_collection.update_many(
				{'screen_ids': old_screen_id},
				{'$pull': {'screen_ids': old_screen_id}, '$addToSet': {'screen_ids': new_screen_id}}
			)
		
		# Update workflows
		from navigator.knowledge.persist.collections import get_workflows_collection
		workflows_collection = await get_workflows_collection()
		if workflows_collection:
			await workflows_collection.update_many(
				{'screen_ids': old_screen_id},
				{'$pull': {'screen_ids': old_screen_id}, '$addToSet': {'screen_ids': new_screen_id}}
			)
	
	async def _deduplicate_actions(self, result: DeduplicationResult) -> int:
		"""Phase 4.3: Deduplicate actions by similarity."""
		logger.info("Deduplicating actions...")
		
		actions_collection = await get_actions_collection()
		if not actions_collection:
			logger.warning("MongoDB unavailable, cannot deduplicate actions")
			return 0
		
		# Load all actions
		query_filter: dict[str, Any] = {}
		if self.knowledge_id:
			query_filter['knowledge_id'] = self.knowledge_id
		
		actions = []
		async for doc in actions_collection.find(query_filter):
			actions.append(doc)
		
		if len(actions) < 2:
			return 0
		
		# Find duplicates
		duplicate_groups = []
		processed = set()
		
		for i, action1 in enumerate(actions):
			if action1['action_id'] in processed:
				continue
			
			group = [action1]
			for j, action2 in enumerate(actions[i+1:], start=i+1):
				if action2['action_id'] in processed:
					continue
				
				similarity = self._calculate_action_similarity(action1, action2)
				if similarity >= self.similarity_threshold:
					group.append(action2)
					processed.add(action2['action_id'])
			
			if len(group) > 1:
				duplicate_groups.append(group)
				processed.add(action1['action_id'])
		
		# Merge duplicates
		merged_count = 0
		for group in duplicate_groups:
			try:
				merged = await self._merge_actions(group)
				if merged:
					merged_count += len(group) - 1
					result.merged_actions.append({
						'kept_action_id': merged['action_id'],
						'merged_action_ids': [a['action_id'] for a in group if a['action_id'] != merged['action_id']],
						'similarity_scores': [self._calculate_action_similarity(group[0], a) for a in group[1:]]
					})
			except Exception as e:
				logger.error(f"Failed to merge action group: {e}")
				result.errors.append(f"Action merge error: {str(e)}")
		
		return merged_count
	
	def _calculate_action_similarity(self, action1: dict[str, Any], action2: dict[str, Any]) -> float:
		"""Calculate similarity between two actions (0-1)."""
		scores = []
		
		# Name similarity
		name1 = action1.get('name', '').lower().strip()
		name2 = action2.get('name', '').lower().strip()
		if name1 and name2:
			name_sim = SequenceMatcher(None, name1, name2).ratio()
			scores.append(('name', name_sim, 0.3))
		
		# Action type match
		type1 = action1.get('action_type', '')
		type2 = action2.get('action_type', '')
		if type1 and type2:
			type_sim = 1.0 if type1 == type2 else 0.0
			scores.append(('action_type', type_sim, 0.3))
		
		# Selector similarity
		selector1 = action1.get('selector', '') or (action1.get('selector', {}) or {}).get('css', '')
		selector2 = action2.get('selector', '') or (action2.get('selector', {}) or {}).get('css', '')
		if selector1 and selector2:
			selector_sim = SequenceMatcher(None, selector1, selector2).ratio()
			scores.append(('selector', selector_sim, 0.4))
		
		# Weighted average
		if scores:
			total_weight = sum(weight for _, _, weight in scores)
			if total_weight > 0:
				weighted_sum = sum(score * weight for _, score, weight in scores)
				return weighted_sum / total_weight
		
		return 0.0
	
	async def _merge_actions(self, actions: list[dict[str, Any]]) -> dict[str, Any] | None:
		"""Merge duplicate actions into one, preserving all relationships."""
		if not actions:
			return None
		
		# Keep the action with most relationships or best browser-use mapping
		primary = max(actions, key=lambda a: (
			len(a.get('screen_ids', [])) +
			len(a.get('business_function_ids', [])) +
			(1 if a.get('browser_use_action') else 0)
		))
		
		# Merge data from other actions
		for action in actions:
			if action['action_id'] == primary['action_id']:
				continue
			
			# Merge selectors (prefer more specific)
			if not primary.get('selector') and action.get('selector'):
				primary['selector'] = action['selector']
			
			# Merge browser-use action (prefer the one with higher confidence)
			if not primary.get('browser_use_action') and action.get('browser_use_action'):
				primary['browser_use_action'] = action['browser_use_action']
				primary['confidence_score'] = action.get('confidence_score')
			elif primary.get('browser_use_action') and action.get('browser_use_action'):
				primary_conf = primary.get('confidence_score', 0.0)
				action_conf = action.get('confidence_score', 0.0)
				if action_conf > primary_conf:
					primary['browser_use_action'] = action['browser_use_action']
					primary['confidence_score'] = action_conf
			
			# Merge cross-references
			primary['screen_ids'] = list(set(primary.get('screen_ids', []) + action.get('screen_ids', [])))
			primary['business_function_ids'] = list(set(primary.get('business_function_ids', []) + action.get('business_function_ids', [])))
			
			# Update all references to point to primary action
			await self._update_action_references(action['action_id'], primary['action_id'])
			
			# Delete duplicate action
			actions_collection = await get_actions_collection()
			if actions_collection:
				await actions_collection.delete_one({'action_id': action['action_id']})
		
		# Save merged action
		actions_collection = await get_actions_collection()
		if actions_collection:
			await actions_collection.update_one(
				{'action_id': primary['action_id']},
				{'$set': primary},
				upsert=True
			)
		
		return primary
	
	async def _update_action_references(self, old_action_id: str, new_action_id: str) -> None:
		"""Update all references from old_action_id to new_action_id."""
		# Update screens
		screens_collection = await get_screens_collection()
		if screens_collection:
			await screens_collection.update_many(
				{'action_ids': old_action_id},
				{'$pull': {'action_ids': old_action_id}, '$addToSet': {'action_ids': new_action_id}}
			)
		
		# Update tasks (in steps)
		tasks_collection = await get_tasks_collection()
		if tasks_collection:
			async for task in tasks_collection.find({'steps.action_id': old_action_id}):
				steps = task.get('steps', [])
				for step in steps:
					if step.get('action_id') == old_action_id:
						step['action_id'] = new_action_id
				await tasks_collection.update_one(
					{'task_id': task['task_id']},
					{'$set': {'steps': steps}}
				)
		
		# Update user flows
		from navigator.knowledge.persist.collections import get_user_flows_collection
		user_flows_collection = await get_user_flows_collection()
		if user_flows_collection:
			await user_flows_collection.update_many(
				{'related_actions': old_action_id},
				{'$pull': {'related_actions': old_action_id}, '$addToSet': {'related_actions': new_action_id}}
			)
	
	async def _deduplicate_tasks(self, result: DeduplicationResult) -> int:
		"""Phase 4.3: Deduplicate tasks by similarity."""
		logger.info("Deduplicating tasks...")
		
		tasks_collection = await get_tasks_collection()
		if not tasks_collection:
			logger.warning("MongoDB unavailable, cannot deduplicate tasks")
			return 0
		
		# Load all tasks
		query_filter: dict[str, Any] = {}
		if self.knowledge_id:
			query_filter['knowledge_id'] = self.knowledge_id
		
		tasks = []
		async for doc in tasks_collection.find(query_filter):
			tasks.append(doc)
		
		if len(tasks) < 2:
			return 0
		
		# Find duplicates
		duplicate_groups = []
		processed = set()
		
		for i, task1 in enumerate(tasks):
			if task1['task_id'] in processed:
				continue
			
			group = [task1]
			for j, task2 in enumerate(tasks[i+1:], start=i+1):
				if task2['task_id'] in processed:
					continue
				
				similarity = self._calculate_task_similarity(task1, task2)
				if similarity >= self.similarity_threshold:
					group.append(task2)
					processed.add(task2['task_id'])
			
			if len(group) > 1:
				duplicate_groups.append(group)
				processed.add(task1['task_id'])
		
		# Merge duplicates
		merged_count = 0
		for group in duplicate_groups:
			try:
				merged = await self._merge_tasks(group)
				if merged:
					merged_count += len(group) - 1
					result.merged_tasks.append({
						'kept_task_id': merged['task_id'],
						'merged_task_ids': [t['task_id'] for t in group if t['task_id'] != merged['task_id']],
						'similarity_scores': [self._calculate_task_similarity(group[0], t) for t in group[1:]]
					})
			except Exception as e:
				logger.error(f"Failed to merge task group: {e}")
				result.errors.append(f"Task merge error: {str(e)}")
		
		return merged_count
	
	def _calculate_task_similarity(self, task1: dict[str, Any], task2: dict[str, Any]) -> float:
		"""Calculate similarity between two tasks (0-1)."""
		scores = []
		
		# Name similarity
		name1 = task1.get('name', '').lower().strip()
		name2 = task2.get('name', '').lower().strip()
		if name1 and name2:
			name_sim = SequenceMatcher(None, name1, name2).ratio()
			scores.append(('name', name_sim, 0.3))
		
		# Description similarity
		desc1 = task1.get('description', '').lower().strip()
		desc2 = task2.get('description', '').lower().strip()
		if desc1 and desc2:
			desc_sim = SequenceMatcher(None, desc1, desc2).ratio()
			scores.append(('description', desc_sim, 0.3))
		
		# Step similarity (compare step sequences)
		steps1 = task1.get('steps', [])
		steps2 = task2.get('steps', [])
		if steps1 and steps2:
			# Compare step actions
			actions1 = [step.get('action', '') for step in steps1 if step.get('action')]
			actions2 = [step.get('action', '') for step in steps2 if step.get('action')]
			if actions1 and actions2:
				# Use sequence similarity
				step_sim = SequenceMatcher(None, actions1, actions2).ratio()
				scores.append(('steps', step_sim, 0.4))
		
		# Weighted average
		if scores:
			total_weight = sum(weight for _, _, weight in scores)
			if total_weight > 0:
				weighted_sum = sum(score * weight for _, score, weight in scores)
				return weighted_sum / total_weight
		
		return 0.0
	
	async def _merge_tasks(self, tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
		"""Merge duplicate tasks into one, preserving all relationships."""
		if not tasks:
			return None
		
		# Keep the task with most relationships or most complete steps
		primary = max(tasks, key=lambda t: (
			len(t.get('screen_ids', [])) +
			len(t.get('business_function_ids', [])) +
			len(t.get('steps', []))
		))
		
		# Merge data from other tasks
		for task in tasks:
			if task['task_id'] == primary['task_id']:
				continue
			
			# Merge steps (prefer longer sequence, merge unique steps)
			primary_steps = {step.get('order'): step for step in primary.get('steps', [])}
			for step in task.get('steps', []):
				order = step.get('order')
				if order and order not in primary_steps:
					primary_steps[order] = step
			primary['steps'] = sorted(primary_steps.values(), key=lambda s: s.get('order', 0))
			
			# Merge IO spec (prefer more complete)
			if not primary.get('io_spec') and task.get('io_spec'):
				primary['io_spec'] = task['io_spec']
			
			# Merge iterator spec (prefer more complete)
			if not primary.get('iterator_spec') and task.get('iterator_spec'):
				primary['iterator_spec'] = task['iterator_spec']
			
			# Merge cross-references
			primary['screen_ids'] = list(set(primary.get('screen_ids', []) + task.get('screen_ids', [])))
			primary['business_function_ids'] = list(set(primary.get('business_function_ids', []) + task.get('business_function_ids', [])))
			
			# Update all references to point to primary task
			await self._update_task_references(task['task_id'], primary['task_id'])
			
			# Delete duplicate task
			tasks_collection = await get_tasks_collection()
			if tasks_collection:
				await tasks_collection.delete_one({'task_id': task['task_id']})
		
		# Save merged task
		tasks_collection = await get_tasks_collection()
		if tasks_collection:
			await tasks_collection.update_one(
				{'task_id': primary['task_id']},
				{'$set': primary},
				upsert=True
			)
		
		return primary
	
	async def _update_task_references(self, old_task_id: str, new_task_id: str) -> None:
		"""Update all references from old_task_id to new_task_id."""
		# Update screens
		screens_collection = await get_screens_collection()
		if screens_collection:
			await screens_collection.update_many(
				{'task_ids': old_task_id},
				{'$pull': {'task_ids': old_task_id}, '$addToSet': {'task_ids': new_task_id}}
			)
		
		# Update user flows
		from navigator.knowledge.persist.collections import get_user_flows_collection
		user_flows_collection = await get_user_flows_collection()
		if user_flows_collection:
			await user_flows_collection.update_many(
				{'related_tasks': old_task_id},
				{'$pull': {'related_tasks': old_task_id}, '$addToSet': {'related_tasks': new_task_id}}
			)
	
	async def _filter_artifacts(self, result: DeduplicationResult) -> int:
		"""
		Filter out video artifacts and duplicate form tasks.
		
		Artifacts to filter:
		- Video transcription segments: "Transcription Segment 1", "Transcription Segment 2", etc.
		- Frame analysis artifacts: "Frame Analysis 1", "Frame Analysis 2", etc.
		- Generic extraction artifacts: "Extracted Actions", "Complete Transcription", etc.
		- Duplicate form tasks: Multiple "Submit form on X" tasks with same page_url
		
		Returns:
			Number of artifacts removed
		"""
		logger.info("Filtering artifacts...")
		removed_count = 0
		
		# Filter artifact screens
		screens_collection = await get_screens_collection()
		if screens_collection:
			query_filter: dict[str, Any] = {}
			if self.knowledge_id:
				query_filter['knowledge_id'] = self.knowledge_id
			
			artifact_patterns = [
				r'^transcription\s+segment\s+\d+$',
				r'^frame\s+analysis\s+\d+$',
				r'^extracted\s+actions$',
				r'^complete\s+transcription$',
				r'^s3_download_\w+$',  # S3 download artifacts
			]
			
			async for screen in screens_collection.find(query_filter):
				screen_name = screen.get('name', '').lower().strip()
				screen_id = screen.get('screen_id')
				
				# Check if screen name matches artifact patterns
				is_artifact = any(
					re.match(pattern, screen_name, re.IGNORECASE)
					for pattern in artifact_patterns
				)
				
				# Also check metadata for video extraction sources
				metadata = screen.get('metadata', {})
				extraction_source = metadata.get('extraction_source', '')
				if extraction_source in ['video_transcription', 'video_frame_analysis', 'video_metadata']:
					is_artifact = True
				
				# Check if it's a documentation screen with no relationships
				if (screen.get('content_type') == 'documentation' and 
				    not screen.get('url_patterns') and
				    not screen.get('task_ids') and
				    not screen.get('action_ids')):
					# Likely an artifact if name matches patterns
					if any(re.match(pattern, screen_name, re.IGNORECASE) for pattern in artifact_patterns):
						is_artifact = True
				
				if is_artifact:
					await screens_collection.delete_one({'screen_id': screen_id})
					removed_count += 1
					result.orphaned_entities.append({
						'entity_type': 'screen',
						'entity_id': screen_id,
						'reason': f'Video/documentation artifact: {screen.get("name")}'
					})
					logger.debug(f"Removed artifact screen: {screen.get('name')} ({screen_id})")
		
		# Filter duplicate form tasks (same name + page_url)
		tasks_collection = await get_tasks_collection()
		if tasks_collection:
			query_filter: dict[str, Any] = {}
			if self.knowledge_id:
				query_filter['knowledge_id'] = self.knowledge_id
			
			# Group tasks by name and page_url
			task_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
			
			async for task in tasks_collection.find(query_filter):
				task_name = task.get('name', '').lower().strip()
				page_url = task.get('metadata', {}).get('page_url', '')
				
				# Only filter "Submit form" tasks
				if 'submit form' in task_name:
					key = (task_name, page_url)
					if key not in task_groups:
						task_groups[key] = []
					task_groups[key].append(task)
			
			# Keep only one task per group, delete the rest
			for (task_name, page_url), tasks in task_groups.items():
				if len(tasks) > 1:
					# Keep the task with most relationships or most complete steps
					primary = max(tasks, key=lambda t: (
						len(t.get('screen_ids', [])) +
						len(t.get('steps', [])) +
						len(t.get('business_function_ids', []))
					))
					
					for task in tasks:
						if task['task_id'] == primary['task_id']:
							continue
						
						# Delete duplicate
						await tasks_collection.delete_one({'task_id': task['task_id']})
						removed_count += 1
						result.orphaned_entities.append({
							'entity_type': 'task',
							'entity_id': task['task_id'],
							'reason': f'Duplicate form task: {task.get("name")} on {page_url}'
						})
						logger.debug(f"Removed duplicate form task: {task.get('name')} ({task['task_id']})")
		
		if removed_count > 0:
			logger.info(f"Filtered {removed_count} artifacts ({removed_count - len([e for e in result.orphaned_entities if e.get('entity_type') == 'task'])}) screens, {len([e for e in result.orphaned_entities if e.get('entity_type') == 'task'])} tasks)")
		
		return removed_count
	
	async def _cleanup_orphaned_entities(self, result: DeduplicationResult) -> int:
		"""Phase 4.3: Clean up orphaned entities (entities with no relationships)."""
		logger.info("Cleaning up orphaned entities...")
		
		removed_count = 0
		
		# Check for orphaned screens (no business functions, user flows, tasks, actions)
		screens_collection = await get_screens_collection()
		if screens_collection:
			query_filter: dict[str, Any] = {}
			if self.knowledge_id:
				query_filter['knowledge_id'] = self.knowledge_id
			
			async for screen in screens_collection.find(query_filter):
				screen_id = screen.get('screen_id')
				has_relationships = (
					screen.get('business_function_ids') or
					screen.get('user_flow_ids') or
					screen.get('task_ids') or
					screen.get('action_ids')
				)
				
				# Also check if referenced by transitions
				from navigator.knowledge.persist.collections import get_transitions_collection
				transitions_collection = await get_transitions_collection()
				if transitions_collection:
					referenced = await transitions_collection.find_one({
						'$or': [
							{'from_screen_id': screen_id},
							{'to_screen_id': screen_id}
						]
					})
					if referenced:
						has_relationships = True
				
				if not has_relationships and screen.get('content_type') == 'documentation':
					# Remove orphaned documentation screens (but keep web_ui screens)
					await screens_collection.delete_one({'screen_id': screen_id})
					removed_count += 1
					result.orphaned_entities.append({
						'entity_type': 'screen',
						'entity_id': screen_id,
						'reason': 'No relationships and documentation type'
					})
		
		# Check for orphaned actions (no screens, business functions)
		actions_collection = await get_actions_collection()
		if actions_collection:
			query_filter: dict[str, Any] = {}
			if self.knowledge_id:
				query_filter['knowledge_id'] = self.knowledge_id
			
			async for action in actions_collection.find(query_filter):
				action_id = action.get('action_id')
				has_relationships = (
					action.get('screen_ids') or
					action.get('business_function_ids')
				)
				
				if not has_relationships:
					await actions_collection.delete_one({'action_id': action_id})
					removed_count += 1
					result.orphaned_entities.append({
						'entity_type': 'action',
						'entity_id': action_id,
						'reason': 'No relationships'
					})
		
		# Check for orphaned tasks (no screens, business functions)
		tasks_collection = await get_tasks_collection()
		if tasks_collection:
			query_filter: dict[str, Any] = {}
			if self.knowledge_id:
				query_filter['knowledge_id'] = self.knowledge_id
			
			async for task in tasks_collection.find(query_filter):
				task_id = task.get('task_id')
				has_relationships = (
					task.get('screen_ids') or
					task.get('business_function_ids')
				)
				
				if not has_relationships:
					await tasks_collection.delete_one({'task_id': task_id})
					removed_count += 1
					result.orphaned_entities.append({
						'entity_type': 'task',
						'entity_id': task_id,
						'reason': 'No relationships'
					})
		
		return removed_count


async def deduplicate_knowledge(knowledge_id: str | None = None, similarity_threshold: float = 0.85) -> DeduplicationResult:
	"""
	Phase 4.3: Convenience function to deduplicate knowledge.
	
	Args:
		knowledge_id: Optional knowledge ID to deduplicate specific knowledge set
		similarity_threshold: Similarity threshold for duplicate detection (0-1, default: 0.85)
	
	Returns:
		DeduplicationResult with statistics
	"""
	deduplicator = KnowledgeDeduplicator(knowledge_id=knowledge_id, similarity_threshold=similarity_threshold)
	return await deduplicator.deduplicate_all()

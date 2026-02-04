"""
Priority 10: Relationship Deduplication

Removes duplicate or conflicting relationships from entity relationship arrays.
Ensures each entity pair is linked only once per relationship type.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from navigator.knowledge.persist.collections import (
	get_actions_collection,
	get_business_functions_collection,
	get_screens_collection,
	get_tasks_collection,
)

logger = logging.getLogger(__name__)


@dataclass
class RelationshipDeduplicationResult:
	"""Result of relationship deduplication."""
	knowledge_id: str | None = None
	
	# Statistics
	duplicates_removed: int = 0
	screens_cleaned: int = 0
	actions_cleaned: int = 0
	tasks_cleaned: int = 0
	business_functions_cleaned: int = 0
	
	# Details
	cleaned_entities: list[dict[str, Any]] = field(default_factory=list)
	
	# Errors
	errors: list[str] = field(default_factory=list)
	
	def to_dict(self) -> dict[str, Any]:
		"""Convert to dictionary for serialization."""
		return {
			'knowledge_id': self.knowledge_id,
			'duplicates_removed': self.duplicates_removed,
			'screens_cleaned': self.screens_cleaned,
			'actions_cleaned': self.actions_cleaned,
			'tasks_cleaned': self.tasks_cleaned,
			'business_functions_cleaned': self.business_functions_cleaned,
			'cleaned_entities': self.cleaned_entities,
			'errors': self.errors,
		}


class RelationshipDeduplicator:
	"""
	Priority 10: Relationship deduplicator.
	
	Removes duplicate relationships from entity relationship arrays:
	- Screens: business_function_ids, task_ids, action_ids
	- Actions: screen_ids, business_function_ids
	- Tasks: screen_ids, business_function_ids
	- Business Functions: screen_ids, task_ids, action_ids
	"""
	
	def __init__(self, knowledge_id: str | None = None):
		"""
		Initialize relationship deduplicator.
		
		Args:
			knowledge_id: Optional knowledge ID to deduplicate specific knowledge set
		"""
		self.knowledge_id = knowledge_id
	
	async def deduplicate_all(self) -> RelationshipDeduplicationResult:
		"""
		Remove duplicate relationships from all entities.
		
		Returns:
			RelationshipDeduplicationResult with statistics
		"""
		result = RelationshipDeduplicationResult(knowledge_id=self.knowledge_id)
		
		logger.info(f"Priority 10: Starting relationship deduplication (knowledge_id={self.knowledge_id})")
		
		try:
			# Deduplicate screens
			screens_cleaned = await self._deduplicate_screen_relationships()
			result.screens_cleaned = screens_cleaned['cleaned']
			result.duplicates_removed += screens_cleaned['duplicates_removed']
			result.cleaned_entities.extend(screens_cleaned['entities'])
			
			# Deduplicate actions
			actions_cleaned = await self._deduplicate_action_relationships()
			result.actions_cleaned = actions_cleaned['cleaned']
			result.duplicates_removed += actions_cleaned['duplicates_removed']
			result.cleaned_entities.extend(actions_cleaned['entities'])
			
			# Deduplicate tasks
			tasks_cleaned = await self._deduplicate_task_relationships()
			result.tasks_cleaned = tasks_cleaned['cleaned']
			result.duplicates_removed += tasks_cleaned['duplicates_removed']
			result.cleaned_entities.extend(tasks_cleaned['entities'])
			
			# Deduplicate business functions
			bf_cleaned = await self._deduplicate_business_function_relationships()
			result.business_functions_cleaned = bf_cleaned['cleaned']
			result.duplicates_removed += bf_cleaned['duplicates_removed']
			result.cleaned_entities.extend(bf_cleaned['entities'])
			
			logger.info(
				f"Priority 10: Relationship deduplication complete: "
				f"{result.duplicates_removed} duplicates removed from "
				f"{result.screens_cleaned} screens, {result.actions_cleaned} actions, "
				f"{result.tasks_cleaned} tasks, {result.business_functions_cleaned} business functions"
			)
		
		except Exception as e:
			logger.error(f"Priority 10: Relationship deduplication failed: {e}", exc_info=True)
			result.errors.append(str(e))
		
		return result
	
	async def _deduplicate_screen_relationships(self) -> dict[str, Any]:
		"""Priority 10: Remove duplicate relationships from screens."""
		screens_collection = await get_screens_collection()
		if not screens_collection:
			return {'cleaned': 0, 'duplicates_removed': 0, 'entities': []}
		
		query_filter: dict[str, Any] = {}
		if self.knowledge_id:
			query_filter['knowledge_id'] = self.knowledge_id
		
		cleaned_count = 0
		total_duplicates = 0
		cleaned_entities = []
		
		async for screen in screens_collection.find(query_filter):
			screen_id = screen.get('screen_id')
			if not screen_id:
				continue
			
			updated = False
			duplicates_in_entity = 0
			
			# Deduplicate business_function_ids
			bf_ids = screen.get('business_function_ids', [])
			if bf_ids:
				original_count = len(bf_ids)
				bf_ids_deduped = list(dict.fromkeys(bf_ids))  # Preserve order, remove duplicates
				if len(bf_ids_deduped) < original_count:
					screen['business_function_ids'] = bf_ids_deduped
					duplicates_in_entity += original_count - len(bf_ids_deduped)
					updated = True
			
			# Deduplicate task_ids
			task_ids = screen.get('task_ids', [])
			if task_ids:
				original_count = len(task_ids)
				task_ids_deduped = list(dict.fromkeys(task_ids))
				if len(task_ids_deduped) < original_count:
					screen['task_ids'] = task_ids_deduped
					duplicates_in_entity += original_count - len(task_ids_deduped)
					updated = True
			
			# Deduplicate action_ids
			action_ids = screen.get('action_ids', [])
			if action_ids:
				original_count = len(action_ids)
				action_ids_deduped = list(dict.fromkeys(action_ids))
				if len(action_ids_deduped) < original_count:
					screen['action_ids'] = action_ids_deduped
					duplicates_in_entity += original_count - len(action_ids_deduped)
					updated = True
			
			if updated:
				await screens_collection.update_one(
					{'screen_id': screen_id},
					{'$set': {
						'business_function_ids': screen.get('business_function_ids', []),
						'task_ids': screen.get('task_ids', []),
						'action_ids': screen.get('action_ids', []),
					}}
				)
				cleaned_count += 1
				total_duplicates += duplicates_in_entity
				cleaned_entities.append({
					'entity_type': 'screen',
					'entity_id': screen_id,
					'duplicates_removed': duplicates_in_entity
				})
		
		return {
			'cleaned': cleaned_count,
			'duplicates_removed': total_duplicates,
			'entities': cleaned_entities
		}
	
	async def _deduplicate_action_relationships(self) -> dict[str, Any]:
		"""Priority 10: Remove duplicate relationships from actions."""
		actions_collection = await get_actions_collection()
		if not actions_collection:
			return {'cleaned': 0, 'duplicates_removed': 0, 'entities': []}
		
		query_filter: dict[str, Any] = {}
		if self.knowledge_id:
			query_filter['knowledge_id'] = self.knowledge_id
		
		cleaned_count = 0
		total_duplicates = 0
		cleaned_entities = []
		
		async for action in actions_collection.find(query_filter):
			action_id = action.get('action_id')
			if not action_id:
				continue
			
			updated = False
			duplicates_in_entity = 0
			
			# Deduplicate screen_ids
			screen_ids = action.get('screen_ids', [])
			if screen_ids:
				original_count = len(screen_ids)
				screen_ids_deduped = list(dict.fromkeys(screen_ids))
				if len(screen_ids_deduped) < original_count:
					action['screen_ids'] = screen_ids_deduped
					duplicates_in_entity += original_count - len(screen_ids_deduped)
					updated = True
			
			# Deduplicate business_function_ids
			bf_ids = action.get('business_function_ids', [])
			if bf_ids:
				original_count = len(bf_ids)
				bf_ids_deduped = list(dict.fromkeys(bf_ids))
				if len(bf_ids_deduped) < original_count:
					action['business_function_ids'] = bf_ids_deduped
					duplicates_in_entity += original_count - len(bf_ids_deduped)
					updated = True
			
			if updated:
				await actions_collection.update_one(
					{'action_id': action_id},
					{'$set': {
						'screen_ids': action.get('screen_ids', []),
						'business_function_ids': action.get('business_function_ids', []),
					}}
				)
				cleaned_count += 1
				total_duplicates += duplicates_in_entity
				cleaned_entities.append({
					'entity_type': 'action',
					'entity_id': action_id,
					'duplicates_removed': duplicates_in_entity
				})
		
		return {
			'cleaned': cleaned_count,
			'duplicates_removed': total_duplicates,
			'entities': cleaned_entities
		}
	
	async def _deduplicate_task_relationships(self) -> dict[str, Any]:
		"""Priority 10: Remove duplicate relationships from tasks."""
		tasks_collection = await get_tasks_collection()
		if not tasks_collection:
			return {'cleaned': 0, 'duplicates_removed': 0, 'entities': []}
		
		query_filter: dict[str, Any] = {}
		if self.knowledge_id:
			query_filter['knowledge_id'] = self.knowledge_id
		
		cleaned_count = 0
		total_duplicates = 0
		cleaned_entities = []
		
		async for task in tasks_collection.find(query_filter):
			task_id = task.get('task_id')
			if not task_id:
				continue
			
			updated = False
			duplicates_in_entity = 0
			
			# Deduplicate screen_ids
			screen_ids = task.get('screen_ids', [])
			if screen_ids:
				original_count = len(screen_ids)
				screen_ids_deduped = list(dict.fromkeys(screen_ids))
				if len(screen_ids_deduped) < original_count:
					task['screen_ids'] = screen_ids_deduped
					duplicates_in_entity += original_count - len(screen_ids_deduped)
					updated = True
			
			# Deduplicate business_function_ids
			bf_ids = task.get('business_function_ids', [])
			if bf_ids:
				original_count = len(bf_ids)
				bf_ids_deduped = list(dict.fromkeys(bf_ids))
				if len(bf_ids_deduped) < original_count:
					task['business_function_ids'] = bf_ids_deduped
					duplicates_in_entity += original_count - len(bf_ids_deduped)
					updated = True
			
			if updated:
				await tasks_collection.update_one(
					{'task_id': task_id},
					{'$set': {
						'screen_ids': task.get('screen_ids', []),
						'business_function_ids': task.get('business_function_ids', []),
					}}
				)
				cleaned_count += 1
				total_duplicates += duplicates_in_entity
				cleaned_entities.append({
					'entity_type': 'task',
					'entity_id': task_id,
					'duplicates_removed': duplicates_in_entity
				})
		
		return {
			'cleaned': cleaned_count,
			'duplicates_removed': total_duplicates,
			'entities': cleaned_entities
		}
	
	async def _deduplicate_business_function_relationships(self) -> dict[str, Any]:
		"""Priority 10: Remove duplicate relationships from business functions."""
		bf_collection = await get_business_functions_collection()
		if not bf_collection:
			return {'cleaned': 0, 'duplicates_removed': 0, 'entities': []}
		
		query_filter: dict[str, Any] = {}
		if self.knowledge_id:
			query_filter['knowledge_id'] = self.knowledge_id
		
		cleaned_count = 0
		total_duplicates = 0
		cleaned_entities = []
		
		async for bf in bf_collection.find(query_filter):
			bf_id = bf.get('business_function_id')
			if not bf_id:
				continue
			
			updated = False
			duplicates_in_entity = 0
			
			# Deduplicate screen_ids
			screen_ids = bf.get('screen_ids', [])
			if screen_ids:
				original_count = len(screen_ids)
				screen_ids_deduped = list(dict.fromkeys(screen_ids))
				if len(screen_ids_deduped) < original_count:
					bf['screen_ids'] = screen_ids_deduped
					duplicates_in_entity += original_count - len(screen_ids_deduped)
					updated = True
			
			# Deduplicate task_ids
			task_ids = bf.get('task_ids', [])
			if task_ids:
				original_count = len(task_ids)
				task_ids_deduped = list(dict.fromkeys(task_ids))
				if len(task_ids_deduped) < original_count:
					bf['task_ids'] = task_ids_deduped
					duplicates_in_entity += original_count - len(task_ids_deduped)
					updated = True
			
			# Deduplicate action_ids
			action_ids = bf.get('action_ids', [])
			if action_ids:
				original_count = len(action_ids)
				action_ids_deduped = list(dict.fromkeys(action_ids))
				if len(action_ids_deduped) < original_count:
					bf['action_ids'] = action_ids_deduped
					duplicates_in_entity += original_count - len(action_ids_deduped)
					updated = True
			
			if updated:
				await bf_collection.update_one(
					{'business_function_id': bf_id},
					{'$set': {
						'screen_ids': bf.get('screen_ids', []),
						'task_ids': bf.get('task_ids', []),
						'action_ids': bf.get('action_ids', []),
					}}
				)
				cleaned_count += 1
				total_duplicates += duplicates_in_entity
				cleaned_entities.append({
					'entity_type': 'business_function',
					'entity_id': bf_id,
					'duplicates_removed': duplicates_in_entity
				})
		
		return {
			'cleaned': cleaned_count,
			'duplicates_removed': total_duplicates,
			'entities': cleaned_entities
		}


async def deduplicate_relationships(knowledge_id: str | None = None) -> RelationshipDeduplicationResult:
	"""
	Priority 10: Convenience function to deduplicate relationships.
	
	Args:
		knowledge_id: Optional knowledge ID to deduplicate specific knowledge set
	
	Returns:
		RelationshipDeduplicationResult with statistics
	"""
	deduplicator = RelationshipDeduplicator(knowledge_id=knowledge_id)
	return await deduplicator.deduplicate_all()

"""
Database Consistency Validator

Phase 8.5: Cross-database consistency checks between MongoDB and ArangoDB.
"""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyIssue:
	"""A consistency issue found during validation."""
	issue_type: str  # 'missing_node', 'orphaned_edge', 'missing_document', etc.
	severity: str  # 'critical', 'warning', 'info'
	entity_type: str  # 'screen', 'task', 'action', 'transition'
	entity_id: str
	description: str
	details: dict[str, Any]


@dataclass
class ConsistencyReport:
	"""Report of database consistency validation."""
	total_checks: int
	passed_checks: int
	failed_checks: int
	issues: list[ConsistencyIssue]
	mongodb_stats: dict[str, int]
	arangodb_stats: dict[str, int]
	
	@property
	def success_rate(self) -> float:
		"""Calculate success rate percentage."""
		if self.total_checks == 0:
			return 100.0
		return (self.passed_checks / self.total_checks) * 100
	
	@property
	def has_critical_issues(self) -> bool:
		"""Check if there are any critical issues."""
		return any(issue.severity == 'critical' for issue in self.issues)


class ConsistencyValidator:
	"""
	Validates consistency between MongoDB and ArangoDB.
	
	Checks:
	1. All ArangoDB screen nodes have MongoDB screen documents
	2. All ArangoDB edges reference valid nodes
	3. All MongoDB tasks reference valid screens/actions
	4. No orphaned entities
	"""
	
	def __init__(self, mongodb_client, arango_client):
		"""
		Initialize consistency validator.
		
		Args:
			mongodb_client: MongoDB client instance
			arango_client: ArangoDB client instance
		"""
		self.mongodb = mongodb_client
		self.arango = arango_client
		self.issues: list[ConsistencyIssue] = []
	
	async def validate_all(self) -> ConsistencyReport:
		"""
		Run all consistency checks.
		
		Returns:
			ConsistencyReport with results
		"""
		logger.info("Starting database consistency validation")
		self.issues = []
		
		# Collect stats
		mongodb_stats = await self._get_mongodb_stats()
		arangodb_stats = await self._get_arangodb_stats()
		
		# Run checks
		checks = [
			self._check_screen_consistency(),
			self._check_transition_consistency(),
			self._check_task_consistency(),
			self._check_action_consistency(),
			self._check_orphaned_entities(),
		]
		
		total_checks = len(checks)
		passed_checks = 0
		
		for check in checks:
			try:
				await check
				passed_checks += 1
			except Exception as e:
				logger.error(f"Consistency check failed: {e}")
		
		failed_checks = total_checks - passed_checks
		
		report = ConsistencyReport(
			total_checks=total_checks,
			passed_checks=passed_checks,
			failed_checks=failed_checks,
			issues=self.issues,
			mongodb_stats=mongodb_stats,
			arangodb_stats=arangodb_stats,
		)
		
		logger.info(
			f"Consistency validation complete: {passed_checks}/{total_checks} checks passed, "
			f"{len(self.issues)} issues found"
		)
		
		return report
	
	async def _get_mongodb_stats(self) -> dict[str, int]:
		"""Get MongoDB collection counts."""
		try:
			db = self.mongodb['knowledge_extraction']
			return {
				'screens': await db.screens.count_documents({}),
				'tasks': await db.tasks.count_documents({}),
				'actions': await db.actions.count_documents({}),
				'transitions': await db.transitions.count_documents({}),
			}
		except Exception as e:
			logger.error(f"Failed to get MongoDB stats: {e}")
			return {'screens': 0, 'tasks': 0, 'actions': 0, 'transitions': 0}
	
	async def _get_arangodb_stats(self) -> dict[str, int]:
		"""Get ArangoDB collection counts."""
		try:
			db = self.arango.db('knowledge_graph')
			return {
				'screens': db.collection('screens').count(),
				'transitions': db.collection('transitions').count(),
			}
		except Exception as e:
			logger.error(f"Failed to get ArangoDB stats: {e}")
			return {'screens': 0, 'transitions': 0}
	
	async def _check_screen_consistency(self):
		"""Check that all ArangoDB screens exist in MongoDB."""
		logger.info("Checking screen consistency")
		
		# Get all screen IDs from ArangoDB
		try:
			db = self.arango.db('knowledge_graph')
			arango_screens = [doc['_key'] for doc in db.collection('screens')]
			
			# Check each screen exists in MongoDB
			mongodb_db = self.mongodb['knowledge_extraction']
			for screen_id in arango_screens:
				mongo_screen = await mongodb_db.screens.find_one({'screen_id': screen_id})
				if not mongo_screen:
					self.issues.append(ConsistencyIssue(
						issue_type='missing_document',
						severity='critical',
						entity_type='screen',
						entity_id=screen_id,
						description=f"Screen {screen_id} exists in ArangoDB but not in MongoDB",
						details={'arango_key': screen_id},
					))
		except Exception as e:
			logger.error(f"Screen consistency check failed: {e}")
			raise
	
	async def _check_transition_consistency(self):
		"""Check that all transitions reference valid screens."""
		logger.info("Checking transition consistency")
		
		try:
			db = self.arango.db('knowledge_graph')
			transitions = db.collection('transitions')
			
			for edge in transitions:
				# Check source exists
				source_key = edge['_from'].split('/')[1]
				if not db.collection('screens').has(source_key):
					self.issues.append(ConsistencyIssue(
						issue_type='orphaned_edge',
						severity='critical',
						entity_type='transition',
						entity_id=edge['_key'],
						description=f"Transition references non-existent source screen {source_key}",
						details={'edge': edge},
					))
				
				# Check target exists
				target_key = edge['_to'].split('/')[1]
				if not db.collection('screens').has(target_key):
					self.issues.append(ConsistencyIssue(
						issue_type='orphaned_edge',
						severity='critical',
						entity_type='transition',
						entity_id=edge['_key'],
						description=f"Transition references non-existent target screen {target_key}",
						details={'edge': edge},
					))
		except Exception as e:
			logger.error(f"Transition consistency check failed: {e}")
			raise
	
	async def _check_task_consistency(self):
		"""Check that all tasks reference valid screens and actions."""
		logger.info("Checking task consistency")
		
		try:
			mongodb_db = self.mongodb['knowledge_extraction']
			
			async for task in mongodb_db.tasks.find({}):
				task_id = task.get('task_id')
				
				# Check referenced screens exist
				for step in task.get('steps', []):
					screen_id = step.get('screen_id')
					if screen_id:
						screen = await mongodb_db.screens.find_one({'screen_id': screen_id})
						if not screen:
							self.issues.append(ConsistencyIssue(
								issue_type='broken_reference',
								severity='warning',
								entity_type='task',
								entity_id=task_id,
								description=f"Task references non-existent screen {screen_id}",
								details={'task_id': task_id, 'screen_id': screen_id},
							))
		except Exception as e:
			logger.error(f"Task consistency check failed: {e}")
			raise
	
	async def _check_action_consistency(self):
		"""Check that all actions reference valid screens."""
		logger.info("Checking action consistency")
		
		try:
			mongodb_db = self.mongodb['knowledge_extraction']
			
			async for action in mongodb_db.actions.find({}):
				action_id = action.get('action_id')
				screen_id = action.get('screen_id')
				
				if screen_id:
					screen = await mongodb_db.screens.find_one({'screen_id': screen_id})
					if not screen:
						self.issues.append(ConsistencyIssue(
							issue_type='broken_reference',
							severity='warning',
							entity_type='action',
							entity_id=action_id,
							description=f"Action references non-existent screen {screen_id}",
							details={'action_id': action_id, 'screen_id': screen_id},
						))
		except Exception as e:
			logger.error(f"Action consistency check failed: {e}")
			raise
	
	async def _check_orphaned_entities(self):
		"""Check for orphaned entities (exist in MongoDB but not in graph)."""
		logger.info("Checking for orphaned entities")
		
		try:
			mongodb_db = self.mongodb['knowledge_extraction']
			db = self.arango.db('knowledge_graph')
			arango_screen_keys = set(doc['_key'] for doc in db.collection('screens'))
			
			# Check for MongoDB screens not in ArangoDB
			async for screen in mongodb_db.screens.find({}):
				screen_id = screen.get('screen_id')
				if screen_id not in arango_screen_keys:
					self.issues.append(ConsistencyIssue(
						issue_type='orphaned_document',
						severity='info',
						entity_type='screen',
						entity_id=screen_id,
						description=f"Screen {screen_id} exists in MongoDB but not in ArangoDB graph",
						details={'screen_id': screen_id},
					))
		except Exception as e:
			logger.error(f"Orphaned entity check failed: {e}")
			raise


async def check_database_consistency(mongodb_client, arango_client) -> ConsistencyReport:
	"""
	Convenience function to check database consistency.
	
	Args:
		mongodb_client: MongoDB client
		arango_client: ArangoDB client
	
	Returns:
		ConsistencyReport
	"""
	validator = ConsistencyValidator(mongodb_client, arango_client)
	return await validator.validate_all()

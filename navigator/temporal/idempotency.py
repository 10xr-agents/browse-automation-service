"""
Idempotency management for Temporal activities.

Ensures activities can be retried without side effects by caching results
and detecting duplicate executions.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class IdempotencyManager:
	"""
	Manages idempotency for Temporal activities.
	
	Uses MongoDB to store execution logs and detect duplicate invocations.
	"""

	def __init__(self, db: AsyncIOMotorDatabase):
		"""
		Initialize idempotency manager.
		
		Args:
			db: MongoDB database instance
		"""
		self.db = db
		self.collection = db['activity_execution_log']

	async def ensure_indexes(self):
		"""Create indexes for activity execution log."""
		await self.collection.create_index('idempotency_key', unique=True)
		await self.collection.create_index('workflow_id')
		await self.collection.create_index('expires_at', expireAfterSeconds=0)
		logger.info("✅ Idempotency indexes created")

	@staticmethod
	def _serialize_for_mongodb(data: Any) -> Any:
		"""
		Recursively convert Pydantic models and other non-serializable objects to dicts.
		
		Args:
			data: Data to serialize (can contain Pydantic models, dataclasses, etc.)
		
		Returns:
			Serializable dict/list/primitive
		"""
		if isinstance(data, BaseModel):
			# Pydantic v2: use model_dump(), v1: use dict()
			if hasattr(data, 'model_dump'):
				return data.model_dump()
			elif hasattr(data, 'dict'):
				return data.dict()
			else:
				# Fallback: convert to dict manually
				return {k: IdempotencyManager._serialize_for_mongodb(v) for k, v in data.__dict__.items()}
		elif isinstance(data, dict):
			return {k: IdempotencyManager._serialize_for_mongodb(v) for k, v in data.items()}
		elif isinstance(data, (list, tuple)):
			return [IdempotencyManager._serialize_for_mongodb(item) for item in data]
		elif hasattr(data, '__dict__') and not isinstance(data, (str, int, float, bool, type(None))):
			# Dataclass or other object with __dict__
			return {k: IdempotencyManager._serialize_for_mongodb(v) for k, v in data.__dict__.items()}
		else:
			# Primitive type (str, int, float, bool, None)
			return data

	@staticmethod
	def compute_input_hash(input_data: Any) -> str:
		"""
		Compute stable hash of input data.
		
		Args:
			input_data: Activity input (must be JSON-serializable)
		
		Returns:
			SHA-256 hash of input
		"""
		# Convert to stable JSON string
		json_str = json.dumps(input_data, sort_keys=True, default=str)

		# Compute SHA-256 hash
		hash_obj = hashlib.sha256(json_str.encode('utf-8'))
		return hash_obj.hexdigest()[:16]  # First 16 chars for readability

	@staticmethod
	def generate_idempotency_key(
		workflow_id: str,
		activity_name: str,
		input_hash: str,
	) -> str:
		"""
		Generate idempotency key for activity execution.
		
		Format: {workflow_id}:{activity_name}:{input_hash}
		
		Args:
			workflow_id: Workflow execution ID
			activity_name: Activity name
			input_hash: Hash of activity input
		
		Returns:
			Idempotency key
		"""
		return f"{workflow_id}:{activity_name}:{input_hash}"

	async def check_already_executed(
		self,
		workflow_id: str,
		activity_name: str,
		input_data: Any,
	) -> dict[str, Any] | None:
		"""
		Check if activity already executed with same input.
		
		Args:
			workflow_id: Workflow execution ID
			activity_name: Activity name
			input_data: Activity input
		
		Returns:
			Cached output if found, None otherwise
		"""
		# Compute input hash
		input_hash = self.compute_input_hash(input_data)

		# Generate idempotency key
		idempotency_key = self.generate_idempotency_key(
			workflow_id, activity_name, input_hash
		)

		# Query execution log
		log_entry = await self.collection.find_one({
			'idempotency_key': idempotency_key,
			'success': True,  # Only use successful executions
		})

		if log_entry:
			logger.info(
				f"✅ Found cached result for {activity_name} "
				f"(workflow: {workflow_id}, hash: {input_hash})"
			)
			return log_entry['output_data']

		return None

	async def record_execution(
		self,
		workflow_id: str,
		activity_name: str,
		input_data: Any,
		output_data: dict[str, Any],
		success: bool,
		error: str | None = None,
		attempt: int = 1,
		ttl_hours: int = 720,  # 30 days default
	):
		"""
		Record activity execution in log.
		
		Args:
			workflow_id: Workflow execution ID
			activity_name: Activity name
			input_data: Activity input
			output_data: Activity output
			success: Whether execution succeeded
			error: Error message if failed
			attempt: Retry attempt number
			ttl_hours: Time-to-live in hours
		"""
		# Compute input hash
		input_hash = self.compute_input_hash(input_data)

		# Generate idempotency key
		idempotency_key = self.generate_idempotency_key(
			workflow_id, activity_name, input_hash
		)

		# Create log entry
		# Serialize output_data to ensure MongoDB compatibility
		# (convert Pydantic models, dataclasses, etc. to dicts)
		now = datetime.utcnow()
		log_entry = {
			'idempotency_key': idempotency_key,
			'workflow_id': workflow_id,
			'activity_name': activity_name,
			'input_hash': input_hash,
			'output_data': self._serialize_for_mongodb(output_data),  # Serialize output (handles Pydantic models like ActionDefinition)
			'started_at': now,
			'completed_at': now,
			'success': success,
			'error': error,
			'attempt': attempt,
			'expires_at': now + timedelta(hours=ttl_hours),
		}

		# Upsert (update if exists, insert if not)
		await self.collection.update_one(
			{'idempotency_key': idempotency_key},
			{'$set': log_entry},
			upsert=True,
		)

		logger.info(
			f"✅ Recorded execution for {activity_name} "
			f"(workflow: {workflow_id}, success: {success})"
		)

	async def get_execution_count(self, workflow_id: str) -> int:
		"""
		Get number of completed activities for workflow.
		
		Args:
			workflow_id: Workflow execution ID
		
		Returns:
			Count of completed activities
		"""
		count = await self.collection.count_documents({
			'workflow_id': workflow_id,
			'success': True,
		})
		return count

	async def get_execution_log(
		self,
		workflow_id: str,
		activity_name: str | None = None,
	) -> list[dict[str, Any]]:
		"""
		Get execution log for workflow.
		
		Args:
			workflow_id: Workflow execution ID
			activity_name: Filter by activity name (optional)
		
		Returns:
			List of log entries
		"""
		query = {'workflow_id': workflow_id}
		if activity_name:
			query['activity_name'] = activity_name

		cursor = self.collection.find(query).sort('completed_at', -1)
		return await cursor.to_list(length=None)

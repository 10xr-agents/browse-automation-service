"""
Job Registry for Knowledge Retrieval Jobs

Stores job state and metadata in MongoDB.
All collections use the 'brwsr_auto_svc_' prefix.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from navigator.storage.mongodb import get_collection

logger = logging.getLogger(__name__)


class JobRegistry:
	"""
	MongoDB-based job registry for tracking knowledge retrieval jobs.
	"""
	
	def __init__(self, use_mongodb: bool = True):
		"""
		Initialize job registry.
		
		Args:
			use_mongodb: Whether to use MongoDB (True by default, falls back to in-memory if unavailable)
		"""
		self.use_mongodb = use_mongodb
		self._in_memory_registry: dict[str, dict[str, Any]] = {}
		
		if use_mongodb:
			logger.info("JobRegistry initialized with MongoDB")
		else:
			logger.debug("JobRegistry initialized with in-memory storage")
	
	async def register_job(self, job_id: str, job_data: dict[str, Any]) -> None:
		"""
		Register a new job or update existing job.
		
		Args:
			job_id: Job ID
			job_data: Job data dictionary
		"""
		from datetime import datetime, timezone
		job_document = {
			'job_id': job_id,
			**job_data,
			'created_at': datetime.now(timezone.utc) if 'created_at' not in job_data else job_data.get('created_at'),
			'updated_at': datetime.utcnow(),
		}
		
		if self.use_mongodb:
			try:
				collection = await get_collection('jobs')
				if collection is None:
					# Fallback to in-memory
					self._in_memory_registry[job_id] = job_document
					logger.debug(f"Registered job {job_id} in in-memory (MongoDB unavailable)")
					return
				
				# Upsert by job_id
				await collection.update_one(
					{'job_id': job_id},
					{'$set': job_document},
					upsert=True
				)
				logger.debug(f"Registered job {job_id} in MongoDB")
			except Exception as e:
				logger.error(f"Failed to register job {job_id} in MongoDB: {e}")
				# Fallback to in-memory
				self._in_memory_registry[job_id] = job_document
				logger.debug(f"Registered job {job_id} in in-memory (fallback)")
		else:
			self._in_memory_registry[job_id] = job_document
			logger.debug(f"Registered job {job_id} in in-memory")
	
	async def get_job(self, job_id: str) -> dict[str, Any] | None:
		"""
		Get job data by ID.
		
		Args:
			job_id: Job ID
		
		Returns:
			Job data dictionary or None if not found
		"""
		if self.use_mongodb:
			try:
				collection = await get_collection('jobs')
				if collection is None:
					# Fallback to in-memory
					return self._in_memory_registry.get(job_id)
				
				doc = await collection.find_one({'job_id': job_id})
				if doc:
					doc.pop('_id', None)  # Remove MongoDB _id
					return doc
				return None
			except Exception as e:
				logger.error(f"Failed to get job {job_id} from MongoDB: {e}")
				# Fallback to in-memory
				return self._in_memory_registry.get(job_id)
		else:
			return self._in_memory_registry.get(job_id)
	
	async def update_job(self, job_id: str, updates: dict[str, Any]) -> None:
		"""
		Update job data.
		
		Args:
			job_id: Job ID
			updates: Dictionary with fields to update
		"""
		updates['updated_at'] = datetime.utcnow()
		
		if self.use_mongodb:
			try:
				collection = await get_collection('jobs')
				if collection is None:
					# Fallback to in-memory
					if job_id not in self._in_memory_registry:
						# Initialize job in in-memory if it doesn't exist
						self._in_memory_registry[job_id] = {'job_id': job_id}
					self._in_memory_registry[job_id].update(updates)
					logger.debug(f"Updated job {job_id} in in-memory (MongoDB unavailable)")
					return
				
				await collection.update_one(
					{'job_id': job_id},
					{'$set': updates},
					upsert=True  # Create job if it doesn't exist
				)
				logger.debug(f"Updated job {job_id} in MongoDB")
			except Exception as e:
				logger.error(f"Failed to update job {job_id} in MongoDB: {e}")
				# Fallback to in-memory
				if job_id not in self._in_memory_registry:
					# Initialize job in in-memory if it doesn't exist
					self._in_memory_registry[job_id] = {'job_id': job_id}
				self._in_memory_registry[job_id].update(updates)
				logger.debug(f"Updated job {job_id} in in-memory (fallback)")
		else:
			if job_id not in self._in_memory_registry:
				# Initialize job in in-memory if it doesn't exist
				self._in_memory_registry[job_id] = {'job_id': job_id}
			self._in_memory_registry[job_id].update(updates)
			logger.debug(f"Updated job {job_id} in in-memory")
	
	async def list_jobs(self, status: str | None = None) -> list[dict[str, Any]]:
		"""
		List all jobs, optionally filtered by status.
		
		Args:
			status: Optional status filter
		
		Returns:
			List of job data dictionaries
		"""
		if self.use_mongodb:
			try:
				collection = await get_collection('jobs')
				if collection is None:
					# Fallback to in-memory
					return self._list_from_memory(status)
				
				query = {}
				if status:
					query['status'] = status
				
				cursor = collection.find(query)
				jobs = []
				async for doc in cursor:
					doc.pop('_id', None)  # Remove MongoDB _id
					jobs.append(doc)
				
				return jobs
			except Exception as e:
				logger.error(f"Failed to list jobs from MongoDB: {e}")
				# Fallback to in-memory
				return self._list_from_memory(status)
		else:
			return self._list_from_memory(status)
	
	def _list_from_memory(self, status: str | None = None) -> list[dict[str, Any]]:
		"""List jobs from in-memory storage."""
		jobs = list(self._in_memory_registry.values())
		if status:
			jobs = [job for job in jobs if job.get('status') == status]
		return jobs
	
	async def delete_job(self, job_id: str) -> None:
		"""
		Delete a job.
		
		Args:
			job_id: Job ID
		"""
		if self.use_mongodb:
			try:
				collection = await get_collection('jobs')
				if collection:
					await collection.delete_one({'job_id': job_id})
					logger.debug(f"Deleted job {job_id} from MongoDB")
			except Exception as e:
				logger.error(f"Failed to delete job {job_id} from MongoDB: {e}")
		
		# Also delete from in-memory
		self._in_memory_registry.pop(job_id, None)
		logger.debug(f"Deleted job {job_id} from in-memory")


# Global job registry instance
_job_registry_instance: JobRegistry | None = None


async def get_job_registry() -> JobRegistry:
	"""Get or create global job registry instance."""
	global _job_registry_instance
	if _job_registry_instance is None:
		_job_registry_instance = JobRegistry(use_mongodb=True)
	return _job_registry_instance

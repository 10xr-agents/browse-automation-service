"""
Temporal worker service for knowledge extraction workflows.

The worker polls the task queue and executes workflows and activities.
"""

import asyncio
import logging
from typing import Any

from temporalio.client import Client
from temporalio.worker import Worker

from browser_use import BrowserSession
from browser_use.browser.profile import BrowserProfile
from navigator.knowledge.storage import KnowledgeStorage
from navigator.knowledge.vector_store import VectorStore
from navigator.temporal.activities import (
	discover_links_activity,
	init_activity_dependencies,
	process_page_activity,
	store_link_activity,
)
from navigator.temporal.activities_v2 import (
	build_graph_activity,
	enrich_knowledge_activity,
	extract_actions_activity,
	extract_screens_activity,
	extract_tasks_activity,
	extract_transitions_activity,
	ingest_source_activity,
	init_activity_dependencies_v2,
	verify_extraction_activity,
)
from navigator.temporal.config import TemporalConfig, get_temporal_client
from navigator.temporal.idempotency import IdempotencyManager
from navigator.temporal.workflows import KnowledgeExtractionWorkflow
from navigator.temporal.workflows_v2 import KnowledgeExtractionWorkflowV2

logger = logging.getLogger(__name__)


class TemporalWorkerService:
	"""
	Temporal worker service that runs workflows and activities.
	
	Features:
	- Manages worker lifecycle
	- Initializes activity dependencies (browser session, storage)
	- Handles graceful shutdown
	- Auto-reconnects on connection loss
	- Supports both V1 (legacy) and V2 (upgraded) workflows on a unified task queue
	- Enables gradual migration from V1 to V2 workflows
	"""
	
	def __init__(
		self,
		config: TemporalConfig | None = None,
		browser_session: BrowserSession | None = None,
		storage: KnowledgeStorage | None = None,
		vector_store: VectorStore | None = None,
		enable_v2: bool = True,
	):
		"""
		Initialize Temporal worker service.
		
		Args:
			config: Temporal configuration (uses default from env if None)
			browser_session: Browser session for activities (creates new if None)
			storage: Knowledge storage (creates new if None)
			vector_store: Vector store (creates new if None)
			enable_v2: Enable V2 workflow (default: True)
		"""
		self.config = config or TemporalConfig.from_env()
		self.client: Client | None = None
		self.worker: Worker | None = None
		self.browser_session = browser_session
		self.storage = storage or KnowledgeStorage(use_mongodb=True)
		self.vector_store = vector_store or VectorStore(use_mongodb=True)
		self.enable_v2 = enable_v2
		self.idempotency_manager: IdempotencyManager | None = None
		self._running = False
		self._worker_task: asyncio.Task | None = None
	
	async def start(self):
		"""Start the Temporal worker."""
		if self._running:
			logger.warning("Worker already running")
			return
		
		logger.info("🚀 Starting Temporal worker service...")
		
		# Connect to Temporal
		self.client = await get_temporal_client(self.config)
		
		# Initialize browser session if not provided
		if self.browser_session is None:
			logger.info("📱 Creating browser session for worker...")
			profile = BrowserProfile(
				headless=True,
				disable_security=False,
			)
			self.browser_session = BrowserSession(profile=profile)
			await self.browser_session.start()
			logger.info("✅ Browser session created")
		
		# Initialize activity dependencies (V1)
		init_activity_dependencies(
			browser_session=self.browser_session,
			storage=self.storage,
			vector_store=self.vector_store,
		)
		
		# Initialize idempotency manager (V2)
		if self.enable_v2:
			from navigator.storage.mongodb import get_mongodb_client, get_mongodb_database_name
			
			# Use centralized MongoDB configuration from environment
			mongo_client = await get_mongodb_client()
			if mongo_client is None:
				logger.error("❌ MongoDB client not available - V2 worker requires MongoDB")
				raise RuntimeError("MongoDB connection required for V2 worker")
			
			database_name = get_mongodb_database_name()
			db = mongo_client[database_name]
			
			self.idempotency_manager = IdempotencyManager(db)
			await self.idempotency_manager.ensure_indexes()
			
			init_activity_dependencies_v2(self.idempotency_manager)
			logger.info("✅ V2 dependencies initialized with MongoDB")
		
		# Determine workflows and activities based on version support
		workflows = [KnowledgeExtractionWorkflow]
		activities = [
			discover_links_activity,
			process_page_activity,
			store_link_activity,
		]
		
		# Add V2 workflows and activities if enabled
		if self.enable_v2:
			workflows.append(KnowledgeExtractionWorkflowV2)
			activities.extend([
				ingest_source_activity,
				extract_screens_activity,
				extract_tasks_activity,
				extract_actions_activity,
				extract_transitions_activity,
				build_graph_activity,
				verify_extraction_activity,
				enrich_knowledge_activity,
			])
		
		# Add Phase 7 verification workflow and activities if feature enabled
		from navigator.config import get_feature_flags
		flags = get_feature_flags()
		
		if flags.is_verification_enabled():
			from navigator.temporal.workflows_verification import KnowledgeVerificationWorkflow
			from navigator.temporal.activities_verification import (
				load_knowledge_definitions_activity,
				launch_browser_session_activity,
				verify_screens_activity,
				apply_enrichments_activity,
				generate_verification_report_activity,
				cleanup_browser_session_activity,
			)
			
			workflows.append(KnowledgeVerificationWorkflow)
			activities.extend([
				load_knowledge_definitions_activity,
				launch_browser_session_activity,
				verify_screens_activity,
				apply_enrichments_activity,
				generate_verification_report_activity,
				cleanup_browser_session_activity,
			])
			logger.info("✅ Phase 7 verification enabled (FEATURE_BROWSER_VERIFICATION=true)")
		
		# Create unified worker for both V1 and V2 on the same task queue
		logger.info(f"👷 Creating Temporal worker for task queue: {self.config.knowledge_task_queue}")
		logger.info(f"   Workflows: {[w.__name__ for w in workflows]}")
		logger.info(f"   Activities: {len(activities)} registered")
		
		self.worker = Worker(
			self.client,
			task_queue=self.config.knowledge_task_queue,
			workflows=workflows,
			activities=activities,
		)
		
		# Run worker
		self._running = True
		self._worker_task = asyncio.create_task(self.worker.run())
		
		logger.info("✅ Temporal worker started successfully")
		logger.info(f"   Task queue: {self.config.knowledge_task_queue}")
		logger.info(f"   Namespace: {self.config.namespace}")
		logger.info(f"   V1 support: ✅ (legacy workflows)")
		logger.info(f"   V2 support: {'✅' if self.enable_v2 else '❌'} (upgraded pipeline)")
	
	async def stop(self):
		"""Stop the Temporal worker."""
		if not self._running:
			logger.warning("Worker not running")
			return
		
		logger.info("🛑 Stopping Temporal worker service...")
		
		# Stop worker
		if self.worker:
			self.worker.shutdown()
			logger.info("   Worker shutdown signal sent")
		
		# Wait for worker task to complete
		if self._worker_task:
			try:
				await asyncio.wait_for(self._worker_task, timeout=30.0)
				logger.info("   Worker task completed")
			except asyncio.TimeoutError:
				logger.warning("   Worker task did not complete within timeout")
				self._worker_task.cancel()
		
		# Close browser session if we created it
		if self.browser_session:
			try:
				await self.browser_session.stop()
				logger.info("   Browser session closed")
			except Exception as e:
				logger.error(f"   Error closing browser session: {e}")
		
		self._running = False
		logger.info("✅ Temporal worker stopped")
	
	async def run_until_stopped(self):
		"""Run the worker until explicitly stopped."""
		await self.start()
		
		try:
			# Keep running until worker task completes
			while self._running:
				if self._worker_task is None or self._worker_task.done():
					break
				
				await asyncio.sleep(1)
		finally:
			await self.stop()
	
	def is_running(self) -> bool:
		"""Check if worker is running."""
		return self._running


# Singleton worker instance
_worker_service: TemporalWorkerService | None = None


async def get_worker_service(
	config: TemporalConfig | None = None,
	browser_session: BrowserSession | None = None,
	storage: KnowledgeStorage | None = None,
	vector_store: VectorStore | None = None,
) -> TemporalWorkerService:
	"""
	Get or create the global worker service instance.
	
	Args:
		config: Temporal configuration
		browser_session: Browser session for activities
		storage: Knowledge storage
		vector_store: Vector store
	
	Returns:
		Worker service instance
	"""
	global _worker_service
	
	if _worker_service is None:
		_worker_service = TemporalWorkerService(
			config=config,
			browser_session=browser_session,
			storage=storage,
			vector_store=vector_store,
		)
	
	return _worker_service


async def start_worker(
	config: TemporalConfig | None = None,
	browser_session: BrowserSession | None = None,
	storage: KnowledgeStorage | None = None,
	vector_store: VectorStore | None = None,
):
	"""
	Start the Temporal worker service.
	
	This is a convenience function that creates and starts the worker.
	"""
	worker = await get_worker_service(
		config=config,
		browser_session=browser_session,
		storage=storage,
		vector_store=vector_store,
	)
	
	if not worker.is_running():
		await worker.start()
	
	return worker


async def stop_worker():
	"""Stop the Temporal worker service."""
	global _worker_service
	
	if _worker_service is not None:
		await _worker_service.stop()
		_worker_service = None

"""
Temporal worker service for knowledge extraction workflows.

The worker polls the task queue and executes workflows and activities.
"""

import asyncio
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from browser_use import BrowserSession
from browser_use.browser.profile import BrowserProfile
from navigator.knowledge.storage import KnowledgeStorage
from navigator.knowledge.vector_store import VectorStore
from navigator.temporal.activities import (
	build_graph_activity,
	delete_knowledge_activity,
	enrich_knowledge_activity,
	explore_primary_url_activity,
	extract_actions_activity,
	extract_business_functions_activity,
	extract_screens_activity,
	extract_tasks_activity,
	extract_transitions_activity,
	extract_user_flows_activity,
	extract_workflows_activity,
	ingest_source_activity,
	init_activity_dependencies,
	link_entities_activity,
	verify_extraction_activity,
)
from navigator.temporal.activities_extraction_video import (
	analyze_frames_batch_activity,
	assemble_video_ingestion_activity,
	filter_frames_activity,
	transcribe_video_activity,
)
from navigator.temporal.config import TemporalConfig, get_temporal_client
from navigator.temporal.idempotency import IdempotencyManager
from navigator.temporal.workflows import KnowledgeExtractionWorkflowV2

logger = logging.getLogger(__name__)


class TemporalWorkerService:
	"""
	Temporal worker service that runs workflows and activities.
	
	Features:
	- Manages worker lifecycle
	- Initializes activity dependencies (browser session, storage)
	- Handles graceful shutdown
	- Auto-reconnects on connection loss
	- Runs Knowledge Extraction Workflow V2 on the unified task queue
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
			self.browser_session = BrowserSession(browser_profile=profile)
			await self.browser_session.start()
			logger.info("✅ Browser session created")

		# Initialize idempotency manager for extraction workflows
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

			init_activity_dependencies(self.idempotency_manager)
			logger.info("✅ Extraction workflow dependencies initialized with MongoDB")

		# Add extraction workflows and activities
		workflows = []
		activities = []
		if self.enable_v2:
			workflows.append(KnowledgeExtractionWorkflowV2)
			activities.extend([
				# ========================================================================
				# Phase 1: Source Ingestion Activities
				# ========================================================================
				# Universal ingestion router (handles documents, websites, videos)
				ingest_source_activity,  # Routes to: document analysis, web crawl analysis, or video ingestion

				# ========================================================================
				# Phase 1.5: Video-Specific Sub-Activities (parallelized video processing)
				# ========================================================================
				transcribe_video_activity,  # Video transcription
				filter_frames_activity,  # Video frame filtering and deduplication
				analyze_frames_batch_activity,  # Video frame analysis (batch processing)
				assemble_video_ingestion_activity,  # Video ingestion assembly

				# ========================================================================
				# Phase 2: Website DOM Analysis Activities
				# ========================================================================
				explore_primary_url_activity,  # Primary URL DOM crawl and analysis (authenticated/unauthenticated)

				# ========================================================================
				# Phase 3: Knowledge Extraction Activities
				# ========================================================================
				extract_screens_activity,  # Extract screen definitions
				extract_tasks_activity,  # Extract task definitions
				extract_actions_activity,  # Extract action definitions
				extract_transitions_activity,  # Extract transition definitions
				extract_business_functions_activity,  # Extract business functions (LLM-based)
				extract_workflows_activity,  # Extract operational workflows (LLM-based)
				extract_user_flows_activity,  # Extract user flows (Phase 4: synthesis from all entities)
				link_entities_activity,  # Priority 2: Post-extraction entity linking

				# ========================================================================
				# Phase 4: Graph Construction Activities
				# ========================================================================
				build_graph_activity,  # Build knowledge graph from extracted entities

				# ========================================================================
				# Phase 5: Verification & Enrichment Activities
				# ========================================================================
				verify_extraction_activity,  # Verify extracted knowledge
				enrich_knowledge_activity,  # Enrich knowledge based on verification

				# ========================================================================
				# Phase 0: Cleanup Activities (runs before extraction)
				# ========================================================================
				delete_knowledge_activity,  # Delete existing knowledge before re-extraction
			])

		# Add Phase 7 verification workflow and activities if feature enabled
		from navigator.config import get_feature_flags
		flags = get_feature_flags()

		if flags.is_verification_enabled():
			from navigator.temporal.activities_verification import (
				apply_enrichments_activity,
				cleanup_browser_session_activity,
				generate_verification_report_activity,
				launch_browser_session_activity,
				load_knowledge_definitions_activity,
				verify_screens_activity,
			)
			from navigator.temporal.workflows_verification import KnowledgeVerificationWorkflow

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

		# Create unified worker for knowledge extraction workflows
		logger.info(f"👷 Creating Temporal worker for task queue: {self.config.knowledge_task_queue}")
		logger.info(f"   Workflows: {[w.__name__ for w in workflows]}")
		logger.info(f"   Activities: {len(activities)} registered")

		# Disable sandbox for development (pydantic_settings Path.expanduser issue)
		# Use the unsandboxed runner to avoid Path.expanduser restrictions
		try:
			from temporalio.worker import UnsandboxedWorkflowRunner

			self.worker = Worker(
				self.client,
				task_queue=self.config.knowledge_task_queue,
				workflows=workflows,
				activities=activities,
				workflow_runner=UnsandboxedWorkflowRunner(),
			)
			logger.info("⚠️  Using unsandboxed workflow runner (development mode)")
		except ImportError:
			# Fallback to default runner if UnsandboxedWorkflowRunner not available
			self.worker = Worker(
				self.client,
				task_queue=self.config.knowledge_task_queue,
				workflows=workflows,
				activities=activities,
			)
			logger.warning("⚠️  UnsandboxedWorkflowRunner not available, using default")

		# Run worker
		self._running = True
		self._worker_task = asyncio.create_task(self.worker.run())

		logger.info("✅ Temporal worker started successfully")
		logger.info(f"   Task queue: {self.config.knowledge_task_queue}")
		logger.info(f"   Namespace: {self.config.namespace}")
		logger.info(f"   Knowledge extraction workflows: {'✅' if self.enable_v2 else '❌'}")

	async def stop(self):
		"""Stop the Temporal worker."""
		if not self._running:
			logger.warning("Worker not running")
			return

		logger.info("🛑 Stopping Temporal worker service...")

		# Mark as not running immediately to prevent new work
		self._running = False

		# Stop worker (shutdown is async in some Temporal versions)
		if self.worker:
			try:
				shutdown_result = self.worker.shutdown()
				# Check if it's a coroutine and await it
				if asyncio.iscoroutine(shutdown_result):
					await shutdown_result
				logger.info("   Worker shutdown signal sent")
			except Exception as e:
				logger.warning(f"   Error during worker shutdown: {e}")

		# Wait for worker task to complete with timeout
		if self._worker_task and not self._worker_task.done():
			try:
				await asyncio.wait_for(self._worker_task, timeout=5.0)
				logger.info("   Worker task completed")
			except asyncio.TimeoutError:
				logger.warning("   Worker task timed out, cancelling...")
				self._worker_task.cancel()
				try:
					await self._worker_task
				except asyncio.CancelledError:
					logger.info("   Worker task cancelled")
				except Exception as e:
					logger.warning(f"   Error during task cancellation: {e}")

		# Close browser session if we created it
		if self.browser_session:
			try:
				await asyncio.wait_for(self.browser_session.stop(), timeout=3.0)
				logger.info("   Browser session closed")
			except asyncio.TimeoutError:
				logger.warning("   Browser session close timed out")
			except Exception as e:
				logger.warning(f"   Error closing browser session: {e}")

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

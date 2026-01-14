"""
Temporal activities for Knowledge Extraction Workflow V2.

Activities implement the actual work: ingestion, extraction, graph construction,
verification, and enrichment. Each activity is idempotent and includes retry logic.
"""

import logging
import time
from typing import TYPE_CHECKING, Any

from temporalio import activity

if TYPE_CHECKING:
	from navigator.temporal.idempotency import IdempotencyManager

from navigator.schemas import (
	BuildGraphInput,
	BuildGraphResult,
	EnrichKnowledgeInput,
	EnrichKnowledgeResult,
	ExtractActionsInput,
	ExtractActionsResult,
	ExtractScreensInput,
	ExtractScreensResult,
	ExtractTasksInput,
	ExtractTasksResult,
	ExtractTransitionsInput,
	ExtractTransitionsResult,
	IngestSourceInput,
	IngestSourceResult,
	SourceMetadata,
	SourceType,
	VerifyExtractionInput,
	VerifyExtractionResult,
)

logger = logging.getLogger(__name__)


# Global dependencies (initialized by worker)
_idempotency_manager: Any = None


def init_activity_dependencies_v2(idempotency_manager: Any):
	"""
	Initialize dependencies for V2 activities.
	
	Args:
		idempotency_manager: Idempotency manager for activity deduplication
	"""
	global _idempotency_manager
	_idempotency_manager = idempotency_manager
	logger.info("✅ V2 activity dependencies initialized")


# ============================================================================
# Activity 1: Ingest Source
# ============================================================================

@activity.defn(name="ingest_source_v2")
async def ingest_source_activity(input: IngestSourceInput) -> IngestSourceResult:
	"""
	Ingest source content (documentation, website, or video).
	
	This activity:
	1. Detects source type if not provided
	2. Routes to appropriate ingester
	3. Chunks content if needed
	4. Stores raw content in MongoDB
	5. Returns ingestion metadata
	
	Args:
		input: Ingestion parameters
	
	Returns:
		Ingestion result with metadata
	"""
	start_time = time.time()
	workflow_id = activity.info().workflow_id
	
	# Check idempotency
	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "ingest_source_v2", input
		)
		if cached:
			return IngestSourceResult(**cached)
	
	# Send heartbeat
	activity.heartbeat({"status": "starting", "source": input.source_url})
	
	logger.info(f"📥 Starting ingestion: {input.source_url} (type: {input.source_type})")
	
	try:
		# Get ingestion router
		from navigator.knowledge.ingest import get_ingestion_router
		
		router = get_ingestion_router()
		
		# Send heartbeat
		activity.heartbeat({"status": "ingesting", "source": input.source_url})
		
		# Ingest content using router
		ingestion_result = await router.ingest(
			source_url=input.source_url,
			source_type=input.source_type,
			options=input.options
		)
		
		# Send heartbeat with results
		activity.heartbeat({
			"status": "completed",
			"chunks": ingestion_result.total_chunks,
			"tokens": ingestion_result.total_tokens
		})
		
		# Convert to activity result
		result = IngestSourceResult.from_ingestion_result(ingestion_result)
		
		# Record execution
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"ingest_source_v2",
				input,
				result.__dict__,
				success=True,
			)
		
		processing_time = time.time() - start_time
		logger.info(f"✅ Ingestion completed in {processing_time:.2f}s")
		
		return result
		
	except Exception as e:
		logger.error(f"❌ Ingestion failed: {e}", exc_info=True)
		
		# Record failure
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"ingest_source_v2",
				input,
				{},
				success=False,
				error=str(e),
			)
		
		raise


# ============================================================================
# Activity 2: Extract Screens
# ============================================================================

@activity.defn(name="extract_screens_v2")
async def extract_screens_activity(input: ExtractScreensInput) -> ExtractScreensResult:
	"""
	Extract screen definitions from ingested content.
	
	This activity:
	1. Analyzes content to identify screen descriptions
	2. Extracts screen elements (name, URL patterns, state signatures)
	3. Normalizes to schema format
	4. Stores in staging collection
	
	Args:
		input: Extraction parameters
	
	Returns:
		Extraction result with screen IDs
	"""
	start_time = time.time()
	workflow_id = activity.info().workflow_id
	
	# Check idempotency
	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "extract_screens_v2", input
		)
		if cached:
			return ExtractScreensResult(**cached)
	
	activity.heartbeat({"status": "extracting", "ingestion_id": input.ingestion_id})
	
	logger.info(f"🔍 Extracting screens from: {input.ingestion_id}")
	
	try:
		# Get ingestion result to access content chunks
		# TODO: Load from MongoDB in production
		# For now, use mock content chunks for demonstration
		
		from navigator.schemas import ContentChunk
		from navigator.knowledge.extract import ScreenExtractor
		
		# Create mock content chunks (in production, load from MongoDB)
		content_chunks = [
			ContentChunk(
				chunk_id=f"{input.ingestion_id}_0",
				content="""
				## Agent Creation Screen
				
				Navigate to /agent/create to create a new agent.
				
				You must enter the Agent Name in the text field.
				Click the "Save Changes" button to create the agent.
				
				If the "Delete" button is present, you are in Edit mode, not Create mode.
				The Edit Agent page differs by having a Delete button that indicates editing.
				""",
				chunk_index=0,
				token_count=100,
				chunk_type="documentation"
			)
		]
		
		# Send heartbeat
		activity.heartbeat({"status": "extracting", "chunks": len(content_chunks)})
		
		# Extract screens using ScreenExtractor
		extractor = ScreenExtractor(website_id=input.website_id)
		extraction_result = extractor.extract_screens(content_chunks)
		
		# Send heartbeat with results
		activity.heartbeat({
			"status": "completed",
			"screens": extraction_result.statistics.get('total_screens', 0)
		})
		
		# Convert to activity result
		result = ExtractScreensResult(
			screens_extracted=extraction_result.statistics.get('total_screens', 0),
			screen_ids=[s.screen_id for s in extraction_result.screens],
			success=extraction_result.success,
		)
		
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id, "extract_screens_v2", input, result.__dict__, result.success
			)
		
		processing_time = time.time() - start_time
		logger.info(
			f"✅ Screen extraction completed in {processing_time:.2f}s: "
			f"{result.screens_extracted} screens extracted"
		)
		
		return result
		
	except Exception as e:
		logger.error(f"❌ Screen extraction failed: {e}", exc_info=True)
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id, "extract_screens_v2", input, {}, False, str(e)
			)
		raise


# ============================================================================
# Activity 3: Extract Tasks
# ============================================================================

@activity.defn(name="extract_tasks_v2")
async def extract_tasks_activity(input: ExtractTasksInput) -> ExtractTasksResult:
	"""
	Extract task definitions from ingested content.
	
	This activity:
	1. Identifies task descriptions in content
	2. Extracts steps, preconditions, postconditions
	3. Normalizes to schema format
	4. Stores in staging collection
	"""
	workflow_id = activity.info().workflow_id
	
	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "extract_tasks_v2", input
		)
		if cached:
			return ExtractTasksResult(**cached)
	
	activity.heartbeat({"status": "extracting", "ingestion_id": input.ingestion_id})
	
	try:
		# TODO: Implement task extraction
		result = ExtractTasksResult(tasks_extracted=0, task_ids=[], success=True)
		
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id, "extract_tasks_v2", input, result.__dict__, True
			)
		
		return result
	except Exception as e:
		logger.error(f"❌ Task extraction failed: {e}", exc_info=True)
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id, "extract_tasks_v2", input, {}, False, str(e)
			)
		raise


# ============================================================================
# Activity 4: Extract Actions
# ============================================================================

@activity.defn(name="extract_actions_v2")
async def extract_actions_activity(input: ExtractActionsInput) -> ExtractActionsResult:
	"""Extract action definitions from ingested content."""
	workflow_id = activity.info().workflow_id
	
	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "extract_actions_v2", input
		)
		if cached:
			return ExtractActionsResult(**cached)
	
	activity.heartbeat({"status": "extracting", "ingestion_id": input.ingestion_id})
	
	try:
		# TODO: Implement action extraction
		result = ExtractActionsResult(actions_extracted=0, action_ids=[], success=True)
		
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id, "extract_actions_v2", input, result.__dict__, True
			)
		
		return result
	except Exception as e:
		logger.error(f"❌ Action extraction failed: {e}", exc_info=True)
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id, "extract_actions_v2", input, {}, False, str(e)
			)
		raise


# ============================================================================
# Activity 5: Extract Transitions
# ============================================================================

@activity.defn(name="extract_transitions_v2")
async def extract_transitions_activity(
	input: ExtractTransitionsInput,
) -> ExtractTransitionsResult:
	"""Extract transition definitions from ingested content."""
	workflow_id = activity.info().workflow_id
	
	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "extract_transitions_v2", input
		)
		if cached:
			return ExtractTransitionsResult(**cached)
	
	activity.heartbeat({"status": "extracting", "ingestion_id": input.ingestion_id})
	
	try:
		# TODO: Implement transition extraction
		result = ExtractTransitionsResult(
			transitions_extracted=0, transition_ids=[], success=True
		)
		
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id, "extract_transitions_v2", input, result.__dict__, True
			)
		
		return result
	except Exception as e:
		logger.error(f"❌ Transition extraction failed: {e}", exc_info=True)
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id, "extract_transitions_v2", input, {}, False, str(e)
			)
		raise


# ============================================================================
# Activity 6: Build Graph
# ============================================================================

@activity.defn(name="build_graph_v2")
async def build_graph_activity(input: BuildGraphInput) -> BuildGraphResult:
	"""
	Build knowledge graph in ArangoDB.
	
	This activity:
	1. Creates nodes for screens
	2. Creates edges for transitions
	3. Creates screen groups
	4. Validates graph against schema
	"""
	workflow_id = activity.info().workflow_id
	
	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "build_graph_v2", input
		)
		if cached:
			return BuildGraphResult(**cached)
	
	activity.heartbeat({"status": "building", "nodes": len(input.screen_ids)})
	
	try:
		# TODO: Implement graph construction
		result = BuildGraphResult(
			graph_nodes=0, graph_edges=0, screen_groups=0, success=True
		)
		
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id, "build_graph_v2", input, result.__dict__, True
			)
		
		return result
	except Exception as e:
		logger.error(f"❌ Graph construction failed: {e}", exc_info=True)
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id, "build_graph_v2", input, {}, False, str(e)
			)
		raise


# ============================================================================
# Activity 7: Verify Extraction
# ============================================================================

@activity.defn(name="verify_extraction_v2")
async def verify_extraction_activity(
	input: VerifyExtractionInput,
) -> VerifyExtractionResult:
	"""
	Verify extracted knowledge with browser-based testing.
	
	This activity:
	1. Launches browser session
	2. Replays extracted actions
	3. Captures discrepancies
	4. Generates verification report
	"""
	workflow_id = activity.info().workflow_id
	
	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "verify_extraction_v2", input
		)
		if cached:
			return VerifyExtractionResult(**cached)
	
	activity.heartbeat({"status": "verifying", "screens": len(input.screen_ids)})
	
	try:
		# TODO: Implement browser-based verification
		result = VerifyExtractionResult(
			screens_verified=0,
			discrepancies_found=0,
			discrepancy_ids=[],
			success=True,
		)
		
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id, "verify_extraction_v2", input, result.__dict__, True
			)
		
		return result
	except Exception as e:
		logger.error(f"❌ Verification failed: {e}", exc_info=True)
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id, "verify_extraction_v2", input, {}, False, str(e)
			)
		raise


# ============================================================================
# Activity 8: Enrich Knowledge
# ============================================================================

@activity.defn(name="enrich_knowledge_v2")
async def enrich_knowledge_activity(
	input: EnrichKnowledgeInput,
) -> EnrichKnowledgeResult:
	"""
	Enrich knowledge definitions based on verification results.
	
	This activity:
	1. Analyzes discrepancies
	2. Updates screen/task/action definitions
	3. Fixes selectors and adds fallbacks
	4. Updates reliability metrics
	"""
	workflow_id = activity.info().workflow_id
	
	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "enrich_knowledge_v2", input
		)
		if cached:
			return EnrichKnowledgeResult(**cached)
	
	activity.heartbeat({
		"status": "enriching",
		"discrepancies": len(input.discrepancy_ids),
	})
	
	try:
		# TODO: Implement knowledge enrichment
		result = EnrichKnowledgeResult(
			enrichments_applied=0,
			updated_screen_ids=[],
			updated_task_ids=[],
			success=True,
		)
		
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id, "enrich_knowledge_v2", input, result.__dict__, True
			)
		
		return result
	except Exception as e:
		logger.error(f"❌ Enrichment failed: {e}", exc_info=True)
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id, "enrich_knowledge_v2", input, {}, False, str(e)
			)
		raise

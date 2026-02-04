"""
Extract screens activity for knowledge extraction workflow.

Extracts screen definitions from ingested content.
"""

import logging
import time

from temporalio import activity

from navigator.schemas import ExtractScreensInput, ExtractScreensResult
from navigator.temporal.activities.shared import get_idempotency_manager

logger = logging.getLogger(__name__)


@activity.defn(name="extract_screens")
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
	activity_id = activity.info().activity_id
	_idempotency_manager = get_idempotency_manager()

	# 🚨 AGGRESSIVE LOGGING: Activity start
	logger.info(f"{'='*80}")
	logger.info("🔵 ACTIVITY START: extract_screens")
	logger.info(f"   Workflow ID: {workflow_id}")
	logger.info(f"   Activity ID: {activity_id}")
	logger.info(f"   Ingestion ID: {input.ingestion_id}")
	logger.info(f"   Website ID: {input.website_id}")
	logger.info(f"{'='*80}")

	# Check idempotency
	if _idempotency_manager:
		cached = await _idempotency_manager.check_already_executed(
			workflow_id, "extract_screens", input
		)
		if cached:
			logger.info("♻️  Using cached result from previous execution")
			return ExtractScreensResult(**cached)

	activity.heartbeat({"status": "extracting", "ingestion_id": input.ingestion_id})

	try:
		# 🚨 CRITICAL FIX: Load REAL ingestion result from MongoDB (NOT MOCK DATA!)
		from navigator.knowledge.extract import ScreenExtractor
		from navigator.knowledge.persist.ingestion import get_ingestion_chunks

		# Determine which ingestion IDs to load from
		ingestion_ids_to_load = input.ingestion_ids if input.ingestion_ids else [input.ingestion_id]

		logger.info(f"📥 Loading chunks from {len(ingestion_ids_to_load)} ingestion(s): {ingestion_ids_to_load}")

		# Load chunks from all ingestion results
		all_chunks = []
		for ingestion_id in ingestion_ids_to_load:
			chunks = await get_ingestion_chunks(ingestion_id)
			if chunks:
				all_chunks.extend(chunks)
				logger.info(f"✅ Loaded {len(chunks)} chunks from ingestion: {ingestion_id}")
			else:
				logger.warning(f"⚠️ No chunks found for ingestion: {ingestion_id}")

		content_chunks = all_chunks

		# Validate chunks exist
		if not content_chunks:
			error_msg = (
				f"❌ CRITICAL: No content chunks found for any ingestion: {ingestion_ids_to_load}. "
				f"This indicates ingestion results were not persisted correctly. "
				f"Extraction cannot proceed without source content."
			)
			logger.error(error_msg)
			raise ValueError(error_msg)

		# Extract screens from chunks
		# website_id is required for ScreenExtractor, use input value or default
		website_id = input.website_id or "unknown"
		screen_extractor = ScreenExtractor(
			website_id=website_id,
			confidence_threshold=0.3,  # Priority 9: Auto-reject screens below 0.3 confidence
			knowledge_id=input.knowledge_id  # Priority 9: Enable cross-reference validation
		)
		screens_result = await screen_extractor.extract_screens(content_chunks)

		# Phase 5.2: Enrich screens with spatial information from video frame analyses
		frame_analysis_chunks = [c for c in content_chunks if c.chunk_type == "video_frame_analysis"]
		if frame_analysis_chunks:
			logger.info(f"🎬 Phase 5.2: Enriching screens with spatial info from {len(frame_analysis_chunks)} video frame analyses")
			
			# Extract frame analyses from chunk metadata or parse from content
			frame_analyses = []
			for chunk in frame_analysis_chunks:
				# Try to get raw frame analysis from metadata
				if hasattr(chunk, 'metadata') and chunk.metadata and 'frame_analysis' in chunk.metadata:
					frame_analyses.append(chunk.metadata['frame_analysis'])
				else:
					# Try to parse from formatted content (fallback)
					# Note: This is less reliable, ideally frame_analysis should be in metadata
					logger.debug(f"Frame analysis chunk {chunk.chunk_id} has no metadata.frame_analysis, skipping spatial enrichment for this chunk")
			
			if frame_analyses:
				# Enrich screens with spatial information
				enriched_screens = ScreenExtractor.enrich_screens_with_video_spatial_info(
					screens_result.screens,
					frame_analyses
				)
				screens_result.screens = enriched_screens
				logger.info(f"✅ Phase 5.2: Enriched {len(enriched_screens)} screens with spatial information from video frames")

		# Phase 5.3 / Priority 4: Link documentation screens to web UI screens with fuzzy matching
		documentation_screens = [s for s in screens_result.screens if s.content_type == "documentation"]
		web_ui_screens = [s for s in screens_result.screens if s.content_type == "web_ui" and s.is_actionable]
		
		if documentation_screens and web_ui_screens:
			logger.info(f"🔗 Phase 5.3 / Priority 4: Linking {len(documentation_screens)} documentation screens to {len(web_ui_screens)} web UI screens")
			from navigator.knowledge.persist.cross_references import get_cross_reference_manager
			from difflib import SequenceMatcher
			cross_ref_manager = get_cross_reference_manager()
			
			linked_count = 0
			for doc_screen in documentation_screens:
				best_match = None
				best_similarity = 0.0
				
				doc_name_lower = doc_screen.name.lower().strip()
				
				for web_screen in web_ui_screens:
					web_name_lower = web_screen.name.lower().strip()
					
					# Priority 4: Enhanced matching with fuzzy similarity
					# 1. Exact match or substring match (highest priority)
					if doc_name_lower == web_name_lower:
						best_match = web_screen
						best_similarity = 1.0
						break
					elif doc_name_lower in web_name_lower or web_name_lower in doc_name_lower:
						similarity = 0.9
						if similarity > best_similarity:
							best_match = web_screen
							best_similarity = similarity
					# 2. Word overlap (medium priority)
					elif any(word in web_name_lower for word in doc_name_lower.split() if len(word) > 3):
						# Calculate word overlap ratio
						doc_words = set(doc_name_lower.split())
						web_words = set(web_name_lower.split())
						overlap = len(doc_words & web_words) / max(len(doc_words), len(web_words), 1)
						similarity = 0.5 + (overlap * 0.3)  # 0.5-0.8 range
						if similarity > best_similarity:
							best_match = web_screen
							best_similarity = similarity
					# 3. Fuzzy string matching (lower priority, threshold 0.6)
					else:
						similarity = SequenceMatcher(None, doc_name_lower, web_name_lower).ratio()
						if similarity >= 0.6 and similarity > best_similarity:
							best_match = web_screen
							best_similarity = similarity
				
				# Link if we found a good match
				if best_match and best_similarity >= 0.5:
					# Link documentation screen to web UI screen
					doc_screen.metadata = doc_screen.metadata or {}
					doc_screen.metadata['linked_web_ui_screen_id'] = best_match.screen_id
					doc_screen.metadata['linking_similarity'] = best_similarity
					linked_count += 1
					logger.debug(
						f"Priority 4: Linked documentation screen '{doc_screen.name}' "
						f"to web UI screen '{best_match.name}' (similarity: {best_similarity:.2f})"
					)
			
			if linked_count > 0:
				logger.info(f"✅ Priority 4: Linked {linked_count} documentation screens to web UI screens with fuzzy matching")

		# Persist screens to MongoDB with knowledge_id and job_id
		if screens_result.screens:
			from navigator.knowledge.persist.documents import save_screens
			await save_screens(screens_result.screens, knowledge_id=input.knowledge_id, job_id=input.job_id)
			logger.info(f"💾 Saved {len(screens_result.screens)} screen(s) to MongoDB with knowledge_id={input.knowledge_id}, job_id={input.job_id}")

		# Convert ScreenExtractionResult (Pydantic) to ExtractScreensResult (dataclass) for Temporal
		extract_result = ExtractScreensResult(
			screens_extracted=len(screens_result.screens),
			screen_ids=[s.screen_id for s in screens_result.screens],
			errors=[str(err.get("message", err)) for err in screens_result.errors] if screens_result.errors else [],
			success=screens_result.success,
		)

		# Record execution
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"extract_screens",
				input,
				{
					"screens_extracted": extract_result.screens_extracted,
					"screen_ids": extract_result.screen_ids,
					"errors": extract_result.errors,
					"success": extract_result.success,
				},
				success=True,
			)

		return extract_result

	except Exception as e:
		logger.error(f"❌ Screen extraction failed: {e}", exc_info=True)

		# Record failure
		if _idempotency_manager:
			await _idempotency_manager.record_execution(
				workflow_id,
				"extract_screens",
				input,
				{},
				success=False,
				error=str(e),
			)

		raise

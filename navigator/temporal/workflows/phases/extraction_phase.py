"""
Phase 2: Knowledge Extraction

Extracts screens, tasks, actions, transitions, business functions, and workflows
from ingested content across multiple source types.
"""

from urllib.parse import urlparse

from temporalio import workflow

# Import activities and schemas - wrap ALL imports
with workflow.unsafe.imports_passed_through():
	from navigator.schemas import (
		ExtractActionsInput,
		ExtractActionsResult,
		ExtractBusinessFunctionsInput,
		ExtractBusinessFunctionsResult,
		ExtractScreensInput,
		ExtractScreensResult,
		ExtractTasksInput,
		ExtractTasksResult,
		ExtractTransitionsInput,
		ExtractTransitionsResult,
		ExtractUserFlowsInput,
		ExtractUserFlowsResult,
		ExtractWorkflowsInput,
		ExtractWorkflowsResult,
		IngestSourceResult,
		KnowledgeExtractionInputV2,
		KnowledgeExtractionProgressV2,
		KnowledgeExtractionResultV2,
		LinkEntitiesInput,
		LinkEntitiesResult,
		WorkflowPhase,
	)
	from navigator.schemas.temporal import DeleteKnowledgeInput, DeleteKnowledgeResult
	from navigator.temporal.activities import (
		delete_knowledge_activity,
		extract_actions_activity,
		extract_business_functions_activity,
		extract_screens_activity,
		extract_tasks_activity,
		extract_transitions_activity,
		extract_user_flows_activity,
		extract_workflows_activity,
		link_entities_activity,
	)


async def execute_extraction_phase(
	input: KnowledgeExtractionInputV2,
	result: KnowledgeExtractionResultV2,
	progress: KnowledgeExtractionProgressV2,
	ingest_results: list[IngestSourceResult],
	ingest_result: IngestSourceResult,
	activity_options: dict,
	check_pause_or_cancel,
) -> tuple[ExtractScreensResult, ExtractTasksResult, ExtractActionsResult, ExtractTransitionsResult]:
	"""
	Execute Phase 2: Knowledge Extraction.
	
	Extracts:
	- Screens (from web/DOM sources)
	- Tasks (from all sources)
	- Actions (from all sources)
	- Transitions (from all sources)
	- Business functions (from video/documentation)
	- Workflows (from video/documentation)
	
	Args:
		input: Workflow input parameters
		result: Workflow result object to update
		progress: Progress tracking object
		ingest_results: List of all ingestion results
		ingest_result: Primary ingestion result (for backward compatibility)
		activity_options: Activity execution options
		check_pause_or_cancel: Function to check for pause/cancel
	
	Returns:
		Tuple of (screens_result, tasks_result, actions_result, transitions_result)
		for use in subsequent phases
	"""
	progress.phase = WorkflowPhase.EXTRACTION
	await check_pause_or_cancel()

	workflow.logger.info("🔍 Phase 2: Extracting knowledge...")

	# If knowledge_id is provided and exists, delete old knowledge before extracting new
	# This allows resyncing/re-extracting to replace existing knowledge
	# NOTE: Must use activity, not direct DB call (Temporal workflows can't call async DB operations)
	if input.knowledge_id:
		deletion_result: DeleteKnowledgeResult = await workflow.execute_activity(
			delete_knowledge_activity,
			DeleteKnowledgeInput(knowledge_id=input.knowledge_id),
			**activity_options,
		)

		if deletion_result.success:
			if deletion_result.total_deleted > 0:
				workflow.logger.info(
					f"🗑️  Deleted {deletion_result.total_deleted} existing knowledge entity(ies) for knowledge_id={input.knowledge_id} "
					f"before extracting new knowledge (resync/replacement mode)"
				)
			else:
				workflow.logger.info(
					f"ℹ️  No existing knowledge found for knowledge_id={input.knowledge_id} (first extraction)"
				)
		else:
			workflow.logger.warning(
				f"⚠️  Failed to delete existing knowledge for knowledge_id={input.knowledge_id}: {deletion_result.errors}. "
				f"Continuing with extraction anyway (new knowledge will be added)."
			)

	# Extract website_id from primary source_url (or aggregate if multiple)
	# For mixed assets, use the first source's domain or a common identifier
	if input.source_url:
		website_id = urlparse(input.source_url).netloc
	else:
		# Use input source_urls if available, otherwise default
		if input.source_urls and len(input.source_urls) > 0:
			first_url = input.source_urls[0]
			website_id = urlparse(first_url).netloc if first_url.startswith('http') else "mixed-assets"
		else:
			website_id = "unknown"

	# Aggregate all ingestion IDs for knowledge extraction
	# This allows extraction to merge knowledge from all sources (files, videos, websites)
	all_ingestion_ids = [r.ingestion_id for r in ingest_results]

	# Calculate asset type counts for logging
	video_count = sum(1 for r in ingest_results if r.source_type in ['video_walkthrough', 'video'])
	docs_count = sum(1 for r in ingest_results if r.source_type in ['technical_documentation', 'documentation'])
	website_count = sum(1 for r in ingest_results if r.source_type in ['website_documentation', 'website'])

	workflow.logger.info(
		f"🔍 Extracting knowledge from {len(all_ingestion_ids)} ingestion(s) "
		f"(mixed asset types: {video_count} video, {docs_count} docs, {website_count} websites). "
		f"Knowledge will be merged and deduplicated across all sources to create comprehensive knowledge base."
	)

	# Extract screens
	progress.current_activity = "extract_screens"
	screens_result: ExtractScreensResult = await workflow.execute_activity(
		extract_screens_activity,
		ExtractScreensInput(
			ingestion_id=ingest_result.ingestion_id,  # Primary (for backward compatibility)
			job_id=input.job_id,
			website_id=website_id,
			ingestion_ids=all_ingestion_ids if len(all_ingestion_ids) > 1 else None,
			knowledge_id=input.knowledge_id,  # Pass knowledge_id for persistence
		),
		**activity_options,
	)

	result.screens_extracted = screens_result.screens_extracted
	progress.screens_extracted = screens_result.screens_extracted

	# 🚨 CRITICAL VALIDATION: Fail loudly if zero screens extracted
	# EXCEPTION: Videos don't produce "screens" like web/DOM sources, so 0 screens is expected for video-only sources
	if screens_result.screens_extracted == 0:
		# Check if all sources are videos - if so, 0 screens is expected and acceptable
		if video_count > 0 and docs_count == 0 and website_count == 0:
			workflow.logger.warning(
				"⚠️ Screen extraction returned 0 screens for video-only source(s). "
				"This is expected - videos produce frame analysis and actions, not DOM screens. "
				"Continuing with knowledge extraction (tasks, actions, workflows will still be extracted from video content)."
			)
		else:
			# Non-video sources (docs/websites) should produce screens
			error_msg = (
				f"❌ CRITICAL: Screen extraction returned 0 screens for job {input.job_id}! "
				f"This indicates a silent extraction failure. "
				f"Ingestion ID: {ingest_result.ingestion_id}. "
				f"Source: {input.source_url}. "
				f"Either the source has no screens, extraction logic failed, or "
				f"content chunks were not loaded correctly. "
				f"Workflow cannot continue with empty extraction results."
			)
			workflow.logger.error(error_msg)
			raise Exception(error_msg)

	workflow.logger.info(
		f"✅ Screen extraction validation passed: {screens_result.screens_extracted} screens"
	)

	# Extract tasks (load from all ingestion results if multiple files)
	progress.current_activity = "extract_tasks"
	tasks_result: ExtractTasksResult = await workflow.execute_activity(
		extract_tasks_activity,
		ExtractTasksInput(
			ingestion_id=ingest_result.ingestion_id,
			job_id=input.job_id,
			website_id=website_id,
			ingestion_ids=all_ingestion_ids if len(all_ingestion_ids) > 1 else None,
			knowledge_id=input.knowledge_id,  # Pass knowledge_id for persistence
		),
		**activity_options,
	)

	result.tasks_extracted = tasks_result.tasks_extracted
	progress.tasks_extracted = tasks_result.tasks_extracted

	# Extract actions (load from all ingestion results if multiple files)
	progress.current_activity = "extract_actions"
	actions_result: ExtractActionsResult = await workflow.execute_activity(
		extract_actions_activity,
		ExtractActionsInput(
			ingestion_id=ingest_result.ingestion_id,
			job_id=input.job_id,
			website_id=website_id,
			ingestion_ids=all_ingestion_ids if len(all_ingestion_ids) > 1 else None,
			knowledge_id=input.knowledge_id,  # Pass knowledge_id for persistence
		),
		**activity_options,
	)

	result.actions_extracted = actions_result.actions_extracted
	progress.actions_extracted = actions_result.actions_extracted

	# Extract transitions (load from all ingestion results if multiple files)
	progress.current_activity = "extract_transitions"
	transitions_result: ExtractTransitionsResult = await workflow.execute_activity(
		extract_transitions_activity,
		ExtractTransitionsInput(
			ingestion_id=ingest_result.ingestion_id,
			job_id=input.job_id,
			website_id=website_id,
			ingestion_ids=all_ingestion_ids if len(all_ingestion_ids) > 1 else None,
			knowledge_id=input.knowledge_id,  # Pass knowledge_id for persistence
		),
		**activity_options,
	)

	result.transitions_extracted = transitions_result.transitions_extracted

	# Extract business functions and workflows from all asset types
	# Check if we have any assets that support business function extraction
	# (video, documentation files, or crawled documentation sites)
	has_extractable_content = any(
		r.source_type in ['video_walkthrough', 'video', 'technical_documentation',
		                  'documentation', 'website_documentation', 'website']
		for r in ingest_results
	)

	if has_extractable_content:
		progress.current_activity = "extract_business_functions"
		business_functions_result: ExtractBusinessFunctionsResult = await workflow.execute_activity(
			extract_business_functions_activity,
			ExtractBusinessFunctionsInput(
				ingestion_id=ingest_result.ingestion_id,
				job_id=input.job_id,
				website_id=website_id,
				ingestion_ids=all_ingestion_ids if len(all_ingestion_ids) > 1 else None,
				knowledge_id=input.knowledge_id,  # Pass knowledge_id for persistence
			),
			**activity_options,
		)

		result.business_functions_extracted = business_functions_result.business_functions_extracted
		progress.business_functions_extracted = business_functions_result.business_functions_extracted

		workflow.logger.info(
			f"✅ Business functions extracted: {result.business_functions_extracted}"
		)

		# Extract workflows (video and documentation)
		# Enable for both video and documentation files to extract operational workflows
		progress.current_activity = "extract_workflows"
		workflows_result: ExtractWorkflowsResult = await workflow.execute_activity(
			extract_workflows_activity,
			ExtractWorkflowsInput(
				ingestion_id=ingest_result.ingestion_id,
				job_id=input.job_id,
				website_id=website_id,
				business_function=None,  # Extract all workflows
				ingestion_ids=all_ingestion_ids if len(all_ingestion_ids) > 1 else None,
				knowledge_id=input.knowledge_id,  # Pass knowledge_id for persistence
			),
			**activity_options,
		)

		result.workflows_extracted = workflows_result.workflows_extracted
		progress.workflows_extracted = workflows_result.workflows_extracted

		workflow.logger.info(
			f"✅ Workflows extracted: {result.workflows_extracted}"
		)

	# Extract user flows (Phase 4: User Flow Extraction & Synthesis)
	# This synthesizes user flows from all extracted entities (screens, workflows, transitions, etc.)
	progress.current_activity = "extract_user_flows"
	user_flows_result: ExtractUserFlowsResult = await workflow.execute_activity(
		extract_user_flows_activity,
		ExtractUserFlowsInput(
			job_id=input.job_id,
			knowledge_id=input.knowledge_id,
			website_id=website_id,
		),
		**activity_options,
	)

	# Note: user_flows_extracted is not in KnowledgeExtractionResultV2 yet
	# For now, we'll log it
	workflow.logger.info(
		f"✅ User flows extracted: {user_flows_result.user_flows_extracted} "
		f"(Phase 4: User Flow Extraction & Synthesis)"
	)

	# Log extraction summary with deduplication note
	extraction_summary = (
		f"✅ Extraction completed from {len(ingest_results)} asset(s): "
		f"{result.screens_extracted} screens, "
		f"{result.tasks_extracted} tasks, "
		f"{result.actions_extracted} actions, "
		f"{result.transitions_extracted} transitions"
	)

	if hasattr(result, 'business_functions_extracted') and result.business_functions_extracted > 0:
		extraction_summary += f", {result.business_functions_extracted} business functions"

	if hasattr(result, 'workflows_extracted') and result.workflows_extracted > 0:
		extraction_summary += f", {result.workflows_extracted} workflows"

	extraction_summary += ". Knowledge merged and deduplicated across all sources."

	workflow.logger.info(extraction_summary)

	# ================================================================
	# Phase 2.5: Post-Extraction Entity Linking (Priority 2)
	# ================================================================
	
	progress.current_activity = "link_entities"
	workflow.logger.info("🔗 Phase 2.5: Linking entities...")
	
	link_result: LinkEntitiesResult = await workflow.execute_activity(
		link_entities_activity,
		LinkEntitiesInput(
			knowledge_id=input.knowledge_id,
			job_id=input.job_id,
		),
		**activity_options,
	)
	
	workflow.logger.info(
		f"✅ Entity linking complete: "
		f"{link_result.tasks_linked} tasks, {link_result.actions_linked} actions, "
		f"{link_result.business_functions_linked} business functions, "
		f"{link_result.workflows_linked} workflows, {link_result.transitions_linked} transitions linked"
	)
	
	if link_result.errors:
		workflow.logger.warning(f"⚠️ Entity linking had {len(link_result.errors)} errors: {link_result.errors}")

	# Return result objects for use in subsequent phases
	return (screens_result, tasks_result, actions_result, transitions_result)

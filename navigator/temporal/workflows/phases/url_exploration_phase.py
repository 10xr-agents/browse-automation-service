"""
Phase 3.5: URL Exploration

Performs DOM-level analysis on websites with authentication support.
Explores multiple URLs in parallel to discover additional screens and actions.
"""

import asyncio
from datetime import timedelta

from temporalio import workflow

# Import activities and schemas - wrap ALL imports
with workflow.unsafe.imports_passed_through():
	from navigator.schemas import (
		ExplorePrimaryUrlInput,
		ExplorePrimaryUrlResult,
		ExtractActionsResult,
		ExtractScreensResult,
		ExtractTasksResult,
		KnowledgeExtractionInputV2,
		KnowledgeExtractionProgressV2,
		KnowledgeExtractionResultV2,
		WorkflowPhase,
	)
	from navigator.temporal.activities import explore_primary_url_activity


async def execute_url_exploration_phase(
	input: KnowledgeExtractionInputV2,
	result: KnowledgeExtractionResultV2,
	progress: KnowledgeExtractionProgressV2,
	screens_result: ExtractScreensResult,
	tasks_result: ExtractTasksResult,
	actions_result: ExtractActionsResult,
	website_id: str,
	activity_options: dict,
	check_pause_or_cancel,
) -> None:
	"""
	Execute Phase 3.5: URL Exploration.
	
	Performs DOM-level analysis on website(s) with authentication.
	Supports multiple URLs for parallel exploration.
	
	Args:
		input: Workflow input parameters
		result: Workflow result object to update
		progress: Progress tracking object
		screens_result: Screen extraction results
		tasks_result: Task extraction results
		actions_result: Action extraction results
		website_id: Website identifier
		activity_options: Activity execution options
		check_pause_or_cancel: Function to check for pause/cancel
	"""
	# Phase 2: DOM-level analysis on website(s) with authentication
	# Support multiple website URLs for exploration
	website_urls: list[str] = []

	# Check for single website_url (backward compatible)
	website_url = input.options.get('website_url') if input.options else None
	if website_url:
		website_urls.append(website_url)

	# Check for multiple website_urls (new feature)
	website_urls_list = input.options.get('website_urls') if input.options else None
	if website_urls_list and isinstance(website_urls_list, list):
		website_urls.extend(website_urls_list)
		# Remove duplicates while preserving order
		seen = set()
		website_urls = [url for url in website_urls if url not in seen and not seen.add(url)]

	if website_urls:
		progress.phase = WorkflowPhase.EXTRACTION  # Keep in extraction phase
		progress.current_activity = "explore_primary_url"
		await check_pause_or_cancel()

		workflow.logger.info(
			f"🌐 Phase 2: Performing DOM-level analysis on {len(website_urls)} website(s): "
			f"{', '.join(website_urls[:3])}{'...' if len(website_urls) > 3 else ''}"
		)

		# Extract credentials from options if provided (for authenticated login)
		credentials = input.options.get('credentials') if input.options else None
		if credentials:
			workflow.logger.info("🔐 Credentials provided - will perform authenticated login before DOM analysis")

		# Process multiple URLs in parallel (up to 3 at a time to avoid overwhelming)
		exploration_results: list[ExplorePrimaryUrlResult] = []
		batch_size = 3

		for batch_start in range(0, len(website_urls), batch_size):
			batch_urls = website_urls[batch_start:batch_start + batch_size]
			batch_num = (batch_start // batch_size) + 1
			total_batches = (len(website_urls) + batch_size - 1) // batch_size

			workflow.logger.info(
				f"📦 Processing URL exploration batch {batch_num}/{total_batches} "
				f"({len(batch_urls)} URL(s))"
			)

			await workflow.sleep(timedelta(seconds=0))

			# Process batch in parallel using workflow.execute_activity with asyncio.gather
			# This pattern works reliably: create coroutines and gather them
			activity_tasks = [
				workflow.execute_activity(
					explore_primary_url_activity,
					ExplorePrimaryUrlInput(
						job_id=input.job_id,
						primary_url=url,
						website_id=website_id,
						credentials=credentials,
						max_pages=input.options.get('max_pages', input.options.get('exploration_max_pages', 10)) if input.options else 10,
						max_depth=input.options.get('max_depth', input.options.get('exploration_max_depth', 3)) if input.options else 3,
						screen_ids=screens_result.screen_ids,
						task_ids=tasks_result.task_ids,
						action_ids=actions_result.action_ids,
						knowledge_id=input.knowledge_id,  # Pass knowledge_id for persistence
					),
					**activity_options,
				)
				for url in batch_urls
			]

			# Wait for all activities to complete
			batch_results = await asyncio.gather(
				*activity_tasks,
				return_exceptions=True
			)

			# Process batch results
			for url, batch_result in zip(batch_urls, batch_results):
				if isinstance(batch_result, Exception):
					workflow.logger.error(f"❌ URL exploration failed for {url}: {batch_result}")
					continue

				# Type narrowing: we know it's not an Exception at this point
				if not isinstance(batch_result, ExplorePrimaryUrlResult):
					workflow.logger.error(
						f"❌ Unexpected result type for {url}: {type(batch_result)}"
					)
					continue

				explore_result: ExplorePrimaryUrlResult = batch_result
				exploration_results.append(explore_result)

				if explore_result.success:
					workflow.logger.info(
						f"✅ URL exploration completed for {url}: "
						f"{explore_result.pages_explored} pages explored, "
						f"{explore_result.new_screens_found} new screens, "
						f"{explore_result.new_actions_found} new actions"
					)
				else:
					workflow.logger.warning(
						f"⚠️ URL exploration had issues for {url}: {explore_result.errors}"
					)

		# Aggregate results from all URL explorations
		if exploration_results:
			total_pages = sum(r.pages_explored for r in exploration_results)
			total_forms = sum(r.forms_identified for r in exploration_results)
			total_new_screens = sum(r.new_screens_found for r in exploration_results)
			total_new_actions = sum(r.new_actions_found for r in exploration_results)
			any_login_successful = any(r.login_successful for r in exploration_results)

			workflow.logger.info(
				f"✅ Phase 2 DOM analysis completed across {len(exploration_results)} website(s): "
				f"{total_pages} total pages explored, "
				f"{total_forms} forms identified, "
				f"{total_new_screens} new screens found, "
				f"{total_new_actions} new actions found"
			)
			if any_login_successful:
				workflow.logger.info("✅ Login successful for at least one website - authenticated DOM analysis completed")

			# Update extraction counts with aggregated findings
			result.screens_extracted += total_new_screens
			result.actions_extracted += total_new_actions
			result.pages_explored = total_pages
			result.forms_identified = total_forms
			result.new_screens_from_exploration = total_new_screens
			result.new_actions_from_exploration = total_new_actions
			result.login_successful = any_login_successful
	else:
		workflow.logger.info(
			"ℹ️  No website_url(s) provided in options - skipping Phase 2 DOM analysis "
			"(only Phase 1 file/documentation processing was performed)"
		)

	# Legacy: Keep old primary URL exploration if website_url(s) not provided but we have a non-file primary URL
	legacy_primary_url = input.source_url if input.source_url and not input.source_url.startswith('file://') else None
	if legacy_primary_url and not website_urls:
		progress.phase = WorkflowPhase.EXTRACTION
		progress.current_activity = "explore_primary_url"
		await check_pause_or_cancel()

		workflow.logger.info(f"🌐 Legacy: Exploring primary URL to enrich knowledge: {legacy_primary_url}")

		credentials = input.options.get('credentials') if input.options else None

		explore_result: ExplorePrimaryUrlResult = await workflow.execute_activity(
			explore_primary_url_activity,
			ExplorePrimaryUrlInput(
				job_id=input.job_id,
				primary_url=legacy_primary_url,
				website_id=website_id,
				credentials=credentials,
				max_pages=input.options.get('exploration_max_pages', 10) if input.options else 10,
				max_depth=input.options.get('exploration_max_depth', 3) if input.options else 3,
				screen_ids=screens_result.screen_ids,
				task_ids=tasks_result.task_ids,
				action_ids=actions_result.action_ids,
				knowledge_id=input.knowledge_id,  # Pass knowledge_id for persistence
			),
			**activity_options,
		)

		if explore_result.success:
			workflow.logger.info(
				f"✅ Primary URL exploration completed: "
				f"{explore_result.pages_explored} pages explored, "
				f"{explore_result.forms_identified} forms identified, "
				f"{explore_result.new_screens_found} new screens found, "
				f"{explore_result.new_actions_found} new actions found"
			)
			if explore_result.login_successful:
				workflow.logger.info("✅ Login successful - authenticated exploration completed")

			result.screens_extracted += explore_result.new_screens_found
			result.actions_extracted += explore_result.new_actions_found
			result.pages_explored = explore_result.pages_explored
			result.forms_identified = explore_result.forms_identified
			result.new_screens_from_exploration = explore_result.new_screens_found
			result.new_actions_from_exploration = explore_result.new_actions_found
			result.login_successful = explore_result.login_successful
		else:
			workflow.logger.warning(
				f"⚠️ Primary URL exploration had issues: {explore_result.errors}"
			)
	elif not legacy_primary_url and not website_url:
		workflow.logger.info(
			"ℹ️ Skipping primary URL exploration (no primary URL or file-only ingestion)"
		)

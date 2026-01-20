"""
Phase 1: Source Ingestion

Handles ingestion of multiple source types (videos, documentation, websites)
with parallel processing support and auto-detection of source types.
"""

import asyncio
from datetime import timedelta

from temporalio import workflow

# Import activities and schemas - wrap ALL imports
with workflow.unsafe.imports_passed_through():
	from navigator.schemas import (
		IngestSourceInput,
		IngestSourceResult,
		KnowledgeExtractionInputV2,
		KnowledgeExtractionProgressV2,
		KnowledgeExtractionResultV2,
		WorkflowPhase,
	)
	from navigator.temporal.activities import ingest_source_activity
	from navigator.temporal.workflows.helpers.source_detection import detect_source_type
	from navigator.temporal.workflows.helpers.video_processing import ingest_video_with_sub_activities


async def execute_ingestion_phase(
	input: KnowledgeExtractionInputV2,
	result: KnowledgeExtractionResultV2,
	progress: KnowledgeExtractionProgressV2,
	activity_options: dict,
	check_pause_or_cancel,
) -> list[IngestSourceResult]:
	"""
	Execute Phase 1: Source Ingestion.
	
	Handles:
	- Multiple source types (videos, documentation, websites)
	- Auto-detection of source types
	- Parallel processing of multiple sources
	- Single source backward compatibility
	
	Args:
		input: Workflow input parameters
		result: Workflow result object to update
		progress: Progress tracking object
		activity_options: Activity execution options
		check_pause_or_cancel: Function to check for pause/cancel
	
	Returns:
		List of ingestion results from all sources
	"""
	# 🐛 DEBUG: Log first phase start
	workflow.logger.debug("=" * 80)
	workflow.logger.debug("🐛 DEBUG: Starting Phase 1: Ingestion")
	workflow.logger.debug("   This is the FIRST PHASE of the workflow")
	workflow.logger.debug("   Will call: ingest_source_activity")
	workflow.logger.debug("=" * 80)

	progress.phase = WorkflowPhase.INGESTION
	progress.current_activity = "ingest_source"
	await check_pause_or_cancel()

	# Determine if we have multiple assets to process (files, videos, websites)
	sources_to_process: list[tuple[str, str | None, str | None]] = []  # (url, name, detected_type)

	if input.source_urls and len(input.source_urls) > 1:
		# Multiple assets - auto-detect type for each
		source_names = input.source_names or [None] * len(input.source_urls)
		sources_to_process = []
		for url, name in zip(input.source_urls, source_names):
			# Auto-detect source type for each asset
			detected_type = detect_source_type(url, input.source_type)
			sources_to_process.append((url, name, detected_type))
		workflow.logger.info(
			f"📥 Phase 1: Processing {len(sources_to_process)} mixed asset(s) "
			f"(auto-detecting type for each)..."
		)
	else:
		# Single source (backward compatible)
		detected_type = detect_source_type(input.source_url, input.source_type)
		sources_to_process = [(input.source_url, input.source_name, detected_type)]
		workflow.logger.info(f"📥 Phase 1: Ingesting source (type: {detected_type})...")

	# Process all sources with their detected types
	ingest_results: list[IngestSourceResult] = []
	total_chunks = 0
	asset_type_counts: dict[str, int] = {}  # Track counts by type

	# If we have multiple sources, process them in parallel (up to 5 at a time to avoid overwhelming)
	# For single source, process sequentially
	if len(sources_to_process) > 1:
		workflow.logger.info(
			f"⚡ Processing {len(sources_to_process)} sources in parallel batches "
			f"(max 5 concurrent to avoid resource exhaustion)"
		)

		# Process in batches of 5 to avoid overwhelming the system
		batch_size = 5
		for batch_start in range(0, len(sources_to_process), batch_size):
			batch = sources_to_process[batch_start:batch_start + batch_size]
			batch_num = (batch_start // batch_size) + 1
			total_batches = (len(sources_to_process) + batch_size - 1) // batch_size

			workflow.logger.info(
				f"📦 Processing batch {batch_num}/{total_batches} "
				f"({len(batch)} source(s))"
			)

			# Yield control before starting batch
			await workflow.sleep(timedelta(seconds=0))

			# Process batch in parallel
			# Mix of workflow methods (videos) and activities (docs/websites)
			all_tasks = []
			batch_metadata = []  # Track metadata for each item in batch

			for idx, (source_url, source_name, detected_type) in enumerate(batch):
				global_idx = batch_start + idx
				file_num = f"{global_idx + 1}/{len(sources_to_process)}"

				# Store metadata for result processing
				batch_metadata.append((source_url, source_name, detected_type, file_num))

				# For video sources, use workflow method (async workflow code)
				if detected_type in ['video', 'video_walkthrough']:
					task = ingest_video_with_sub_activities(
						source_url=source_url,
						source_name=source_name,
						job_id=input.job_id,
						options=input.options,
						activity_options=activity_options,
					)
				else:
					# For non-video sources, use workflow.execute_activity (simpler and reliable)
					task = workflow.execute_activity(
						ingest_source_activity,
						IngestSourceInput(
							source_url=source_url,
							source_type=detected_type,
							job_id=input.job_id,
							source_name=source_name,
							options=input.options,
						),
						**activity_options,
					)

				all_tasks.append((task, source_url, source_name, detected_type, file_num))

			# Wait for all tasks to complete (both workflow methods and activities)
			# Use asyncio.gather with all tasks
			task_results = await asyncio.gather(
				*[task for task, _, _, _, _ in all_tasks],
				return_exceptions=True
			)

			# Combine results in order
			batch_results = [
				(result, source_url, source_name, detected_type, file_num)
				for (_, source_url, source_name, detected_type, file_num), result
				in zip(all_tasks, task_results)
			]

			# Process batch results
			for batch_result_item, source_url, source_name, detected_type, file_num in batch_results:
				if isinstance(batch_result_item, Exception):
					workflow.logger.error(
						f"❌ Ingestion failed for asset {file_num} ({detected_type}): {batch_result_item}"
					)
					continue

				# Type narrowing: we know it's not an Exception at this point
				if not isinstance(batch_result_item, IngestSourceResult):
					workflow.logger.error(
						f"❌ Unexpected result type for asset {file_num}: {type(batch_result_item)}"
					)
					continue

				ingest_result: IngestSourceResult = batch_result_item

				# Track asset types
				asset_type_counts[detected_type] = asset_type_counts.get(detected_type, 0) + 1

				# Handle errors
				if not ingest_result.success and ingest_result.content_chunks == 0:
					workflow.logger.warning(
						f"⚠️ Ingestion failed for asset {file_num} ({detected_type}): {ingest_result.errors}. "
						f"No chunks produced. Continuing with other assets..."
					)
					continue
				elif not ingest_result.success and ingest_result.content_chunks > 0:
					workflow.logger.warning(
						f"⚠️ Ingestion had non-fatal errors for asset {file_num} ({detected_type}): {ingest_result.errors}. "
						f"But {ingest_result.content_chunks} chunks were produced - treating as successful."
					)

				ingest_results.append(ingest_result)
				total_chunks += ingest_result.content_chunks

				workflow.logger.info(
					f"✅ Asset {file_num} ({detected_type}) ingested: {ingest_result.content_chunks} chunks"
				)
	else:
		# Single source - process sequentially (backward compatible)
		if not sources_to_process or len(sources_to_process) == 0:
			error_msg = "❌ No sources to process - source_url and source_urls are both empty or invalid"
			workflow.logger.error(error_msg)
			raise Exception(error_msg)
		
		source_url, source_name, detected_type = sources_to_process[0]
		file_num = ""

		await check_pause_or_cancel()
		await workflow.sleep(timedelta(seconds=0))

		workflow.logger.info(
			f"📄 Processing asset ({detected_type}): {source_name or source_url}"
		)

		# Track asset types
		if detected_type:
			asset_type_counts[detected_type] = asset_type_counts.get(detected_type, 0) + 1

		# Log processing details based on type
		if detected_type in ['video', 'video_walkthrough']:
			workflow.logger.info(
				"🎥 Video asset detected - comprehensive processing enabled: "
				"transcription, frame analysis, action extraction, OCR, subtitles"
			)
		elif detected_type in ['website', 'website_documentation']:
			workflow.logger.info(
				"🌐 Website asset detected - will use Crawl4AI or Browser-Use crawler"
			)
		elif detected_type in ['documentation', 'technical_documentation']:
			workflow.logger.info(
				"📄 Documentation asset detected - comprehensive feature extraction enabled"
			)

		# For video sources, use sub-activities for parallel processing
		# For other sources, use monolithic activity
		if detected_type in ['video', 'video_walkthrough']:
			workflow.logger.info(
				"🎥 Using video sub-activities for parallel processing: "
				"transcription + frame filtering (parallel), then parallel batch frame analysis"
			)

			ingest_result: IngestSourceResult = await ingest_video_with_sub_activities(
				source_url=source_url,
				source_name=source_name,
				job_id=input.job_id,
				options=input.options,
				activity_options=activity_options,
			)
		else:
			ingest_result: IngestSourceResult = await workflow.execute_activity(
				ingest_source_activity,
				IngestSourceInput(
					source_url=source_url,
					source_type=detected_type,
					job_id=input.job_id,
					source_name=source_name,
					options=input.options,
				),
				**activity_options,
			)

		# Handle errors
		if not ingest_result.success and ingest_result.content_chunks == 0:
			error_msg = (
				f"❌ Ingestion failed for asset ({detected_type}): {ingest_result.errors}. "
				f"No chunks produced."
			)
			workflow.logger.error(error_msg)
			raise Exception(error_msg)
		elif not ingest_result.success and ingest_result.content_chunks > 0:
			workflow.logger.warning(
				f"⚠️ Ingestion had non-fatal errors for asset ({detected_type}): {ingest_result.errors}. "
				f"But {ingest_result.content_chunks} chunks were produced - treating as successful."
			)

		ingest_results.append(ingest_result)
		total_chunks += ingest_result.content_chunks

		# Log success with type-specific details
		if detected_type in ['video', 'video_walkthrough']:
			workflow.logger.info(
				f"✅ Video processed: {ingest_result.content_chunks} chunks "
				f"(all features extracted)"
			)
		else:
			workflow.logger.info(
				f"✅ Asset ({detected_type}) ingested: {ingest_result.content_chunks} chunks"
			)

	# Handle empty case gracefully
	if not ingest_results:
		error_msg = (
			"All ingestion attempts failed. No sources were successfully ingested. "
			f"Attempted {len(sources_to_process)} asset(s) of types: {list(asset_type_counts.keys())}"
		)
		workflow.logger.error(error_msg)
		raise Exception(error_msg)

	# Log asset type summary
	if len(asset_type_counts) > 1:
		workflow.logger.info(
			f"📊 Processed mixed asset types: {dict(asset_type_counts)}"
		)

	# Log summary by asset type
	video_count = sum(1 for r in ingest_results if r.source_type in ['video_walkthrough', 'video'])
	docs_count = sum(1 for r in ingest_results if r.source_type in ['technical_documentation', 'documentation'])
	website_count = sum(1 for r in ingest_results if r.source_type in ['website_documentation', 'website'])

	if video_count > 0:
		workflow.logger.info(
			f"🎥 Processed {video_count} video asset(s) with comprehensive analysis: "
			f"transcription, frame analysis, action extraction, OCR, subtitles"
		)
	if docs_count > 0:
		workflow.logger.info(
			f"📄 Processed {docs_count} documentation asset(s) with comprehensive feature extraction"
		)
	if website_count > 0:
		workflow.logger.info(
			f"🌐 Processed {website_count} website asset(s) with comprehensive crawling"
		)

	# Validate we have at least one successful ingestion
	if not ingest_results or len(ingest_results) == 0:
		error_msg = "❌ No successful ingestion results - all sources failed"
		workflow.logger.error(error_msg)
		raise Exception(error_msg)

	# All ingestion results are persisted separately
	# Extraction will aggregate from all ingestion IDs and merge/deduplicate knowledge
	ingest_result = ingest_results[0]  # Primary for backward compatibility

	result.sources_ingested = len(ingest_results)
	progress.sources_ingested = len(ingest_results)

	workflow.logger.info(
		f"✅ Ingestion completed: {len(ingest_results)} asset(s) ({video_count} video, "
		f"{docs_count} docs, {website_count} websites), {total_chunks} total chunks. "
		f"Knowledge will be merged and deduplicated across all sources."
	)

	# Ensure all assets were processed (validation)
	if len(ingest_results) < len(sources_to_process):
		failed_count = len(sources_to_process) - len(ingest_results)
		workflow.logger.warning(
			f"⚠️ {failed_count} asset(s) failed ingestion, but {len(ingest_results)} succeeded. "
			f"Continuing with successful ingestions. Knowledge will be merged from successful sources."
		)

	return ingest_results

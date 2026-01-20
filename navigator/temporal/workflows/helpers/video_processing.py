"""
Video ingestion helper.

Orchestrates video ingestion using sub-activities for parallel processing.
"""

import asyncio
import hashlib
from datetime import timedelta
from pathlib import Path

from temporalio import workflow

# Import activities and schemas - wrap ALL imports
with workflow.unsafe.imports_passed_through():
	from navigator.schemas import (
		AnalyzeFramesBatchInput,
		AssembleVideoIngestionInput,
		FilterFramesInput,
		IngestSourceResult,
		TranscribeVideoInput,
	)
	from navigator.temporal.activities_extraction_video import (
		analyze_frames_batch_activity,
		assemble_video_ingestion_activity,
		filter_frames_activity,
		transcribe_video_activity,
	)


async def ingest_video_with_sub_activities(
	source_url: str,
	source_name: str | None,
	job_id: str,
	options: dict,
	activity_options: dict,
) -> IngestSourceResult:
	"""
	Ingest video using sub-activities for parallel processing.
	
	Orchestrates:
	1. Transcribe video (Deepgram) - parallel with frame filtering
	2. Filter frames (extract + SSIM deduplication) - parallel with transcription
	3. Analyze frames in parallel batches (each batch processes frames concurrently)
	
	Args:
		source_url: Video file path
		source_name: Human-readable name
		job_id: Job ID
		options: Ingestion options
		activity_options: Activity execution options (timeouts, retry policy)
	
	Returns:
		IngestSourceResult with video chunks
	"""
	# Generate ingestion ID deterministically based on workflow inputs
	# This ensures replay generates the same ID (deterministic workflow requirement)
	workflow_id = workflow.info().workflow_id
	id_source = f"{workflow_id}:{source_url}:{job_id}"
	ingestion_id = hashlib.sha256(id_source.encode()).hexdigest()[:32]

	# Handle file:// URLs
	if source_url.startswith('file://'):
		video_path = source_url.replace('file://', '')
	else:
		video_path = source_url

	video_path_obj = Path(video_path)

	# For now, pass duration=0.0 and let filter_frames_activity extract metadata
	# The activity will extract metadata internally
	duration = 0.0  # Will be extracted by filter_frames_activity (float type required)
	workflow.logger.info("📹 Video metadata will be extracted by filter_frames_activity")

	# Step 2: Run transcription and frame filtering in parallel
	# Note: Only 2 activities in parallel is safe for Temporal workflows
	workflow.logger.info("🎬 Starting parallel video processing: transcription + frame filtering")

	# Yield control before starting activities
	await workflow.sleep(timedelta(seconds=0))

	transcribe_task = workflow.execute_activity(
		transcribe_video_activity,
		TranscribeVideoInput(
			video_path=video_path,
			ingestion_id=ingestion_id,
			job_id=job_id,
		),
		**activity_options,
	)

	# Filter frames activity will handle scene detection internally if enabled
	# Pass empty list for now - activity will detect if needed
	filter_frames_task = workflow.execute_activity(
		filter_frames_activity,
		FilterFramesInput(
			video_path=video_path,
			ingestion_id=ingestion_id,
			duration=duration,
			job_id=job_id,
			scene_changes=[],  # Activity will detect scene changes internally if enabled
		),
		**activity_options,
	)

	# Wait for both to complete (workflow yields here during activity execution)
	transcribe_result, filter_result = await asyncio.gather(
		transcribe_task,
		filter_frames_task,
	)

	if not transcribe_result.success:
		workflow.logger.warning(f"⚠️ Transcription failed: {transcribe_result.errors}")
	if not filter_result.success:
		workflow.logger.warning(f"⚠️ Frame filtering failed: {filter_result.errors}")

	# Step 3: Process frames in parallel batches (Claim Check pattern - store results in S3)
	filtered_frames = filter_result.filtered_frame_paths
	all_frame_paths = filter_result.all_frame_paths  # All frames (for duplicate expansion)
	duplicate_map = filter_result.duplicate_map
	metadata = filter_result.metadata  # Extracted metadata

	if not filtered_frames:
		workflow.logger.warning("⚠️ No frames to analyze after filtering")
		# Still assemble and persist result with transcription if available
		# This ensures transcription chunks are persisted even without frames
		workflow.logger.info("🔧 Assembling video ingestion result (transcription only, no frames)...")

		# Yield control before assembly activity
		await workflow.sleep(timedelta(seconds=0))

		assembly_result = await workflow.execute_activity(
			assemble_video_ingestion_activity,
			AssembleVideoIngestionInput(
				ingestion_id=ingestion_id,
				video_path=video_path,
				transcription_data=transcribe_result.transcription_data if transcribe_result.success else None,
				filtered_frame_paths=[],
				duplicate_map={},
				analysis_result_s3_keys=[],  # Empty - no frame batches to process
				metadata=metadata,  # Use metadata from filter_frames_activity
				job_id=job_id,
				options=options,
			),
			**activity_options,
		)

		if not assembly_result.success:
			workflow.logger.error(f"❌ Video assembly failed: {assembly_result.errors}")
			return IngestSourceResult(
				ingestion_id=ingestion_id,
				source_type='video_walkthrough',
				content_chunks=0,
				total_tokens=0,
				success=False,
				errors=assembly_result.errors,
			)

		workflow.logger.info(
			f"✅ Video ingestion complete (transcription only): {assembly_result.content_chunks} chunks, "
			f"{assembly_result.total_tokens} tokens"
		)

		return IngestSourceResult(
			ingestion_id=assembly_result.ingestion_id,
			source_type='video_walkthrough',
			content_chunks=assembly_result.content_chunks,
			total_tokens=assembly_result.total_tokens,
			success=assembly_result.content_chunks > 0,
			errors=[] if assembly_result.content_chunks > 0 else ["No frames to analyze"],
		)

	# Split frames into batches (10 frames per batch)
	# This is a lightweight operation, but yield if processing many frames
	batch_size = 10
	batches = []
	for i in range(0, len(filtered_frames), batch_size):
		batches.append(filtered_frames[i:i + batch_size])
		# Yield every 50 batches to prevent deadlock (unlikely but safe)
		if i > 0 and (i // batch_size) % 50 == 0:
			await workflow.sleep(timedelta(seconds=0))

	workflow.logger.info(
		f"🔍 Processing {len(filtered_frames)} frames in {len(batches)} batch(es)"
	)

	# S3 prefix for batch results (Claim Check pattern - avoids passing large data through Temporal history)
	results_s3_prefix = f"results/{ingestion_id}"

	# Process batches sequentially to avoid workflow deadlock
	# Temporal workflows must yield control frequently (every 2 seconds max)
	# Processing batches one at a time ensures proper yielding
	batch_results = []

	for batch_idx, batch in enumerate(batches):
		workflow.logger.info(
			f"🔄 Processing batch {batch_idx + 1}/{len(batches)}: "
			f"{len(batch)} frames"
		)

		# Yield control before starting activity to prevent deadlock
		await workflow.sleep(timedelta(seconds=0))

		# Execute batch activity (workflow yields here during activity execution)
		try:
			batch_result = await workflow.execute_activity(
				analyze_frames_batch_activity,
				AnalyzeFramesBatchInput(
					frame_batch=batch,
					ingestion_id=ingestion_id,
					batch_index=batch_idx,
					job_id=job_id,
					output_s3_prefix=results_s3_prefix,  # Tell activity where to save batch results in S3
				),
				**activity_options,
			)
			batch_results.append(batch_result)
		except Exception as e:
			workflow.logger.warning(f"⚠️ Batch {batch_idx} failed: {e}")
			batch_results.append(e)

	# Collect S3 keys from batch results (Claim Check pattern - pass references, not data)
	# Yield control periodically during result collection to prevent deadlock
	analysis_result_s3_keys = []
	for i, result in enumerate(batch_results):
		# Yield control every 10 results to prevent deadlock
		if i > 0 and i % 10 == 0:
			await workflow.sleep(timedelta(seconds=0))

		if isinstance(result, Exception):
			workflow.logger.warning(f"⚠️ Batch {i} failed: {result}")
			continue
		if result.success:
			analysis_result_s3_keys.append(result.s3_key)  # Store S3 key, not data

	workflow.logger.info(f"📤 Collected {len(analysis_result_s3_keys)} batch result S3 keys (Claim Check pattern)")

	# Step 4: Assemble results into IngestionResult with chunks
	workflow.logger.info("🔧 Assembling video ingestion result from sub-activity outputs...")

	# Yield control before assembly activity
	await workflow.sleep(timedelta(seconds=0))

	# Call assembly activity to create chunks and persist (passes S3 keys, not data)
	assembly_result = await workflow.execute_activity(
		assemble_video_ingestion_activity,
		AssembleVideoIngestionInput(
			ingestion_id=ingestion_id,
			video_path=video_path,
			transcription_data=transcribe_result.transcription_data if transcribe_result.success else None,
			filtered_frame_paths=filtered_frames,
			duplicate_map=duplicate_map,
			analysis_result_s3_keys=analysis_result_s3_keys,  # Pass S3 keys, not data (Claim Check pattern)
			metadata=metadata,  # Use metadata from filter_frames_activity
			job_id=job_id,
			options=options,
		),
		**activity_options,
	)

	if not assembly_result.success:
		workflow.logger.error(f"❌ Video assembly failed: {assembly_result.errors}")
		return IngestSourceResult(
			ingestion_id=ingestion_id,
			source_type='video_walkthrough',
			content_chunks=0,
			total_tokens=0,
			success=False,
			errors=assembly_result.errors,
		)

	workflow.logger.info(
		f"✅ Video ingestion complete: {assembly_result.content_chunks} chunks, "
		f"{assembly_result.total_tokens} tokens"
	)

	return IngestSourceResult(
		ingestion_id=assembly_result.ingestion_id,
		source_type='video_walkthrough',
		content_chunks=assembly_result.content_chunks,
		total_tokens=assembly_result.total_tokens,
		success=assembly_result.success,
		errors=assembly_result.errors,
	)

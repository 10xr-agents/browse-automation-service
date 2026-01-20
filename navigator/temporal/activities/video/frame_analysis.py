"""
Video Frame Analysis Activity

Analyzes video frames in parallel batches using vision models.
"""

import asyncio
import json
import logging
import os
from pathlib import Path

from temporalio import activity

from navigator.knowledge.ingest.video.frame_analysis.formatting import format_frame_analysis
from navigator.knowledge.ingest.video.frame_analysis.vision import analyze_frame_with_vision
from navigator.knowledge.s3_frame_storage import get_frame_storage
from navigator.schemas import AnalyzeFramesBatchInput, AnalyzeFramesBatchResult

logger = logging.getLogger(__name__)


@activity.defn(name="analyze_frames_batch")
async def analyze_frames_batch_activity(input: AnalyzeFramesBatchInput) -> AnalyzeFramesBatchResult:
	"""
	Analyze a batch of video frames in parallel using vision models.
	
	This activity:
	1. Downloads frames from S3 (if needed)
	2. Analyzes each frame with vision model (parallel)
	3. Formats analysis results
	4. Uploads results to S3 (Claim Check pattern)
	
	Args:
		input: Batch analysis parameters (frame_batch, batch_index, ingestion_id, job_id)
	
	Returns:
		Analysis result with S3 key for batch results
	"""
	workflow_id = activity.info().workflow_id

	logger.info(
		f"🔵 ACTIVITY START: analyze_frames_batch (Workflow: {workflow_id}, "
		f"Batch: {input.batch_index}, Frames: {len(input.frame_batch)})"
	)

	activity.heartbeat({
		"status": "analyzing",
		"batch_index": input.batch_index,
		"frames_count": len(input.frame_batch)
	})

	frame_storage = get_frame_storage()

	# Process all frames in parallel using asyncio.gather
	async def analyze_frame(timestamp: float, frame_path_string: str) -> dict[str, Any] | None:
		"""Analyze a single frame (download from S3 if needed)."""
		try:
			# Download frame bytes (from local filesystem or S3)
			if frame_path_string.startswith('s3://'):
				# Download from S3
				logger.debug(f"📥 Downloading frame {timestamp:.2f}s from S3: {frame_path_string}")
				frame_bytes = await frame_storage.download_frame_from_path(frame_path_string)

				# Create temporary file for frame analysis
				import tempfile as tf
				with tf.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
					temp_path = Path(temp_file.name)
					temp_file.write(frame_bytes)

				try:
					# Analyze frame
					analysis = await analyze_frame_with_vision(temp_path, timestamp)
					return analysis
				finally:
					# Clean up temporary file
					if temp_path.exists():
						temp_path.unlink()
			else:
				# Local filesystem path
				frame_path_obj = Path(frame_path_string)

				# Verify frame exists
				if not frame_path_obj.exists():
					logger.warning(f"⚠️ Frame not found at {frame_path_string}, skipping analysis")
					return None

				analysis = await analyze_frame_with_vision(frame_path_obj, timestamp)
				return analysis
		except Exception as e:
			logger.warning(f"Frame analysis failed for {timestamp}s: {e}")
			return None

	# Create tasks for all frames in the batch
	tasks = [
		analyze_frame(timestamp, frame_path)
		for timestamp, frame_path in input.frame_batch
	]

	# Heartbeat before starting parallel processing
	activity.heartbeat({
		"status": "analyzing_frames",
		"batch_index": input.batch_index,
		"frames_count": len(tasks),
		"progress": "starting_parallel_analysis"
	})

	# Process all frames in parallel
	frame_analyses_list = await asyncio.gather(*tasks, return_exceptions=True)

	# Heartbeat after parallel processing completes
	activity.heartbeat({
		"status": "frames_analyzed",
		"batch_index": input.batch_index,
		"frames_analyzed": len([a for a in frame_analyses_list if not isinstance(a, Exception) and a is not None])
	})

	# Filter out None and Exception results
	frame_analyses = []
	for i, analysis in enumerate(frame_analyses_list):
		if isinstance(analysis, Exception):
			logger.warning(f"Frame {input.frame_batch[i][0]}s analysis raised exception: {analysis}")
			continue
		if analysis is not None:
			frame_analyses.append(analysis)

	logger.info(f"✅ Batch {input.batch_index} complete: {len(frame_analyses)}/{len(input.frame_batch)} frames analyzed")

	# Claim Check Pattern: Upload batch results to S3 (avoid passing large data through Temporal history)
	frame_analyses_json = json.dumps(frame_analyses, default=str)

	# Heartbeat before uploading results
	activity.heartbeat({
		"status": "uploading_results",
		"batch_index": input.batch_index,
		"results_size": len(frame_analyses_json)
	})

	# Determine S3 key for batch results
	s3_bucket = os.getenv('S3_BUCKET')

	if not s3_bucket:
		error_msg = (
			"❌ S3_BUCKET environment variable is not set. "
			"Batch results must be stored in S3 for distributed Temporal workflows. "
			"Please set S3_BUCKET environment variable."
		)
		logger.error(error_msg)
		return AnalyzeFramesBatchResult(
			batch_index=input.batch_index,
			frames_analyzed=0,
			analysis_result_s3_key=None,
			success=False,
			errors=[error_msg],
		)

	# Upload to S3
	s3_key = f"knowledge-extraction-wf-dev/{input.ingestion_id}/frame_analysis_batch_{input.batch_index}.json"
	s3_client = frame_storage._get_s3_client()

	loop = asyncio.get_event_loop()
	await loop.run_in_executor(
		None,
		lambda: s3_client.put_object(
			Bucket=s3_bucket,
			Key=s3_key,
			Body=frame_analyses_json.encode('utf-8'),
			ContentType='application/json',
		)
	)

	s3_url = f"s3://{s3_bucket}/{s3_key}"
	logger.info(f"📤 Uploaded batch {input.batch_index} results to S3: {s3_url}")

	return AnalyzeFramesBatchResult(
		batch_index=input.batch_index,
		frames_analyzed=len(frame_analyses),
		analysis_result_s3_key=s3_url,
		success=True,
	)

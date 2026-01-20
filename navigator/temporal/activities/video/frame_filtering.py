"""
Video Frame Filtering Activity

Extracts and filters video frames using scene change detection and SSIM deduplication.
"""

import logging
import subprocess
import tempfile
from pathlib import Path

from temporalio import activity

from navigator.knowledge.ingest.video import VideoIngester
from navigator.knowledge.ingest.video.frame_analysis.deduplication import compute_ssim
from navigator.knowledge.ingest.video.frame_analysis.filtering import detect_scene_changes, smart_filter_pass1
from navigator.knowledge.ingest.video.metadata import extract_metadata
from navigator.knowledge.s3_frame_storage import get_frame_storage
from navigator.schemas import FilterFramesInput, FilterFramesResult

logger = logging.getLogger(__name__)


@activity.defn(name="filter_frames")
async def filter_frames_activity(input: FilterFramesInput) -> FilterFramesResult:
	"""
	Extract and filter video frames using scene change detection and SSIM deduplication.
	
	This activity:
	1. Detects scene changes in video
	2. Applies smart filtering (pass 1)
	3. Extracts candidate frames
	4. Applies SSIM-based deduplication
	5. Uploads frames to shared storage (S3 or local)
	
	Args:
		input: Filtering parameters (video_path, ingestion_id, job_id, frame_interval)
	
	Returns:
		Filter result with frame references and metadata
	"""
	workflow_id = activity.info().workflow_id

	logger.info(f"🔵 ACTIVITY START: filter_frames (Workflow: {workflow_id}, Video: {input.video_path})")

	activity.heartbeat({"status": "filtering", "video_path": input.video_path})

	try:
		video_ingester = VideoIngester()
		video_path = Path(input.video_path)
		frame_storage = get_frame_storage()

		# Step 0: Get video duration (required for scene detection)
		activity.heartbeat({"status": "extracting_metadata"})
		metadata = extract_metadata(video_path)
		if not metadata:
			raise ValueError(f"Failed to extract metadata from video: {video_path}")
		duration = metadata.get('duration', 0)
		if duration <= 0:
			raise ValueError(f"Invalid video duration: {duration}")

		# Step 1: Detect scene changes
		activity.heartbeat({"status": "detecting_scenes"})
		scene_changes = await detect_scene_changes(video_path, duration)
		logger.info(f"🎬 Detected {len(scene_changes)} scene changes")

		# Step 2: Apply smart filtering (pass 1)
		activity.heartbeat({"status": "smart_filtering"})
		filtered_timestamps = await smart_filter_pass1(
			video_path,
			duration,
			scene_changes,  # strategic_timestamps
		)
		logger.info(f"🎯 Smart filtering: {len(filtered_timestamps)} candidate frames")

		# Step 3: Extract frames to temporary location (for SSIM comparison)
		temp_dir = Path(tempfile.gettempdir()) / 'video_frames' / input.ingestion_id / 'temp'
		temp_dir.mkdir(parents=True, exist_ok=True)

		temp_frame_paths = []
		for timestamp in filtered_timestamps:
			temp_frame_path = temp_dir / f"frame_{timestamp:.2f}.jpg"

			cmd = [
				'ffmpeg',
				'-ss', str(timestamp),
				'-i', str(video_path),
				'-vframes', '1',
				'-q:v', '2',
				'-y',
				str(temp_frame_path)
			]

			result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
			if result.returncode == 0 and temp_frame_path.exists():
				temp_frame_paths.append((timestamp, temp_frame_path))

		logger.info(f"📸 Extracted {len(temp_frame_paths)} frames from {len(filtered_timestamps)} candidate timestamps")

		# Step 4: Apply SSIM-based deduplication
		filtered_temp_frames = []
		duplicate_map = {}
		previous_frame_path = None

		# Sort frames by timestamp for sequential SSIM comparison
		sorted_temp_frames = sorted(temp_frame_paths, key=lambda x: x[0])
		total_frames = len(sorted_temp_frames)

		activity.heartbeat({"status": "ssim_deduplication", "total_frames": total_frames})

		for i, (timestamp, temp_frame_path) in enumerate(sorted_temp_frames):
			# Heartbeat every 100 frames to prevent timeout
			if i % 100 == 0:
				activity.heartbeat({
					"status": "ssim_deduplication",
					"processed": i,
					"total": total_frames,
					"unique_so_far": len(filtered_temp_frames)
				})
			is_duplicate = False
			if previous_frame_path and previous_frame_path.exists() and temp_frame_path.exists():
				ssim_value = compute_ssim(previous_frame_path, temp_frame_path)

				if ssim_value > video_ingester.ssim_threshold:
					is_duplicate = True
					logger.debug(f"🔄 Frame {timestamp:.2f}s is duplicate (SSIM={ssim_value:.3f})")
					if filtered_temp_frames:
						prev_unique_timestamp = filtered_temp_frames[-1][0]
						duplicate_map[timestamp] = prev_unique_timestamp

			if not is_duplicate:
				filtered_temp_frames.append((timestamp, temp_frame_path))
				previous_frame_path = temp_frame_path

		deduplication_rate = ((len(temp_frame_paths) - len(filtered_temp_frames)) / len(temp_frame_paths) * 100) if temp_frame_paths else 0
		logger.info(
			f"🎯 SSIM deduplication: {len(filtered_temp_frames)}/{len(temp_frame_paths)} frames unique "
			f"({deduplication_rate:.1f}% duplicates filtered)"
		)

		# Step 5: Upload frames to shared storage (S3 or local) and create frame references
		all_frame_paths: list[tuple[float, str]] = []
		filtered_frame_paths: list[tuple[float, str]] = []

		activity.heartbeat({"status": "uploading_frames", "total_frames": len(sorted_temp_frames)})

		# Read all frame bytes first (prepare for batch upload)
		frames_to_upload: list[tuple[bytes, float, Path]] = []
		for timestamp, temp_frame_path in sorted_temp_frames:
			try:
				with open(temp_frame_path, 'rb') as f:
					frame_bytes = f.read()
				frames_to_upload.append((frame_bytes, timestamp, temp_frame_path))
			except Exception as e:
				logger.warning(f"⚠️ Failed to read frame {timestamp:.2f}s: {e}")

		# Batch upload all frames concurrently
		try:
			frame_data = [(frame_bytes, timestamp) for frame_bytes, timestamp, _ in frames_to_upload]
			frame_refs = await frame_storage.upload_frames_batch(frame_data, input.ingestion_id)

			activity.heartbeat({
				"status": "uploading_frames",
				"uploaded": len([r for r in frame_refs if r is not None]),
				"total": len(frames_to_upload)
			})

			# Map timestamps to frame references
			# Convert FrameReference objects to strings for JSON serialization
			for (timestamp, _), frame_ref in zip(sorted_temp_frames, frame_refs):
				if frame_ref:
					# Convert FrameReference to string path for Temporal serialization
					frame_path_str = frame_ref.to_path_string()
					all_frame_paths.append((timestamp, frame_path_str))
					# Check if this frame is in filtered list
					if any(ts == timestamp for ts, _ in filtered_temp_frames):
						filtered_frame_paths.append((timestamp, frame_path_str))

		except Exception as e:
			logger.error(f"❌ Frame upload failed: {e}", exc_info=True)
			# Continue with local paths as fallback
			for timestamp, temp_frame_path in sorted_temp_frames:
				all_frame_paths.append((timestamp, str(temp_frame_path)))
				if any(ts == timestamp for ts, _ in filtered_temp_frames):
					filtered_frame_paths.append((timestamp, str(temp_frame_path)))

		# Clean up temporary frames
		try:
			for _, temp_path in temp_frame_paths:
				if temp_path.exists():
					temp_path.unlink()
			if temp_dir.exists():
				temp_dir.rmdir()
		except Exception as e:
			logger.warning(f"⚠️ Failed to clean up temp frames: {e}")

		logger.info(f"✅ Frame filtering completed: {len(filtered_frame_paths)} unique frames from {len(all_frame_paths)} total")

		return FilterFramesResult(
			all_frame_paths=all_frame_paths,
			filtered_frame_paths=filtered_frame_paths,
			duplicate_map=duplicate_map,
			metadata=metadata,
			success=True,
		)

	except Exception as e:
		logger.error(f"❌ Frame filtering failed: {e}", exc_info=True)
		return FilterFramesResult(
			all_frame_paths=[],
			filtered_frame_paths=[],
			duplicate_map={},
			metadata=None,
			success=False,
			errors=[str(e)],
		)

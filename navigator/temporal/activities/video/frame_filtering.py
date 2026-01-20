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
		logger.info(f"🎬 Detected {len(scene_changes)} scene changes in {duration:.2f}s video")

		# Step 2: Apply smart filtering (pass 1)
		activity.heartbeat({"status": "smart_filtering"})
		filtered_timestamps = await smart_filter_pass1(
			video_path,
			duration,
			scene_changes,  # strategic_timestamps
		)
		logger.info(
			f"🎯 Smart filtering: {len(filtered_timestamps)} candidate frames "
			f"(from {duration:.2f}s video with {len(scene_changes)} scene changes)"
		)
		
		if len(filtered_timestamps) == 0:
			logger.warning(
				f"⚠️ WARNING: Smart filtering returned 0 candidate frames! "
				f"Video duration: {duration:.2f}s, Scene changes: {len(scene_changes)}"
			)

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

		logger.info(
			f"📸 Extracted {len(temp_frame_paths)} frames from {len(filtered_timestamps)} candidate timestamps"
		)
		
		if len(temp_frame_paths) == 0:
			logger.error(
				f"❌ CRITICAL: Failed to extract any frames from video! "
				f"Video path: {video_path}, Duration: {duration:.2f}s, "
				f"Candidate timestamps: {len(filtered_timestamps)}"
			)

		# Step 4: Apply SSIM-based deduplication
		filtered_temp_frames = []
		duplicate_map = {}
		previous_frame_path = None

		# Sort frames by timestamp for sequential SSIM comparison
		sorted_temp_frames = sorted(temp_frame_paths, key=lambda x: x[0])
		total_frames = len(sorted_temp_frames)

		if total_frames == 0:
			logger.error("❌ No frames extracted - cannot proceed with SSIM deduplication")
			raise ValueError("No frames extracted from video")

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
				try:
					ssim_value = compute_ssim(previous_frame_path, temp_frame_path)

					if ssim_value > video_ingester.ssim_threshold:
						is_duplicate = True
						logger.debug(f"🔄 Frame {timestamp:.2f}s is duplicate (SSIM={ssim_value:.3f})")
						if filtered_temp_frames:
							prev_unique_timestamp = filtered_temp_frames[-1][0]
							duplicate_map[timestamp] = prev_unique_timestamp
				except Exception as e:
					logger.warning(f"⚠️ SSIM computation failed for frame {timestamp:.2f}s: {e}, treating as unique")
					# Treat as unique if SSIM fails

			if not is_duplicate:
				filtered_temp_frames.append((timestamp, temp_frame_path))
				previous_frame_path = temp_frame_path
		
		# Safety check: Ensure at least one frame is kept (first frame should always be unique)
		if len(filtered_temp_frames) == 0 and len(sorted_temp_frames) > 0:
			logger.warning(
				"⚠️ All frames filtered out by SSIM - this should not happen. "
				"Keeping first frame as fallback."
			)
			first_timestamp, first_path = sorted_temp_frames[0]
			filtered_temp_frames.append((first_timestamp, first_path))

		deduplication_rate = ((len(temp_frame_paths) - len(filtered_temp_frames)) / len(temp_frame_paths) * 100) if temp_frame_paths else 0
		logger.info(
			f"🎯 SSIM deduplication: {len(filtered_temp_frames)}/{len(temp_frame_paths)} frames unique "
			f"({deduplication_rate:.1f}% duplicates filtered)"
		)
		
		if len(filtered_temp_frames) == 0:
			logger.warning(
				f"⚠️ WARNING: All {len(temp_frame_paths)} frames were filtered out by SSIM deduplication! "
				f"This may indicate all frames are duplicates or there's an issue with the video."
			)

		# Step 5: Upload frames to shared storage (S3 or local) and create frame references
		all_frame_paths: list[tuple[float, str]] = []
		filtered_frame_paths: list[tuple[float, str]] = []

		# Create a set of filtered timestamps for O(1) lookup (avoid floating point comparison issues)
		# Use a small tolerance for floating point comparison
		filtered_timestamps_set: set[float] = {ts for ts, _ in filtered_temp_frames}
		
		logger.info(
			f"📤 Preparing to upload frames: {len(sorted_temp_frames)} total frames, "
			f"{len(filtered_temp_frames)} unique frames after SSIM deduplication"
		)

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

		logger.info(f"📦 Read {len(frames_to_upload)} frames for batch upload")

		# Batch upload all frames concurrently
		try:
			# Build frame_data preserving order and timestamp mapping
			frame_data = [(frame_bytes, timestamp) for frame_bytes, timestamp, _ in frames_to_upload]
			frame_refs = await frame_storage.upload_frames_batch(frame_data, input.ingestion_id)

			uploaded_count = len([r for r in frame_refs if r is not None])
			activity.heartbeat({
				"status": "uploading_frames",
				"uploaded": uploaded_count,
				"total": len(frames_to_upload)
			})

			logger.info(f"✅ Uploaded {uploaded_count}/{len(frames_to_upload)} frames to storage")

			# Map timestamps to frame references
			# IMPORTANT: frames_to_upload and frame_refs are in the same order
			# frames_to_upload was built from sorted_temp_frames, so we can zip by index
			# Create a timestamp -> frame_ref mapping for reliable lookup
			timestamp_to_frame_ref: dict[float, str] = {}
			for (frame_bytes, timestamp, _), frame_ref in zip(frames_to_upload, frame_refs):
				if frame_ref:
					# Convert FrameReference to string path for Temporal serialization
					frame_path_str = frame_ref.to_path_string()
					timestamp_to_frame_ref[timestamp] = frame_path_str
			
			logger.info(
				f"🔗 Created timestamp mapping: {len(timestamp_to_frame_ref)} frames mapped to storage paths"
			)
			
			# Now map all frames (from sorted_temp_frames) to their references
			# Use set-based lookup for filtered frames (O(1) instead of O(n) with any())
			for timestamp, temp_frame_path in sorted_temp_frames:
				if timestamp in timestamp_to_frame_ref:
					frame_path_str = timestamp_to_frame_ref[timestamp]
					all_frame_paths.append((timestamp, frame_path_str))
					# Check if this frame is in filtered list using set lookup
					if timestamp in filtered_timestamps_set:
						filtered_frame_paths.append((timestamp, frame_path_str))
				else:
					# Fallback to local path if upload failed
					logger.warning(f"⚠️ Frame {timestamp:.2f}s upload failed, using local path")
					all_frame_paths.append((timestamp, str(temp_frame_path)))
					if timestamp in filtered_timestamps_set:
						filtered_frame_paths.append((timestamp, str(temp_frame_path)))

		except Exception as e:
			logger.error(f"❌ Frame upload failed: {e}", exc_info=True)
			# Continue with local paths as fallback
			for timestamp, temp_frame_path in sorted_temp_frames:
				all_frame_paths.append((timestamp, str(temp_frame_path)))
				if timestamp in filtered_timestamps_set:
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

		# Final summary log with detailed diagnostics
		logger.info(
			f"✅ Frame filtering completed: {len(filtered_frame_paths)} unique frames from {len(all_frame_paths)} total frames"
		)
		
		# Validation: Ensure filtered_frame_paths matches filtered_temp_frames count
		if len(filtered_frame_paths) != len(filtered_temp_frames):
			logger.error(
				f"❌ CRITICAL MISMATCH: filtered_frame_paths ({len(filtered_frame_paths)}) "
				f"does not match filtered_temp_frames ({len(filtered_temp_frames)})! "
				f"This indicates a mapping error. Frame analysis may be incomplete."
			)
			# Log the timestamps for debugging
			filtered_ts_from_temp = {ts for ts, _ in filtered_temp_frames}
			filtered_ts_from_paths = {ts for ts, _ in filtered_frame_paths}
			missing_ts = filtered_ts_from_temp - filtered_ts_from_paths
			if missing_ts:
				logger.error(
					f"❌ Missing timestamps in filtered_frame_paths: {sorted(missing_ts)}"
				)
			extra_ts = filtered_ts_from_paths - filtered_ts_from_temp
			if extra_ts:
				logger.error(
					f"❌ Extra timestamps in filtered_frame_paths: {sorted(extra_ts)}"
				)
		else:
			logger.info(
				f"✅ Validation passed: filtered_frame_paths count ({len(filtered_frame_paths)}) "
				f"matches filtered_temp_frames count ({len(filtered_temp_frames)})"
			)
		
		if len(filtered_frame_paths) == 0 and len(all_frame_paths) > 0:
			logger.error(
				f"❌ CRITICAL: All {len(all_frame_paths)} frames were filtered out! "
				f"This will cause frame analysis to be skipped. "
				f"Check SSIM threshold and deduplication logic. "
				f"filtered_temp_frames count: {len(filtered_temp_frames)}"
			)
		elif len(filtered_frame_paths) == 0:
			logger.warning(
				"⚠️ No frames extracted from video. This may indicate a video processing issue."
			)
		else:
			# Log sample of filtered frames for diagnostics
			sample_size = min(3, len(filtered_frame_paths))
			sample_frames = filtered_frame_paths[:sample_size]
			logger.info(
				f"📊 Sample filtered frames (first {sample_size}): "
				f"{[(ts, path[:50] + '...' if len(path) > 50 else path) for ts, path in sample_frames]}"
			)

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

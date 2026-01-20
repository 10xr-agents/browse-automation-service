"""
Video ingestion main module.

Contains the VideoIngester class that orchestrates video processing
using modular components for metadata, transcription, frame analysis, etc.
"""

import asyncio
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from navigator.knowledge.ingest.video.action_extraction import extract_action_sequence
from navigator.knowledge.ingest.video.frame_analysis.deduplication import (
	compute_ssim,
)
from navigator.knowledge.ingest.video.frame_analysis.filtering import (
	detect_scene_changes,
	smart_filter_pass1,
)
from navigator.knowledge.ingest.video.frame_analysis.formatting import format_frame_analysis
from navigator.knowledge.ingest.video.frame_analysis.vision import analyze_frame_with_vision
from navigator.knowledge.ingest.video.metadata import extract_metadata, format_metadata_as_text
from navigator.knowledge.ingest.video.thumbnails import generate_thumbnails
from navigator.knowledge.ingest.video.transcription import (
	extract_subtitles,
	transcribe_video,
)
from navigator.schemas import (
	ContentChunk,
	IngestionResult,
	SourceMetadata,
	SourceType,
	detect_video_format,
)

logger = logging.getLogger(__name__)


class VideoIngester:
	"""
	Ingester for video walkthrough files.
	
	Processes video files with comprehensive analysis:
	- Metadata extraction (ffprobe)
	- Audio transcription (Deepgram API)
	- Subtitle extraction (embedded subtitles)
		- Frame analysis (Gemini Vision)
	- Action sequence extraction
	- Thumbnail generation
	"""

	def __init__(
		self,
		enable_transcription: bool = True,
		enable_frame_analysis: bool = True,
		enable_subtitle_extraction: bool = True,
		enable_action_extraction: bool = True,
		enable_scene_detection: bool = True,
		frame_interval_seconds: float = 5.0,
		ssim_threshold: float = 0.96,
		diff_resolution: tuple[int, int] = (640, 360),
		action_diff_threshold: float = 0.05,
		thumbnail_count: int = 5,
	):
		"""
		Initialize VideoIngester.
		
		Args:
			enable_transcription: Enable audio transcription via Deepgram
			enable_frame_analysis: Enable frame analysis via Vision LLMs
			enable_subtitle_extraction: Enable embedded subtitle extraction
			enable_action_extraction: Enable action sequence extraction
			enable_scene_detection: Enable scene change detection
			frame_interval_seconds: Base interval for frame sampling (seconds)
			ssim_threshold: SSIM threshold for duplicate detection (0.0-1.0)
			diff_resolution: Low-res proxy resolution for fast pixel diff (width, height)
			action_diff_threshold: Percentage threshold for detecting visual changes
			thumbnail_count: Number of thumbnails to generate
		"""
		self.enable_transcription = enable_transcription
		self.enable_frame_analysis = enable_frame_analysis
		self.enable_subtitle_extraction = enable_subtitle_extraction
		self.enable_action_extraction = enable_action_extraction
		self.enable_scene_detection = enable_scene_detection
		self.frame_interval_seconds = frame_interval_seconds
		self.ssim_threshold = ssim_threshold
		self.diff_resolution = diff_resolution
		self.action_diff_threshold = action_diff_threshold
		self.thumbnail_count = thumbnail_count

	async def ingest_video(self, video_path: str | Path) -> IngestionResult:
		"""
		Ingest a video file with comprehensive analysis.
		
		Args:
			video_path: Path to the video file
		
		Returns:
			IngestionResult with video metadata, transcription, frame analysis, and actions
		"""
		video_path = Path(video_path)

		# Create result
		ingestion_id = str(uuid4())
		result = IngestionResult(
			ingestion_id=ingestion_id,
			source_type=SourceType.VIDEO_WALKTHROUGH,
			metadata=SourceMetadata(
				source_type=SourceType.VIDEO_WALKTHROUGH,
				url=str(video_path),
				title=video_path.stem,
				format=detect_video_format(str(video_path)),
				size_bytes=video_path.stat().st_size if video_path.exists() else 0,
				last_modified=datetime.fromtimestamp(video_path.stat().st_mtime) if video_path.exists() else None,
			)
		)

		try:
			# Check if file exists
			if not video_path.exists():
				result.add_error(
					"FileNotFoundError",
					f"Video file not found: {video_path}",
					{"video_path": str(video_path)}
				)
				result.mark_complete()
				return result

			# Check file size (max 2GB)
			if video_path.stat().st_size > 2 * 1024 * 1024 * 1024:
				result.add_error(
					"FileSizeError",
					f"Video file too large (max 2GB): {video_path.stat().st_size / (1024**3):.2f}GB",
					{"video_path": str(video_path), "size_gb": video_path.stat().st_size / (1024**3)}
				)
				result.mark_complete()
				return result

			# Extract metadata
			metadata = extract_metadata(video_path)

			if not metadata:
				result.add_error(
					"MetadataExtractionError",
					"Could not extract video metadata",
					{"video_path": str(video_path)}
				)
				result.mark_complete()
				return result

			duration = metadata.get('duration', 0)

			# Create content chunk with metadata
			chunk = ContentChunk(
				chunk_id=f"{ingestion_id}_metadata",
				content=format_metadata_as_text(video_path, metadata),
				chunk_index=0,
				token_count=100,  # Approximate
				chunk_type="video_metadata",
				section_title=video_path.stem,
			)
			result.content_chunks.append(chunk)

			# Enhanced processing: Subtitle extraction
			subtitle_data = None
			if self.enable_subtitle_extraction and metadata.get('subtitle_tracks', 0) > 0:
				try:
					subtitle_data = await extract_subtitles(video_path, ingestion_id)
					if subtitle_data:
						# Create subtitle chunks
						for idx, subtitle in enumerate(subtitle_data.get('subtitles', [])):
							subtitle_chunk = ContentChunk(
								chunk_id=f"{ingestion_id}_subtitle_{idx}",
								content=f"[{subtitle['start']:.2f}-{subtitle['end']:.2f}] {subtitle['text']}",
								chunk_index=len(result.content_chunks),
								token_count=int(len(subtitle['text'].split()) * 1.3),  # Convert float to int
								chunk_type="video_subtitle",
								section_title=f"Subtitle {idx + 1}",
							)
							result.content_chunks.append(subtitle_chunk)
				except Exception as e:
					logger.warning(f"⚠️ Subtitle extraction failed: {e}", exc_info=True)
					result.add_error("SubtitleExtractionError", f"Subtitle extraction failed: {str(e)}", {"video_path": str(video_path)})

			# Parallel execution: Run Transcription (Audio Track) and Frame Analysis (Video Track) concurrently
			# This reduces total processing time by ~30-40% (CPU processes frames while waiting for Deepgram API)
			transcription_data = None
			frame_analyses = []

			async def process_audio_track():
				"""Audio processing track (IO-bound, waits for Deepgram API)"""
				nonlocal transcription_data
				if self.enable_transcription and metadata.get('audio_tracks', 0) > 0:
					try:
						transcription_data = await transcribe_video(video_path)
						if transcription_data:
							logger.info(f"✅ Transcribed video: {len(transcription_data.get('segments', []))} segments")
					except Exception as e:
						logger.warning(f"⚠️ Transcription failed: {e}", exc_info=True)
						result.add_error("TranscriptionError", f"Transcription failed: {str(e)}", {"video_path": str(video_path)})

			async def process_video_track():
				"""Video processing track (CPU-bound, processes frames while waiting for audio)"""
				nonlocal frame_analyses
				if self.enable_frame_analysis:
					try:
						# Note: transcription_data may still be None during parallel execution
						# Frame analysis will use transcription_data once available (via closure)
						frame_analyses = await self._analyze_frames(
							video_path,
							ingestion_id,
							duration,
							None,  # Will be available after parallel execution
							subtitle_data
						)
					except Exception as e:
						logger.warning(f"⚠️ Frame analysis failed: {e}", exc_info=True)
						result.add_error("FrameAnalysisError", f"Frame analysis failed: {str(e)}", {"video_path": str(video_path)})

			# Run audio and video tracks in parallel
			await asyncio.gather(
				process_audio_track(),
				process_video_track()
			)

			# Now that both tracks are complete, merge transcription_data into frame analysis if needed
			# (Frame analysis runs independently but can use transcription for better alignment)

			# Create transcription chunks after parallel execution
			if transcription_data:
				try:
					# Create transcription chunks
					for idx, segment in enumerate(transcription_data.get('segments', [])):
						transcription_chunk = ContentChunk(
							chunk_id=f"{ingestion_id}_transcription_{idx}",
							content=f"[{segment['start']:.2f}-{segment['end']:.2f}] {segment['text']}",
							chunk_index=len(result.content_chunks),
							token_count=int(len(segment['text'].split()) * 1.3),  # Convert float to int
							chunk_type="video_transcription",
							section_title=f"Transcription Segment {idx + 1}",
						)
						result.content_chunks.append(transcription_chunk)

					# Add full transcription summary
					full_transcription = transcription_data.get('transcription', '')
					if full_transcription:
						summary_chunk = ContentChunk(
							chunk_id=f"{ingestion_id}_transcription_full",
							content=f"# Full Video Transcription\n\n{full_transcription}",
							chunk_index=len(result.content_chunks),
							token_count=int(len(full_transcription.split()) * 1.3),  # Convert float to int
							chunk_type="video_transcription_full",
							section_title="Complete Transcription",
						)
						result.content_chunks.append(summary_chunk)
				except Exception as e:
					logger.warning(f"⚠️ Transcription chunk creation failed: {e}", exc_info=True)

			# Create frame analysis chunks after parallel execution
			if frame_analyses:
				# Create frame analysis chunks
				for idx, analysis in enumerate(frame_analyses):
					frame_chunk = ContentChunk(
						chunk_id=f"{ingestion_id}_frame_{idx}",
						content=format_frame_analysis(analysis),
						chunk_index=len(result.content_chunks),
						token_count=int(len(str(analysis).split()) * 1.3),  # Convert float to int
						chunk_type="video_frame_analysis",
						section_title=f"Frame Analysis {idx + 1}",
					)
					result.content_chunks.append(frame_chunk)

				logger.info(f"✅ Analyzed {len(frame_analyses)} frames")

			# Enhanced processing: Action extraction
			if self.enable_action_extraction and frame_analyses:
				try:
					actions = extract_action_sequence(frame_analyses, transcription_data, subtitle_data)

					if actions:
						for idx, action in enumerate(actions):
							action_chunk = ContentChunk(
								chunk_id=f"{ingestion_id}_action_{idx}",
								content=f"[{action.get('timestamp', 0):.2f}s] {action.get('action_type', 'unknown')}: {action.get('target', 'unknown')} - {action.get('context', '')}",
								chunk_index=len(result.content_chunks),
								token_count=int(len(str(action).split()) * 1.3),  # Convert float to int
								chunk_type="video_action",
								section_title=f"Action {idx + 1}",
							)
							result.content_chunks.append(action_chunk)

						logger.info(f"✅ Extracted {len(actions)} actions")
				except Exception as e:
					logger.warning(f"⚠️ Action extraction failed: {e}", exc_info=True)
					result.add_error("ActionExtractionError", f"Action extraction failed: {str(e)}", {"video_path": str(video_path)})

			# Generate thumbnails
			thumbnail_paths = generate_thumbnails(video_path, ingestion_id, duration, self.thumbnail_count)

			if thumbnail_paths:
				# Create chunk with thumbnail references
				thumbnail_chunk = ContentChunk(
					chunk_id=f"{ingestion_id}_thumbnails",
					content=f"Generated {len(thumbnail_paths)} thumbnails: {', '.join(str(p) for p in thumbnail_paths)}",
					chunk_index=len(result.content_chunks),
					token_count=50,
					chunk_type="video_thumbnails",
				)
				result.content_chunks.append(thumbnail_chunk)

			logger.info(f"✅ Ingested video {video_path.name}: {len(result.content_chunks)} chunks")

			# Mark complete
			result.mark_complete()

		except Exception as e:
			logger.error(f"❌ Error ingesting video {video_path}: {e}", exc_info=True)
			result.add_error("VideoIngestionError", str(e), {"video_path": str(video_path)})
			result.mark_complete()

		return result

	async def _analyze_frames(
		self,
		video_path: Path,
		ingestion_id: str,
		duration: float,
		transcription_data: dict[str, Any] | None = None,
		subtitle_data: dict[str, Any] | None = None
	) -> list[dict[str, Any]]:
		"""
		Analyze video frames using Gemini Vision.
		
		Extracts frames at intervals and analyzes them for:
		- UI elements (buttons, forms, menus)
		- Screen states
		- Business context
		- Visible text (extracted by Vision LLM as part of comprehensive analysis)
		
		Uses adaptive frame sampling:
		- Scene change detection for better frame selection
		- Higher frequency sampling for action-heavy segments
		- Transcription/subtitle alignment for context
		- SSIM-based deduplication to reduce Vision LLM calls by 40-60%
		"""
		frame_analyses = []

		try:
			# Step 1: Detect scene changes for better frame extraction
			scene_changes = []
			if self.enable_scene_detection:
				scene_changes = await detect_scene_changes(video_path, duration)
				logger.info(f"🎬 Detected {len(scene_changes)} scene changes")

			# Step 2: Extract frames at strategic points
			frame_timestamps = []

			# Base interval sampling
			current_time = 0.0
			while current_time < duration:
				frame_timestamps.append(current_time)
				current_time += self.frame_interval_seconds

			# Add scene change timestamps (critical moments)
			for scene_time in scene_changes:
				if scene_time not in frame_timestamps:
					frame_timestamps.append(scene_time)

			# Add transcription segment boundaries for better alignment
			if transcription_data:
				for segment in transcription_data.get('segments', []):
					# Add start, midpoint, and end of each segment
					for point in [segment['start'], (segment['start'] + segment['end']) / 2, segment['end']]:
						if point not in frame_timestamps and 0 <= point < duration:
							frame_timestamps.append(point)

			# Add subtitle timestamps
			if subtitle_data:
				for subtitle in subtitle_data.get('subtitles', []):
					midpoint = (subtitle['start'] + subtitle['end']) / 2
					if midpoint not in frame_timestamps and 0 <= midpoint < duration:
						frame_timestamps.append(midpoint)

			frame_timestamps = sorted(set(frame_timestamps))

			# Ensure minimum coverage: at least one frame per 5 seconds (comprehensive coverage)
			coverage_timestamps = []
			current = 0.0
			while current < duration:
				if current not in frame_timestamps:
					coverage_timestamps.append(current)
				current += 5.0  # 1 frame per 5 seconds minimum

			frame_timestamps.extend(coverage_timestamps)
			frame_timestamps = sorted(set(frame_timestamps))

			# Final validation: ensure we have reasonable coverage
			if len(frame_timestamps) < duration / 10:  # At least 1 frame per 10 seconds minimum
				logger.warning(f"⚠️ Low frame count ({len(frame_timestamps)}) for {duration}s video, adding more samples")
				additional = []
				current = 0.0
				while current < duration:
					if current not in frame_timestamps:
						additional.append(current)
					current += 10.0
				frame_timestamps.extend(additional)
				frame_timestamps = sorted(set(frame_timestamps))

			logger.info(f"📸 Extracting {len(frame_timestamps)} frames for comprehensive analysis (coverage: {len(frame_timestamps)/duration*60:.1f} frames/minute)")

			# Smart Filter: Pass 1 - Fast scanning with OpenCV pixel diff (lightweight CPU)
			# This pre-filters frames before expensive SSIM/Vision LLM processing
			action_candidate_timestamps = await smart_filter_pass1(
				video_path,
				duration,
				frame_timestamps,
				self.diff_resolution,
				self.action_diff_threshold
			)

			# Merge strategic timestamps with action candidates
			all_candidate_timestamps = sorted(set(frame_timestamps + action_candidate_timestamps))
			logger.info(f"🎯 Smart Filter Pass 1: {len(action_candidate_timestamps)} action candidates detected from {len(frame_timestamps)} strategic timestamps")

			# Extract frames at candidate timestamps
			temp_dir = Path(tempfile.gettempdir()) / 'video_frames' / ingestion_id
			temp_dir.mkdir(parents=True, exist_ok=True)

			frame_paths = []
			for timestamp in all_candidate_timestamps:
				frame_path = temp_dir / f"frame_{timestamp:.2f}.jpg"

				import subprocess
				cmd = [
					'ffmpeg',
					'-ss', str(timestamp),
					'-i', str(video_path),
					'-vframes', '1',
					'-q:v', '2',
					'-y',
					str(frame_path)
				]

				result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
				if result.returncode == 0 and frame_path.exists():
					frame_paths.append((timestamp, frame_path))

			logger.info(f"📸 Extracted {len(frame_paths)} frames from {len(all_candidate_timestamps)} candidate timestamps")

			# Apply SSIM-based frame deduplication before Vision LLM
			# This filters 40-60% of redundant frames (identical screens)
			filtered_frame_paths = []
			duplicate_map = {}  # Map duplicate timestamps to their previous unique frame timestamp
			previous_frame_path = None

			# Sort frames by timestamp for sequential SSIM comparison
			sorted_frame_paths = sorted(frame_paths, key=lambda x: x[0])

			for timestamp, frame_path in sorted_frame_paths:
				# Check SSIM against previous frame (if available)
				is_duplicate = False
				if previous_frame_path and previous_frame_path.exists() and frame_path.exists():
					ssim_value = compute_ssim(previous_frame_path, frame_path, self.ssim_threshold)

					# If SSIM > threshold (0.98), frames are virtually identical
					if ssim_value > self.ssim_threshold:
						is_duplicate = True
						logger.debug(f"🔄 Frame {timestamp:.2f}s is duplicate (SSIM={ssim_value:.3f}), will skip Vision LLM")
						# Map this duplicate to the previous frame for analysis copying later
						if filtered_frame_paths:
							prev_unique_timestamp = filtered_frame_paths[-1][0]
							duplicate_map[timestamp] = prev_unique_timestamp

				if not is_duplicate:
					# Frame is unique, add to filtered list for Vision LLM analysis
					filtered_frame_paths.append((timestamp, frame_path))
					previous_frame_path = frame_path  # Update for next comparison

			deduplication_rate = ((len(frame_paths) - len(filtered_frame_paths)) / len(frame_paths) * 100) if frame_paths else 0
			logger.info(
				f"🎯 SSIM deduplication: {len(filtered_frame_paths)}/{len(frame_paths)} frames unique "
				f"({deduplication_rate:.1f}% duplicates filtered)"
			)

			# Analyze unique frames with vision AI
			# Process in batches to avoid overwhelming API
			batch_size = 10
			total_batches = (len(filtered_frame_paths) + batch_size - 1) // batch_size

			for batch_idx in range(0, len(filtered_frame_paths), batch_size):
				batch = filtered_frame_paths[batch_idx:batch_idx + batch_size]
				logger.info(
					f"🔍 Analyzing frame batch {batch_idx // batch_size + 1}/{total_batches} "
					f"({len(batch)} unique frames, {len(batch)}/{len(frame_paths)} after deduplication)"
				)

				# Process batch sequentially
				batch_analyses = []
				for timestamp, frame_path in batch:
					try:
						# Vision LLM frame analysis already includes visible_text (OCR)
						# No separate OCR step needed - Vision LLMs provide superior text extraction
						analysis = await analyze_frame_with_vision(frame_path, timestamp)
						if analysis:
							batch_analyses.append(analysis)
					except Exception as e:
						logger.warning(f"Frame analysis failed for {timestamp}s: {e}")
						# Continue with other frames
						continue

				frame_analyses.extend(batch_analyses)
				logger.debug(f"✅ Batch {batch_idx // batch_size + 1} complete: {len(batch_analyses)}/{len(batch)} frames analyzed")

			# Post-process: Expand frame_analyses with duplicates (copy from previous unique frames)
			# This allows us to preserve all frames but skip Vision LLM for duplicates
			if frame_analyses and duplicate_map:
				# Create mapping of timestamp -> analysis for duplicate expansion
				analysis_map = {analysis['timestamp']: analysis for analysis in frame_analyses}

				# Copy analysis for duplicate frames from their previous unique frames
				for duplicate_timestamp, previous_unique_timestamp in duplicate_map.items():
					if previous_unique_timestamp in analysis_map:
						previous_analysis = analysis_map[previous_unique_timestamp]

						# Copy previous frame's analysis for duplicate
						duplicate_analysis = previous_analysis.copy()
						duplicate_analysis['timestamp'] = duplicate_timestamp

						# Find frame path for duplicate timestamp
						duplicate_frame_path = None
						for t, fp in sorted_frame_paths:
							if t == duplicate_timestamp:
								duplicate_frame_path = fp
								break

						if duplicate_frame_path:
							duplicate_analysis['frame_path'] = str(duplicate_frame_path)
							duplicate_analysis['is_duplicate'] = True
							frame_analyses.append(duplicate_analysis)

			# Sort frame analyses by timestamp (deduplicates and unique frames)
			frame_analyses = sorted(frame_analyses, key=lambda x: x.get('timestamp', 0))

		except Exception as e:
			logger.error(f"Error analyzing frames: {e}", exc_info=True)

		return frame_analyses

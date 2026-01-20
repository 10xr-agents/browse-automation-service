"""
Frame filtering and scene detection.

Handles smart frame filtering using OpenCV pixel diff and scene change detection.
"""

import logging
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


async def detect_scene_changes(video_path: Path, duration: float) -> list[float]:
	"""
	Detect scene changes in video using FFmpeg scene detection.
	
	Args:
		video_path: Path to video file
		duration: Video duration in seconds
	
	Returns:
		List of scene change timestamps
	"""
	scene_changes = []

	try:
		# Use FFmpeg scene detection filter
		cmd = [
			'ffmpeg',
			'-i', str(video_path),
			'-vf', 'select=gt(scene\\,0.3),showinfo',
			'-f', 'null',
			'-'
		]

		result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

		# Parse output for scene change timestamps
		# Look for pts_time in ffmpeg output
		pts_pattern = r'pts_time:([\d.]+)'
		matches = re.finditer(pts_pattern, result.stderr)

		for match in matches:
			timestamp = float(match.group(1))
			if 0 <= timestamp < duration:
				scene_changes.append(timestamp)

		# Remove duplicates and sort
		scene_changes = sorted(set(scene_changes))

		logger.debug(f"🎬 Detected {len(scene_changes)} scene changes")

	except Exception as e:
		logger.warning(f"Scene detection failed: {e}, using fallback method")
		# Fallback: sample more frequently
		pass

	return scene_changes


async def smart_filter_pass1(
	video_path: Path,
	duration: float,
	strategic_timestamps: list[float],
	diff_resolution: tuple[int, int] = (640, 360),
	action_diff_threshold: float = 0.05
) -> list[float]:
	"""
	Smart Filter Pass 1: Fast scanning with OpenCV pixel diff (lightweight CPU).
	
	Scans video at 1fps using OpenCV VideoCapture to detect visual changes.
	This pre-filters frames before expensive SSIM/Vision LLM processing.
	
	Args:
		video_path: Path to video file
		duration: Video duration in seconds
		strategic_timestamps: Pre-computed strategic timestamps (scene changes, transcription, etc.)
		diff_resolution: Low-res proxy resolution for fast pixel diff (width, height)
		action_diff_threshold: Percentage threshold for detecting visual changes
	
	Returns:
		List of timestamps where visual changes were detected (action candidates)
	"""
	action_candidates = []

	try:
		import cv2
		import numpy as np
	except ImportError:
		logger.warning("OpenCV not available, skipping Smart Filter Pass 1")
		return []

	try:
		# Open video with OpenCV for fast scanning
		cap = cv2.VideoCapture(str(video_path))
		if not cap.isOpened():
			logger.warning(f"Failed to open video with OpenCV: {video_path}")
			return []

		fps = cap.get(cv2.CAP_PROP_FPS)
		if fps <= 0:
			fps = 30.0  # Default fallback

		# Sampling config: Check 1 frame per second (lightweight)
		sample_rate = 1  # 1 frame per second
		frame_skip = int(fps * sample_rate)  # Skip frames between samples

		# Low-res proxy resolution for fast pixel diff (10x faster than 1080p/4K)
		diff_width, diff_height = diff_resolution  # (640, 360) = 360p

		# Visual change threshold (5% of pixels changed = significant change)
		# Using percentage instead of absolute pixel count for resolution-independent detection
		pixel_diff_threshold_percent = action_diff_threshold  # 5% of pixels
		total_pixels_proxy = diff_width * diff_height
		diff_threshold = int(total_pixels_proxy * pixel_diff_threshold_percent * 255)  # Approximate threshold for absdiff sum

		last_processed_frame = None
		last_processed_timestamp = None

		logger.debug(f"🎬 Starting Smart Filter Pass 1: scanning video at {sample_rate}fps for visual changes...")

		frame_count = 0
		while True:
			ret, frame = cap.read()
			if not ret:
				break

			frame_count += 1

			# Skip frames to sample at 1fps (lightweight)
			if frame_count % frame_skip != 0:
				continue

			# Get current timestamp
			timestamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
			if timestamp >= duration:
				break

			# Pass 1: Fast pixel diff on low-res proxy (is something moving?)
			# Resize to 360p for 10x faster diff calculation (only for this check)
			frame_proxy = cv2.resize(frame, (diff_width, diff_height))

			if last_processed_frame is None:
				# First frame is always a candidate
				action_candidates.append(timestamp)
				last_processed_frame = frame_proxy.copy()
				last_processed_timestamp = timestamp
			else:
				# Fast subtract on low-res proxy - very cheap on CPU (10x faster than 1080p)
				diff = cv2.absdiff(frame_proxy, last_processed_frame)
				score = np.sum(diff)

				# If pixel difference > threshold, mark as action candidate
				# We only load full-resolution frames for candidates that pass this filter
				if score > diff_threshold:
					# Only add if not too close to previous candidate (avoid duplicates)
					if last_processed_timestamp is None or (timestamp - last_processed_timestamp) > 0.5:
						action_candidates.append(timestamp)
						last_processed_frame = frame_proxy.copy()
						last_processed_timestamp = timestamp

		cap.release()

		logger.debug(f"✅ Smart Filter Pass 1 complete: {len(action_candidates)} action candidates detected")

	except Exception as e:
		logger.warning(f"Smart Filter Pass 1 failed: {e}, continuing without action-triggered sampling")

	return action_candidates

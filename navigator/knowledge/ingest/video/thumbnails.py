"""
Video thumbnail generation.

Generates thumbnails at key intervals in the video.
"""

import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_thumbnails(
	video_path: Path,
	ingestion_id: str,
	duration: float,
	thumbnail_count: int = 5
) -> list[Path]:
	"""
	Generate thumbnails at key intervals.
	
	Args:
		video_path: Path to video file
		ingestion_id: Ingestion ID for naming
		duration: Video duration in seconds
		thumbnail_count: Number of thumbnails to generate
	
	Returns:
		List of thumbnail file paths
	"""
	if duration <= 0:
		logger.warning(f"Invalid duration for thumbnail generation: {duration}")
		return []

	thumbnail_paths = []

	try:
		# Create temp directory for thumbnails
		temp_dir = Path(tempfile.gettempdir()) / 'video_thumbnails' / ingestion_id
		temp_dir.mkdir(parents=True, exist_ok=True)

		# Generate thumbnails at intervals
		for i in range(thumbnail_count):
			# Calculate timestamp (0%, 25%, 50%, 75%, 100%)
			progress = i / (thumbnail_count - 1) if thumbnail_count > 1 else 0
			timestamp = duration * progress

			# Cap timestamp at duration - 0.1s to avoid FFmpeg errors at exact end (100%)
			# FFmpeg can fail when extracting frames at the very end of video
			if progress >= 1.0:
				timestamp = max(0.0, duration - 0.1)

			# Output path
			output_path = temp_dir / f"thumbnail_{i}_{int(progress*100)}pct.jpg"

			# Use ffmpeg to extract frame
			cmd = [
				'ffmpeg',
				'-ss', str(timestamp),
				'-i', str(video_path),
				'-vframes', '1',
				'-q:v', '2',
				'-y',
				str(output_path)
			]

			result = subprocess.run(
				cmd,
				capture_output=True,
				text=True,
				timeout=30
			)

			if result.returncode == 0 and output_path.exists():
				thumbnail_paths.append(output_path)
				logger.debug(f"✅ Generated thumbnail at {int(progress*100)}%: {output_path}")
			else:
				logger.error(f"Failed to generate thumbnail at {timestamp}s: {result.stderr}")

	except FileNotFoundError:
		logger.error("ffmpeg not found. Please install ffmpeg.")
	except Exception as e:
		logger.error(f"Error generating thumbnails: {e}")

	return thumbnail_paths

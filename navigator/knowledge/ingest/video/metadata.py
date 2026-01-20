"""
Video metadata extraction and formatting.

Handles extraction of video metadata using ffprobe and formatting as text.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def extract_metadata(video_path: Path) -> dict[str, Any] | None:
	"""
	Extract video metadata using ffprobe.
	
	Args:
		video_path: Path to video file
	
	Returns:
		Metadata dictionary or None if extraction failed
	"""
	try:
		# Use ffprobe to extract metadata
		cmd = [
			'ffprobe',
			'-v', 'quiet',
			'-print_format', 'json',
			'-show_format',
			'-show_streams',
			str(video_path)
		]

		result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

		if result.returncode != 0:
			logger.error(f"ffprobe failed: {result.stderr}")
			return None

		data = json.loads(result.stdout)

		# Extract relevant metadata
		format_info = data.get('format', {})
		streams = data.get('streams', [])

		# Find video stream
		video_stream = next((s for s in streams if s.get('codec_type') == 'video'), {})
		audio_streams = [s for s in streams if s.get('codec_type') == 'audio']
		subtitle_streams = [s for s in streams if s.get('codec_type') == 'subtitle']

		metadata = {
			'duration': float(format_info.get('duration', 0)),
			'size_bytes': int(format_info.get('size', 0)),
			'format_name': format_info.get('format_name', 'unknown'),
			'bit_rate': int(format_info.get('bit_rate', 0)),
			# Video stream info
			'width': video_stream.get('width', 0),
			'height': video_stream.get('height', 0),
			'codec_name': video_stream.get('codec_name', 'unknown'),
			'codec_long_name': video_stream.get('codec_long_name', 'unknown'),
			'frame_rate': video_stream.get('r_frame_rate', 'unknown'),
			'aspect_ratio': video_stream.get('display_aspect_ratio', 'unknown'),
			# Stream counts
			'audio_tracks': len(audio_streams),
			'subtitle_tracks': len(subtitle_streams),
		}

		return metadata

	except FileNotFoundError:
		logger.error("ffprobe not found. Please install ffmpeg.")
		return None
	except Exception as e:
		logger.error(f"Error extracting metadata: {e}")
		return None


def format_metadata_as_text(video_path: Path, metadata: dict[str, Any]) -> str:
	"""Format video metadata as readable text."""
	duration_min = int(metadata.get('duration', 0) // 60)
	duration_sec = int(metadata.get('duration', 0) % 60)

	size_mb = metadata.get('size_bytes', 0) / (1024 * 1024)

	text = f"""# Video: {video_path.name}

## Metadata

- **Duration**: {duration_min}:{duration_sec:02d}
- **Resolution**: {metadata.get('width', 0)}x{metadata.get('height', 0)}
- **Format**: {metadata.get('format_name', 'unknown')}
- **Codec**: {metadata.get('codec_long_name', 'unknown')} ({metadata.get('codec_name', 'unknown')})
- **Frame Rate**: {metadata.get('frame_rate', 'unknown')}
- **Aspect Ratio**: {metadata.get('aspect_ratio', 'unknown')}
- **Bit Rate**: {metadata.get('bit_rate', 0) // 1000} kbps
- **File Size**: {size_mb:.2f} MB
- **Audio Tracks**: {metadata.get('audio_tracks', 0)}
- **Subtitle Tracks**: {metadata.get('subtitle_tracks', 0)}

## File Information

- **Path**: {video_path}
- **Format**: {video_path.suffix}
"""
	return text

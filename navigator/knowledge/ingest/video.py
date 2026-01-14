"""
Video ingestion and metadata extraction.

Supports video file uploads or URLs with comprehensive metadata extraction
and thumbnail generation.
"""

import logging
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from navigator.schemas import (
	ContentChunk,
	IngestionResult,
	SourceMetadata,
	SourceType,
	VideoFormat,
	detect_video_format,
)

logger = logging.getLogger(__name__)


class VideoIngester:
	"""
	Ingests video files and extracts metadata.
	
	Features:
	- Video metadata extraction (duration, resolution, format, codec)
	- Thumbnail generation at key intervals
	- Support for multiple video formats (MP4, WebM, AVI, MOV, MKV)
	- Audio and subtitle track detection
	"""
	
	def __init__(self, thumbnail_count: int = 5):
		"""
		Initialize video ingester.
		
		Args:
			thumbnail_count: Number of thumbnails to generate per video
		"""
		self.thumbnail_count = thumbnail_count
	
	def ingest_video(self, video_path: str | Path) -> IngestionResult:
		"""
		Ingest a video file.
		
		Args:
			video_path: Path to the video file
		
		Returns:
			IngestionResult with video metadata
		"""
		video_path = Path(video_path)
		
		# Create result
		result = IngestionResult(
			ingestion_id=str(uuid4()),
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
			metadata = self._extract_metadata(video_path)
			
			if metadata:
				# Create content chunk with metadata
				chunk = ContentChunk(
					chunk_id=f"{result.ingestion_id}_metadata",
					content=self._format_metadata_as_text(video_path, metadata),
					chunk_index=0,
					token_count=100,  # Approximate
					chunk_type="video_metadata",
					section_title=video_path.stem,
				)
				result.content_chunks.append(chunk)
				
				# Generate thumbnails
				thumbnail_paths = self._generate_thumbnails(video_path, result.ingestion_id, metadata.get('duration', 0))
				
				if thumbnail_paths:
					# Create chunk with thumbnail references
					thumbnail_chunk = ContentChunk(
						chunk_id=f"{result.ingestion_id}_thumbnails",
						content=f"Generated {len(thumbnail_paths)} thumbnails: {', '.join(str(p) for p in thumbnail_paths)}",
						chunk_index=1,
						token_count=50,
						chunk_type="video_thumbnails",
					)
					result.content_chunks.append(thumbnail_chunk)
				
				logger.info(f"✅ Ingested video {video_path.name}: {len(result.content_chunks)} chunks")
			else:
				result.add_error(
					"MetadataExtractionError",
					"Could not extract video metadata",
					{"video_path": str(video_path)}
				)
			
			# Mark complete
			result.mark_complete()
		
		except Exception as e:
			logger.error(f"❌ Error ingesting video {video_path}: {e}", exc_info=True)
			result.add_error("VideoIngestionError", str(e), {"video_path": str(video_path)})
			result.mark_complete()
		
		return result
	
	def _extract_metadata(self, video_path: Path) -> dict[str, Any] | None:
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
			
			import json
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
	
	def _generate_thumbnails(
		self,
		video_path: Path,
		ingestion_id: str,
		duration: float
	) -> list[Path]:
		"""
		Generate thumbnails at key intervals.
		
		Args:
			video_path: Path to video file
			ingestion_id: Ingestion ID for naming
			duration: Video duration in seconds
		
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
			for i in range(self.thumbnail_count):
				# Calculate timestamp (0%, 25%, 50%, 75%, 100%)
				progress = i / (self.thumbnail_count - 1) if self.thumbnail_count > 1 else 0
				timestamp = duration * progress
				
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
					logger.info(f"✅ Generated thumbnail at {int(progress*100)}%: {output_path}")
				else:
					logger.error(f"Failed to generate thumbnail at {timestamp}s: {result.stderr}")
			
		except FileNotFoundError:
			logger.error("ffmpeg not found. Please install ffmpeg.")
		except Exception as e:
			logger.error(f"Error generating thumbnails: {e}")
		
		return thumbnail_paths
	
	def _format_metadata_as_text(self, video_path: Path, metadata: dict[str, Any]) -> str:
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

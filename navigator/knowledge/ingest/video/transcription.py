"""
Video transcription using Deepgram API and subtitle extraction.

Handles video audio transcription via Deepgram cloud API and embedded subtitle extraction.
"""

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from tenacity import (
	retry,
	retry_if_exception_type,
	stop_after_attempt,
	wait_exponential,
)

logger = logging.getLogger(__name__)


@retry(
	stop=stop_after_attempt(3),
	wait=wait_exponential(multiplier=1, min=4, max=10),
	retry=retry_if_exception_type((ConnectionError, TimeoutError, Exception)),
	reraise=True
)
def transcribe_with_deepgram_retry(dg_client, buffer_data):
	"""
	Transcribe audio buffer using Deepgram API with retry logic.
	
	Args:
		dg_client: Deepgram client instance
		buffer_data: Audio file buffer data
	
	Returns:
		Deepgram response object
	"""
	try:
		# Deepgram SDK v3 API: use listen.v1.media.transcribe_file()
		# All options are passed directly as keyword arguments (not as options dict)
		return dg_client.listen.v1.media.transcribe_file(
			request=buffer_data,
			model="nova-2",  # Fast & cost effective (30% faster than nova-3)
			language="en",
			utterances=True,  # Enable utterances (segments)
			smart_format=True,  # Punctuation, capitalization, etc.
			punctuate=True,  # Additional formatting
			# diarize=False,  # Optional: speaker diarization (set to True if needed)
		)
	except Exception as e:
		logger.warning(f"Deepgram API call failed (retrying...): {e}")
		raise  # Re-raise to trigger retry


async def transcribe_video(video_path: Path) -> dict[str, Any] | None:
	"""
	Transcribe video audio using Deepgram API (cloud-based).
	
	Uses Deepgram for cloud-based transcription with high accuracy,
	word-level timestamps, and speaker diarization support.
	Requires DEEPGRAM_API_KEY environment variable.
	
	Returns:
		Transcription data with segments and full text
	"""
	# Check for Deepgram API key
	deepgram_api_key = os.getenv('DEEPGRAM_API_KEY')
	if not deepgram_api_key:
		error_msg = (
			"DEEPGRAM_API_KEY environment variable is required for video transcription. "
			"Get your API key at https://console.deepgram.com/"
		)
		logger.error(error_msg)
		raise ValueError(error_msg)

	try:
		from deepgram import DeepgramClient
	except ImportError as e:
		error_msg = (
			"deepgram-sdk is required for video transcription but is not installed. "
			"Install it with: uv pip install deepgram-sdk "
			"or ensure it's in your pyproject.toml dependencies."
		)
		logger.error(error_msg)
		raise ImportError(error_msg) from e

	# Validate file exists
	if not video_path.exists():
		raise FileNotFoundError(f"Video file not found: {video_path}")

	try:
		file_size = video_path.stat().st_size
		logger.info(f"Transcribing video with Deepgram: {video_path.name} ({file_size / (1024**2):.2f} MB)")

		# Extract audio from video using ffmpeg (Deepgram needs audio file)
		# Use tempfile to create a temporary audio file
		with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as audio_temp:
			audio_path = Path(audio_temp.name)

		try:
			# Extract audio using ffmpeg
			logger.debug("Extracting audio from video for Deepgram transcription...")
			cmd = [
				'ffmpeg',
				'-i', str(video_path),
				'-vn',  # No video
				'-acodec', 'pcm_s16le',  # PCM 16-bit WAV
				'-ar', '16000',  # Sample rate 16kHz (Deepgram works well with this)
				'-ac', '1',  # Mono channel
				'-y',  # Overwrite output file
				str(audio_path)
			]

			result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
			if result.returncode != 0:
				raise RuntimeError(f"FFmpeg audio extraction failed: {result.stderr}")

			if not audio_path.exists():
				raise RuntimeError("Audio file was not created by FFmpeg")

			logger.debug(f"Audio extracted successfully: {audio_path.name}")

			# Initialize Deepgram client
			dg_client = DeepgramClient(api_key=deepgram_api_key)

			# Read audio file as buffer
			with open(audio_path, 'rb') as audio_file:
				buffer_data = audio_file.read()

			# Transcribe audio using Deepgram with retry logic
			# Deepgram SDK v3: pass options directly as keyword arguments (not as options dict)
			logger.info("Starting Deepgram transcription (cloud-based API)...")
			response = transcribe_with_deepgram_retry(dg_client, buffer_data)

			# Process Deepgram response
			transcription_parts = []
			segments = []
			words = []
			confidences = []

			# Extract utterances (segments)
			if hasattr(response, 'results') and hasattr(response.results, 'utterances'):
				utterances = response.results.utterances

				for utt in utterances:
					segment_text = utt.transcript.strip() if hasattr(utt, 'transcript') else ''
					if not segment_text:
						continue

					transcription_parts.append(segment_text)

					# Create segment entry
					segments.append({
						'start': utt.start if hasattr(utt, 'start') else 0.0,
						'end': utt.end if hasattr(utt, 'end') else 0.0,
						'text': segment_text,
					})

					# Extract words from utterance (Deepgram provides word-level timestamps)
					if hasattr(utt, 'words') and utt.words:
						for word in utt.words:
							word_text = word.word.strip() if hasattr(word, 'word') else ''
							if word_text:
								word_confidence = word.confidence if hasattr(word, 'confidence') else utt.confidence if hasattr(utt, 'confidence') else 0.95
								words.append({
									'word': word_text,
									'start': word.start if hasattr(word, 'start') else 0.0,
									'end': word.end if hasattr(word, 'end') else 0.0,
									'confidence': word_confidence,
								})
								confidences.append(word_confidence)

			# Combine all transcription text
			transcription_text = ' '.join(transcription_parts)

			# Validate we have transcription data
			if not transcription_text and not segments:
				logger.warning("Deepgram returned empty transcription")
				return None

			# Calculate average confidence
			avg_confidence = sum(confidences) / len(confidences) if confidences else 0.95

			# Get detected language from response metadata
			detected_language = "en-US"
			if hasattr(response, 'metadata') and hasattr(response.metadata, 'language'):
				detected_language = response.metadata.language

			# If we only have segments but no word-level timestamps, merge segments by gaps
			if segments and not words:
				# Group segments by time gap (>3 seconds creates new segment group)
				grouped_segments = []
				for seg in segments:
					if not grouped_segments or seg['start'] - grouped_segments[-1]['end'] > 3.0:
						grouped_segments.append(seg.copy())
					else:
						grouped_segments[-1]['end'] = seg['end']
						grouped_segments[-1]['text'] += ' ' + seg['text']

				segments = grouped_segments

			logger.info(
				f"✅ Deepgram transcription completed: {len(segments)} segments, "
				f"{len(transcription_text)} chars, language: {detected_language}, "
				f"confidence: {avg_confidence:.2f}"
			)

			return {
				'transcription': transcription_text,
				'segments': segments,
				'language': detected_language,
				'confidence': avg_confidence,
			}

		finally:
			# Clean up temporary audio file
			if audio_path.exists():
				try:
					audio_path.unlink()
				except Exception as e:
					logger.debug(f"Failed to delete temporary audio file: {e}")

	except (ValueError, FileNotFoundError, ImportError):
		# Re-raise these as-is (already have good error messages)
		raise
	except Exception as e:
		logger.error(f"Unexpected error transcribing video with Deepgram: {e}", exc_info=True)
		raise RuntimeError(f"Video transcription failed: {str(e)}") from e


async def extract_subtitles(video_path: Path, ingestion_id: str) -> dict[str, Any] | None:
	"""
	Extract embedded subtitles from video file using ffmpeg.
	
	Args:
		video_path: Path to video file
		ingestion_id: Ingestion ID for naming
	
	Returns:
		Subtitle data with segments and timestamps
	"""
	try:
		# Use ffmpeg to extract subtitles (SRT format)
		with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False) as temp_srt:
			srt_path = Path(temp_srt.name)

		try:
			cmd = [
				'ffmpeg',
				'-i', str(video_path),
				'-map', '0:s:0',  # Extract first subtitle stream
				'-y',
				str(srt_path)
			]

			result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

			if result.returncode != 0 or not srt_path.exists():
				logger.debug("No embedded subtitles found or extraction failed")
				return None

			# Parse SRT file
			subtitles = []
			with open(srt_path, 'r', encoding='utf-8', errors='ignore') as f:
				content = f.read()

				# Parse SRT format (sequence number, timestamps, text)
				srt_pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\d+\n|\n*$)'
				matches = re.finditer(srt_pattern, content, re.DOTALL)

				for match in matches:
					start_str = match.group(2).replace(',', '.')
					end_str = match.group(3).replace(',', '.')
					text = match.group(4).strip().replace('\n', ' ')

					# Convert SRT timestamp to seconds
					def srt_to_seconds(srt_time: str) -> float:
						parts = srt_time.split(':')
						hours = int(parts[0])
						minutes = int(parts[1])
						secs_parts = parts[2].split('.')
						seconds = int(secs_parts[0])
						milliseconds = int(secs_parts[1]) / 1000.0
						return hours * 3600 + minutes * 60 + seconds + milliseconds

					start = srt_to_seconds(start_str)
					end = srt_to_seconds(end_str)

					subtitles.append({
						'start': start,
						'end': end,
						'text': text,
					})

			if subtitles:
				logger.info(f"✅ Extracted {len(subtitles)} subtitle segments")
				return {'subtitles': subtitles}

			return None

		finally:
			# Clean up temporary SRT file
			if srt_path.exists():
				try:
					srt_path.unlink()
				except Exception:
					pass

	except Exception as e:
		logger.debug(f"Subtitle extraction failed: {e}")
		return None

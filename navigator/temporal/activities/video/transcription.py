"""
Video Transcription Activity

Transcribes video audio using Deepgram API.
"""

import logging
from pathlib import Path

from temporalio import activity

from navigator.knowledge.ingest.video.transcription import transcribe_video
from navigator.schemas import TranscribeVideoInput, TranscribeVideoResult

logger = logging.getLogger(__name__)


@activity.defn(name="transcribe_video")
async def transcribe_video_activity(input: TranscribeVideoInput) -> TranscribeVideoResult:
	"""
	Transcribe video audio using Deepgram API (cloud-based).
	
	This activity:
	1. Extracts audio from video using ffmpeg
	2. Sends audio to Deepgram API for transcription
	3. Returns transcription segments with timestamps
	
	Args:
		input: Transcription parameters (video_path, ingestion_id, job_id)
	
	Returns:
		Transcription result with segments and full text
	"""
	workflow_id = activity.info().workflow_id

	logger.info(f"🔵 ACTIVITY START: transcribe_video (Workflow: {workflow_id}, Video: {input.video_path})")

	activity.heartbeat({"status": "transcribing", "video_path": input.video_path})

	try:
		# Transcribe video using module function
		video_path = Path(input.video_path)
		transcription_data = await transcribe_video(video_path)

		if not transcription_data:
			error_msg = "Transcription returned empty data"
			logger.warning(f"⚠️ {error_msg}")
			return TranscribeVideoResult(
				transcription_data={},
				success=False,
				errors=[error_msg],
			)

		logger.info(f"✅ Transcription completed: {len(transcription_data.get('segments', []))} segments")

		return TranscribeVideoResult(
			transcription_data=transcription_data,
			success=True,
		)

	except Exception as e:
		logger.error(f"❌ Transcription failed: {e}", exc_info=True)
		return TranscribeVideoResult(
			transcription_data={},
			success=False,
			errors=[str(e)],
		)

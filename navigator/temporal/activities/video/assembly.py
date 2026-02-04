"""
Video Ingestion Assembly Activity

Assembles video ingestion results from transcription, frame analysis, and metadata.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from temporalio import activity

from navigator.knowledge.ingest.video import VideoIngester
from navigator.knowledge.ingest.video.action_extraction import extract_action_sequence
from navigator.knowledge.ingest.video.frame_analysis.formatting import format_frame_analysis
from navigator.knowledge.ingest.video.metadata import extract_metadata, format_metadata_as_text
from navigator.knowledge.ingest.video.thumbnails import generate_thumbnails
from navigator.knowledge.persist.ingestion import save_ingestion_result
from navigator.knowledge.s3_frame_storage import get_frame_storage
from navigator.schemas import (
	AssembleVideoIngestionInput,
	AssembleVideoIngestionResult,
	ContentChunk,
	IngestionResult,
	SourceMetadata,
	SourceType,
	detect_video_format,
)

logger = logging.getLogger(__name__)


@activity.defn(name="assemble_video_ingestion")
async def assemble_video_ingestion_activity(
	input: AssembleVideoIngestionInput
) -> AssembleVideoIngestionResult:
	"""
	Assemble video ingestion results from transcription, frame analysis, and metadata.
	
	This activity:
	1. Creates metadata chunk
	2. Creates transcription chunks
	3. Downloads and merges frame analysis results from S3
	4. Creates frame analysis chunks
	5. Extracts action sequences
	6. Generates thumbnails
	7. Saves final ingestion result to MongoDB
	
	Args:
		input: Assembly parameters (video_path, ingestion_id, transcription_data, analysis_result_s3_keys, metadata)
	
	Returns:
		Assembly result with chunk counts
	"""
	workflow_id = activity.info().workflow_id

	logger.info(
		f"🔵 ACTIVITY START: assemble_video_ingestion (Workflow: {workflow_id}, "
		f"Ingestion: {input.ingestion_id})"
	)

	activity.heartbeat({"status": "assembling", "ingestion_id": input.ingestion_id})

	try:
		# Initialize video ingester for helper methods
		video_ingester = VideoIngester()
		video_path = Path(input.video_path)

		# Extract metadata if not provided
		metadata_dict = input.metadata
		if not metadata_dict:
			metadata_dict = extract_metadata(video_path)

		# Create SourceMetadata
		# Safely get file stats (handle missing file or permission errors)
		size_bytes = 0
		last_modified = None
		if video_path.exists():
			try:
				stat_result = video_path.stat()
				size_bytes = stat_result.st_size
				last_modified = datetime.fromtimestamp(stat_result.st_mtime)
			except (OSError, PermissionError) as e:
				logger.warning(f"⚠️ Failed to get file stats for {video_path}: {e}")
		
		source_metadata = SourceMetadata(
			source_type=SourceType.VIDEO_WALKTHROUGH,
			url=str(video_path),
			title=video_path.stem,
			format=detect_video_format(str(video_path)),
			size_bytes=size_bytes,
			last_modified=last_modified,
		)

		# Create IngestionResult
		result = IngestionResult(
			ingestion_id=input.ingestion_id,
			source_type=SourceType.VIDEO_WALKTHROUGH,
			metadata=source_metadata,
		)

		# Step 1: Create metadata chunk
		if metadata_dict:
			metadata_text = format_metadata_as_text(video_path, metadata_dict)
			metadata_chunk = ContentChunk(
				chunk_id=f"{input.ingestion_id}_metadata",
				content=metadata_text,
				chunk_index=0,
				token_count=100,
				chunk_type="video_metadata",
				section_title=video_path.stem,
			)
			result.content_chunks.append(metadata_chunk)

		# Step 2: Create transcription chunks
		if input.transcription_data:
			segments = input.transcription_data.get('segments', [])
			for idx, segment in enumerate(segments):
				transcription_chunk = ContentChunk(
					chunk_id=f"{input.ingestion_id}_transcription_{idx}",
					content=f"[{segment['start']:.2f}-{segment['end']:.2f}] {segment['text']}",
					chunk_index=len(result.content_chunks),
					token_count=int(len(segment['text'].split()) * 1.3),
					chunk_type="video_transcription",
					section_title=f"Transcription Segment {idx + 1}",
				)
				result.content_chunks.append(transcription_chunk)

			# Add full transcription summary
			full_transcription = input.transcription_data.get('transcription', '')
			if full_transcription:
				summary_chunk = ContentChunk(
					chunk_id=f"{input.ingestion_id}_transcription_full",
					content=f"# Full Video Transcription\n\n{full_transcription}",
					chunk_index=len(result.content_chunks),
					token_count=int(len(full_transcription.split()) * 1.3),
					chunk_type="video_transcription_full",
					section_title="Complete Transcription",
				)
				result.content_chunks.append(summary_chunk)

		# Step 3: Download and merge frame analysis results from S3 (Claim Check pattern)
		all_frame_analyses = []
		frame_storage = get_frame_storage()

		for s3_key in input.analysis_result_s3_keys:
			# Skip empty S3 keys (failed batches)
			if not s3_key or not s3_key.strip():
				logger.debug(f"⚠️ Skipping empty S3 key (failed batch)")
				continue
			
			try:
				# Download batch result JSON from S3
				if s3_key.startswith('s3://'):
					# Parse s3://bucket/key format
					parts = s3_key.replace('s3://', '').split('/', 1)
					if len(parts) != 2:
						logger.warning(f"⚠️ Invalid S3 key format: {s3_key}, skipping")
						continue

					bucket, key = parts

					# Download JSON from S3
					s3_client = frame_storage._get_s3_client()

					loop = asyncio.get_event_loop()
					response = await loop.run_in_executor(
						None,
						lambda: s3_client.get_object(Bucket=bucket, Key=key)
					)

					# Parse JSON
					batch_results = json.loads(response['Body'].read().decode('utf-8'))
					all_frame_analyses.extend(batch_results)
					logger.debug(f"📥 Downloaded batch results from S3: {s3_key} ({len(batch_results)} frames)")
				else:
					# Local filesystem path (fallback)
					with open(s3_key, 'r') as f:
						batch_results = json.load(f)
					all_frame_analyses.extend(batch_results)
					logger.debug(f"📥 Read batch results from local: {s3_key} ({len(batch_results)} frames)")

			except Exception as e:
				logger.warning(f"⚠️ Failed to load batch results from {s3_key}: {e}")
				continue

		# Step 4: Create frame analysis chunks
		if all_frame_analyses:
			activity.heartbeat({"status": "formatting_frame_analyses", "frames_count": len(all_frame_analyses)})

			# Format frame analyses into text chunks
			for idx, frame_analysis in enumerate(all_frame_analyses):
				formatted_text = format_frame_analysis(frame_analysis)
				# Phase 5.2: Store raw frame analysis in metadata for spatial extraction
				frame_chunk = ContentChunk(
					chunk_id=f"{input.ingestion_id}_frame_{idx}",
					content=formatted_text,
					chunk_index=len(result.content_chunks),
					token_count=int(len(formatted_text.split()) * 1.3),
					chunk_type="video_frame_analysis",
					section_title=f"Frame Analysis {idx + 1}",
					# Phase 5.2: Store raw frame analysis data in metadata for spatial extraction
					metadata={
						'frame_analysis': frame_analysis,  # Store raw analysis dict for spatial extraction
						'timestamp': frame_analysis.get('timestamp', 0),
						'screen_state': frame_analysis.get('screen_state', 'Unknown'),
					}
				)
				result.content_chunks.append(frame_chunk)

		# Step 5: Extract action sequences
		if all_frame_analyses:
			activity.heartbeat({"status": "extracting_actions"})
			action_sequences = extract_action_sequence(all_frame_analyses)
			if action_sequences:
				# Format action sequences as a readable string
				action_lines = []
				for idx, action in enumerate(action_sequences, 1):
					timestamp = action.get('timestamp', 0)
					action_type = action.get('action_type', 'unknown')
					target = action.get('target', 'unknown')
					context = action.get('context', '')
					screen = action.get('screen', 'Unknown')
					action_lines.append(
						f"{idx}. [{timestamp:.2f}s] {action_type}: {target} on {screen}"
					)
					if context:
						action_lines.append(f"   Context: {context}")
				
				action_text = "# Action Sequences\n\n" + "\n".join(action_lines)
				
				action_chunk = ContentChunk(
					chunk_id=f"{input.ingestion_id}_actions",
					content=action_text,
					chunk_index=len(result.content_chunks),
					token_count=int(len(action_text.split()) * 1.3),
					chunk_type="video_actions",
					section_title="Extracted Actions",
				)
				result.content_chunks.append(action_chunk)

		# Step 6: Generate thumbnails
		activity.heartbeat({"status": "generating_thumbnails"})
		# Get duration from metadata
		duration = metadata_dict.get('duration', 0) if metadata_dict else 0
		if duration <= 0:
			# Extract metadata if duration not available
			extracted_metadata = extract_metadata(video_path)
			if extracted_metadata:
				duration = extracted_metadata.get('duration', 0)
		
		if duration > 0:
			thumbnails = generate_thumbnails(video_path, input.ingestion_id, duration)
			if thumbnails:
				result.metadata.thumbnails = [str(t) for t in thumbnails]
		else:
			logger.warning(f"⚠️ Cannot generate thumbnails: invalid duration ({duration})")

		# Step 7: Save to MongoDB
		activity.heartbeat({"status": "saving_result"})
		await save_ingestion_result(result)

		logger.info(f"✅ Assembled video ingestion: {result.total_chunks} chunks, {result.total_tokens} tokens")

		return AssembleVideoIngestionResult(
			ingestion_id=input.ingestion_id,
			content_chunks=result.total_chunks,
			total_tokens=result.total_tokens,
			success=True,
		)

	except Exception as e:
		logger.error(f"❌ Video assembly failed: {e}", exc_info=True)
		return AssembleVideoIngestionResult(
			ingestion_id=input.ingestion_id,
			content_chunks=0,
			total_tokens=0,
			success=False,
			errors=[str(e)],
		)

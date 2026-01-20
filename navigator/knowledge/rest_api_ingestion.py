"""
REST API: Ingestion Endpoints (Phase 6.1)

Endpoints for starting knowledge extraction workflows.
"""

import logging
from uuid import uuid4

try:
	from fastapi import APIRouter, File, Form, HTTPException, UploadFile
	FASTAPI_AVAILABLE = True
except ImportError:
	FASTAPI_AVAILABLE = False
	logging.warning('FastAPI not installed. Install with: pip install fastapi')

from temporalio.client import Client
from temporalio.common import RetryPolicy
from datetime import timedelta

from navigator.knowledge.rest_api_models import (
	IngestionOptionsModel,
	StartIngestionRequest,
	StartIngestionResponse,
)
from navigator.knowledge.persist.collections import SourceType
from navigator.knowledge.persist.state import WorkflowState, WorkflowStatus, save_workflow_state
from navigator.knowledge.s3_downloader import get_s3_downloader
from navigator.schemas import KnowledgeExtractionInputV2
from navigator.schemas.s3 import S3DownloadError
from navigator.temporal.config import get_temporal_client
from navigator.temporal.workflows import KnowledgeExtractionWorkflowV2

logger = logging.getLogger(__name__)


def register_ingestion_routes(
	router: APIRouter,
	_get_temporal_client: callable
) -> None:
	"""
	Register ingestion API routes (Phase 6.1).
	
	Args:
		router: FastAPI router to register routes on
		_get_temporal_client: Function to get Temporal client
	"""
	
	@router.post(
		"/ingest/start",
		response_model=StartIngestionResponse,
		summary="Start Knowledge Extraction (Two-Phase Process)",
		description=(
			"Start a knowledge extraction workflow with two phases:\n\n"
			"**Phase 1:** Extract knowledge from files or documentation URLs\n"
			"- Process uploaded files (video, audio, txt, md, docx, pdf, etc.) OR\n"
			"- Process publicly available documentation URLs for crawling\n\n"
			"**Phase 2:** DOM-level analysis on website with authentication\n"
			"- Use website_url + credentials to perform authenticated DOM analysis\n"
			"- Extract additional knowledge through browser-based interaction\n\n"
			"**Required Fields:**\n"
			"- `website_url`: Target website/webportal for Phase 2 DOM analysis\n"
			"- At least one of: `s3_references` (files) OR `documentation_urls`\n\n"
			"**Example Request (Files + Website with Credentials):**\n"
			"```json\n"
			"{\n"
			"  \"website_url\": \"https://app.example.com\",\n"
			"  \"website_name\": \"Example App\",\n"
			"  \"credentials\": {\n"
			"    \"username\": \"user@example.com\",\n"
			"    \"password\": \"secure-password\",\n"
			"    \"login_url\": \"https://app.example.com/signin\"\n"
			"  },\n"
			"  \"s3_references\": [...],\n"
			"  \"file_metadata_list\": [...],\n"
			"  \"documentation_urls\": [\"https://docs.example.com\"],\n"
			"  \"knowledge_id\": \"696cc27b31f1cd2e29d55bc1\"\n"
			"}\n"
			"```\n\n"
			"**Note:** `s3_references` and `file_metadata_list` must have the same length.\n"
			"`login_url` in credentials is optional - crawler will auto-detect login pages.\n\n"
			"**Process:**\n"
			"1. Phase 1: Process files/documentation URLs\n"
			"2. Phase 2: Perform authenticated DOM analysis on website\n"
			"3. Receive `job_id` for tracking\n"
			"4. Poll `/workflows/status/{job_id}` for progress\n"
			"5. Query extracted knowledge via graph API"
		),
		response_description="Ingestion job details with tracking ID",
		responses={
			200: {"description": "Workflow started successfully"},
			400: {"description": "Invalid request parameters"},
			500: {"description": "Internal server error"}
		}
	)
	async def start_ingestion(request: StartIngestionRequest) -> StartIngestionResponse:
		"""
		Start knowledge extraction workflow (two-phase process).
		
		Phase 1: Extract knowledge from files or documentation URLs
		- Process uploaded files (video, audio, txt, md, docx, pdf, etc.) OR
		- Process publicly available documentation URLs for crawling
		
		Phase 2: DOM-level analysis on website with authentication
		- Use website_url + credentials to perform authenticated DOM analysis
		- Extract additional knowledge through browser-based interaction
		
		Returns job_id for tracking workflow progress.
		"""
		# 🐛 DEBUG: Log incoming request from UI
		logger.debug("=" * 80)
		logger.debug("🐛 DEBUG: Received knowledge extraction request from UI")
		logger.debug(f"   Request body: {request.model_dump_json(indent=2)}")
		logger.debug(f"   website_url: {request.website_url}")
		logger.debug(f"   website_name: {request.website_name}")
		logger.debug(f"   knowledge_id: {request.knowledge_id}")
		logger.debug(f"   job_id: {request.job_id}")
		logger.debug(f"   credentials: {'provided' if request.credentials else 'none'}")
		if request.s3_references:
			logger.debug(f"   files: {len(request.s3_references)} file(s) provided")
		if request.documentation_urls:
			logger.debug(f"   documentation_urls: {len(request.documentation_urls)} URL(s) provided")
		logger.debug(f"   options: {request.options.model_dump() if request.options else None}")
		logger.debug("=" * 80)

		try:
			# Validate request: website_url is required, at least one of files or documentation_urls
			has_files = request.s3_references and request.file_metadata_list
			has_docs = request.documentation_urls and len(request.documentation_urls) > 0

			if not has_files and not has_docs:
				raise HTTPException(
					status_code=400,
					detail=(
						"For knowledge extraction, provide at least one of: "
						"(1) s3_references + file_metadata_list (uploaded files), or "
						"(2) documentation_urls (publicly available documentation URLs). "
						"Files will be processed in Phase 1, then website DOM analysis in Phase 2."
					)
				)

			# Validate files if provided
			if has_files:
				if len(request.s3_references) != len(request.file_metadata_list):
					raise HTTPException(
						status_code=400,
						detail=f"s3_references and file_metadata_list must have the same length. Got {len(request.s3_references)} references and {len(request.file_metadata_list)} metadata entries"
					)

			# Phase 1: Prepare sources (files and/or documentation URLs)
			source_urls: list[str] = []
			source_names: list[str] = []

			# Process files if provided
			if has_files:
				# Download file(s) from S3
				downloader = get_s3_downloader()

				logger.info(f"📦 Phase 1: Processing {len(request.s3_references)} file(s) from S3")

				# Count video files for special handling
				video_extensions = ['.mp4', '.webm', '.mov', '.avi', '.mkv']
				video_files_count = sum(
					1 for meta in request.file_metadata_list
					if any(meta.filename.lower().endswith(ext) for ext in video_extensions)
				)

				if video_files_count > 0:
					logger.info(
						f"🎥 Detected {video_files_count} video file(s) in batch - "
						f"comprehensive processing enabled (transcription, frame analysis, OCR, subtitles)"
					)

				for i, (s3_ref, file_meta) in enumerate(zip(request.s3_references, request.file_metadata_list)):
					try:
						downloaded_file = await downloader.download_file(
							s3_ref=s3_ref,
							file_metadata=file_meta,
						)

						source_urls.append(f"file://{downloaded_file}")
						source_names.append(file_meta.filename)

						# Log video files with special note
						is_video = any(file_meta.filename.lower().endswith(ext) for ext in video_extensions)
						file_type_note = " (video - comprehensive processing)" if is_video else ""

						logger.info(
							f"✅ Downloaded file {i+1}/{len(request.s3_references)}: {file_meta.filename}{file_type_note}",
							extra={
								"bucket": s3_ref.bucket,
								"key": s3_ref.key,
								"file_name": file_meta.filename,
								"is_video": is_video,
							}
						)
					except S3DownloadError as e:
						logger.error(f"S3 download failed for file {i+1}: {e}", extra=e.details)
						raise HTTPException(status_code=e.status_code, detail=f"Failed to download file {i+1} ({file_meta.filename}): {str(e)}")

			# Add documentation URLs if provided
			if has_docs:
				logger.info(f"📄 Phase 1: Processing {len(request.documentation_urls)} documentation URL(s) for crawling")
				source_urls.extend(request.documentation_urls)
				source_names.extend([url for url in request.documentation_urls])

			# Phase 2: Website URL will be used for DOM analysis (stored in options.credentials)
			logger.info(f"🌐 Phase 2: Will perform DOM-level analysis on {request.website_url}")
			if request.credentials:
				logger.info("🔐 Credentials provided - will perform authenticated login before DOM analysis")

			# Generate job_id if not provided
			job_id = request.job_id or f"job-{uuid4()}"
			workflow_id = f"knowledge-extraction-{job_id}"

			# Get Temporal client
			client = await _get_temporal_client()
			if client is None:
				raise HTTPException(
					status_code=503,
					detail=(
						"Temporal server is not available. "
						"Knowledge extraction workflows require Temporal to be running. "
						"Please start Temporal server: docker run -d -p 7233:7233 --name temporal-server temporalio/auto-setup:latest"
					)
				)

			# Build workflow input
			# source_url is required - use first item from source_urls
			if not source_urls:
				raise HTTPException(
					status_code=400,
					detail="At least one source URL is required (s3_references or documentation_urls)"
				)
			
			workflow_input = KnowledgeExtractionInputV2(
				job_id=job_id,
				source_url=source_urls[0],  # Required: primary source URL
				source_urls=source_urls,  # All source URLs for Phase 1
				source_names=source_names,
				source_name=source_names[0] if source_names else None,  # Primary source name
				knowledge_id=request.knowledge_id,
				options={
					"website_url": request.website_url,  # Website URL for Phase 2 DOM analysis
					"website_name": request.website_name or request.website_url,  # Website name
					"max_pages": request.options.max_pages,
					"max_depth": request.options.max_depth,
					"extract_code_blocks": request.options.extract_code_blocks,
					"extract_thumbnails": request.options.extract_thumbnails,
					"credentials": request.credentials,
				}
			)

			# Start workflow with appropriate timeout
			# Video processing can take 30-60+ minutes, so set timeout to 2 hours
			handle = await client.start_workflow(
				KnowledgeExtractionWorkflowV2.run,
				workflow_input,
				id=workflow_id,
				task_queue="knowledge-extraction-queue",
				execution_timeout=timedelta(hours=2),  # Total workflow execution time
				retry_policy=RetryPolicy(
					initial_interval=timedelta(seconds=1),
					maximum_interval=timedelta(seconds=60),
					backoff_coefficient=2.0,
					maximum_attempts=3,
				),
			)

			phase1_sources = len(source_urls)
			phase2_note = f", Phase 2: DOM analysis on {request.website_url}" if request.website_url else ""
			logger.info(f"Started knowledge extraction workflow: job_id={job_id}, workflow_id={workflow_id}")
			logger.info(f"   Phase 1: {phase1_sources} source(s) (files/documentation){phase2_note}")
			logger.debug(f"🐛 DEBUG: Workflow handle created: {handle.id}")

			# Save initial workflow state to MongoDB so status endpoint can find it immediately
			try:
				initial_state = WorkflowState(
					workflow_id=workflow_id,
					job_id=job_id,
					status=WorkflowStatus.QUEUED,
					phase=None,
					progress=0.0,
					metadata={
						"website_url": request.website_url,
						"website_name": request.website_name,
						"phase1_sources": phase1_sources,
						"has_credentials": bool(request.credentials),
						"knowledge_id": request.knowledge_id,
						"has_files": has_files,
						"has_docs": has_docs,
						"file_count": len(request.s3_references) if request.s3_references else 0,
						"documentation_url_count": len(request.documentation_urls) if request.documentation_urls else 0,
					}
				)
				saved = await save_workflow_state(initial_state)
				if saved:
					logger.info(f"✅ Saved initial workflow state: job_id={job_id}, workflow_id={workflow_id}")
				else:
					logger.warning(f"⚠️ Failed to save initial workflow state: job_id={job_id}, workflow_id={workflow_id}")
			except Exception as e:
				logger.error(f"❌ Error saving initial workflow state: {e}", exc_info=True)

			# Estimate duration (Phase 1 + Phase 2)
			phase1_duration = 300  # Base: 5 minutes per file/URL
			if has_files:
				phase1_duration += len(request.s3_references) * 300  # Add 5 min per file
			if has_docs:
				phase1_duration += len(request.documentation_urls) * 600  # Add 10 min per doc URL

			phase2_duration = 900  # Phase 2: 15 minutes for DOM analysis
			estimated_duration = phase1_duration + phase2_duration

			return StartIngestionResponse(
				job_id=job_id,
				workflow_id=workflow_id,
				status="queued",
				estimated_duration_seconds=estimated_duration,
				message=f"Knowledge extraction started: Phase 1 ({phase1_sources} source(s)), Phase 2 (DOM analysis on {request.website_url})"
			)

		except HTTPException:
			raise
		except Exception as e:
			# Check if it's a Temporal connection error
			error_msg = str(e).lower()
			if "connection" in error_msg and "refused" in error_msg:
				raise HTTPException(
					status_code=503,
					detail=(
						"Temporal server is not available. "
						"Knowledge extraction workflows require Temporal to be running. "
						"Please start Temporal server: docker run -d -p 7233:7233 --name temporal-server temporalio/auto-setup:latest"
					)
				)
			logger.error(f"Failed to start ingestion workflow: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to start workflow: {str(e)}")

	@router.post("/ingest/upload", response_model=StartIngestionResponse)
	async def start_ingestion_upload(
		source_type: SourceType = Form(...),
		source_name: str = Form(...),
		file: UploadFile = File(...),
		job_id: str | None = Form(None),
	) -> StartIngestionResponse:
		"""
		Start knowledge extraction with file upload (Phase 6.1).
		
		Supports:
		- Video files (mp4, webm, mov, avi, mkv)
		- Audio files (mp3, wav, ogg)
		- Text files (txt, md)
		- Documents (pdf, docx)
		
		Returns job_id for tracking workflow progress.
		"""
		# This endpoint is a simplified version that accepts file uploads
		# For now, we'll convert it to the standard StartIngestionRequest format
		# In production, files should be uploaded to S3 first, then referenced
		
		raise HTTPException(
			status_code=501,
			detail="File upload endpoint not yet implemented. Use /ingest/start with S3 references instead."
		)

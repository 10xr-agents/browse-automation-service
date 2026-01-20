"""
REST API: Verification Endpoints (Phase 6.5)

Endpoints for triggering browser-based verification workflows.
"""

import logging
from uuid import uuid4

try:
	from fastapi import APIRouter, HTTPException
	FASTAPI_AVAILABLE = True
except ImportError:
	FASTAPI_AVAILABLE = False
	logging.warning('FastAPI not installed. Install with: pip install fastapi')

from temporalio.client import Client

from navigator.knowledge.rest_api_models import VerificationRequest, VerificationResponse
from navigator.schemas.verification import VerificationWorkflowInput
from navigator.temporal.config import get_temporal_client
from navigator.temporal.workflows_verification import KnowledgeVerificationWorkflow

logger = logging.getLogger(__name__)


def register_verification_routes(
	router: APIRouter,
	_get_temporal_client: callable
) -> None:
	"""
	Register verification API routes (Phase 6.5).
	
	Args:
		router: FastAPI router to register routes on
		_get_temporal_client: Function to get Temporal client
	"""
	
	@router.post("/verify/start", response_model=VerificationResponse)
	async def start_verification(request: VerificationRequest) -> VerificationResponse:
		"""
		Start browser-based verification workflow (Phase 7).
		
		Verifies extracted knowledge by:
		- Navigating to screens
		- Executing tasks
		- Validating state signatures
		- Checking UI elements
		
		Returns verification_job_id for tracking progress.
		
		Note: Requires FEATURE_BROWSER_VERIFICATION=true
		"""
		try:
			# Check if verification feature is enabled
			from navigator.config import get_feature_flags
			flags = get_feature_flags()

			if not flags.is_verification_enabled():
				raise HTTPException(
					status_code=503,
					detail="Browser verification is not enabled. Set FEATURE_BROWSER_VERIFICATION=true to enable."
				)

			# Generate verification job ID
			verification_job_id = f"verify-{uuid4()}"
			workflow_id = f"verification-{verification_job_id}"

			# Get Temporal client
			client = await _get_temporal_client()
			if client is None:
				raise HTTPException(
					status_code=503,
					detail=(
						"Temporal server is not available. "
						"Verification workflows require Temporal to be running. "
						"Please start Temporal server: docker run -d -p 7233:7233 --name temporal-server temporalio/auto-setup:latest"
					)
				)

			# Create workflow input
			workflow_input = VerificationWorkflowInput(
				verification_job_id=verification_job_id,
				target_type=request.target_type,
				target_id=request.target_id,
				verification_options=request.verification_options,
			)

			# Start verification workflow
			handle = await client.start_workflow(
				KnowledgeVerificationWorkflow.run,
				workflow_input,
				id=workflow_id,
				task_queue="knowledge-extraction-queue",
			)

			logger.info(f"Started verification workflow: job_id={verification_job_id}, workflow_id={workflow_id}")

			return VerificationResponse(
				verification_job_id=verification_job_id,
				target_type=request.target_type,
				target_id=request.target_id,
				status="queued",
				message=f"Verification workflow started for {request.target_type} {request.target_id}"
			)

		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to start verification: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to start verification: {str(e)}")

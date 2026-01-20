"""
REST API: Workflow Status Endpoints (Phase 6.4)

Endpoints for querying workflow status and progress.
"""

import logging

try:
	from fastapi import APIRouter, HTTPException
	FASTAPI_AVAILABLE = True
except ImportError:
	FASTAPI_AVAILABLE = False
	logging.warning('FastAPI not installed. Install with: pip install fastapi')

from temporalio.client import Client, WorkflowExecutionStatus

from navigator.knowledge.persist.checkpoints import list_checkpoints
from navigator.knowledge.persist.state import (
	WorkflowStatus,
	load_workflow_state_by_job_id,
	query_workflows_by_status,
)
from navigator.knowledge.rest_api_models import WorkflowStatusResponse
from navigator.temporal.workflows import KnowledgeExtractionWorkflowV2

logger = logging.getLogger(__name__)


def register_workflow_routes(
	router: APIRouter,
	_get_temporal_client: callable
) -> None:
	"""
	Register workflow status API routes (Phase 6.4).
	
	Args:
		router: FastAPI router to register routes on
		_get_temporal_client: Function to get Temporal client
	"""
	
	@router.get("/workflows/status/{job_id}", response_model=WorkflowStatusResponse)
	async def get_workflow_status(job_id: str) -> WorkflowStatusResponse:
		"""
		Get detailed workflow status (Phase 6.4).
		
		Queries both MongoDB (for persisted state, errors, warnings, checkpoints) and
		Temporal (for authoritative real-time status and progress).
		
		Returns:
		- Current status and phase (from Temporal)
		- Progress percentage (from Temporal workflow query)
		- Errors and warnings (from MongoDB)
		- Checkpoint information (from MongoDB)
		- Timestamps (from Temporal and MongoDB)
		"""
		try:
			# Load workflow state from MongoDB
			state = await load_workflow_state_by_job_id(job_id)
			if not state:
				raise HTTPException(status_code=404, detail=f"Workflow not found: {job_id}")

			# Get Temporal client and query actual workflow status
			client = await _get_temporal_client()
			temporal_status = None
			temporal_progress = None
			temporal_phase = None

			if client:
				try:
					# Get workflow handle
					handle = client.get_workflow_handle(state.workflow_id)

					# Get workflow description (authoritative status from Temporal)
					description = await handle.describe()
					temporal_status = description.status.name.lower()  # RUNNING -> running, COMPLETED -> completed, etc.

					# Map Temporal status to our WorkflowStatus enum
					# IMPORTANT: Always prioritize Temporal's status over MongoDB state
					status_mapping = {
						'running': WorkflowStatus.RUNNING,
						'completed': WorkflowStatus.COMPLETED,
						'failed': WorkflowStatus.FAILED,
						'canceled': WorkflowStatus.CANCELLED,
						'cancelled': WorkflowStatus.CANCELLED,  # Handle both spellings
						'terminated': WorkflowStatus.FAILED,
						'timed_out': WorkflowStatus.FAILED,
						'continued_as_new': WorkflowStatus.RUNNING,
					}
					
					# Use Temporal status if available, otherwise check if workflow has errors
					if temporal_status in status_mapping:
						actual_status = status_mapping[temporal_status]
					elif description.status == WorkflowExecutionStatus.FAILED:
						# Explicitly check for FAILED status
						actual_status = WorkflowStatus.FAILED
					else:
						# Fallback to MongoDB state, but log warning
						logger.warning(
							f"Unknown Temporal status '{temporal_status}' for workflow {state.workflow_id}, "
							f"using MongoDB state: {state.status}"
						)
						actual_status = state.status

					# Try to query workflow progress (if workflow is running)
					# Also check for failed status to ensure we capture errors
					if description.status == WorkflowExecutionStatus.RUNNING:
						try:
							progress_data = await handle.query(KnowledgeExtractionWorkflowV2.get_progress)
							if progress_data:
								# Calculate progress percentage if available
								items_processed = progress_data.get('items_processed', 0)
								total_items = progress_data.get('total_items', 0)
								if total_items > 0:
									progress_pct = (items_processed / total_items) * 100
									# Use Temporal progress if available, otherwise use MongoDB
									if progress_pct > 0:
										state.progress = progress_pct

								# Update phase from Temporal if available
								if progress_data.get('phase'):
									temporal_phase = progress_data.get('phase')
									state.phase = temporal_phase

								# Update metadata with Temporal progress data
								state.metadata.update({
									'temporal_progress': progress_data,
									'current_activity': progress_data.get('current_activity'),
									'items_processed': items_processed,
									'total_items': total_items,
								})
						except Exception as query_error:
							# Workflow might not support query or might be in a state where query fails
							logger.debug(f"Could not query workflow progress: {query_error}")

					# Update status from Temporal (authoritative source)
					# CRITICAL: Always use Temporal's status, especially for failures
					state.status = actual_status
					
					# If workflow failed, ensure we capture the failure reason
					if actual_status == WorkflowStatus.FAILED:
						# Try to get failure details from Temporal
						try:
							# Get workflow result to check for error details
							# Note: This will raise an exception if workflow failed, which we catch
							pass  # We'll handle this in the exception handler below
						except Exception:
							# Workflow failed - this is expected, don't log as error
							pass
					
					# Log status update for debugging
					if actual_status != state.status:
						logger.info(
							f"Workflow {state.workflow_id} status updated: "
							f"{state.status} -> {actual_status} (Temporal: {temporal_status})"
						)

				except Exception as temporal_error:
					# Temporal query failed - use MongoDB state as fallback
					logger.warning(
						f"Could not query Temporal workflow {state.workflow_id}: {temporal_error}. "
						f"Using MongoDB state: {state.status}"
					)
					# Don't update state.status if Temporal query fails - keep MongoDB state

			# Get checkpoints for this workflow
			checkpoints = await list_checkpoints(state.workflow_id)

			# Convert checkpoints to response format
			checkpoint_info = [
				{
					"activity_name": cp.activity_name,
					"checkpoint_id": cp.checkpoint_id,
					"items_processed": cp.items_processed,
					"total_items": cp.total_items,
					"progress_percentage": cp.progress_percentage,
				}
				for cp in checkpoints
			]

			return WorkflowStatusResponse(
				job_id=state.job_id,
				workflow_id=state.workflow_id,
				status=state.status.value,
				phase=state.phase,
				progress=state.progress,
				errors=state.errors,
				warnings=state.warnings,
				checkpoints=checkpoint_info,
				metadata=state.metadata,
				created_at=state.created_at.isoformat(),
				updated_at=state.updated_at.isoformat(),
			)

		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to get workflow status: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to retrieve workflow status: {str(e)}")

	@router.get("/workflows/list", response_model=list[dict])
	async def list_workflows_by_status(status: WorkflowStatus | None = None, limit: int = 100) -> list[dict]:
		"""
		List workflows (optionally filtered by status).
		
		Supports pagination via limit parameter.
		"""
		try:
			if status:
				workflows = await query_workflows_by_status(status, limit=limit)
			else:
				# Get all statuses
				workflows = []
				for workflow_status in WorkflowStatus:
					batch = await query_workflows_by_status(workflow_status, limit=limit)
					workflows.extend(batch)

			return [
				{
					"job_id": w.job_id,
					"workflow_id": w.workflow_id,
					"status": w.status.value,
					"phase": w.phase,
					"progress": w.progress,
					"created_at": w.created_at.isoformat(),
					"updated_at": w.updated_at.isoformat(),
				}
				for w in workflows[:limit]
			]

		except Exception as e:
			logger.error(f"Failed to list workflows: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to list workflows: {str(e)}")

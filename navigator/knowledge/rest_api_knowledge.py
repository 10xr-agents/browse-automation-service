"""
REST API: Knowledge Query Endpoints (Phase 6.3)

Endpoints for retrieving knowledge definitions and querying by knowledge_id.
"""

import logging

try:
	from fastapi import APIRouter, HTTPException
	FASTAPI_AVAILABLE = True
except ImportError:
	FASTAPI_AVAILABLE = False
	logging.warning('FastAPI not installed. Install with: pip install fastapi')

from navigator.knowledge.persist.documents import (
	get_action,
	get_latest_job_id_for_knowledge_id,
	get_screen,
	get_task,
	get_transition,
	query_actions_by_knowledge_id,
	query_business_functions_by_knowledge_id,
	query_screens_by_knowledge_id,
	query_screens_by_website,
	query_tasks_by_knowledge_id,
	query_tasks_by_website,
	query_transitions_by_knowledge_id,
	query_workflows_by_knowledge_id,
)
from navigator.knowledge.persist.state import record_workflow_error, load_workflow_state_by_job_id

logger = logging.getLogger(__name__)

# Phase 3: Agent Communication
if FASTAPI_AVAILABLE:
	from navigator.knowledge.agent_communication import (
		AgentInstruction,
		AgentResponse,
		ScreenRecognitionService,
	)
	from navigator.knowledge.extract.browser_use_mapping import translate_to_browser_use
	from navigator.knowledge.persist.navigation import get_navigation_path


def register_knowledge_routes(router: APIRouter) -> None:
	"""
	Register knowledge query API routes (Phase 6.3).
	
	Args:
		router: FastAPI router to register routes on
	"""
	
	# ========================================================================
	# Phase 6.3: Knowledge Definition APIs (Legacy - by individual IDs)
	# ========================================================================
	
	@router.get("/screens/{screen_id}", response_model=dict)
	async def get_screen_definition(screen_id: str) -> dict:
		"""
		Get full screen definition from MongoDB (Phase 6.3).
		
		Returns complete screen definition with:
		- State signature (indicators)
		- UI elements with selectors
		- Affordances
		- Metadata
		"""
		try:
			screen = await get_screen(screen_id)
			if not screen:
				raise HTTPException(status_code=404, detail=f"Screen not found: {screen_id}")

			return screen.dict()

		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to get screen: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to retrieve screen: {str(e)}")

	@router.get("/tasks/{task_id}", response_model=dict)
	async def get_task_definition(task_id: str) -> dict:
		"""
		Get full task definition from MongoDB (Phase 6.3).
		
		Returns complete task definition with:
		- Steps with action references
		- Preconditions and postconditions
		- Iterator spec (if loops present)
		- IO spec (inputs/outputs with volatility)
		"""
		try:
			task = await get_task(task_id)
			if not task:
				raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

			return task.dict()

		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to get task: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to retrieve task: {str(e)}")

	@router.get("/actions/{action_id}", response_model=dict)
	async def get_action_definition(action_id: str) -> dict:
		"""
		Get full action definition from MongoDB (Phase 6.3).
		
		Returns complete action definition with:
		- Action type and parameters
		- Target element selectors
		- Preconditions and effects
		"""
		try:
			action = await get_action(action_id)
			if not action:
				raise HTTPException(status_code=404, detail=f"Action not found: {action_id}")

			return action.dict()

		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to get action: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to retrieve action: {str(e)}")

	@router.get("/screens", response_model=list[dict])
	async def list_screens(
		knowledge_id: str | None = None,
		website_id: str | None = None,
		limit: int = 100
	) -> list[dict]:
		"""
		List screens by knowledge_id or website_id.
		
		**Required:** Either `knowledge_id` or `website_id` parameter.
		"""
		try:
			if not knowledge_id and not website_id:
				raise HTTPException(
					status_code=400,
					detail="Either knowledge_id or website_id parameter is required"
				)
			
			if knowledge_id:
				screens = await query_screens_by_knowledge_id(knowledge_id, limit=limit)
			else:
				screens = await query_screens_by_website(website_id, limit=limit)
			
			return [s.dict() for s in screens]
		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to list screens: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to list screens: {str(e)}")

	@router.get("/tasks", response_model=list[dict])
	async def list_tasks(
		knowledge_id: str | None = None,
		website_id: str | None = None,
		limit: int = 100
	) -> list[dict]:
		"""
		List tasks by knowledge_id or website_id.
		
		**Required:** Either `knowledge_id` or `website_id` parameter.
		"""
		try:
			if not knowledge_id and not website_id:
				raise HTTPException(
					status_code=400,
					detail="Either knowledge_id or website_id parameter is required"
				)
			
			if knowledge_id:
				tasks = await query_tasks_by_knowledge_id(knowledge_id, limit=limit)
			else:
				tasks = await query_tasks_by_website(website_id, limit=limit)
			
			return [t.dict() for t in tasks]
		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to list tasks: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to list tasks: {str(e)}")

	@router.get("/actions", response_model=list[dict])
	async def list_actions(
		knowledge_id: str | None = None,
		limit: int = 100
	) -> list[dict]:
		"""
		List actions by knowledge_id.
		
		**Required:** `knowledge_id` parameter to query by knowledge ID.
		"""
		try:
			if not knowledge_id:
				raise HTTPException(
					status_code=400,
					detail="knowledge_id parameter is required"
				)
			actions = await query_actions_by_knowledge_id(knowledge_id, limit=limit)
			return [a.dict() for a in actions]
		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to list actions: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to list actions: {str(e)}")

	@router.get("/transitions", response_model=list[dict])
	async def list_transitions(
		knowledge_id: str | None = None,
		limit: int = 1000
	) -> list[dict]:
		"""
		List transitions by knowledge_id.
		
		**Required:** `knowledge_id` parameter to query by knowledge ID.
		"""
		try:
			if not knowledge_id:
				raise HTTPException(
					status_code=400,
					detail="knowledge_id parameter is required"
				)
			transitions = await query_transitions_by_knowledge_id(knowledge_id, limit=limit)
			return [t.dict() for t in transitions]
		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to list transitions: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to list transitions: {str(e)}")

	@router.get("/business-functions", response_model=list[dict])
	async def list_business_functions(
		knowledge_id: str | None = None,
		limit: int = 100
	) -> list[dict]:
		"""
		List business functions by knowledge_id.
		
		**Required:** `knowledge_id` parameter to query by knowledge ID.
		"""
		try:
			if not knowledge_id:
				raise HTTPException(
					status_code=400,
					detail="knowledge_id parameter is required"
				)
			business_functions = await query_business_functions_by_knowledge_id(knowledge_id, limit=limit)
			return [bf.dict() for bf in business_functions]
		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to list business functions: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to list business functions: {str(e)}")

	@router.get("/workflows", response_model=list[dict])
	async def list_workflows_by_knowledge_id(
		knowledge_id: str | None = None,
		limit: int = 100
	) -> list[dict]:
		"""
		List workflows by knowledge_id.
		
		**Required:** `knowledge_id` parameter to query by knowledge ID.
		"""
		try:
			if not knowledge_id:
				raise HTTPException(
					status_code=400,
					detail="knowledge_id parameter is required"
				)
			workflows = await query_workflows_by_knowledge_id(knowledge_id, limit=limit)
			return [wf.dict() for wf in workflows]
		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to list workflows: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to list workflows: {str(e)}")

	# ========================================================================
	# Phase 6.3.1: Primary Knowledge Query API (knowledge_id based)
	# ========================================================================
	
	@router.get(
		"/query/{knowledge_id}",
		response_model=dict,
		summary="Get All Knowledge by Knowledge ID (Primary Endpoint)",
		description=(
			"**PRIMARY ENDPOINT** - Retrieve all knowledge entities (screens, tasks, actions, transitions, business functions, workflows) "
			"associated with a knowledge_id.\n\n"
			"This is the main endpoint for querying extracted knowledge. All entities are grouped by knowledge_id "
			"during extraction and can be retrieved together using this endpoint.\n\n"
			"**Query Behavior:**\n"
			"- If `job_id` is provided: Returns knowledge for that specific job (historical view)\n"
			"- If `job_id` is not provided: Returns latest knowledge (most recent job) for the knowledge_id\n\n"
			"**Returns:**\n"
			"- `screens`: List of screen definitions\n"
			"- `tasks`: List of task definitions\n"
			"- `actions`: List of action definitions\n"
			"- `transitions`: List of transition definitions\n"
			"- `business_functions`: List of business function definitions\n"
			"- `workflows`: List of operational workflow definitions\n"
			"- `statistics`: Summary counts for each entity type\n"
			"- `job_id`: The job_id used for this query (if provided or latest)\n\n"
			"**Usage:**\n"
			"```\n"
			"GET /api/knowledge/query/{knowledge_id}?job_id={job_id}\n"
			"```\n\n"
			"**Examples:**\n"
			"```\n"
			"# Get latest knowledge\n"
			"GET /api/knowledge/query/696d1b52e1c3d23b77b94982\n"
			"\n"
			"# Get knowledge for specific job\n"
			"GET /api/knowledge/query/696d1b52e1c3d23b77b94982?job_id=job-abc-123\n"
			"```\n\n"
			"**Error Handling:**\n"
			"If `job_id` is provided and no knowledge is found, the job will be marked as failed with an error."
		),
		response_description="Complete knowledge base for the given knowledge_id",
		responses={
			200: {"description": "Knowledge retrieved successfully"},
			404: {"description": "Knowledge not found"},
			500: {"description": "Internal server error"}
		}
	)
	async def get_knowledge_by_id(knowledge_id: str, job_id: str | None = None) -> dict:
		"""
		Get all knowledge entities by knowledge_id, optionally filtered by job_id.
		
		If job_id is provided, returns knowledge for that specific job (historical view).
		If job_id is None, returns latest knowledge (most recent job) for the knowledge_id.
		
		If job_id is provided and no knowledge is found, the job will be marked as failed.
		
		Returns complete knowledge base including all entity types.
		"""
		try:
			# Query all entity types by knowledge_id (and optionally job_id)
			screens = await query_screens_by_knowledge_id(knowledge_id, job_id=job_id)
			tasks = await query_tasks_by_knowledge_id(knowledge_id, job_id=job_id)
			actions = await query_actions_by_knowledge_id(knowledge_id, job_id=job_id)
			transitions = await query_transitions_by_knowledge_id(knowledge_id, job_id=job_id)
			business_functions = await query_business_functions_by_knowledge_id(knowledge_id, job_id=job_id)
			workflows = await query_workflows_by_knowledge_id(knowledge_id, job_id=job_id)

			# Calculate total entities
			total_entities = (
				len(screens) +
				len(tasks) +
				len(actions) +
				len(transitions) +
				len(business_functions) +
				len(workflows)
			)

			if total_entities == 0:
				# If job_id was provided and no knowledge found, mark job as failed
				if job_id:
					# Try to get workflow state to mark it as failed
					workflow_state = await load_workflow_state_by_job_id(job_id)
					if workflow_state:
						error_msg = (
							f"No knowledge entities found for job_id={job_id} and knowledge_id={knowledge_id}. "
							f"This indicates the knowledge extraction job did not produce any results. "
							f"Possible reasons: extraction failed, no content was extracted, or persistence failed."
						)
						await record_workflow_error(workflow_state.workflow_id, error_msg)
						logger.error(f"Marked job as failed: job_id={job_id}, error={error_msg}")

					raise HTTPException(
						status_code=404,
						detail=(
							f"No knowledge found for knowledge_id={knowledge_id} and job_id={job_id}. "
							f"The job has been marked as failed. Check workflow status for details."
						)
					)
				else:
					raise HTTPException(
						status_code=404,
						detail=f"No knowledge found for knowledge_id: {knowledge_id}"
					)

			# Determine the actual job_id used
			# If job_id was provided, use it; otherwise get the latest job_id for this knowledge_id
			actual_job_id = job_id
			if not actual_job_id:
				actual_job_id = await get_latest_job_id_for_knowledge_id(knowledge_id)

			# Convert to dict format
			return {
				"knowledge_id": knowledge_id,
				"job_id": actual_job_id,
				"screens": [s.dict() for s in screens],
				"tasks": [t.dict() for t in tasks],
				"actions": [a.dict() for a in actions],
				"transitions": [tr.dict() for tr in transitions],
				"business_functions": [bf.dict() for bf in business_functions],
				"workflows": [wf.dict() for wf in workflows],
				"statistics": {
					"screens_count": len(screens),
					"tasks_count": len(tasks),
					"actions_count": len(actions),
					"transitions_count": len(transitions),
					"business_functions_count": len(business_functions),
					"workflows_count": len(workflows),
					"total_entities": total_entities,
				}
			}

		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to get knowledge by knowledge_id: {e}")
			raise HTTPException(status_code=500, detail=f"Failed to retrieve knowledge: {str(e)}")
	
	# ========================================================================
	# Phase 3: Agent Communication API
	# ========================================================================
	
	@router.post("/knowledge/{knowledge_id}/query", response_model=dict)
	async def query_knowledge_for_agent(
		knowledge_id: str,
		instruction: AgentInstruction
	) -> dict:
		"""
		Agent-friendly knowledge query endpoint (Phase 3).
		
		Query types:
		- "navigate_to_screen": Get navigation instructions to a screen
		- "execute_task": Get task execution steps
		- "find_screen": Find screen by URL or description
		- "get_actions": Get available actions on current screen
		- "get_screen_context": Get complete context for a screen
		
		Returns browser-use actions ready for execution.
		"""
		try:
			from navigator.knowledge.extract.actions import ActionDefinition
			from navigator.knowledge.extract.browser_use_mapping import (
				ActionTranslator,
			)
			from navigator.knowledge.extract.tasks import TaskStep
			
			# Ensure instruction has correct knowledge_id
			if instruction.knowledge_id != knowledge_id:
				raise HTTPException(
					status_code=400,
					detail=f"Knowledge ID mismatch: instruction has {instruction.knowledge_id}, URL has {knowledge_id}"
				)
			
			response = AgentResponse(success=False)
			
			if instruction.instruction_type == "navigate_to_screen":
				# Get navigation path
				current_url = instruction.context.get("current_url")
				current_screen_id = instruction.context.get("current_screen_id")
				target_screen_id = instruction.target
				
				# Find current screen if not provided
				if not current_screen_id and current_url:
					recognition_service = ScreenRecognitionService()
					recognition_result = await recognition_service.recognize_screen(
						current_url,
						instruction.context.get("dom_summary", ""),
						knowledge_id
					)
					current_screen_id = recognition_result.get("screen_id")
				
				if not current_screen_id:
					response.error = "Could not determine current screen. Provide current_url or current_screen_id in context."
					return response.dict()
				
				# Get navigation path
				path_result = await get_navigation_path(
					current_screen_id,
					target_screen_id,
					knowledge_id
				)
				
				if not path_result.get("path"):
					response.error = f"No path found from screen {current_screen_id} to {target_screen_id}"
					return response.dict()
				
				# Translate transitions to browser-use actions
				translator = ActionTranslator()
				actions = []
				
				for step in path_result.get("steps", []):
					# Extract action from step
					if "action" in step:
						action_data = step["action"]
						# Create temporary ActionDefinition for translation
						action_def = ActionDefinition(
							action_id=action_data.get("action_id", ""),
							name=action_data.get("action_name", ""),
							website_id="",  # Not needed for translation
							action_type=action_data.get("action_type", "click"),
							target_selector=action_data.get("target", ""),
							parameters=action_data.get("parameters", {})
						)
						browser_action = translator.translate_action(
							action_def,
							screen_id=step.get("to_screen_id")
						)
						actions.append(browser_action)
				
				# Get target screen for verification
				target_screen = await get_screen(target_screen_id)
				verification = {}
				if target_screen:
					verification = {
						"url_patterns": target_screen.url_patterns,
						"required_indicators": [
							{
								"type": ind.type,
								"value": ind.value,
								"pattern": ind.pattern
							}
							for ind in target_screen.state_signature.required_indicators[:5]  # Limit to 5
						]
					}
				
				response = AgentResponse(
					success=True,
					actions=actions,
					expected_result={
						"screen_id": target_screen_id,
						"screen_name": target_screen.name if target_screen else None,
						"verification": verification
					}
				)
			
			elif instruction.instruction_type == "execute_task":
				# Get task
				task = await get_task(instruction.target)
				
				if not task:
					response.error = f"Task not found: {instruction.target}"
					return response.dict()
				
				# Translate task steps to browser-use actions
				translator = ActionTranslator()
				actions = []
				
				for step in task.steps:
					if isinstance(step, TaskStep) and step.action:
						browser_action = translator.translate_action(
							step.action,
							screen_id=step.screen_id
						)
						actions.append(browser_action)
				
				response = AgentResponse(
					success=True,
					actions=actions,
					expected_result={
						"task_id": task.task_id,
						"task_name": task.name,
						"success_criteria": getattr(task, 'success_criteria', None)
					}
				)
			
			elif instruction.instruction_type == "find_screen":
				# Find screen by URL or description
				current_url = instruction.context.get("current_url") or instruction.target
				
				recognition_service = ScreenRecognitionService()
				recognition_result = await recognition_service.recognize_screen(
					current_url,
					instruction.context.get("dom_summary", ""),
					knowledge_id
				)
				
				if recognition_result.get("screen_id"):
					response = AgentResponse(
						success=True,
						actions=[],  # No actions needed, just recognition
						expected_result=recognition_result
					)
				else:
					response.error = f"Screen not found for URL: {current_url}"
			
			elif instruction.instruction_type == "get_actions":
				# Get available actions on current screen
				current_screen_id = instruction.context.get("current_screen_id")
				if not current_screen_id:
					# Try to recognize screen from URL
					current_url = instruction.context.get("current_url")
					if current_url:
						recognition_service = ScreenRecognitionService()
						recognition_result = await recognition_service.recognize_screen(
							current_url,
							instruction.context.get("dom_summary", ""),
							knowledge_id
						)
						current_screen_id = recognition_result.get("screen_id")
				
				if not current_screen_id:
					response.error = "Could not determine current screen. Provide current_screen_id or current_url in context."
					return response.dict()
				
				# Get available actions
				recognition_service = ScreenRecognitionService()
				available_actions = await recognition_service._get_available_actions(
					current_screen_id,
					knowledge_id
				)
				
				response = AgentResponse(
					success=True,
					actions=[],  # Raw action data, not browser-use actions
					expected_result={
						"screen_id": current_screen_id,
						"available_actions": available_actions
					}
				)
			
			elif instruction.instruction_type == "get_screen_context":
				# Get complete screen context
				screen_id = instruction.target
				from navigator.knowledge.persist.navigation import get_screen_context
				
				context = await get_screen_context(screen_id, knowledge_id)
				
				response = AgentResponse(
					success=True,
					actions=[],
					expected_result=context
				)
			
			return response.dict()
		
		except HTTPException:
			raise
		except Exception as e:
			logger.error(f"Failed to query knowledge for agent: {e}", exc_info=True)
			raise HTTPException(
				status_code=500,
				detail=f"Failed to process agent query: {str(e)}"
			)

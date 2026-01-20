"""
Phase 3: Graph Construction

Builds knowledge graph from extracted screens, tasks, actions, and transitions.
"""

from temporalio import workflow

# Import activities and schemas - wrap ALL imports
with workflow.unsafe.imports_passed_through():
	from navigator.schemas import (
		BuildGraphInput,
		BuildGraphResult,
		ExtractActionsResult,
		ExtractScreensResult,
		ExtractTasksResult,
		ExtractTransitionsResult,
		KnowledgeExtractionProgressV2,
		KnowledgeExtractionResultV2,
		WorkflowPhase,
	)
	from navigator.temporal.activities import build_graph_activity


async def execute_graph_construction_phase(
	result: KnowledgeExtractionResultV2,
	progress: KnowledgeExtractionProgressV2,
	screens_result: ExtractScreensResult,
	tasks_result: ExtractTasksResult,
	actions_result: ExtractActionsResult,
	transitions_result: ExtractTransitionsResult,
	input_job_id: str,
	activity_options: dict,
	check_pause_or_cancel,
) -> None:
	"""
	Execute Phase 3: Graph Construction.
	
	Builds knowledge graph connecting screens, tasks, actions, and transitions.
	
	Args:
		result: Workflow result object to update
		progress: Progress tracking object
		screens_result: Screen extraction results
		tasks_result: Task extraction results
		actions_result: Action extraction results
		transitions_result: Transition extraction results
		input_job_id: Job ID
		activity_options: Activity execution options
		check_pause_or_cancel: Function to check for pause/cancel
	"""
	progress.phase = WorkflowPhase.GRAPH_CONSTRUCTION
	progress.current_activity = "build_graph"
	await check_pause_or_cancel()

	workflow.logger.info("🔗 Phase 3: Building knowledge graph...")

	graph_result: BuildGraphResult = await workflow.execute_activity(
		build_graph_activity,
		BuildGraphInput(
			job_id=input_job_id,
			screen_ids=screens_result.screen_ids,
			task_ids=tasks_result.task_ids,
			action_ids=actions_result.action_ids,
			transition_ids=transitions_result.transition_ids,
		),
		**activity_options,
	)

	result.graph_nodes = graph_result.graph_nodes
	result.graph_edges = graph_result.graph_edges

	workflow.logger.info(
		f"✅ Graph constructed: "
		f"{result.graph_nodes} nodes, "
		f"{result.graph_edges} edges"
	)

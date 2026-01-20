"""
Continue-as-new utility for workflows.

Helps workflows determine when to continue as new to avoid history size limits.
"""

from typing import Any

from temporalio import workflow


def should_continue_as_new() -> bool:
	"""
	Check if workflow should continue as new to avoid history size limits.
	
	Returns:
		True if Temporal suggests continuing as new (based on event count/history size)
	"""
	return workflow.info().is_continue_as_new_suggested()


async def safe_continue_as_new(input: Any) -> Any:
	"""
	Safely continue workflow as new, ensuring all handlers finish first.
	
	This prevents "Task not found when completing" warnings by ensuring
	all signal and query handlers complete before closing the current run.
	
	Args:
		input: Input to pass to the new workflow run
	
	Returns:
		Result from workflow.continue_as_new()
	"""
	# Wait for all signal/query handlers to finish before continuing as new
	# This prevents "Task not found when completing" warnings when handlers
	# try to complete tasks for a run that's already been closed
	workflow.logger.debug("⏳ Waiting for all handlers to finish before continue_as_new...")
	await workflow.wait_condition(lambda: workflow.all_handlers_finished())
	workflow.logger.debug("✅ All handlers finished, safe to continue as new")

	return workflow.continue_as_new(input)

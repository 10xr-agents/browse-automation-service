"""
Workflow control helpers (pause, resume, cancel).

Provides pause/resume/cancel functionality for workflows.
"""

from temporalio import workflow


class WorkflowControl:
	"""Workflow control state and methods."""

	def __init__(self):
		"""Initialize control flags."""
		self._paused = False
		self._cancelled = False

	def pause(self):
		"""Pause workflow execution."""
		workflow.logger.info("⏸️  Pause signal received")
		self._paused = True

	def resume(self):
		"""Resume paused workflow."""
		workflow.logger.info("▶️  Resume signal received")
		self._paused = False

	def cancel(self):
		"""Cancel workflow execution."""
		workflow.logger.info("⏹️  Cancel signal received")
		self._cancelled = True

	def is_paused(self) -> bool:
		"""Check if workflow is paused."""
		return self._paused

	def is_cancelled(self) -> bool:
		"""Check if workflow is cancelled."""
		return self._cancelled

	async def check_pause_or_cancel(self):
		"""
		Check for pause/cancel signals and wait if needed.
		
		Raises:
			Exception: If workflow is cancelled
		"""
		# Check cancel first
		if self._cancelled:
			workflow.logger.info("⏹️  Workflow cancelled")
			raise Exception("Workflow cancelled by user")

		# Check pause and wait until resumed
		while self._paused:
			workflow.logger.info("⏸️  Workflow paused, waiting for resume...")
			await workflow.wait_condition(lambda: not self._paused or self._cancelled)

			if self._cancelled:
				workflow.logger.info("⏹️  Workflow cancelled during pause")
				raise Exception("Workflow cancelled by user during pause")

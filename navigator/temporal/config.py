"""
Temporal configuration and client management.

Provides centralized configuration for Temporal connection and client creation.
"""

import logging
import os
from dataclasses import dataclass

from temporalio.client import Client

logger = logging.getLogger(__name__)


@dataclass
class TemporalConfig:
	"""Temporal connection configuration."""

	# Temporal server URL
	url: str = "localhost:7233"

	# Namespace for workflows
	namespace: str = "default"

	# Task queue for knowledge extraction workflows
	knowledge_task_queue: str = "knowledge-extraction-queue"

	@classmethod
	def from_env(cls) -> "TemporalConfig":
		"""
		Create configuration from environment variables.
		
		Environment variables:
		- TEMPORAL_URL: Temporal server URL (default: localhost:7233)
		- TEMPORAL_NAMESPACE: Temporal namespace (default: default)
		- TEMPORAL_KNOWLEDGE_QUEUE: Task queue name (default: knowledge-extraction-queue)
		"""
		return cls(
			url=os.getenv("TEMPORAL_URL", "localhost:7233"),
			namespace=os.getenv("TEMPORAL_NAMESPACE", "default"),
			knowledge_task_queue=os.getenv("TEMPORAL_KNOWLEDGE_QUEUE", "knowledge-extraction-queue"),
		)


async def get_temporal_client(config: TemporalConfig | None = None) -> Client:
	"""
	Get or create Temporal client.
	
	Args:
		config: Temporal configuration (uses default from env if None)
	
	Returns:
		Connected Temporal client
	"""
	if config is None:
		config = TemporalConfig.from_env()

	logger.info(f"Connecting to Temporal at {config.url} (namespace: {config.namespace})")

	try:
		client = await Client.connect(
			config.url,
			namespace=config.namespace,
		)
		logger.info("✅ Successfully connected to Temporal")
		return client
	except Exception as e:
		# Don't log here - let the caller handle it gracefully
		# This prevents duplicate log messages when Temporal is not available
		raise

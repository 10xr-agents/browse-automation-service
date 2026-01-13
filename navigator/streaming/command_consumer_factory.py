"""
Command Consumer Factory

Helper function to create CommandConsumer instances with proper component initialization.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


async def create_command_consumer(
	session_manager: Any,
	instance_id: str | None = None,
	consumer_group: str = "browser_agent_cluster",
) -> Any | None:
	"""
	Create a CommandConsumer instance with proper component initialization.
	
	Args:
		session_manager: BrowserSessionManager instance
		instance_id: Instance identifier (defaults to hostname or random UUID)
		consumer_group: Consumer group name (default: "browser_agent_cluster")
	
	Returns:
		CommandConsumer instance or None if components/Redis not available
	"""
	try:
		from navigator.streaming.command_consumer import CommandConsumer
		from navigator.streaming.redis_client import get_redis_streams_client
		
		# Generate instance ID if not provided
		if not instance_id:
			import socket
			try:
				hostname = socket.gethostname()
				instance_id = f"{hostname}_{os.getpid()}"
			except Exception:
				from uuid import uuid4
				instance_id = uuid4().hex[:8]
		
		# Get Redis client
		redis_client = await get_redis_streams_client()
		if not redis_client:
			logger.debug("Redis streams client not available, CommandConsumer not created")
			return None
		
		# Get components from session_manager
		state_diff_engine = session_manager.get_state_diff_engine()
		sequence_tracker = session_manager.get_sequence_tracker()
		dedup_cache = session_manager.get_dedup_cache()
		state_publisher = await session_manager.get_state_publisher()
		
		if not all([state_diff_engine, sequence_tracker, dedup_cache, state_publisher]):
			logger.debug("Sequenced communication components not available, CommandConsumer not created")
			return None
		
		# Create CommandConsumer
		command_consumer = CommandConsumer(
			redis_client=redis_client,
			instance_id=instance_id,
			session_manager=session_manager,
			sequence_tracker=sequence_tracker,
			dedup_cache=dedup_cache,
			state_diff_engine=state_diff_engine,
			state_publisher=state_publisher,
			consumer_group=consumer_group,
		)
		
		logger.info(f"CommandConsumer created for instance {instance_id}")
		return command_consumer
		
	except ImportError as e:
		logger.debug(f"CommandConsumer not available: {e}")
		return None
	except Exception as e:
		logger.warning(f"Failed to create CommandConsumer: {e}")
		return None

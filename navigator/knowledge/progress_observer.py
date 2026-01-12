"""
Progress Observer for Knowledge Retrieval Pipeline

Provides real-time progress updates for long-running exploration tasks.
Supports multiple observers (Redis Pub/Sub, WebSocket, logging, etc.)
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExplorationProgress:
	"""Progress update for exploration task."""
	job_id: str
	status: str  # 'running', 'paused', 'completed', 'failed', 'cancelled'
	current_page: str | None = None
	pages_completed: int = 0
	pages_queued: int = 0
	pages_failed: int = 0
	links_discovered: int = 0
	external_links_detected: int = 0
	features_discovered: int = 0
	depth: int = 0
	error: str | None = None
	timestamp: str | None = None
	
	def to_dict(self) -> dict[str, Any]:
		"""Convert to dictionary."""
		data = asdict(self)
		if not data.get('timestamp'):
			data['timestamp'] = datetime.utcnow().isoformat()
		return data


class ProgressObserver(ABC):
	"""Abstract base class for progress observers."""
	
	@abstractmethod
	async def on_progress(self, progress: ExplorationProgress) -> None:
		"""Handle progress update."""
		pass
	
	@abstractmethod
	async def on_page_completed(self, url: str, result: dict[str, Any]) -> None:
		"""Handle page completion."""
		pass
	
	@abstractmethod
	async def on_external_link_detected(self, from_url: str, to_url: str) -> None:
		"""Handle external link detection."""
		pass
	
	@abstractmethod
	async def on_error(self, url: str, error: str) -> None:
		"""Handle error."""
		pass


class LoggingProgressObserver(ProgressObserver):
	"""Simple logging-based progress observer."""
	
	async def on_progress(self, progress: ExplorationProgress) -> None:
		"""Log progress update."""
		logger.info(
			f"[{progress.job_id}] Progress: {progress.status} | "
			f"Completed: {progress.pages_completed} | "
			f"Queued: {progress.pages_queued} | "
			f"Failed: {progress.pages_failed} | "
			f"Current: {progress.current_page or 'N/A'}"
		)
	
	async def on_page_completed(self, url: str, result: dict[str, Any]) -> None:
		"""Log page completion."""
		success = result.get('success', False)
		logger.info(f"Page completed: {url} (success: {success})")
	
	async def on_external_link_detected(self, from_url: str, to_url: str) -> None:
		"""Log external link detection."""
		logger.debug(f"External link detected: {from_url} -> {to_url} (not following)")
	
	async def on_error(self, url: str, error: str) -> None:
		"""Log error."""
		logger.error(f"Error processing {url}: {error}")


class WebSocketProgressObserver(ProgressObserver):
	"""WebSocket-based progress observer for real-time UI updates."""
	
	def __init__(self, websocket_manager: Any = None):
		"""
		Initialize WebSocket progress observer.
		
		Args:
			websocket_manager: WebSocket manager instance (optional)
		"""
		self.websocket_manager = websocket_manager
	
	async def on_progress(self, progress: ExplorationProgress) -> None:
		"""Broadcast progress via WebSocket."""
		if self.websocket_manager:
			await self.websocket_manager.broadcast({
				'type': 'exploration_progress',
				'data': progress.to_dict(),
			})
	
	async def on_page_completed(self, url: str, result: dict[str, Any]) -> None:
		"""Broadcast page completion via WebSocket."""
		if self.websocket_manager:
			await self.websocket_manager.broadcast({
				'type': 'page_completed',
				'data': {
					'url': url,
					'result': result,
				},
			})
	
	async def on_external_link_detected(self, from_url: str, to_url: str) -> None:
		"""Broadcast external link detection via WebSocket."""
		if self.websocket_manager:
			await self.websocket_manager.broadcast({
				'type': 'external_link_detected',
				'data': {
					'from_url': from_url,
					'to_url': to_url,
				},
			})
	
	async def on_error(self, url: str, error: str) -> None:
		"""Broadcast error via WebSocket."""
		if self.websocket_manager:
			await self.websocket_manager.broadcast({
				'type': 'exploration_error',
				'data': {
					'url': url,
					'error': error,
				},
			})


class RedisProgressObserver(ProgressObserver):
	"""Redis Pub/Sub-based progress observer for high-frequency updates."""
	
	def __init__(self, redis_client: Any = None, channel_prefix: str = "exploration:"):
		"""
		Initialize Redis progress observer.
		
		Args:
			redis_client: Redis client instance (optional)
			channel_prefix: Channel prefix for Redis pub/sub
		"""
		self.redis_client = redis_client
		self.channel_prefix = channel_prefix
	
	async def on_progress(self, progress: ExplorationProgress) -> None:
		"""Publish progress to Redis."""
		if self.redis_client:
			channel = f"{self.channel_prefix}{progress.job_id}:progress"
			await self.redis_client.publish(channel, json.dumps(progress.to_dict()))
	
	async def on_page_completed(self, url: str, result: dict[str, Any]) -> None:
		"""Publish page completion to Redis."""
		if self.redis_client:
			# Extract job_id from result if available
			job_id = result.get('job_id', 'default')
			channel = f"{self.channel_prefix}{job_id}:page_completed"
			await self.redis_client.publish(channel, json.dumps({
				'url': url,
				'result': result,
			}))
	
	async def on_external_link_detected(self, from_url: str, to_url: str) -> None:
		"""Publish external link detection to Redis."""
		if self.redis_client:
			# Use a general channel for external links
			channel = f"{self.channel_prefix}external_links"
			await self.redis_client.publish(channel, json.dumps({
				'from_url': from_url,
				'to_url': to_url,
			}))
	
	async def on_error(self, url: str, error: str) -> None:
		"""Publish error to Redis."""
		if self.redis_client:
			channel = f"{self.channel_prefix}errors"
			await self.redis_client.publish(channel, json.dumps({
				'url': url,
				'error': error,
			}))


class CompositeProgressObserver(ProgressObserver):
	"""Composite observer that forwards to multiple observers."""
	
	def __init__(self, observers: list[ProgressObserver]):
		"""
		Initialize composite observer.
		
		Args:
			observers: List of progress observers
		"""
		self.observers = observers
	
	async def on_progress(self, progress: ExplorationProgress) -> None:
		"""Forward to all observers."""
		await asyncio.gather(
			*[obs.on_progress(progress) for obs in self.observers],
			return_exceptions=True,
		)
	
	async def on_page_completed(self, url: str, result: dict[str, Any]) -> None:
		"""Forward to all observers."""
		await asyncio.gather(
			*[obs.on_page_completed(url, result) for obs in self.observers],
			return_exceptions=True,
		)
	
	async def on_external_link_detected(self, from_url: str, to_url: str) -> None:
		"""Forward to all observers."""
		await asyncio.gather(
			*[obs.on_external_link_detected(from_url, to_url) for obs in self.observers],
			return_exceptions=True,
		)
	
	async def on_error(self, url: str, error: str) -> None:
		"""Forward to all observers."""
		await asyncio.gather(
			*[obs.on_error(url, error) for obs in self.observers],
			return_exceptions=True,
		)

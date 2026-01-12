"""
Tests for Action Queue Management (Steps 1.13-1.15).

Tests cover:
- BullMQ Integration (Step 1.13)
- Rate Limiting (Step 1.14)
- Retry Logic (Step 1.15)
"""

import asyncio
import time

import pytest

from navigator.presentation.action_queue import ActionQueue


class TestActionQueueBasic:
	"""Tests for ActionQueue basic functionality (Step 1.13)."""

	async def test_create_action_queue(self, action_queue):
		"""Test creating an ActionQueue instance."""
		assert action_queue is not None
		assert action_queue.max_retries == 3
		assert action_queue.max_actions_per_second is None
		assert action_queue.queue is None  # In-memory mode

	async def test_enqueue_action(self, action_queue):
		"""Test enqueueing an action."""
		action = {"type": "click", "params": {"index": 0}}
		job_id = await action_queue.enqueue_action(action)
		
		assert job_id is not None
		assert len(action_queue._in_memory_queue) == 1
		assert action_queue._in_memory_queue[0]["action"] == action

	async def test_enqueue_action_with_custom_id(self, action_queue):
		"""Test enqueueing an action with custom job ID."""
		action = {"type": "navigate", "params": {"url": "https://example.com"}}
		custom_id = "custom_job_123"
		job_id = await action_queue.enqueue_action(action, job_id=custom_id)
		
		assert job_id == custom_id
		assert action_queue._in_memory_queue[0]["job_id"] == custom_id

	async def test_process_queue_empty(self, action_queue):
		"""Test processing an empty queue."""
		results = await action_queue.process_queue()
		assert results == []

	async def test_process_queue_with_actions(self, action_queue):
		"""Test processing queue with actions."""
		# Set up a simple processor
		processed_actions = []
		
		async def processor(action: dict):
			processed_actions.append(action)
			return {"result": "processed"}
		
		action_queue.action_processor = processor
		
		# Enqueue actions
		action1 = {"type": "click", "params": {"index": 0}}
		action2 = {"type": "type", "params": {"text": "hello"}}
		
		await action_queue.enqueue_action(action1)
		await action_queue.enqueue_action(action2)
		
		# Process queue
		results = await action_queue.process_queue()
		
		# Verify processing
		assert len(results) == 2
		assert len(processed_actions) == 2
		assert all(r["success"] for r in results)
		assert action_queue._in_memory_queue == []  # Queue should be cleared

	async def test_close_action_queue(self, action_queue):
		"""Test closing an action queue."""
		await action_queue.close()
		# Should not raise any errors
		assert action_queue._worker is None


class TestActionQueueRateLimiting:
	"""Tests for ActionQueue rate limiting (Step 1.14)."""

	async def test_rate_limiting_enabled(self, action_queue_with_rate_limit):
		"""Test that rate limiting is enabled when configured."""
		queue = action_queue_with_rate_limit
		assert queue.max_actions_per_second == 2
		assert queue._rate_limiter is not None
		assert queue._min_delay == 0.5  # 1.0 / 2

	async def test_rate_limiting_enforces_delay(self, action_queue_with_rate_limit):
		"""Test that rate limiting enforces minimum delay between actions."""
		processed_times = []
		
		async def processor(action: dict):
			processed_times.append(time.time())
			return {"result": "processed"}
		
		action_queue_with_rate_limit.action_processor = processor
		
		# Enqueue 2 actions
		await action_queue_with_rate_limit.enqueue_action({"type": "click"})
		await action_queue_with_rate_limit.enqueue_action({"type": "type"})
		
		start_time = time.time()
		await action_queue_with_rate_limit.process_queue()
		duration = time.time() - start_time
		
		# Should take at least min_delay * (num_actions - 1) = 0.5 seconds
		# (First action has no delay, second has min_delay)
		assert duration >= 0.4  # Allow some margin
		
		# Verify actions were processed
		assert len(processed_times) == 2


class TestActionQueueRetryLogic:
	"""Tests for ActionQueue retry logic (Step 1.15)."""

	async def test_retry_on_failure(self, action_queue):
		"""Test that failed actions are retried."""
		attempt_count = 0
		max_attempts = 3
		
		async def failing_processor(action: dict):
			nonlocal attempt_count
			attempt_count += 1
			if attempt_count < max_attempts:
				raise Exception(f"Simulated failure (attempt {attempt_count})")
			return {"result": "success"}
		
		action_queue.action_processor = failing_processor
		action_queue.max_retries = max_attempts - 1  # Will retry 2 times (3 total attempts)
		
		await action_queue.enqueue_action({"type": "test"})
		results = await action_queue.process_queue()
		
		# Should succeed after retries
		assert len(results) == 1
		assert results[0]["success"] is True
		assert attempt_count == max_attempts

	async def test_max_retries_reached(self, action_queue):
		"""Test that action fails after max retries."""
		attempt_count = 0
		
		async def always_failing_processor(action: dict):
			nonlocal attempt_count
			attempt_count += 1
			raise Exception("Always fails")
		
		action_queue.action_processor = always_failing_processor
		action_queue.max_retries = 2  # Will retry 2 times (3 total attempts)
		
		await action_queue.enqueue_action({"type": "test"})
		results = await action_queue.process_queue()
		
		# Should fail after max retries
		assert len(results) == 1
		assert results[0]["success"] is False
		assert results[0]["retries"] == 2
		assert attempt_count == 3  # Initial + 2 retries

	async def test_exponential_backoff(self, action_queue):
		"""Test that exponential backoff is applied between retries."""
		retry_times = []
		start_time = None
		
		async def failing_processor(action: dict):
			nonlocal start_time
			if start_time is None:
				start_time = time.time()
			retry_times.append(time.time())
			if len(retry_times) < 3:
				raise Exception("Fail")
			return {"result": "success"}
		
		action_queue.action_processor = failing_processor
		action_queue.max_retries = 2
		action_queue.retry_backoff_base = 2.0
		
		await action_queue.enqueue_action({"type": "test"})
		results = await action_queue.process_queue()
		
		# Should succeed after retries
		assert results[0]["success"] is True
		assert len(retry_times) == 3  # Initial + 2 retries
		
		# Check that delays increase exponentially
		# First retry: 2^1 = 2 seconds, second retry: 2^2 = 4 seconds
		if len(retry_times) >= 2:
			delay1 = retry_times[1] - retry_times[0]
			delay2 = retry_times[2] - retry_times[1] if len(retry_times) >= 3 else 0
			
			# Allow some margin for execution time
			assert delay1 >= 1.5  # Should be ~2 seconds
			if delay2 > 0:
				assert delay2 >= 3.0  # Should be ~4 seconds

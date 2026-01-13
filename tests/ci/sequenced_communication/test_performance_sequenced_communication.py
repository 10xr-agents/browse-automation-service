"""
Performance Tests for Sequenced Communication (Stage 8).

Tests cover:
- Latency measurement (command → state update)
- Throughput testing (messages per second)
- Memory usage (state snapshots, diffs)
"""

import asyncio
import time

from navigator.state.dedup_cache import DedupCache


class TestLatency:
	"""Tests for latency measurement."""
	
	async def test_sequence_tracker_latency(self, sequence_tracker):
		"""Measure latency of sequence validation and update operations."""
		session_id = "perf_test_session"
		num_operations = 1000
		
		start_time = time.perf_counter()
		
		for i in range(1, num_operations + 1):
			is_valid, expected = await sequence_tracker.validate_sequence(session_id, i)
			assert is_valid is True
			await sequence_tracker.update_last_processed(session_id, i)
		
		end_time = time.perf_counter()
		duration = end_time - start_time
		
		avg_latency_ms = (duration / num_operations) * 1000
		
		# Should be very fast (< 1ms per operation)
		assert avg_latency_ms < 1.0, f"Average latency {avg_latency_ms:.3f}ms exceeds 1ms"
	
	async def test_dedup_cache_latency(self, dedup_cache):
		"""Measure latency of deduplication cache operations."""
		num_commands = 1000
		
		start_time = time.perf_counter()
		
		for i in range(num_commands):
			command_id = f"cmd_perf_{i}"
			await dedup_cache.mark_processing(command_id)
			await dedup_cache.mark_processed(command_id)
			is_processed = await dedup_cache.is_processed(command_id)
			assert is_processed is True
		
		end_time = time.perf_counter()
		duration = end_time - start_time
		
		avg_latency_ms = (duration / num_commands) * 1000
		
		# Should be very fast (< 1ms per operation)
		assert avg_latency_ms < 1.0, f"Average latency {avg_latency_ms:.3f}ms exceeds 1ms"
	
	async def test_state_diff_computation_latency(self, state_diff_engine, browser_session):
		"""Measure latency of state diff computation."""
		# Navigate to a page
		from browser_use.browser.events import NavigateToUrlEvent
		browser_session.event_bus.dispatch(NavigateToUrlEvent(url="https://example.com"))
		await asyncio.sleep(1)
		
		# Capture states
		pre_state = await state_diff_engine.capture_state(browser_session)
		await asyncio.sleep(0.1)
		post_state = await state_diff_engine.capture_state(browser_session)
		
		# Measure diff computation latency
		num_iterations = 100
		
		start_time = time.perf_counter()
		
		for _ in range(num_iterations):
			diff = state_diff_engine.compute_diff(pre_state, post_state)
			assert diff is not None
		
		end_time = time.perf_counter()
		duration = end_time - start_time
		
		avg_latency_ms = (duration / num_iterations) * 1000
		
		# Diff computation should be reasonably fast (< 10ms)
		assert avg_latency_ms < 10.0, f"Average diff latency {avg_latency_ms:.3f}ms exceeds 10ms"


class TestThroughput:
	"""Tests for throughput (messages per second)."""
	
	async def test_sequence_tracker_throughput(self, sequence_tracker):
		"""Measure throughput of sequence tracking operations."""
		session_id = "throughput_test"
		num_operations = 10000
		
		start_time = time.perf_counter()
		
		for i in range(1, num_operations + 1):
			is_valid, expected = await sequence_tracker.validate_sequence(session_id, i)
			await sequence_tracker.update_last_processed(session_id, i)
		
		end_time = time.perf_counter()
		duration = end_time - start_time
		
		throughput = num_operations / duration
		
		# Should handle at least 10k operations per second
		assert throughput > 10000, f"Throughput {throughput:.0f} ops/s below 10k ops/s"
	
	async def test_dedup_cache_throughput(self, dedup_cache):
		"""Measure throughput of deduplication cache operations."""
		num_commands = 10000
		
		start_time = time.perf_counter()
		
		for i in range(num_commands):
			command_id = f"cmd_throughput_{i}"
			await dedup_cache.mark_processed(command_id)
		
		end_time = time.perf_counter()
		duration = end_time - start_time
		
		throughput = num_commands / duration
		
		# Should handle at least 10k operations per second
		assert throughput > 10000, f"Throughput {throughput:.0f} ops/s below 10k ops/s"
	
	async def test_concurrent_sequence_tracking(self, sequence_tracker):
		"""Test throughput with concurrent operations."""
		num_sessions = 100
		ops_per_session = 100
		
		async def process_session(session_id: str):
			for i in range(1, ops_per_session + 1):
				is_valid, expected = await sequence_tracker.validate_sequence(session_id, i)
				await sequence_tracker.update_last_processed(session_id, i)
		
		start_time = time.perf_counter()
		
		# Run concurrent operations
		await asyncio.gather(*[
			process_session(f"session_{i}") for i in range(num_sessions)
		])
		
		end_time = time.perf_counter()
		duration = end_time - start_time
		total_ops = num_sessions * ops_per_session
		throughput = total_ops / duration
		
		# Should handle concurrent operations efficiently
		assert throughput > 5000, f"Concurrent throughput {throughput:.0f} ops/s below 5k ops/s"


class TestMemoryUsage:
	"""Tests for memory usage."""
	
	async def test_sequence_tracker_memory(self, sequence_tracker):
		"""Test memory usage of sequence tracker with many sessions."""
		num_sessions = 1000
		
		# Add many sessions
		for i in range(num_sessions):
			session_id = f"session_mem_{i}"
			await sequence_tracker.update_last_processed(session_id, 100)
		
		# Memory should be reasonable (each session is just an int, so ~1KB for 1000 sessions)
		# This is a basic check - actual memory profiling would require memory_profiler
		last_processed = await sequence_tracker.get_last_processed(f"session_mem_{num_sessions - 1}")
		assert last_processed == 100
	
	async def test_dedup_cache_memory_cleanup(self, dedup_cache):
		"""Test that dedup cache cleans up expired entries."""
		# Use short TTL for testing
		short_ttl_cache = DedupCache(ttl_seconds=1)
		
		# Add many commands
		for i in range(1000):
			command_id = f"cmd_mem_{i}"
			await short_ttl_cache.mark_processed(command_id)
		
		# Wait for TTL to expire
		await asyncio.sleep(1.5)
		
		# Trigger cleanup by checking a command
		is_processed = await short_ttl_cache.is_processed("cmd_mem_0")
		assert is_processed is False  # Should be expired
	
	async def test_state_snapshot_memory(self, state_diff_engine, browser_session):
		"""Test memory usage of state snapshots."""
		# Navigate first
		from browser_use.browser.events import NavigateToUrlEvent
		browser_session.event_bus.dispatch(NavigateToUrlEvent(url="https://example.com"))
		await asyncio.sleep(1)
		
		# Create multiple snapshots
		snapshots = []
		for _ in range(100):
			snapshot = await state_diff_engine.capture_state(browser_session)
			snapshots.append(snapshot)
		
		# Verify snapshots are created (memory check would require memory_profiler)
		assert len(snapshots) == 100
		assert all(snapshot.url is not None for snapshot in snapshots)
	
	async def test_state_diff_memory(self, state_diff_engine, browser_session):
		"""Test memory usage of state diffs."""
		# Navigate first
		from browser_use.browser.events import NavigateToUrlEvent
		browser_session.event_bus.dispatch(NavigateToUrlEvent(url="https://example.com"))
		await asyncio.sleep(1)
		
		# Create snapshots and compute diffs
		pre_state = await state_diff_engine.capture_state(browser_session)
		await asyncio.sleep(0.1)
		post_state = await state_diff_engine.capture_state(browser_session)
		
		# Create many diffs
		diffs = []
		for _ in range(100):
			diff = state_diff_engine.compute_diff(pre_state, post_state)
			diffs.append(diff)
		
		# Verify diffs are created
		assert len(diffs) == 100
		assert all(isinstance(diff, dict) for diff in diffs)

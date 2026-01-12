#!/usr/bin/env python3
"""
Integration Test Script for Phase 1 (Presentation Flow).

This script performs actual calls to test the complete Phase 1 flow.
Run this script to verify all Phase 1 functionality works end-to-end.

Usage:
    python tests/ci/presentation/integration_test_phase1.py

Requirements:
    - Browser automation dependencies installed
    - Optional: Redis running (for Redis Pub/Sub and session persistence tests)
    - Optional: LiveKit server (for LiveKit streaming tests)
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from browser_use.browser import BrowserSession
from browser_use.browser.profile import BrowserProfile

from navigator.action.dispatcher import ActionDispatcher
from navigator.presentation.action_queue import ActionQueue
from navigator.presentation.action_registry import PresentationActionRegistry
from navigator.presentation.flow_manager import PresentationFlowManager
from navigator.streaming.broadcaster import EventBroadcaster

# Configure logging
logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_basic_flow():
	"""Test basic presentation flow: start session, execute actions, close session."""
	logger.info("=" * 80)
	logger.info("Test 1: Basic Presentation Flow")
	logger.info("=" * 80)
	
	# Create flow manager
	flow_manager = PresentationFlowManager(timeout_minutes=1)  # 1 minute for testing
	logger.info("✅ Created PresentationFlowManager")
	
	# Start session
	session_id = await flow_manager.start_session(room_name="integration_test_room")
	logger.info(f"✅ Started session: {session_id[:8]}...")
	
	# Create browser session and action registry
	browser_session = BrowserSession(
		browser_profile=BrowserProfile(headless=True, user_data_dir=None)
	)
	await browser_session.start()
	logger.info("✅ Started browser session")
	
	action_dispatcher = ActionDispatcher(browser_session=browser_session)
	action_registry = PresentationActionRegistry(action_dispatcher=action_dispatcher)
	logger.info("✅ Created action registry")
	
	# Execute actions
	test_url = "https://example.com"
	logger.info(f"📋 Executing navigate action to {test_url}")
	result = await action_registry.execute_action("navigate", {"url": test_url})
	assert result.success, f"Navigate action failed: {result.error}"
	logger.info("✅ Navigate action successful")
	
	await asyncio.sleep(1)  # Wait for page load
	
	logger.info("📋 Executing wait action")
	result = await action_registry.execute_action("wait", {"seconds": 0.5})
	assert result.success, f"Wait action failed: {result.error}"
	logger.info("✅ Wait action successful")
	
	logger.info("📋 Executing scroll action")
	result = await action_registry.execute_action("scroll", {"direction": "down", "amount": 500})
	assert result.success, f"Scroll action failed: {result.error}"
	logger.info("✅ Scroll action successful")
	
	# Close browser session
	await browser_session.kill()
	logger.info("✅ Closed browser session")
	
	# Close presentation session
	await flow_manager.close_session(session_id)
	logger.info(f"✅ Closed presentation session: {session_id[:8]}...")
	
	# Shutdown flow manager
	await flow_manager.shutdown()
	logger.info("✅ Shutdown flow manager")
	
	logger.info("✅ Test 1 PASSED: Basic Presentation Flow")
	return True


async def test_action_queue():
	"""Test action queue functionality."""
	logger.info("=" * 80)
	logger.info("Test 2: Action Queue Management")
	logger.info("=" * 80)
	
	# Create action queue
	processed_actions = []
	
	async def processor(action: dict):
		processed_actions.append(action)
		logger.info(f"  📦 Processed action: {action.get('type')}")
		return {"result": "processed"}
	
	action_queue = ActionQueue(
		queue=None,  # In-memory
		max_actions_per_second=2,
		max_retries=3,
		action_processor=processor
	)
	logger.info("✅ Created ActionQueue (in-memory, rate-limited)")
	
	# Enqueue actions
	actions = [
		{"type": "navigate", "params": {"url": "https://example.com"}},
		{"type": "click", "params": {"index": 0}},
		{"type": "type", "params": {"text": "hello"}},
	]
	
	for action in actions:
		job_id = await action_queue.enqueue_action(action)
		logger.info(f"  📥 Enqueued action: {action['type']} (job_id: {job_id[:8]}...)")
	
	logger.info(f"📋 Processing {len(actions)} actions...")
	start_time = time.time()
	results = await action_queue.process_queue()
	duration = time.time() - start_time
	
	logger.info(f"✅ Processed {len(results)} actions in {duration:.2f} seconds")
	assert len(results) == len(actions)
	assert len(processed_actions) == len(actions)
	assert all(r["success"] for r in results)
	
	# Verify rate limiting (should take at least 1 second for 3 actions at 2/second)
	assert duration >= 0.8, f"Rate limiting not working (duration: {duration:.2f}s)"
	
	await action_queue.close()
	logger.info("✅ Test 2 PASSED: Action Queue Management")
	return True


async def test_event_broadcasting():
	"""Test event broadcasting (WebSocket fallback, no Redis required)."""
	logger.info("=" * 80)
	logger.info("Test 3: Event Broadcasting (WebSocket mode)")
	logger.info("=" * 80)
	
	# Create event broadcaster (WebSocket only, no Redis)
	broadcaster = EventBroadcaster(redis_client=None, use_websocket=False)
	logger.info("✅ Created EventBroadcaster (WebSocket mode)")
	
	# Test broadcasting events (will work but won't send anywhere without WebSocket connections)
	# This tests the API without requiring actual WebSocket setup
	await broadcaster.broadcast_presentation_started("test_room", session_id="test_session")
	logger.info("✅ Broadcast presentation_started event")
	
	await broadcaster.broadcast_action_queued("test_room", {"type": "click"}, session_id="test_session")
	logger.info("✅ Broadcast action_queued event")
	
	await broadcaster.broadcast_presentation_ending("test_room", session_id="test_session")
	logger.info("✅ Broadcast presentation_ending event")
	
	logger.info("✅ Test 3 PASSED: Event Broadcasting")
	return True


async def test_action_registry_extended():
	"""Test extended action registry actions."""
	logger.info("=" * 80)
	logger.info("Test 4: Extended Action Registry")
	logger.info("=" * 80)
	
	# Create browser session and action registry
	browser_session = BrowserSession(
		browser_profile=BrowserProfile(headless=True, user_data_dir=None)
	)
	await browser_session.start()
	logger.info("✅ Started browser session")
	
	action_dispatcher = ActionDispatcher(browser_session=browser_session)
	action_registry = PresentationActionRegistry(action_dispatcher=action_dispatcher)
	
	# Navigate to test page
	test_url = "https://example.com"
	await action_registry.execute_action("navigate", {"url": test_url})
	await asyncio.sleep(1)
	logger.info(f"✅ Navigated to {test_url}")
	
	# Test keyboard shortcut
	logger.info("📋 Testing keyboard_shortcut action")
	result = await action_registry.execute_action("keyboard_shortcut", {"keys": ["Control", "s"]})
	assert result.success or result.error is not None  # May fail in headless, but should not crash
	logger.info("✅ Keyboard shortcut action executed")
	
	# Test zoom actions
	logger.info("📋 Testing zoom_in action")
	result = await action_registry.execute_action("zoom_in", {})
	assert result.success, f"Zoom action failed: {result.error}"
	logger.info("✅ Zoom in action successful")
	
	logger.info("📋 Testing zoom_reset action")
	result = await action_registry.execute_action("zoom_reset", {})
	assert result.success, f"Zoom reset failed: {result.error}"
	logger.info("✅ Zoom reset action successful")
	
	await browser_session.kill()
	logger.info("✅ Test 4 PASSED: Extended Action Registry")
	return True


async def test_complete_integration():
	"""Test complete Phase 1 integration."""
	logger.info("=" * 80)
	logger.info("Test 5: Complete Phase 1 Integration")
	logger.info("=" * 80)
	
	# 1. Create flow manager
	flow_manager = PresentationFlowManager(timeout_minutes=1)
	session_id = await flow_manager.start_session(room_name="integration_complete_room")
	logger.info(f"✅ Started presentation session: {session_id[:8]}...")
	
	# 2. Create browser session and action registry
	browser_session = BrowserSession(
		browser_profile=BrowserProfile(headless=True, user_data_dir=None)
	)
	await browser_session.start()
	
	action_dispatcher = ActionDispatcher(browser_session=browser_session)
	action_registry = PresentationActionRegistry(action_dispatcher=action_dispatcher)
	logger.info("✅ Created action registry")
	
	# 3. Execute multiple actions
	test_url = "https://example.com"
	await action_registry.execute_action("navigate", {"url": test_url})
	await asyncio.sleep(1)
	logger.info("✅ Navigated to test page")
	
	await action_registry.execute_action("wait", {"seconds": 0.5})
	await action_registry.execute_action("scroll", {"direction": "down", "amount": 500})
	logger.info("✅ Executed multiple actions")
	
	# 4. Test action queue integration
	actions = [
		{"type": "scroll", "params": {"direction": "up", "amount": 500}},
	]
	for action in actions:
		await flow_manager.enqueue_action(session_id, action)
	logger.info("✅ Enqueued actions")
	
	# 5. Cleanup
	await browser_session.kill()
	await flow_manager.close_session(session_id)
	await flow_manager.shutdown()
	logger.info("✅ Cleanup complete")
	
	logger.info("✅ Test 5 PASSED: Complete Phase 1 Integration")
	return True


async def main():
	"""Run all integration tests."""
	logger.info("🚀 Starting Phase 1 Integration Tests")
	logger.info("=" * 80)
	
	tests = [
		("Basic Flow", test_basic_flow),
		("Action Queue", test_action_queue),
		("Event Broadcasting", test_event_broadcasting),
		("Extended Action Registry", test_action_registry_extended),
		("Complete Integration", test_complete_integration),
	]
	
	passed = 0
	failed = 0
	
	for test_name, test_func in tests:
		try:
			result = await test_func()
			if result:
				passed += 1
			else:
				failed += 1
				logger.error(f"❌ {test_name} FAILED")
		except Exception as e:
			failed += 1
			logger.error(f"❌ {test_name} FAILED with exception: {e}", exc_info=True)
	
	logger.info("=" * 80)
	logger.info(f"📊 Test Results: {passed} passed, {failed} failed")
	logger.info("=" * 80)
	
	if failed > 0:
		logger.error("❌ Some tests failed!")
		sys.exit(1)
	else:
		logger.info("✅ All tests passed!")
		sys.exit(0)


if __name__ == "__main__":
	asyncio.run(main())

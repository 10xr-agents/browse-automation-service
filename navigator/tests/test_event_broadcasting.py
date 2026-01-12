"""
Tests for Event Broadcasting and Error Handling

Tests validate:
- Event broadcaster functionality
- WebSocket server setup
- Error handling and recovery mechanisms
"""

import asyncio
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_event_broadcaster_import():
	"""Test that event broadcaster can be imported."""
	logger.info('Testing event broadcaster import...')
	try:
		from navigator.streaming.broadcaster import EventBroadcaster

		logger.info('✅ Event broadcaster imported successfully')
		return True
	except ImportError as e:
		logger.error(f'❌ Failed to import event broadcaster: {e}')
		return False


async def test_event_broadcaster_creation():
	"""Test that event broadcaster can be created."""
	logger.info('Testing event broadcaster creation...')
	try:
		from navigator.streaming.broadcaster import EventBroadcaster

		broadcaster = EventBroadcaster()
		assert broadcaster is not None
		assert broadcaster.room_websockets == {}

		logger.info('✅ Event broadcaster created successfully')
		return True
	except Exception as e:
		logger.error(f'❌ Failed to create event broadcaster: {e}')
		return False


async def test_websocket_server_import():
	"""Test that WebSocket server can be imported."""
	logger.info('Testing WebSocket server import...')
	try:
		from navigator.server.websocket import get_app, get_event_broadcaster

		logger.info('✅ WebSocket server imported successfully')
		return True
	except ImportError as e:
		logger.error(f'❌ Failed to import WebSocket server: {e}')
		return False


async def test_websocket_server_creation():
	"""Test that WebSocket server can be created."""
	logger.info('Testing WebSocket server creation...')
	try:
		from navigator.server.websocket import get_app, get_event_broadcaster

		app = get_app()
		assert app is not None

		broadcaster = get_event_broadcaster()
		assert broadcaster is not None

		logger.info('✅ WebSocket server created successfully')
		return True
	except Exception as e:
		logger.error(f'❌ Failed to create WebSocket server: {e}')
		return False


async def test_browser_session_manager_error_handling():
	"""Test that browser session manager has error handling methods."""
	logger.info('Testing browser session manager error handling...')
	try:
		from navigator.session.manager import BrowserSessionManager
		from navigator.streaming.broadcaster import EventBroadcaster

		broadcaster = EventBroadcaster()
		manager = BrowserSessionManager(event_broadcaster=broadcaster)

		# Check error handling methods exist
		assert hasattr(manager, 'handle_browser_error'), 'handle_browser_error method not found'
		assert hasattr(manager, 'recover_session'), 'recover_session method not found'

		logger.info('✅ Browser session manager has error handling methods')
		return True
	except Exception as e:
		logger.error(f'❌ Failed to test error handling: {e}')
		return False


async def test_mcp_server_recovery_tool():
	"""Test that MCP server has recovery tool."""
	logger.info('Testing MCP server recovery tool...')
	try:
		from navigator.server.mcp import BrowserAutomationMCPServer

		server = BrowserAutomationMCPServer()

		# Check recovery method exists
		assert hasattr(server, '_recover_browser_session'), 'recover_browser_session method not found'

		logger.info('✅ MCP server has recovery tool')
		return True
	except Exception as e:
		logger.error(f'❌ Failed to test recovery tool: {e}')
		return False


async def run_all_tests():
	"""Run all event broadcasting and error handling tests."""
	logger.info('=' * 70)
	logger.info('Event Broadcasting and Error Handling Tests')
	logger.info('=' * 70)

	results = []
	results.append(await test_event_broadcaster_import())
	results.append(await test_event_broadcaster_creation())
	results.append(await test_websocket_server_import())
	results.append(await test_websocket_server_creation())
	results.append(await test_browser_session_manager_error_handling())
	results.append(await test_mcp_server_recovery_tool())

	passed = sum(results)
	total = len(results)

	logger.info('=' * 70)
	logger.info(f'Results: {passed}/{total} tests passed')
	logger.info('=' * 70)

	return all(results)


if __name__ == '__main__':
	asyncio.run(run_all_tests())

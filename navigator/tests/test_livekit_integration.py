"""
Tests for LiveKit Integration

These tests validate the browser automation service's LiveKit integration.
Note: These tests require LiveKit SDK and may require a LiveKit server for full testing.
"""

import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_livekit_service_import():
	"""Test that LiveKit service can be imported."""
	logger.info('Testing LiveKit service import...')
	try:
		from navigator.streaming.livekit import LIVEKIT_AVAILABLE, LiveKitStreamingService

		if not LIVEKIT_AVAILABLE:
			logger.warning('LiveKit SDK not installed')
			return False

		logger.info('✅ LiveKit service imported successfully')
		return True
	except ImportError as e:
		logger.error(f'❌ Failed to import LiveKit service: {e}')
		return False


async def test_browser_session_manager_import():
	"""Test that browser session manager can be imported."""
	logger.info('Testing browser session manager import...')
	try:
		from navigator.session.manager import BrowserSessionManager

		logger.info('✅ Browser session manager imported successfully')
		return True
	except ImportError as e:
		logger.error(f'❌ Failed to import browser session manager: {e}')
		return False


async def test_browser_session_manager_creation():
	"""Test that browser session manager can be created."""
	logger.info('Testing browser session manager creation...')
	try:
		from navigator.session.manager import BrowserSessionManager

		manager = BrowserSessionManager()
		assert manager is not None
		assert manager.sessions == {}

		logger.info('✅ Browser session manager created successfully')
		return True
	except Exception as e:
		logger.error(f'❌ Failed to create browser session manager: {e}')
		return False


async def test_mcp_server_livekit_tools():
	"""Test that MCP server has LiveKit-aware tools."""
	logger.info('Testing MCP server LiveKit tools...')
	try:
		from navigator.server.mcp import BrowserAutomationMCPServer

		server = BrowserAutomationMCPServer()

		# Check server structure
		logger.info('Checking server structure...')
		assert hasattr(server, 'session_manager'), 'Session manager not found'
		assert hasattr(server, '_start_browser_session'), 'start_browser_session method not found'
		assert hasattr(server, '_pause_browser_session'), 'pause_browser_session method not found'
		assert hasattr(server, '_resume_browser_session'), 'resume_browser_session method not found'
		assert hasattr(server, '_close_browser_session'), 'close_browser_session method not found'

		logger.info('✅ MCP server has LiveKit tools')
		return True
	except Exception as e:
		logger.error(f'❌ Failed to test MCP server LiveKit tools: {e}')
		return False


async def test_livekit_service_structure():
	"""Test LiveKit service structure."""
	logger.info('Testing LiveKit service structure...')
	try:
		from navigator.streaming.livekit import LIVEKIT_AVAILABLE, LiveKitStreamingService

		if not LIVEKIT_AVAILABLE:
			logger.warning('⚠️  LiveKit SDK not installed - skipping structure test')
			return True  # Not a failure, just missing dependency

		# Test service can be instantiated (without connecting)
		service = LiveKitStreamingService(
			livekit_url='ws://localhost:7880',
			livekit_token='test-token',
			room_name='test-room',
		)

		assert service.livekit_url == 'ws://localhost:7880'
		assert service.room_name == 'test-room'
		assert service.width == 1920
		assert service.height == 1080
		assert service.fps == 10
		assert not service.is_active

		logger.info('✅ LiveKit service structure is correct')
		return True
	except Exception as e:
		logger.error(f'❌ Failed to test LiveKit service structure: {e}')
		return False


async def run_all_tests():
	"""Run all LiveKit integration tests."""
	logger.info('=' * 70)
	logger.info('LiveKit Integration Tests')
	logger.info('=' * 70)

	results = []
	results.append(await test_livekit_service_import())
	results.append(await test_browser_session_manager_import())
	results.append(await test_browser_session_manager_creation())
	results.append(await test_mcp_server_livekit_tools())
	results.append(await test_livekit_service_structure())

	passed = sum(results)
	total = len(results)

	logger.info('=' * 70)
	logger.info(f'Results: {passed}/{total} tests passed')
	logger.info('=' * 70)

	return all(results)


if __name__ == '__main__':
	asyncio.run(run_all_tests())

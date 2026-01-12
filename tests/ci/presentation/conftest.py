"""
Pytest configuration for Phase 1 (Presentation Flow) tests.

Provides fixtures for testing Presentation Flow Manager, Action Registry,
Action Queue, Event Broadcasting, and Session Persistence.
"""

import asyncio
import tempfile
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_httpserver import HTTPServer

from browser_use.browser import BrowserSession
from browser_use.browser.profile import BrowserProfile

from navigator.action.dispatcher import ActionDispatcher
from navigator.presentation.action_queue import ActionQueue
from navigator.presentation.action_registry import PresentationActionRegistry
from navigator.presentation.flow_manager import PresentationFlowManager
from navigator.presentation.session_store import SessionStore
from navigator.session.manager import BrowserSessionManager
from navigator.streaming.broadcaster import EventBroadcaster


@pytest.fixture(scope='session')
def http_server():
	"""Create a test HTTP server for browser automation tests."""
	server = HTTPServer()
	server.start()

	# Simple test page
	server.expect_request('/test').respond_with_data(
		'<html><head><title>Test Page</title></head><body>'
		'<h1>Test Page</h1>'
		'<button id="btn1">Click Me</button>'
		'<input type="text" id="input1" placeholder="Enter text">'
		'<a href="/test2">Link</a>'
		'</body></html>',
		content_type='text/html',
	)

	# Another test page
	server.expect_request('/test2').respond_with_data(
		'<html><head><title>Test Page 2</title></head><body>'
		'<h1>Test Page 2</h1>'
		'<p>This is page 2</p>'
		'</body></html>',
		content_type='text/html',
	)

	yield server
	server.stop()


@pytest.fixture(scope='session')
def base_url(http_server):
	"""Return the base URL for the test HTTP server."""
	return f'http://{http_server.host}:{http_server.port}'


@pytest.fixture(scope='function')
async def browser_session(base_url):
	"""Create a browser session for testing."""
	session = BrowserSession(
		browser_profile=BrowserProfile(
			headless=True,
			user_data_dir=None,
			keep_alive=True,
		)
	)
	await session.start()
	
	# Navigate to test page
	from browser_use.browser.events import NavigateToUrlEvent
	session.event_bus.dispatch(NavigateToUrlEvent(url=f'{base_url}/test'))
	await asyncio.sleep(0.5)  # Wait for navigation
	
	yield session
	await session.kill()


@pytest.fixture(scope='function')
async def action_dispatcher(browser_session):
	"""Create an ActionDispatcher instance."""
	return ActionDispatcher(browser_session=browser_session)


@pytest.fixture(scope='function')
async def action_registry(action_dispatcher):
	"""Create a PresentationActionRegistry instance."""
	return PresentationActionRegistry(action_dispatcher=action_dispatcher)


@pytest.fixture(scope='function')
def event_broadcaster():
	"""Create an EventBroadcaster instance (without Redis)."""
	return EventBroadcaster(redis_client=None, use_websocket=False)


@pytest.fixture(scope='function')
def mock_redis_client():
	"""Create a mock Redis client for testing."""
	mock_redis = AsyncMock()
	mock_redis.publish = AsyncMock(return_value=1)
	mock_redis.get = AsyncMock(return_value=None)
	mock_redis.setex = AsyncMock(return_value=True)
	mock_redis.delete = AsyncMock(return_value=1)
	mock_redis.keys = AsyncMock(return_value=[])
	return mock_redis


@pytest.fixture(scope='function')
def event_broadcaster_with_redis(mock_redis_client):
	"""Create an EventBroadcaster instance with Redis."""
	return EventBroadcaster(redis_client=mock_redis_client, use_websocket=False)


@pytest.fixture(scope='function')
def session_store(mock_redis_client):
	"""Create a SessionStore instance with mock Redis."""
	return SessionStore(redis_client=mock_redis_client)


@pytest.fixture(scope='function')
def action_queue():
	"""Create an ActionQueue instance (in-memory, no BullMQ)."""
	return ActionQueue(queue=None, max_actions_per_second=None, max_retries=3)


@pytest.fixture(scope='function')
def action_queue_with_rate_limit():
	"""Create an ActionQueue instance with rate limiting."""
	return ActionQueue(queue=None, max_actions_per_second=2, max_retries=3)


@pytest.fixture(scope='function')
def flow_manager():
	"""Create a PresentationFlowManager instance (no BullMQ, short timeout for testing)."""
	return PresentationFlowManager(
		timeout_minutes=1,  # 1 minute for testing
		command_queue=None,  # In-memory queue
		browser_session_manager=None,  # Will create one
	)


@pytest.fixture(scope='function')
def browser_session_manager(event_broadcaster):
	"""Create a BrowserSessionManager instance."""
	return BrowserSessionManager(event_broadcaster=event_broadcaster)

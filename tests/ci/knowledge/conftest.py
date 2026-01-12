"""
Pytest configuration for Part 2 (Knowledge Retrieval) tests.

Provides fixtures for testing Exploration Engine and other knowledge retrieval components.
"""

import asyncio

import pytest
from pytest_httpserver import HTTPServer

from browser_use.browser import BrowserSession
from browser_use.browser.profile import BrowserProfile

from navigator.knowledge.exploration_engine import ExplorationEngine, ExplorationStrategy


@pytest.fixture(scope='session')
def http_server():
	"""Create a test HTTP server for knowledge retrieval tests."""
	server = HTTPServer()
	server.start()
	
	# Create a simple multi-page website structure
	# Home page with links
	server.expect_request('/').respond_with_data(
		'<html><head><title>Home</title></head><body>'
		'<h1>Home Page</h1>'
		'<a href="/page1">Page 1</a>'
		'<a href="/page2">Page 2</a>'
		'<a href="/page3">Page 3</a>'
		'</body></html>',
		content_type='text/html',
	)
	
	# Page 1 with links to deeper pages
	server.expect_request('/page1').respond_with_data(
		'<html><head><title>Page 1</title></head><body>'
		'<h1>Page 1</h1>'
		'<a href="/">Home</a>'
		'<a href="/page1/sub1">Sub 1</a>'
		'<a href="/page1/sub2">Sub 2</a>'
		'</body></html>',
		content_type='text/html',
	)
	
	# Page 2
	server.expect_request('/page2').respond_with_data(
		'<html><head><title>Page 2</title></head><body>'
		'<h1>Page 2</h1>'
		'<a href="/">Home</a>'
		'</body></html>',
		content_type='text/html',
	)
	
	# Page 3
	server.expect_request('/page3').respond_with_data(
		'<html><head><title>Page 3</title></head><body>'
		'<h1>Page 3</h1>'
		'<a href="/">Home</a>'
		'</body></html>',
		content_type='text/html',
	)
	
	# Deeper pages
	server.expect_request('/page1/sub1').respond_with_data(
		'<html><head><title>Sub 1</title></head><body>'
		'<h1>Sub 1</h1>'
		'<a href="/page1">Page 1</a>'
		'</body></html>',
		content_type='text/html',
	)
	
	server.expect_request('/page1/sub2').respond_with_data(
		'<html><head><title>Sub 2</title></head><body>'
		'<h1>Sub 2</h1>'
		'<a href="/page1">Page 1</a>'
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
	yield session
	await session.kill()


@pytest.fixture(scope='function')
def exploration_engine(browser_session, base_url):
	"""Create an ExplorationEngine instance."""
	return ExplorationEngine(
		browser_session=browser_session,
		max_depth=3,
		strategy=ExplorationStrategy.BFS,
		base_url=base_url,
	)

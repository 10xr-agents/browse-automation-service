"""
Pytest configuration and shared fixtures for all tests.
"""

import asyncio
import os
import subprocess
import time
from pathlib import Path

import pytest
from httpx import AsyncClient


@pytest.fixture(scope="session")
def event_loop():
	"""Create an event loop for the test session."""
	loop = asyncio.get_event_loop_policy().new_event_loop()
	yield loop
	loop.close()


@pytest.fixture(scope="session")
def server_process():
	"""
	Start the server process for integration tests.
	
	Yields the process handle. Cleans up on teardown.
	"""
	server_port = int(os.getenv("TEST_SERVER_PORT", "8000"))
	server_url = os.getenv("TEST_SERVER_URL", f"http://localhost:{server_port}")
	
	# Check if server is already running
	import socket
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	server_running = sock.connect_ex(('localhost', server_port)) == 0
	sock.close()
	
	if server_running:
		print(f"✅ Server already running on port {server_port}")
		yield None
		return
	
	# Start server
	project_root = Path(__file__).parent.parent
	server_script = project_root / "navigator" / "start_server.py"
	
	print(f"\n🚀 Starting server for integration tests...")
	print(f"   Script: {server_script}")
	print(f"   Port: {server_port}")
	
	# Start server as subprocess
	env = os.environ.copy()
	process = subprocess.Popen(
		["uv", "run", "python", str(server_script)],
		cwd=str(project_root),
		env=env,
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
		text=True,
		bufsize=1,
	)
	
	# Wait for server to be ready
	print(f"⏳ Waiting for server to start...")
	max_wait = 60  # 60 seconds max
	start_time = time.time()
	server_ready = False
	
	while time.time() - start_time < max_wait:
		try:
			import socket
			sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			result = sock.connect_ex(('localhost', server_port))
			sock.close()
			
			if result == 0:
				# Port is open, check health endpoint
				import httpx
				try:
					response = httpx.get(f"{server_url}/health", timeout=2.0)
					if response.status_code == 200:
						server_ready = True
						print(f"✅ Server is ready! (took {time.time() - start_time:.1f}s)")
						break
				except Exception:
					pass
		except Exception:
			pass
		
		# Check if process died
		if process.poll() is not None:
			# Process exited, check output
			stdout, _ = process.communicate()
			print(f"❌ Server process exited early with code {process.returncode}")
			print(f"   Output: {stdout[-500:] if stdout else 'No output'}")
			raise RuntimeError(f"Server failed to start (exit code: {process.returncode})")
		
		time.sleep(1)
	
	if not server_ready:
		process.terminate()
		process.wait(timeout=5)
		raise RuntimeError(f"Server did not become ready within {max_wait} seconds")
	
	yield process
	
	# Cleanup: terminate server
	print(f"\n🛑 Stopping server...")
	try:
		process.terminate()
		process.wait(timeout=10)
		print(f"✅ Server stopped")
	except subprocess.TimeoutExpired:
		print(f"⚠️  Server did not stop gracefully, killing...")
		process.kill()
		process.wait()
	except Exception as e:
		print(f"⚠️  Error stopping server: {e}")


@pytest.fixture
async def client(server_process):
	"""
	Create an async HTTP client for API testing.
	
	Waits for server to be ready if it was just started.
	"""
	server_port = int(os.getenv("TEST_SERVER_PORT", "8000"))
	server_url = os.getenv("TEST_SERVER_URL", f"http://localhost:{server_port}")
	
	# Wait for server to be ready
	max_wait = 30
	start_time = time.time()
	
	while time.time() - start_time < max_wait:
		try:
			async with AsyncClient(base_url=server_url, timeout=5.0) as test_client:
				response = await test_client.get("/health")
				if response.status_code == 200:
					async with AsyncClient(base_url=server_url, timeout=300.0) as client:
						yield client
					return
		except Exception:
			await asyncio.sleep(1)
	
	raise RuntimeError(f"Server not available at {server_url} after {max_wait} seconds")

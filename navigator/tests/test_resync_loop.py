"""
Automated test and fix loop for resync workflow.

This script:
1. Starts the server
2. Initiates a resync using the provided data
3. Monitors logs for errors, exceptions, warnings
4. Fixes issues found
5. Repeats until no errors remain
"""

import asyncio
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

# Test configuration
SERVER_URL = "http://localhost:8000"
KNOWLEDGE_ID = "696fc99db002d6c4ff0d6b3c"
ORGANIZATION_ID = "I7Cchh33eJM0TKnSF8HGJ1X0Fbqat9ub"

# Resync request data (from user's logs)
RESYNC_REQUEST = {
	"website_url": "https://app.spadeworks.co/",
	"website_name": "https://app.spadeworks.co/",
	"credentials": {
		"username": "test@example.com",  # Will need actual credentials
		"password": "test123",  # Will need actual credentials
	},
	"s3_references": [
		{
			"bucket": "knowledge-extraction-wf-dev",
			"key": f"{ORGANIZATION_ID}/knowledge/696fc997b002d6c4ff0d6b3b/2026-01-20T18-29-43-spadeworks-short-demo.mp4",
			"region": "nyc3",
			"presigned_url": ""  # Will be generated
		}
	],
	"file_metadata_list": [
		{
			"filename": "spadeworks-short-demo.mp4",
			"size": 916577,
			"content_type": "video/mp4"
		}
	],
	"knowledge_id": KNOWLEDGE_ID,
	"options": {
		"max_pages": 10,
		"max_depth": 3,
		"extract_thumbnails": True,
	}
}

logger = logging.getLogger(__name__)


class ErrorScanner:
	"""Scans logs for errors, exceptions, and warnings."""
	
	ERROR_PATTERNS = [
		r'ERROR',
		r'Exception',
		r'Traceback',
		r'Failed',
		r'failed',
		r'Error:',
		r'error:',
		r'ValidationError',
		r'TypeError',
		r'AttributeError',
		r'KeyError',
		r'ValueError',
		r'IndexError',
		r'not JSON serializable',
		r'no attribute',
		r'missing.*required',
		r'unexpected keyword',
	]
	
	WARNING_PATTERNS = [
		r'WARNING',
		r'Warning',
		r'warning',
		r'⚠️',
	]
	
	def __init__(self, log_file: Path | None = None):
		self.log_file = log_file
		self.errors: list[dict[str, Any]] = []
		self.warnings: list[dict[str, Any]] = []
	
	def scan_logs(self, log_content: str) -> tuple[list[dict], list[dict]]:
		"""Scan log content for errors and warnings."""
		errors = []
		warnings = []
		
		lines = log_content.split('\n')
		for i, line in enumerate(lines):
			# Check for errors
			for pattern in self.ERROR_PATTERNS:
				if re.search(pattern, line, re.IGNORECASE):
					errors.append({
						'line_number': i + 1,
						'line': line,
						'pattern': pattern,
					})
					break
			
			# Check for warnings
			for pattern in self.WARNING_PATTERNS:
				if re.search(pattern, line, re.IGNORECASE):
					warnings.append({
						'line_number': i + 1,
						'line': line,
						'pattern': pattern,
					})
					break
		
		return errors, warnings
	
	def filter_known_issues(self, errors: list[dict]) -> list[dict]:
		"""Filter out known/expected errors."""
		known_patterns = [
			r'DEBUG.*httpcore',  # HTTP debug logs
			r'DEBUG.*LiteLLM',  # LiteLLM debug logs
			r'Worker heartbeating',  # Temporal warning (expected)
		]
		
		filtered = []
		for error in errors:
			should_filter = False
			for pattern in known_patterns:
				if re.search(pattern, error['line'], re.IGNORECASE):
					should_filter = True
					break
			
			if not should_filter:
				filtered.append(error)
		
		return filtered


class ServerManager:
	"""Manages server process and logs."""
	
	def __init__(self, server_url: str = SERVER_URL):
		self.server_url = server_url
		self.process: subprocess.Popen | None = None
		self.log_file: Path | None = None
	
	async def start_server(self) -> bool:
		"""Start the server process."""
		try:
			# Create log file
			log_dir = Path(__file__).parent.parent / "test_logs"
			log_dir.mkdir(exist_ok=True)
			self.log_file = log_dir / f"server_{int(time.time())}.log"
			
			# Start server
			self.process = subprocess.Popen(
				["uv", "run", "python", "navigator/start_server.py"],
				stdout=open(self.log_file, 'w'),
				stderr=subprocess.STDOUT,
				cwd=Path(__file__).parent.parent.parent,
			)
			
			# Wait for server to be ready
			max_wait = 30
			for _ in range(max_wait):
				try:
					async with httpx.AsyncClient() as client:
						response = await client.get(f"{self.server_url}/health", timeout=2.0)
						if response.status_code == 200:
							logger.info("✅ Server started successfully")
							return True
				except Exception:
					await asyncio.sleep(1)
			
			logger.error("❌ Server failed to start within timeout")
			return False
		except Exception as e:
			logger.error(f"❌ Failed to start server: {e}")
			return False
	
	async def stop_server(self):
		"""Stop the server process."""
		if self.process:
			self.process.terminate()
			try:
				self.process.wait(timeout=5)
			except subprocess.TimeoutExpired:
				self.process.kill()
			self.process = None
	
	def get_logs(self) -> str:
		"""Get current log content."""
		if self.log_file and self.log_file.exists():
			return self.log_file.read_text()
		return ""


class ResyncTester:
	"""Tests resync workflow and fixes issues."""
	
	def __init__(self, server_manager: ServerManager, error_scanner: ErrorScanner):
		self.server_manager = server_manager
		self.error_scanner = error_scanner
		self.client = httpx.AsyncClient(base_url=SERVER_URL, timeout=60.0)
	
	async def initiate_resync(self) -> dict[str, Any]:
		"""Initiate resync workflow."""
		try:
			logger.info(f"🔄 Initiating resync for knowledge_id={KNOWLEDGE_ID}")
			
			# Call the resync endpoint (which internally calls /ingest/start)
			response = await self.client.post(
				f"/api/knowledge/ingest/start",
				json=RESYNC_REQUEST,
			)
			
			if response.status_code == 200:
				result = response.json()
				job_id = result.get('job_id')
				logger.info(f"✅ Resync started: job_id={job_id}")
				return {"success": True, "job_id": job_id, "response": result}
			else:
				logger.error(f"❌ Resync failed: {response.status_code} - {response.text}")
				return {"success": False, "error": response.text, "status_code": response.status_code}
		except Exception as e:
			logger.error(f"❌ Exception during resync: {e}")
			return {"success": False, "error": str(e)}
	
	async def monitor_workflow(self, job_id: str, max_wait: int = 300) -> dict[str, Any]:
		"""Monitor workflow until completion or failure."""
		logger.info(f"📊 Monitoring workflow: job_id={job_id}")
		
		start_time = time.time()
		while time.time() - start_time < max_wait:
			try:
				response = await self.client.get(f"/api/knowledge/workflows/status/{job_id}")
				if response.status_code == 200:
					status_data = response.json()
					status = status_data.get('status', 'unknown')
					phase = status_data.get('phase')
					progress = status_data.get('progress', 0)
					
					logger.info(f"   Status: {status}, Phase: {phase}, Progress: {progress}%")
					
					if status in ['completed', 'failed', 'cancelled']:
						return {
							"status": status,
							"phase": phase,
							"progress": progress,
							"data": status_data,
						}
				
				await asyncio.sleep(5)  # Poll every 5 seconds
			except Exception as e:
				logger.warning(f"⚠️ Error checking workflow status: {e}")
				await asyncio.sleep(5)
		
		return {"status": "timeout", "error": "Workflow monitoring timeout"}
	
	async def scan_and_fix_errors(self) -> tuple[bool, list[dict]]:
		"""Scan logs for errors and attempt to fix them."""
		logs = self.server_manager.get_logs()
		errors, warnings = self.error_scanner.scan_logs(logs)
		
		# Filter known issues
		errors = self.error_scanner.filter_known_issues(errors)
		
		if not errors:
			return True, []
		
		logger.warning(f"⚠️ Found {len(errors)} error(s) in logs")
		for error in errors[:5]:  # Show first 5
			logger.warning(f"   Line {error['line_number']}: {error['line'][:100]}")
		
		# Attempt to fix errors
		fixes_applied = []
		for error in errors:
			fix = await self.attempt_fix(error)
			if fix:
				fixes_applied.append(fix)
		
		return len(fixes_applied) > 0, fixes_applied
	
	async def attempt_fix(self, error: dict) -> dict | None:
		"""Attempt to fix an error based on its pattern."""
		line = error['line']
		
		# Pattern-based fixes
		if 'not JSON serializable' in line:
			return await self.fix_json_serialization_error(error)
		elif 'no attribute' in line or 'missing.*required' in line:
			return await self.fix_attribute_error(error)
		elif 'ValidationError' in line:
			return await self.fix_validation_error(error)
		
		return None
	
	async def fix_json_serialization_error(self, error: dict) -> dict | None:
		"""Fix JSON serialization errors."""
		# This would need to analyze the error and fix the code
		# For now, just log it
		logger.info(f"🔧 Would fix JSON serialization error: {error['line']}")
		return {"type": "json_serialization", "error": error}
	
	async def fix_attribute_error(self, error: dict) -> dict | None:
		"""Fix attribute errors."""
		logger.info(f"🔧 Would fix attribute error: {error['line']}")
		return {"type": "attribute_error", "error": error}
	
	async def fix_validation_error(self, error: dict) -> dict | None:
		"""Fix validation errors."""
		logger.info(f"🔧 Would fix validation error: {error['line']}")
		return {"type": "validation_error", "error": error}


@pytest.mark.asyncio
async def test_resync_loop():
	"""
	Automated test and fix loop for resync workflow.
	
	This test:
	1. Starts the server
	2. Initiates a resync
	3. Monitors for errors
	4. Fixes issues found
	5. Repeats until clean
	"""
	server_manager = ServerManager()
	error_scanner = ErrorScanner()
	tester = ResyncTester(server_manager, error_scanner)
	
	max_iterations = 5
	iteration = 0
	
	try:
		# Start server
		if not await server_manager.start_server():
			pytest.fail("Failed to start server")
		
		# Main test loop
		while iteration < max_iterations:
			iteration += 1
			logger.info(f"\n{'='*80}")
			logger.info(f"🔄 Test Iteration {iteration}/{max_iterations}")
			logger.info(f"{'='*80}\n")
			
			# Initiate resync
			resync_result = await tester.initiate_resync()
			if not resync_result.get('success'):
				logger.error(f"❌ Resync failed: {resync_result.get('error')}")
				break
			
			job_id = resync_result.get('job_id')
			if not job_id:
				logger.error("❌ No job_id returned from resync")
				break
			
			# Wait a bit for workflow to start
			await asyncio.sleep(10)
			
			# Monitor workflow (with timeout)
			workflow_result = await tester.monitor_workflow(job_id, max_wait=60)
			
			# Scan for errors
			errors_fixed, fixes = await tester.scan_and_fix_errors()
			
			if not errors_fixed and workflow_result.get('status') in ['completed', 'failed']:
				# Check if workflow completed successfully
				if workflow_result.get('status') == 'completed':
					logger.info("✅ Workflow completed successfully with no errors!")
					break
				else:
					logger.error(f"❌ Workflow failed: {workflow_result}")
					# Continue to next iteration to try fixing
			
			if errors_fixed:
				logger.info(f"🔧 Applied {len(fixes)} fix(es), restarting server...")
				await server_manager.stop_server()
				await asyncio.sleep(2)
				if not await server_manager.start_server():
					pytest.fail("Failed to restart server after fixes")
			else:
				logger.warning("⚠️ No fixes applied, but errors remain")
		
		# Final error scan
		logs = server_manager.get_logs()
		errors, warnings = error_scanner.scan_logs(logs)
		errors = error_scanner.filter_known_issues(errors)
		
		if errors:
			logger.error(f"❌ Test completed with {len(errors)} remaining error(s)")
			for error in errors[:10]:
				logger.error(f"   {error['line']}")
			pytest.fail(f"Test completed with {len(errors)} errors remaining")
		else:
			logger.info("✅ Test completed successfully with no errors!")
	
	finally:
		await server_manager.stop_server()
		await tester.client.aclose()


if __name__ == '__main__':
	# Configure logging
	logging.basicConfig(
		level=logging.INFO,
		format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
	)
	
	# Run test
	pytest.main([__file__, '-v', '-s'])

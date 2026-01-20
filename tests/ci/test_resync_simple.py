#!/usr/bin/env python3
"""
Simple automated test for resync workflow.

Monitors server logs and reports errors found during resync execution.

Usage:
    # Terminal 1: Start server manually
    uv run python navigator/start_server.py
    
    # Terminal 2: Run this test
    uv run python tests/ci/test_resync_simple.py
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

import httpx

# Test configuration
SERVER_URL = "http://localhost:8000"
KNOWLEDGE_ID = "696fc99db002d6c4ff0d6b3c"
ORGANIZATION_ID = "I7Cchh33eJM0TKnSF8HGJ1X0Fbqat9ub"

# Resync request data
RESYNC_REQUEST = {
	"website_url": "https://app.spadeworks.co/",
	"website_name": "https://app.spadeworks.co/",
	"credentials": {
		"username": os.getenv("TEST_USERNAME", "test@example.com"),
		"password": os.getenv("TEST_PASSWORD", "test123"),
	},
	"s3_references": [
		{
			"bucket": "knowledge-extraction-wf-dev",
			"key": f"{ORGANIZATION_ID}/knowledge/696fc997b002d6c4ff0d6b3b/2026-01-20T18-29-43-spadeworks-short-demo.mp4",
			"region": "nyc3",
			"presigned_url": ""
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

logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


async def check_server_health() -> bool:
	"""Check if server is running."""
	try:
		async with httpx.AsyncClient(timeout=2.0) as client:
			response = await client.get(f"{SERVER_URL}/health")
			return response.status_code == 200
	except Exception:
		return False


async def initiate_resync() -> dict:
	"""Initiate resync workflow."""
	try:
		logger.info(f"🔄 Initiating resync for knowledge_id={KNOWLEDGE_ID}")
		
		async with httpx.AsyncClient(base_url=SERVER_URL, timeout=120.0) as client:
			response = await client.post(
				"/api/knowledge/ingest/start",
				json=RESYNC_REQUEST,
			)
			
			if response.status_code == 200:
				result = response.json()
				job_id = result.get('job_id')
				workflow_id = result.get('workflow_id')
				logger.info(f"✅ Resync started: job_id={job_id}, workflow_id={workflow_id}")
				return {"success": True, "job_id": job_id, "workflow_id": workflow_id}
			else:
				logger.error(f"❌ Resync failed: {response.status_code} - {response.text}")
				return {"success": False, "error": response.text, "status_code": response.status_code}
	except Exception as e:
		logger.error(f"❌ Exception during resync: {e}", exc_info=True)
		return {"success": False, "error": str(e)}


async def monitor_workflow(job_id: str, max_wait: int = 600) -> dict:
	"""Monitor workflow until completion."""
	logger.info(f"📊 Monitoring workflow: job_id={job_id} (max {max_wait}s)")
	
	start_time = time.time()
	last_status = None
	
	async with httpx.AsyncClient(base_url=SERVER_URL, timeout=30.0) as client:
		while time.time() - start_time < max_wait:
			try:
				response = await client.get(f"/api/knowledge/workflows/status/{job_id}")
				if response.status_code == 200:
					status_data = response.json()
					status = status_data.get('status', 'unknown')
					phase = status_data.get('phase')
					progress = status_data.get('progress', 0)
					errors = status_data.get('errors', [])
					
					if status != last_status:
						logger.info(f"   Status: {status}, Phase: {phase}, Progress: {progress}%")
						if errors:
							logger.warning(f"   Errors: {len(errors)} error(s) found")
							for error in errors[:3]:
								logger.warning(f"      - {error}")
						last_status = status
					
					if status in ['completed', 'failed', 'cancelled']:
						return {
							"status": status,
							"phase": phase,
							"progress": progress,
							"errors": errors,
							"data": status_data,
						}
				
				await asyncio.sleep(5)
			except Exception as e:
				logger.warning(f"⚠️ Error checking workflow status: {e}")
				await asyncio.sleep(5)
	
	return {"status": "timeout", "error": "Workflow monitoring timeout"}


async def main():
	"""Main test function."""
	logger.info("=" * 80)
	logger.info("🧪 Resync Workflow Test")
	logger.info("=" * 80)
	
	# Check server health
	if not await check_server_health():
		logger.error("❌ Server is not running. Please start the server first:")
		logger.error("   uv run python navigator/start_server.py")
		return 1
	
	logger.info("✅ Server is running")
	
	# Initiate resync
	resync_result = await initiate_resync()
	if not resync_result.get('success'):
		logger.error(f"❌ Failed to initiate resync: {resync_result.get('error')}")
		return 1
	
	job_id = resync_result.get('job_id')
	if not job_id:
		logger.error("❌ No job_id returned from resync")
		return 1
	
	# Monitor workflow
	workflow_result = await monitor_workflow(job_id, max_wait=600)
	
	# Report results
	logger.info("\n" + "=" * 80)
	logger.info("📊 Test Results")
	logger.info("=" * 80)
	logger.info(f"Workflow Status: {workflow_result.get('status')}")
	logger.info(f"Phase: {workflow_result.get('phase')}")
	logger.info(f"Progress: {workflow_result.get('progress', 0)}%")
	
	errors = workflow_result.get('errors', [])
	if errors:
		logger.error(f"\n❌ Found {len(errors)} error(s):")
		for i, error in enumerate(errors, 1):
			logger.error(f"   {i}. {error}")
		return 1
	elif workflow_result.get('status') == 'failed':
		logger.error("\n❌ Workflow failed")
		return 1
	elif workflow_result.get('status') == 'completed':
		logger.info("\n✅ Workflow completed successfully!")
		return 0
	else:
		logger.warning(f"\n⚠️ Workflow ended with status: {workflow_result.get('status')}")
		return 1


if __name__ == '__main__':
	try:
		exit_code = asyncio.run(main())
		sys.exit(exit_code)
	except KeyboardInterrupt:
		logger.info("\n⚠️  Test interrupted by user")
		sys.exit(130)
	except Exception as e:
		logger.error(f"❌ Test failed with exception: {e}", exc_info=True)
		sys.exit(1)

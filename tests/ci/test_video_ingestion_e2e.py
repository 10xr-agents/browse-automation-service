"""
End-to-end test for video ingestion workflow.

Tests the complete video ingestion flow using a real API request.
"""

import asyncio
import json

import pytest

pytest_plugins = ("pytest_asyncio",)


@pytest.mark.asyncio
async def test_video_ingestion_workflow(client):
	"""
	Test video ingestion workflow with real API request structure.
	
	This test replicates the exact API request from the logs.
	
	Args:
		client: Async HTTP client fixture (provided by conftest.py)
	"""
	# Request payload from logs
	request_payload = {
		"website_url": "https://app.spadeworks.co/",
		"website_name": "https://app.spadeworks.co/",
		"s3_references": [
			{
				"bucket": "knowledge-extraction-wf-dev",
				"key": "I7Cchh33eJM0TKnSF8HGJ1X0Fbqat9ub/knowledge/696d1b4fe1c3d23b77b94981/2026-01-18T17-41-35-Spadeworks_Dashboard_Demo.mp4",
				"region": "nyc3",
				"endpoint": "https://knowledge-extraction-wf-dev.sfo3.digitaloceanspaces.com",
				"presigned_url": "https://knowledge-extraction-wf-dev.sfo3.digitaloceanspaces.com/knowledge-extraction-wf-dev/I7Cchh33eJM0TKnSF8HGJ1X0Fbqat9ub/knowledge/696d1b4fe1c3d23b77b94981/2026-01-18T17-41-35-Spadeworks_Dashboard_Demo.mp4?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Content-Sha256=UNSIGNED-PAYLOAD&X-Amz-Credential=DO00JKTYAG9BWK6TYQHG%2F20260119%2Fnyc3%2Fs3%2Faws4_request&X-Amz-Date=20260119T203709Z&X-Amz-Expires=3600&X-Amz-Signature=7fe872e0da276f7653fa276e66f7fdbf409c65c657bb9c78e6c2058e533380b1&X-Amz-SignedHeaders=host&x-amz-checksum-mode=ENABLED&x-id=GetObject",
				"expires_at": "2026-01-19T21:37:09.603Z"
			}
		],
		"file_metadata_list": [
			{
				"filename": "Spadeworks Dashboard Demo.mp4",
				"size": 7532424,
				"content_type": "video/mp4",
				"uploaded_at": "2026-01-18T17:41:38.750Z"
			}
		],
		"documentation_urls": None,
		"credentials": {
			"username": "sai.satwik@spadeworks.co",
			"password": "12345678"
		},
		"options": {
			"max_pages": 100,
			"max_depth": 10,
			"extract_code_blocks": True,
			"extract_thumbnails": True,
			"credentials": None
		},
		"job_id": None,
		"knowledge_id": "696d1b52e1c3d23b77b94982"
	}
	
	# Step 1: Verify server health
	print("\n" + "="*80)
	print("🧪 Starting video ingestion workflow test...")
	print("="*80)
	
	health_response = await client.get("/health")
	assert health_response.status_code == 200, f"Server health check failed: {health_response.status_code}"
	print("✅ Server health check passed")
	
	# Step 2: Start ingestion workflow
	print("\n📤 Sending ingestion request...")
	
	response = await client.post(
		"/api/knowledge/ingest/start",
		json=request_payload,
	)
	
	print(f"\n📤 Request sent to /api/knowledge/ingest/start")
	print(f"   Status: {response.status_code}")
	
	if response.status_code != 200:
		print(f"❌ Request failed: {response.text}")
		raise AssertionError(f"Expected 200, got {response.status_code}: {response.text}")
	
	result = response.json()
	job_id = result.get("job_id")
	
	print(f"✅ Workflow started")
	print(f"   Job ID: {job_id}")
	
	if not job_id:
		raise AssertionError("No job_id returned from API")
	
	# Step 3: Poll for workflow status
	print(f"\n⏳ Polling workflow status...")
	max_attempts = 60  # 5 minutes with 5-second intervals
	
	for attempt in range(max_attempts):
		await asyncio.sleep(5)
		
		status_response = await client.get(
			f"/api/knowledge/workflows/status/{job_id}",
		)
		
		if status_response.status_code == 404:
			print(f"   Attempt {attempt + 1}/{max_attempts}: Workflow not found yet...")
			continue
		
		if status_response.status_code != 200:
			print(f"   ⚠️  Status check failed: {status_response.status_code}")
			continue
		
		status_data = status_response.json()
		phase = status_data.get("phase", "unknown")
		current_activity = status_data.get("current_activity", "unknown")
		
		print(f"   Attempt {attempt + 1}/{max_attempts}: Phase={phase}, Activity={current_activity}")
		
		if phase == "completed":
			print(f"\n✅ Workflow completed successfully!")
			print(f"   Status data: {json.dumps(status_data, indent=2)}")
			return  # Test passed
		elif phase == "failed":
			error = status_data.get("error", "Unknown error")
			print(f"\n❌ Workflow failed: {error}")
			raise AssertionError(f"Workflow failed: {error}")
	
	# If we get here, workflow didn't complete in time
	print(f"\n⏰ Workflow did not complete within {max_attempts * 5} seconds")
	print(f"   Final status: {status_data if 'status_data' in locals() else 'unknown'}")
	raise AssertionError(f"Workflow did not complete within timeout")


if __name__ == "__main__":
	"""Run the test directly using pytest."""
	import sys
	import subprocess
	result = subprocess.run([sys.executable, "-m", "pytest", __file__, "-v", "-s"])
	sys.exit(result.returncode)

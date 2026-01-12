"""
Test script to verify MVP browser automation with google.com
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import httpx

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Server configuration
SERVER_URL = "http://localhost:8000"
ROOM_NAME = "test-room-google"


async def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
	"""Call an MCP tool via HTTP."""
	url = f"{SERVER_URL}/mcp/tools/call"
	payload = {
		"tool": tool_name,  # HTTP endpoint expects "tool" not "name"
		"arguments": arguments
	}
	
	logger.info(f"🔧 Calling MCP tool: {tool_name}")
	logger.debug(f"   Arguments: {json.dumps(arguments, indent=2)}")
	
	async with httpx.AsyncClient(timeout=60.0) as client:
		try:
			response = await client.post(url, json=payload)
			response.raise_for_status()
			result = response.json()
			logger.info(f"✅ Tool call succeeded: {tool_name}")
			logger.debug(f"   Result: {json.dumps(result, indent=2)}")
			return result
		except httpx.HTTPStatusError as e:
			logger.error(f"❌ HTTP error calling tool {tool_name}: {e.response.status_code}")
			try:
				error_detail = e.response.json()
				logger.error(f"   Error detail: {json.dumps(error_detail, indent=2)}")
			except:
				logger.error(f"   Error response: {e.response.text}")
			raise
		except Exception as e:
			logger.error(f"❌ Error calling tool {tool_name}: {e}")
			raise


async def test_browser_google():
	"""Test browser automation by opening google.com."""
	logger.info("=" * 60)
	logger.info("🧪 Testing MVP Browser Automation with Google.com")
	logger.info("=" * 60)
	
	# Check environment variables
	livekit_url = os.getenv("LIVEKIT_URL")
	livekit_api_key = os.getenv("LIVEKIT_API_KEY")
	livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")
	
	if not livekit_url or not livekit_api_key or not livekit_api_secret:
		logger.warning("⚠️  LiveKit credentials not found in environment variables")
		logger.warning("   Using fallback values (may fail if LiveKit not configured)")
		logger.warning("   Set LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET in .env")
	
	try:
		# Step 1: Start browser session with google.com
		logger.info("\n📋 Step 1: Starting browser session...")
		start_result = await call_mcp_tool("start_browser_session", {
			"room_name": ROOM_NAME,
			"livekit_url": livekit_url or "wss://localhost:7880",
			"livekit_api_key": livekit_api_key or "devkey",
			"livekit_api_secret": livekit_api_secret or "secret",
			"initial_url": "https://www.google.com",
			"viewport_width": 1920,
			"viewport_height": 1080,
			"fps": 10
		})
		logger.info(f"✅ Browser session started: {start_result.get('status')}")
		
		# Step 2: Wait a bit for page to load
		logger.info("\n📋 Step 2: Waiting for page to load (3 seconds)...")
		await asyncio.sleep(3)
		
		# Step 3: Get browser context to verify navigation
		logger.info("\n📋 Step 3: Getting browser context...")
		context_result = await call_mcp_tool("get_browser_context", {
			"room_name": ROOM_NAME
		})
		
		logger.info(f"✅ Browser context retrieved:")
		logger.info(f"   URL: {context_result.get('url')}")
		logger.info(f"   Title: {context_result.get('title')}")
		logger.info(f"   Ready State: {context_result.get('ready_state')}")
		logger.info(f"   Viewport: {context_result.get('viewport_width')}x{context_result.get('viewport_height')}")
		logger.info(f"   Scroll: ({context_result.get('scroll_x')}, {context_result.get('scroll_y')})")
		logger.info(f"   Cursor: ({context_result.get('cursor_x')}, {context_result.get('cursor_y')})")
		
		# Verify we're on google.com
		url = context_result.get('url', '')
		if 'google.com' in url.lower():
			logger.info("✅ Successfully navigated to Google.com!")
		else:
			logger.warning(f"⚠️  Expected google.com but got: {url}")
		
		# Step 4: Get screen content for detailed view
		logger.info("\n📋 Step 4: Getting screen content...")
		screen_result = await call_mcp_tool("get_screen_content", {
			"room_name": ROOM_NAME
		})
		
		logger.info(f"✅ Screen content retrieved:")
		logger.info(f"   Visible elements: {screen_result.get('visible_elements_count')}")
		dom_summary = screen_result.get('dom_summary', '')
		if dom_summary:
			# Show first 500 chars of DOM summary
			summary_preview = dom_summary[:500] + ("..." if len(dom_summary) > 500 else "")
			logger.info(f"   DOM summary preview:\n{summary_preview}")
		
		# Step 5: Wait a bit more to see video streaming
		logger.info("\n📋 Step 5: Waiting for video streaming (2 seconds)...")
		await asyncio.sleep(2)
		
		# Step 6: Close browser session
		logger.info("\n📋 Step 6: Closing browser session...")
		close_result = await call_mcp_tool("close_browser_session", {
			"room_name": ROOM_NAME
		})
		logger.info(f"✅ Browser session closed: {close_result.get('status')}")
		
		logger.info("\n" + "=" * 60)
		logger.info("✅ Test completed successfully!")
		logger.info("=" * 60)
		
		return True
		
	except Exception as e:
		logger.error(f"\n❌ Test failed with error: {e}")
		logger.exception("Full traceback:")
		
		# Try to close session on error
		try:
			logger.info("\n🔄 Attempting to close browser session after error...")
			await call_mcp_tool("close_browser_session", {
				"room_name": ROOM_NAME
			})
		except Exception as close_error:
			logger.error(f"   Failed to close session: {close_error}")
		
		return False


if __name__ == "__main__":
	success = asyncio.run(test_browser_google())
	sys.exit(0 if success else 1)

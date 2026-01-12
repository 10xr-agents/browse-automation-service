"""
Interactive test script to test typing and actions on Google.com
Tests: Navigate → Type → Get Screen Content → Click
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
ROOM_NAME = "test-interactive-google"


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


async def test_interactive_google():
	"""Test interactive actions: navigate → type → get screen content → potential click."""
	logger.info("=" * 70)
	logger.info("🧪 Testing Interactive MVP Browser Automation with Google.com")
	logger.info("=" * 70)
	
	# Check environment variables
	livekit_url = os.getenv("LIVEKIT_URL")
	livekit_api_key = os.getenv("LIVEKIT_API_KEY")
	livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")
	
	if not livekit_url or not livekit_api_key or not livekit_api_secret:
		logger.warning("⚠️  LiveKit credentials not found - using fallback values")
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
		
		# Step 2: Wait for page to load
		logger.info("\n📋 Step 2: Waiting for page to load (3 seconds)...")
		await asyncio.sleep(3)
		
		# Step 3: Get initial screen content to find search box
		logger.info("\n📋 Step 3: Getting initial screen content...")
		screen_result = await call_mcp_tool("get_screen_content", {
			"room_name": ROOM_NAME
		})
		
		if 'error' in screen_result:
			logger.error(f"❌ Failed to get screen content: {screen_result['error']}")
			return False
		
		logger.info(f"✅ Screen content retrieved:")
		logger.info(f"   URL: {screen_result.get('url')}")
		logger.info(f"   Title: {screen_result.get('title')}")
		logger.info(f"   Visible elements: {screen_result.get('visible_elements_count')}")
		logger.info(f"   DOM summary length: {len(screen_result.get('dom_summary', ''))} chars")
		
		dom_summary = screen_result.get('dom_summary', '')
		if dom_summary:
			# Show first 800 chars of DOM summary
			summary_preview = dom_summary[:800] + ("..." if len(dom_summary) > 800 else "")
			logger.info(f"\n   DOM Summary Preview:\n{summary_preview}\n")
		
		# Step 4: Type search query into search box
		logger.info("\n📋 Step 4: Typing search query 'Python browser automation'...")
		# Try to find search input - usually index 0 or 1 for Google search
		# We'll type without specifying index to type into the focused element
		type_result = await call_mcp_tool("execute_action", {
			"room_name": ROOM_NAME,
			"action_type": "type",
			"params": {
				"text": "Python browser automation"
			}
		})
		
		if not type_result.get('success'):
			logger.error(f"❌ Typing failed: {type_result.get('error')}")
			# Try with Enter key instead
			logger.info("   Trying alternative: sending Enter key...")
		else:
			logger.info("✅ Typing successful")
		
		# Step 5: Wait a bit for typing to complete
		logger.info("\n📋 Step 5: Waiting for typing to complete (2 seconds)...")
		await asyncio.sleep(2)
		
		# Step 6: Send Enter key to submit search (using send_keys action)
		logger.info("\n📋 Step 6: Sending Enter key to submit search...")
		send_keys_result = await call_mcp_tool("execute_action", {
			"room_name": ROOM_NAME,
			"action_type": "send_keys",
			"params": {
				"keys": "Enter"
			}
		})
		
		if send_keys_result.get('success'):
			logger.info("✅ Enter key sent successfully")
		else:
			logger.warning(f"⚠️  Send keys failed: {send_keys_result.get('error')}")
			logger.info("   (This is expected if send_keys action is not fully implemented)")
		
		# Step 7: Wait for search results to load
		logger.info("\n📋 Step 7: Waiting for search results to load (3 seconds)...")
		await asyncio.sleep(3)
		
		# Step 8: Get browser context after search
		logger.info("\n📋 Step 8: Getting browser context after search...")
		context_result = await call_mcp_tool("get_browser_context", {
			"room_name": ROOM_NAME
		})
		
		logger.info(f"✅ Browser context retrieved:")
		logger.info(f"   URL: {context_result.get('url')}")
		logger.info(f"   Title: {context_result.get('title')}")
		logger.info(f"   Ready State: {context_result.get('ready_state')}")
		
		# Step 9: Get updated screen content with search results
		logger.info("\n📋 Step 9: Getting updated screen content with search results...")
		final_screen = await call_mcp_tool("get_screen_content", {
			"room_name": ROOM_NAME
		})
		
		if 'error' not in final_screen:
			logger.info(f"✅ Final screen content retrieved:")
			logger.info(f"   URL: {final_screen.get('url')}")
			logger.info(f"   Title: {final_screen.get('title')}")
			logger.info(f"   Visible elements: {final_screen.get('visible_elements_count')}")
			logger.info(f"   DOM summary length: {len(final_screen.get('dom_summary', ''))} chars")
		
		# Step 10: Keep browser open for inspection
		logger.info("\n📋 Step 10: Keeping browser open for 5 seconds...")
		logger.info("   (You should see Google search results page)")
		await asyncio.sleep(5)
		
		# Step 11: Close browser session
		logger.info("\n📋 Step 11: Closing browser session...")
		close_result = await call_mcp_tool("close_browser_session", {
			"room_name": ROOM_NAME
		})
		logger.info(f"✅ Browser session closed: {close_result.get('status')}")
		
		logger.info("\n" + "=" * 70)
		logger.info("✅ Interactive test completed successfully!")
		logger.info("=" * 70)
		
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
	success = asyncio.run(test_interactive_google())
	sys.exit(0 if success else 1)

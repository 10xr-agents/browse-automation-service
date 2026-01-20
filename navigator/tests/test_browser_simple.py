"""
Simple test script to verify MVP browser automation without LiveKit
Tests browser opening and navigation to google.com
"""
import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from browser_use import BrowserSession
from browser_use.browser.profile import BrowserProfile
from navigator.action.dispatcher import ActionDispatcher

# Configure logging
logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_browser_google_simple():
	"""Test browser automation by opening google.com without LiveKit."""
	logger.info("=" * 70)
	logger.info("🧪 Testing MVP Browser Automation - Simple Test (No LiveKit)")
	logger.info("=" * 70)

	browser_session = None
	try:
		# Step 1: Create browser session
		logger.info("\n📋 Step 1: Creating browser session...")
		browser_profile = BrowserProfile(
			headless=False,  # Show browser window
			viewport={'width': 1920, 'height': 1080}
		)
		browser_session = BrowserSession(browser_profile=browser_profile)
		await browser_session.start()
		logger.info("✅ Browser session created and started")

		# Step 2: Create action dispatcher
		logger.info("\n📋 Step 2: Creating action dispatcher...")
		action_dispatcher = ActionDispatcher(browser_session)
		logger.info("✅ Action dispatcher created")

		# Step 3: Navigate to google.com
		logger.info("\n📋 Step 3: Navigating to google.com...")
		from navigator.action.command import NavigateActionCommand

		navigate_action = NavigateActionCommand(
			params={"url": "https://www.google.com", "new_tab": False}
		)
		result = await action_dispatcher.execute_action(navigate_action)

		if result.success:
			logger.info("✅ Navigation to google.com successful")
		else:
			logger.error(f"❌ Navigation failed: {result.error}")
			return False

		# Step 4: Wait for page to load
		logger.info("\n📋 Step 4: Waiting for page to load (3 seconds)...")
		await asyncio.sleep(3)

		# Step 5: Get browser context to verify navigation
		logger.info("\n📋 Step 5: Getting browser context...")
		context = await action_dispatcher.get_browser_context()

		logger.info("✅ Browser context retrieved:")
		logger.info(f"   URL: {context.url}")
		logger.info(f"   Title: {context.title}")
		logger.info(f"   Ready State: {context.ready_state}")
		logger.info(f"   Viewport: {context.viewport_width}x{context.viewport_height}")
		logger.info(f"   Scroll: ({context.scroll_x}, {context.scroll_y})")
		logger.info(f"   Cursor: ({context.cursor_x}, {context.cursor_y})")

		# Verify we're on google.com
		if 'google.com' in context.url.lower():
			logger.info("✅ Successfully navigated to Google.com!")
		else:
			logger.warning(f"⚠️  Expected google.com but got: {context.url}")

		# Step 6: Get screen content
		logger.info("\n📋 Step 6: Getting screen content...")
		screen_content = await action_dispatcher.get_screen_content()

		logger.info("✅ Screen content retrieved:")
		logger.info(f"   Visible elements: {screen_content.visible_elements_count}")
		logger.info(f"   DOM summary length: {len(screen_content.dom_summary)} characters")

		if screen_content.dom_summary:
			# Show first 500 chars of DOM summary
			summary_preview = screen_content.dom_summary[:500] + ("..." if len(screen_content.dom_summary) > 500 else "")
			logger.info(f"   DOM summary preview:\n{summary_preview}")

		# Step 7: Wait a bit to see the browser
		logger.info("\n📋 Step 7: Keeping browser open for 5 seconds...")
		logger.info("   (You should see the browser window with Google.com)")
		await asyncio.sleep(5)

		# Step 8: Close browser
		logger.info("\n📋 Step 8: Closing browser session...")
		await browser_session.kill()
		logger.info("✅ Browser session closed")

		logger.info("\n" + "=" * 70)
		logger.info("✅ Test completed successfully!")
		logger.info("=" * 70)

		return True

	except Exception as e:
		logger.error(f"\n❌ Test failed with error: {e}")
		logger.exception("Full traceback:")

		# Try to close browser on error
		if browser_session:
			try:
				logger.info("\n🔄 Attempting to close browser session after error...")
				await browser_session.kill()
			except Exception as close_error:
				logger.error(f"   Failed to close session: {close_error}")

		return False


if __name__ == "__main__":
	success = asyncio.run(test_browser_google_simple())
	sys.exit(0 if success else 1)

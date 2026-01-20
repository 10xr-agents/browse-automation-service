"""
MCP Server for Browser Automation Service MVP

This server exposes Browser Automation Service capabilities as MCP tools,
allowing Voice Agent Service to connect as an MCP client and execute actions.

Usage:
    python -m mvp.mcp_server

Or as an MCP server in Claude Desktop or other MCP clients:
    {
        "mcpServers": {
            "browser-automation": {
                "command": "python",
                "args": ["-m", "mvp.mcp_server"],
                "env": {}
            }
        }
    }
"""

import asyncio
import logging
import os
import sys
from typing import Any

from dotenv import load_dotenv

try:
	import mcp.server.stdio
	import mcp.types as types
	from mcp.server import Server
	from mcp.server.models import InitializationOptions

	MCP_AVAILABLE = True
except ImportError:
	MCP_AVAILABLE = False
	logging.error('MCP SDK not installed. Install with: pip install mcp')
	sys.exit(1)

# Load environment variables from .env.local first, then .env
# .env.local takes precedence (for local development overrides)
load_dotenv(dotenv_path='.env.local', override=False)  # Load .env.local first
load_dotenv(override=True)  # Then load .env (or system env) with override

from navigator.server.mcp_browser_tools import get_browser_tools, register_browser_tool_handlers
from navigator.server.mcp_knowledge_tools import get_knowledge_tools, register_knowledge_tool_handlers
from navigator.server.websocket import get_event_broadcaster
from navigator.session.manager import BrowserSessionManager

# Configure logging for MCP mode
logging.basicConfig(
	stream=sys.stderr,
	level=logging.WARNING,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
	force=True,
)
logger = logging.getLogger(__name__)


class BrowserAutomationMCPServer:
	"""MCP Server exposing Browser Automation Service capabilities."""

	def __init__(self, session_manager: BrowserSessionManager | None = None):
		self.server = Server('browser-automation-service')
		# Initialize session manager with event broadcaster
		if session_manager is None:
			event_broadcaster = get_event_broadcaster()
			self.session_manager = BrowserSessionManager(event_broadcaster=event_broadcaster)
		else:
			self.session_manager = session_manager
		self._setup_handlers()

	def _setup_handlers(self):
		"""Setup MCP server handlers."""

		@self.server.list_tools()
		async def handle_list_tools() -> list[types.Tool]:
			"""List all available browser automation tools."""
			# Combine browser and knowledge tools
			all_tools = get_browser_tools() + get_knowledge_tools()
			return all_tools

		@self.server.call_tool()
		async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
			"""Handle tool calls."""
			import json
			if arguments is None:
				arguments = {}

			# Get all tool handlers
			browser_handlers = register_browser_tool_handlers(self.server, self.session_manager)
			knowledge_handlers = register_knowledge_tool_handlers(self.server, self)

			# Combine handlers
			all_handlers = {**browser_handlers, **knowledge_handlers}

			# Route to appropriate handler
			if name not in all_handlers:
				raise ValueError(f'Unknown tool: {name}')

			handler = all_handlers[name]
			result = await handler(arguments)

			# Convert result to MCP TextContent format
			if isinstance(result, dict):
				result_json = json.dumps(result, indent=2)
			else:
				result_json = str(result)

			return [types.TextContent(type='text', text=result_json)]

	async def run(self):
		"""Run the MCP server."""
		import json
		async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
			await self.server.run(
				read_stream,
				write_stream,
				InitializationOptions(
					server_name='browser-automation-service',
					server_version='1.0.0',
					capabilities=self.server.get_capabilities(
						experimental_capabilities={},
					),
				),
			)


async def main():
	"""Main entry point for MCP server."""
	server = BrowserAutomationMCPServer()
	await server.run()


if __name__ == '__main__':
	asyncio.run(main())

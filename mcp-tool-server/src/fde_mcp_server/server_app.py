"""Builds the mcp.server.Server instance and wires request handlers."""

from __future__ import annotations

import mcp.types as types
from mcp.server import Server

from . import tools


def build_server() -> Server:
    server = Server(name="fde-assignment-server", version="0.1.0")

    # list_tools has no validation-error subtlety, so the decorator is fine here.
    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return await tools.list_tools()

    # call_tool is registered directly (bypassing @server.call_tool()) so that
    # McpError raised for invalid input propagates as a real JSON-RPC error
    # instead of being downgraded to a CallToolResult(isError=True). See the
    # module docstring in tools.py for why.
    server.request_handlers[types.CallToolRequest] = tools.call_tool

    return server

"""A minimal stand-in for a real downstream MCP server.

NOT part of the mcp_gateway package -- this plays the role of an external
system the gateway has no control over. It's deliberately naive: it has NO
concept of authorization at all, and will happily run admin_reset_key for
anyone who asks it directly. That's the whole point -- the gateway is what
enforces policy in front of an unmodified downstream server, and this file
proves it by being exactly that kind of unprotected downstream server.

Every response carries a "served_by" marker -- not real JSON-RPC shape,
just a test-only tag so a curl through the gateway can prove the body
genuinely came from here, not from something the gateway made up itself.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO, format="%(asctime)s DOWNSTREAM-MOCK: %(message)s")
logger = logging.getLogger("downstream-mock")

app = FastAPI(title="Downstream MCP Server (mock)")

TOOLS = [
    {"name": "get_data", "description": "Fetch non-sensitive data."},
    {"name": "admin_reset_key", "description": "Reset an API key. Sensitive."},
]

_CANNED_RESULTS = {
    "get_data": {"rows": [{"id": 1, "value": "sample-data"}]},
    "admin_reset_key": {"new_key_id": "key-000123", "rotated": True},
}


@app.post("/rpc")
async def rpc(request: Request) -> dict:
    body = await request.json()
    method = body.get("method")
    request_id = body.get("id")
    logger.info("received method=%r params=%r", method, body.get("params"))

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": TOOLS},
            "served_by": "downstream-mock",
        }

    if method == "tools/call":
        name = (body.get("params") or {}).get("name")
        if name in _CANNED_RESULTS:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": _CANNED_RESULTS[name],
                "served_by": "downstream-mock",
            }
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Unknown tool: {name!r}"},
            "served_by": "downstream-mock",
        }

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method!r}"},
        "served_by": "downstream-mock",
    }

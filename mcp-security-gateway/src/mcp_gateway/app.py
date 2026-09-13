"""The gateway's FastAPI app: a single POST /rpc route.

Every response -- success or error -- is HTTP 200; JSON-RPC errors live
inside the body's "error" object, not the HTTP status, so a client always
deserializes the same way regardless of outcome. An unrecognized method is
answered locally (-32601), never forwarded -- the gateway has no policy
for methods outside its known contract, so it doesn't guess.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from pydantic import ValidationError

from .auth import get_role
from .errors import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    UNAUTHORIZED_TOOL_CALL,
    jsonrpc_error,
)
from .forwarder import forward
from .policy import is_authorized
from .rpc import RpcRequest

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # One shared client for the app's lifetime, instead of opening a new
    # connection pool to the downstream server on every single request.
    app.state.http_client = httpx.AsyncClient()
    yield
    await app.state.http_client.aclose()


app = FastAPI(title="MCP Gateway", lifespan=lifespan)


@app.post("/rpc")
async def rpc(request: Request) -> dict:
    try:
        raw = await request.json()
    except json.JSONDecodeError:
        return jsonrpc_error(None, PARSE_ERROR, "Parse error: body is not valid JSON")

    try:
        rpc_request = RpcRequest.model_validate(raw)
    except ValidationError as exc:
        request_id = raw.get("id") if isinstance(raw, dict) else None
        return jsonrpc_error(request_id, INVALID_REQUEST, "Invalid Request", data=exc.errors())

    role = get_role(request)
    logger.info(
        "role=%s method=%s tool=%s", role, rpc_request.method, rpc_request.tool_name
    )

    if rpc_request.method == "tools/list":
        return await forward(request.app.state.http_client, raw)

    if rpc_request.method == "tools/call":
        if rpc_request.tool_name is None:
            return jsonrpc_error(
                rpc_request.id,
                INVALID_PARAMS,
                "Invalid params",
                data={"missing": "params.name"},
            )
        if not is_authorized(role, rpc_request.tool_name):
            logger.warning(
                "denied role=%s tool=%s", role, rpc_request.tool_name
            )
            return jsonrpc_error(
                rpc_request.id, UNAUTHORIZED_TOOL_CALL, "Unauthorized Tool Call"
            )
        return await forward(request.app.state.http_client, raw)

    return jsonrpc_error(rpc_request.id, METHOD_NOT_FOUND, f"Method not found: {rpc_request.method!r}")

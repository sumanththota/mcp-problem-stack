"""Tool definitions and the call_tool dispatch handler.

Error handling has two distinct tiers, matched to the MCP spec's intent:

1. Protocol-level errors (raised as McpError -> serialized as a genuine
   JSON-RPC error object with a standard code): the request itself is
   malformed -- unknown tool name, or arguments that fail our strict
   Pydantic schema. The client made an invalid *call*.
2. Tool-result errors (CallToolResult(isError=True)): the call was valid
   but the underlying business operation could not complete (unknown
   customer, suspended account). The client made a valid call that failed
   for a domain reason -- this is data for the model/caller to react to,
   not a protocol fault.

IMPORTANT: mcp.server.Server's `@server.call_tool()` decorator wraps the
handler in a blanket `except Exception -> isError result`, which would
swallow McpError before it ever reaches the protocol layer and silently
downgrade every validation failure to a tier-2 error. To get real,
spec-correct JSON-RPC error responses for tier 1, this module registers
its handler directly on `server.request_handlers[types.CallToolRequest]`
instead of using that decorator. See wiring in server_app.py.
"""

from __future__ import annotations

import logging

import mcp.types as types
from mcp.shared.exceptions import McpError
from pydantic import BaseModel, ValidationError

from . import store
from .models import GetCustomerRecordInput, TriggerRefundInput

logger = logging.getLogger("fde_mcp_server")

TOOLS: list[types.Tool] = [
    types.Tool(
        name="get_customer_record",
        description="Look up a customer record by customer_id (format CUST-XXXXX).",
        inputSchema=GetCustomerRecordInput.model_json_schema(),
        annotations=types.ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    ),
    types.Tool(
        name="trigger_refund",
        description=(
            "Trigger a refund for a customer. Requires a positive amount and a "
            "reason of at least 10 characters explaining why the refund is issued."
        ),
        inputSchema=TriggerRefundInput.model_json_schema(),
        annotations=types.ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        ),
    ),
]

_MODELS_BY_TOOL: dict[str, type[BaseModel]] = {
    "get_customer_record": GetCustomerRecordInput,
    "trigger_refund": TriggerRefundInput,
}


def _validation_error_payload(exc: ValidationError) -> dict:
    """Turn a Pydantic ValidationError into JSON-safe, field-level detail."""
    return {
        "validation_errors": [
            {
                "field": ".".join(str(p) for p in err["loc"]) or "<root>",
                "issue": err["msg"],
                "input": repr(err.get("input")),
            }
            for err in exc.errors()
        ]
    }


def _error_result(message: str) -> types.ServerResult:
    return types.ServerResult(
        types.CallToolResult(
            content=[types.TextContent(type="text", text=message)],
            isError=True,
        )
    )


def _ok_result(text: str, structured: dict) -> types.ServerResult:
    return types.ServerResult(
        types.CallToolResult(
            content=[types.TextContent(type="text", text=text)],
            structuredContent=structured,
            isError=False,
        )
    )


async def list_tools() -> list[types.Tool]:
    return TOOLS


async def call_tool(request: types.CallToolRequest) -> types.ServerResult:
    name = request.params.name
    raw_arguments = request.params.arguments or {}

    model = _MODELS_BY_TOOL.get(name)
    if model is None:
        logger.warning("Rejected call to unknown tool: %r", name)
        raise McpError(
            types.ErrorData(
                code=types.INVALID_PARAMS,
                message=f"Unknown tool: {name!r}",
            )
        )

    try:
        args = model.model_validate(raw_arguments)
    except ValidationError as exc:
        logger.info("Rejected invalid arguments for %s: %s", name, exc)
        raise McpError(
            types.ErrorData(
                code=types.INVALID_PARAMS,
                message=f"Invalid arguments for tool '{name}'",
                data=_validation_error_payload(exc),
            )
        ) from exc

    logger.info("Executing tool %s", name)

    if isinstance(args, GetCustomerRecordInput):
        return _get_customer_record(args)
    assert isinstance(args, TriggerRefundInput)
    return _trigger_refund(args)


def _get_customer_record(args: GetCustomerRecordInput) -> types.ServerResult:
    record = store.get_customer(args.customer_id)
    if record is None:
        return _error_result(f"No customer found for {args.customer_id}.")
    data = record.to_dict()
    return _ok_result(f"Customer {record.customer_id}: {record.name} ({record.status}).", data)


def _trigger_refund(args: TriggerRefundInput) -> types.ServerResult:
    record = store.get_customer(args.customer_id)
    if record is None:
        return _error_result(f"No customer found for {args.customer_id}; refund not issued.")
    if record.status != "active":
        return _error_result(
            f"Customer {args.customer_id} is '{record.status}'; refunds require an active account."
        )

    refund = store.record_refund(args.customer_id, args.amount, args.reason)
    return _ok_result(
        f"Issued refund {refund.refund_id} of ${refund.amount:.2f} to {args.customer_id}.",
        refund.to_dict(),
    )

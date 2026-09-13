"""The gateway's FastAPI app: a single streaming chat-completions route.

Relays OpenRouter's SSE response back to the caller, redacting PII as it
goes via the Holdback Buffer (ADR-0001/0002). finish_reason is held back
the same way buffered text is (ADR-0004) -- the upstream's own stop
signal is never relayed as-is; this emits its own, only after its final
flush completes.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from .buffer import HoldbackBuffer
from .config import MissingConfigError, api_key, log_level, model
from .models import ChatCompletionRequest
from .upstream import stream_chat_completion

# One JSON object per line, nothing else -- so a log line is directly
# `jq`-able instead of needing to be stripped of a "name: " prefix first.
# Configured here (not just in main.py) so it also applies when uvicorn
# imports this module directly, as the test suite does.
#
# Root stays at INFO regardless of LOG_LEVEL -- only this gateway's own
# logger is raised to DEBUG, so turning on chunk-level tracing doesn't
# also drag in httpx/httpcore/uvicorn's own internal debug noise.
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("llm_gateway")
logger.setLevel(getattr(logging, log_level(), logging.INFO))


def _chunk(envelope: dict, content: str = "", finish_reason: str | None = None) -> bytes:
    # id/object/created/model are captured once from the first real
    # upstream chunk and repeated identically on every chunk this gateway
    # itself synthesizes, mirroring how a real provider's envelope works.
    payload = {
        **envelope,
        "choices": [
            {
                "index": 0,
                "delta": {"content": content} if content else {},
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(payload)}\n\n".encode()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # One shared client for the app's lifetime, instead of opening a new
    # connection pool to OpenRouter on every request.
    app.state.http_client = httpx.AsyncClient()
    yield
    await app.state.http_client.aclose()


app = FastAPI(title="LLM Gateway", lifespan=lifespan)


@app.post("/v1/chat/completions")
async def chat_completions(
    payload: ChatCompletionRequest, request: Request
) -> StreamingResponse:
    try:
        # Checked eagerly, before the stream opens, so a missing key/model
        # surfaces as a normal HTTP error instead of failing mid-response.
        api_key()
        model()
    except MissingConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    client: httpx.AsyncClient = request.app.state.http_client
    messages = [message.model_dump() for message in payload.messages]

    request_id = uuid.uuid4().hex[:12]
    started = time.monotonic()
    logger.info(json.dumps({"event": "request_start", "request_id": request_id}))

    async def event_stream() -> AsyncIterator[bytes]:
        buffer = HoldbackBuffer()  # fresh per request -- never shared, unlike client
        envelope: dict | None = None
        pending_finish_reason: str | None = None
        redaction_counts: dict[str, int] = {}

        async for line in stream_chat_completion(client, messages, request_id):
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            parsed = json.loads(line.removeprefix("data: "))
            if envelope is None:
                envelope = {k: parsed[k] for k in ("id", "object", "created", "model")}

            choice = parsed["choices"][0]
            content = choice["delta"].get("content", "")
            finish_reason = choice.get("finish_reason")

            if finish_reason is not None:
                pending_finish_reason = finish_reason  # ADR-0004: hold, don't relay yet
            if content:
                safe = buffer.append(content, redaction_counts)
                if logger.isEnabledFor(logging.DEBUG):
                    # Lengths only -- never the delta or buffer text itself.
                    logger.debug(json.dumps({
                        "event": "delta",
                        "request_id": request_id,
                        "chars_in": len(content),
                        "chars_flushed": len(safe),
                        "chars_held": buffer.held_length,
                    }))
                if safe:
                    yield _chunk(envelope, content=safe)

        remaining = buffer.flush(redaction_counts)
        if remaining:
            yield _chunk(envelope, content=remaining)
        yield _chunk(envelope, finish_reason=pending_finish_reason or "stop")
        yield b"data: [DONE]\n\n"

        logger.info(json.dumps({
            "event": "request_end",
            "request_id": request_id,
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
            "redactions": redaction_counts,
        }))

    return StreamingResponse(event_stream(), media_type="text/event-stream")

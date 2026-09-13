"""Stand-in for OpenRouter's streaming chat-completion endpoint.

NOT part of the llm_gateway package -- this plays the role of the upstream
LLM provider. A real provider's tokenizer/serving layer decides its own
chunk boundaries, so it can't be made to split a PII pattern at an exact,
chosen character on demand or repeatably (see docs/adr/0003).

The gateway is what actually calls /v1/chat/completions, using its own
fixed payload shape (model/messages/stream) -- there's no field on that
call for a test to smuggle a desired delta split through. So the deltas
this mock emits are configured out of band: a test first calls
POST /configure {"deltas": [...]}, then triggers the gateway's real
forwarded request, which replays whatever was last configured, regardless
of what its own body contains.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s OPENROUTER-MOCK: %(message)s")
logger = logging.getLogger("openrouter-mock")

app = FastAPI(title="OpenRouter Chat Completions (mock)")

_configured_deltas: list[str] = []


class ConfigureRequest(BaseModel):
    deltas: list[str]


class ChatCompletionRequest(BaseModel):
    """Loosely mirrors the gateway's real outgoing payload. Only `model` is
    actually used (for the response envelope) -- what gets emitted is
    controlled by /configure, not by this body.
    """

    model: str = "mock-model"
    messages: list[dict] = []
    stream: bool = True


def _chunk(completion_id: str, created: int, model: str, delta: dict, finish_reason: str | None) -> str:
    # id/model/created are repeated identically on every chunk, mirroring
    # a real OpenAI-compatible provider's envelope.
    payload = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(payload)}\n\n"


async def _stream(deltas: list[str], model: str) -> AsyncIterator[str]:
    completion_id = f"chatcmpl-mock-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    for fragment in deltas:
        yield _chunk(completion_id, created, model, {"content": fragment}, None)
    yield _chunk(completion_id, created, model, {}, "stop")
    yield "data: [DONE]\n\n"


@app.post("/configure")
async def configure(body: ConfigureRequest) -> dict:
    global _configured_deltas
    _configured_deltas = body.deltas
    logger.info("configured deltas=%r", body.deltas)
    return {"ok": True}


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest) -> StreamingResponse:
    logger.info("chat_completions called, replaying configured deltas=%r", _configured_deltas)
    return StreamingResponse(_stream(_configured_deltas, request.model), media_type="text/event-stream")

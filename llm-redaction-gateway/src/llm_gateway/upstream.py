"""Relays a chat-completion request to OpenRouter's streaming endpoint,
line by line, completely unmodified. No redaction or buffering here --
that's layered on separately, on top of this wire path.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator

import httpx

from . import config

logger = logging.getLogger("llm_gateway.upstream")


async def stream_chat_completion(
    client: httpx.AsyncClient, messages: list[dict], request_id: str
) -> AsyncIterator[str]:
    # The model slug is the gateway's own config, not the caller's --
    # the caller only speaks the OpenAI-compatible request shape.
    # stream is always requested upstream: this is the streaming wire path.
    payload = {"model": config.model(), "messages": messages, "stream": True}
    headers = {"Authorization": f"Bearer {config.api_key()}"}
    url = config.openrouter_url()

    started = time.monotonic()
    ttfb_ms: float | None = None
    try:
        # .stream() (not .post()) yields the response as soon as headers
        # arrive, instead of waiting for the whole body before returning --
        # that arrival is exactly what time-to-first-byte measures below.
        async with client.stream("POST", url, json=payload, headers=headers) as response:
            ttfb_ms = round((time.monotonic() - started) * 1000, 1)
            response.raise_for_status()
            async for line in response.aiter_lines():
                yield line
    except httpx.HTTPError as exc:
        logger.info(json.dumps({
            "event": "upstream_call",
            "request_id": request_id,
            "url": url,
            "status_code": getattr(getattr(exc, "response", None), "status_code", None),
            "ttfb_ms": ttfb_ms,
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
            "ok": False,
            "error": type(exc).__name__,
        }))
        raise
    else:
        logger.info(json.dumps({
            "event": "upstream_call",
            "request_id": request_id,
            "url": url,
            "status_code": response.status_code,
            "ttfb_ms": ttfb_ms,
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
            "ok": True,
        }))

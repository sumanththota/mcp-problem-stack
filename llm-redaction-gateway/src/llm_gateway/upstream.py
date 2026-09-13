"""Relays a chat-completion request to OpenRouter's streaming endpoint,
line by line, completely unmodified. No redaction or buffering here --
that's layered on separately, on top of this wire path.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from . import config


async def stream_chat_completion(
    client: httpx.AsyncClient, messages: list[dict]
) -> AsyncIterator[str]:
    # The model slug is the gateway's own config, not the caller's --
    # the caller only speaks the OpenAI-compatible request shape.
    # stream is always requested upstream: this is the streaming wire path.
    payload = {"model": config.model(), "messages": messages, "stream": True}
    headers = {"Authorization": f"Bearer {config.api_key()}"}

    # .stream() (not .post()) yields the response as soon as headers
    # arrive, instead of waiting for the whole body before returning.
    async with client.stream(
        "POST", config.openrouter_url(), json=payload, headers=headers
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            yield line

"""The router's FastAPI app: a single POST /v1/completions route.

Ticket 8 (standardized error sanitization): every gateway-constructed
failure -- rate limit rejection, both providers down, or anything
unexpected -- goes through errors.error_response() / the global exception
handler below, so the caller always sees the same JSON shape regardless of
what actually failed. A single request_id is minted per request up front
(not only once a reservation exists) so even a rejected admission's error
response can carry one.

Ticket 7 (fallback to secondary): router.call_with_fallback() tries the
primary first and falls back to the secondary on a 429 or a timeout.

Ticket 6 (primary call with timeout): the primary call is bounded by the
3000ms timeout from R2. Ticket 5 (TTL backstop sweep): a background task
runs independently of any request, force-releasing reservations that were
never settled. Ticket 4 (settle on completion): once a response is known,
the admitted reservation is corrected from its worst-case reserve down to
actual usage.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request

from . import db, errors, limiter, router, ttl_sweep

logger = logging.getLogger(__name__)


def estimate_prompt_tokens(prompt: str) -> int:
    # Placeholder for a real tokenizer (e.g. tiktoken) -- word count as a
    # stand-in, matching the same heuristic mock/primary_mock.py uses to
    # report its own usage.
    return len(str(prompt).split())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.http_client = httpx.AsyncClient()
    app.state.db = db.connect()
    sweep_task = asyncio.create_task(ttl_sweep.run_sweep_loop(app.state.db))
    yield
    sweep_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await sweep_task
    await app.state.http_client.aclose()
    app.state.db.close()


app = FastAPI(title="Ratelimit Fallback Router", lifespan=lifespan)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    logger.exception("unhandled error for request_id=%s", request_id)
    return errors.error_response(
        errors.INTERNAL_ERROR, "An internal error occurred.", request_id
    )


@app.post("/v1/completions")
async def completions(request: Request):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    body = await request.json()
    tenant_id = body.get("tenant_id")
    prompt = body.get("prompt", "")
    max_tokens = body.get("max_tokens", 0)

    prompt_tokens = estimate_prompt_tokens(prompt)
    allowed, _ = limiter.admit(
        request.app.state.db,
        tenant_id,
        prompt_tokens,
        max_tokens,
        request_id=request_id,
    )

    if not allowed:
        return errors.error_response(
            errors.RATE_LIMIT_EXCEEDED,
            "Token budget exceeded for this tenant.",
            request_id,
        )

    try:
        response, served_by = await router.call_with_fallback(
            request.app.state.http_client, body
        )
    except router.BothProvidersFailed:
        logger.warning(
            "both providers failed for request_id=%s; reservation stays pending for the TTL sweep",
            request_id,
        )
        return errors.error_response(
            errors.ALL_PROVIDERS_UNAVAILABLE,
            "No model provider could complete this request.",
            request_id,
        )

    if served_by == "secondary":
        logger.info("request_id=%s served by secondary (primary failed)", request_id)

    response_data = response.json()

    actual_tokens = response_data.get("usage", {}).get("total_tokens")
    if actual_tokens is not None:
        applied = limiter.settle(request.app.state.db, request_id, actual_tokens)
        if not applied:
            logger.warning(
                "late settle dropped: request_id=%s already expired by the TTL sweep",
                request_id,
            )

    return response_data

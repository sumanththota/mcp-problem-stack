"""A hardcoded stand-in for a real secondary (fallback) model provider.

NOT part of the ratelimit_router package. Same shape as primary_mock.py --
delay_s and force_status, configurable via POST /configure -- so a test can
force "both providers fail" as easily as "primary fails, secondary works".
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s SECONDARY-MOCK: %(message)s")
logger = logging.getLogger("secondary-mock")

app = FastAPI(title="Secondary Model Provider (mock)")

_state = {"delay_s": 0.0, "force_status": None}


@app.post("/configure")
async def configure(request: Request) -> dict:
    body = await request.json()
    if "delay_s" in body:
        _state["delay_s"] = float(body["delay_s"])
    if "force_status" in body:
        _state["force_status"] = body["force_status"]
    logger.info("configured: %r", _state)
    return {"ok": True, **_state}


@app.post("/v1/completions")
async def completions(request: Request):
    body = await request.json()
    prompt = body.get("prompt", "")
    logger.info("received prompt=%r max_tokens=%r", prompt, body.get("max_tokens"))

    if _state["delay_s"] > 0:
        logger.info("delaying %ss before responding", _state["delay_s"])
        await asyncio.sleep(_state["delay_s"])

    if _state["force_status"] is not None:
        logger.info("forcing status %s", _state["force_status"])
        return JSONResponse(
            status_code=_state["force_status"],
            content={"error": {"code": "FORCED", "message": "forced by /configure"}},
        )

    prompt_tokens = len(str(prompt).split())
    completion_tokens = 12
    return {
        "id": "cmpl-mock-0002",
        "model": "secondary-mock",
        "choices": [
            {"text": f"Mock completion for: {prompt!r}", "finish_reason": "stop"}
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        "served_by": "secondary-mock",
    }

"""Ticket 8 (standardized error sanitization), proven against the primary
seam declared in SPEC.md's Testing Decisions: the gateway's own HTTP
endpoint, exercised end-to-end, with the model providers replaced by a
mocked httpx transport.

Every gateway-constructed failure mode -- over budget, both providers
down, and an unexpected internal error -- must come back as the same
{"error": {"code", "message", "request_id"}} shape, and an unexpected
error must never leak its raw exception text to the caller.

lifespan() isn't run here: app.state.db/http_client are set directly per
test instead, so each test gets an isolated in-memory ledger rather than
sharing the real ledger.db file, and no background sweep task needs
tearing down.
"""

from __future__ import annotations

import asyncio
import sqlite3

import httpx
import pytest

from ratelimit_router import app as app_module
from ratelimit_router import db, router


@pytest.fixture
def fastapi_app():
    conn = sqlite3.connect(":memory:")
    conn.execute(db.SCHEMA)
    conn.execute(db.INDEX)
    conn.commit()
    app_module.app.state.db = conn
    yield app_module.app
    conn.close()


def _wire_mock_provider(handler) -> None:
    app_module.app.state.http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )


async def _post(fastapi_app, payload: dict) -> httpx.Response:
    # raise_app_exceptions=False: an unhandled exception still gets sent to
    # the caller as our sanitized response (Starlette's ServerErrorMiddleware
    # re-raises after sending it, for server-side logging -- a real ASGI
    # server swallows that at the protocol layer; ASGITransport needs telling
    # to do the same so the test can assert on the response it actually sent).
    transport = httpx.ASGITransport(app=fastapi_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/v1/completions", json=payload)


@pytest.mark.anyio
async def test_rate_limit_rejection_has_the_standard_error_shape(fastapi_app):
    async def handler(request):
        raise AssertionError("a rejected request must never reach a provider")

    _wire_mock_provider(handler)

    resp = await _post(
        fastapi_app, {"tenant_id": "acme", "prompt": "hi", "max_tokens": 60_000}
    )

    assert resp.status_code == 429
    error = resp.json()["error"]
    assert error["code"] == "RATE_LIMIT_EXCEEDED"
    assert error["request_id"]


@pytest.mark.anyio
async def test_both_providers_down_has_the_standard_error_shape(fastapi_app, monkeypatch):
    monkeypatch.setattr(router, "PRIMARY_TIMEOUT_S", 0.05)
    monkeypatch.setattr(router, "SECONDARY_TIMEOUT_S", 0.05)

    async def handler(request):
        await asyncio.sleep(10)

    _wire_mock_provider(handler)

    resp = await _post(
        fastapi_app, {"tenant_id": "globex", "prompt": "hi", "max_tokens": 100}
    )

    assert resp.status_code == 502
    error = resp.json()["error"]
    assert error["code"] == "ALL_PROVIDERS_UNAVAILABLE"
    assert error["request_id"]


@pytest.mark.anyio
async def test_unexpected_internal_error_is_sanitized(fastapi_app, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("raw internal detail that must never reach the caller")

    monkeypatch.setattr(app_module.limiter, "admit", boom)

    resp = await _post(
        fastapi_app, {"tenant_id": "acme", "prompt": "hi", "max_tokens": 10}
    )

    assert resp.status_code == 500
    error = resp.json()["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert error["request_id"]
    assert "boom" not in resp.text
    assert "RuntimeError" not in resp.text


@pytest.mark.anyio
async def test_admitted_request_gets_the_real_response_not_an_error_shape(fastapi_app):
    async def handler(request):
        return httpx.Response(
            200,
            json={
                "served_by": "primary-mock",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    _wire_mock_provider(handler)

    resp = await _post(
        fastapi_app, {"tenant_id": "acme", "prompt": "hi", "max_tokens": 10}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert "error" not in body
    assert body["served_by"] == "primary-mock"

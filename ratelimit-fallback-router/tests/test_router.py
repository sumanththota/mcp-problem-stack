"""T6/T7's fallback logic, proven for real -- but against an in-process
httpx.MockTransport instead of the real mock servers, so it's fast and
deterministic. No real ports, no real 3-second waits: timeout tests
monkeypatch router's timeout constants down to a few milliseconds first.
The actual timeout mechanism (asyncio.wait_for + cancellation) still runs
for real, just against a smaller number.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from ratelimit_router import router


def _response(status_code: int = 200, served_by: str = "mock") -> httpx.Response:
    return httpx.Response(
        status_code, json={"served_by": served_by, "usage": {"total_tokens": 14}}
    )


def _handler(*, primary=None, secondary=None):
    async def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == router.PRIMARY_URL:
            if primary == "hang":
                await asyncio.sleep(10)
            return primary if isinstance(primary, httpx.Response) else _response(
                served_by="primary-mock"
            )
        if url == router.SECONDARY_URL:
            if secondary == "hang":
                await asyncio.sleep(10)
            return secondary if isinstance(secondary, httpx.Response) else _response(
                served_by="secondary-mock"
            )
        raise AssertionError(f"unexpected URL: {url}")

    return handler


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.anyio
async def test_call_primary_returns_the_response_on_success():
    client = _client(_handler())
    response = await router.call_primary(client, {"prompt": "hi"})
    assert response.status_code == 200
    assert response.json()["served_by"] == "primary-mock"


@pytest.mark.anyio
async def test_call_primary_times_out_on_a_hanging_primary(monkeypatch):
    monkeypatch.setattr(router, "PRIMARY_TIMEOUT_S", 0.05)
    client = _client(_handler(primary="hang"))
    with pytest.raises(router.PrimaryTimeout):
        await router.call_primary(client, {"prompt": "hi"})


@pytest.mark.anyio
async def test_fallback_uses_primary_when_it_is_healthy():
    client = _client(_handler())
    response, served_by = await router.call_with_fallback(client, {"prompt": "hi"})
    assert served_by == "primary"
    assert response.json()["served_by"] == "primary-mock"


@pytest.mark.anyio
async def test_fallback_switches_to_secondary_on_a_429_from_primary():
    client = _client(_handler(primary=_response(429)))
    response, served_by = await router.call_with_fallback(client, {"prompt": "hi"})
    assert served_by == "secondary"
    assert response.json()["served_by"] == "secondary-mock"


@pytest.mark.anyio
async def test_fallback_switches_to_secondary_on_a_primary_timeout(monkeypatch):
    monkeypatch.setattr(router, "PRIMARY_TIMEOUT_S", 0.05)
    client = _client(_handler(primary="hang"))
    response, served_by = await router.call_with_fallback(client, {"prompt": "hi"})
    assert served_by == "secondary"
    assert response.json()["served_by"] == "secondary-mock"


@pytest.mark.anyio
async def test_fallback_raises_when_both_providers_fail(monkeypatch):
    monkeypatch.setattr(router, "PRIMARY_TIMEOUT_S", 0.05)
    monkeypatch.setattr(router, "SECONDARY_TIMEOUT_S", 0.05)
    client = _client(_handler(primary="hang", secondary="hang"))
    with pytest.raises(router.BothProvidersFailed):
        await router.call_with_fallback(client, {"prompt": "hi"})

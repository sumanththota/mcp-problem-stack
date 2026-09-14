"""Primary/secondary call orchestration -- timeout and fallback (R2).

Ticket 7: on a primary timeout or 429, falls back to the secondary. No
further retry if the secondary also fails -- see SPEC.md's Out of Scope.

The "late primary response" race from the design session turns out not to
need separate handling: asyncio.wait_for() cancels the underlying call on
timeout, so a timed-out primary call structurally can never produce a
result call_with_fallback() would see or act on. Verified empirically, not
just assumed -- see the T7 proof notes.
"""

from __future__ import annotations

import asyncio

import httpx

PRIMARY_URL = "http://127.0.0.1:8091/v1/completions"
SECONDARY_URL = "http://127.0.0.1:8092/v1/completions"
PRIMARY_TIMEOUT_S = 3.0  # fixed by R2
SECONDARY_TIMEOUT_S = 3.0  # provisional -- not yet confirmed


class PrimaryTimeout(Exception):
    """The primary provider didn't respond within PRIMARY_TIMEOUT_S."""


class SecondaryTimeout(Exception):
    """The secondary provider didn't respond within SECONDARY_TIMEOUT_S."""


class BothProvidersFailed(Exception):
    """Neither the primary nor the secondary produced a usable response."""


async def call_primary(client: httpx.AsyncClient, body: dict) -> httpx.Response:
    try:
        return await asyncio.wait_for(
            client.post(PRIMARY_URL, json=body), timeout=PRIMARY_TIMEOUT_S
        )
    except asyncio.TimeoutError as exc:
        raise PrimaryTimeout(
            f"primary did not respond within {PRIMARY_TIMEOUT_S}s"
        ) from exc


async def call_secondary(client: httpx.AsyncClient, body: dict) -> httpx.Response:
    try:
        return await asyncio.wait_for(
            client.post(SECONDARY_URL, json=body), timeout=SECONDARY_TIMEOUT_S
        )
    except asyncio.TimeoutError as exc:
        raise SecondaryTimeout(
            f"secondary did not respond within {SECONDARY_TIMEOUT_S}s"
        ) from exc


async def call_with_fallback(client: httpx.AsyncClient, body: dict) -> tuple[httpx.Response, str]:
    """Call the primary; fall back to the secondary on a 429 or a timeout.

    Returns (response, "primary" | "secondary"). Raises BothProvidersFailed
    if the secondary also times out.
    """
    try:
        response = await call_primary(client, body)
        if response.status_code != 429:
            return response, "primary"
    except PrimaryTimeout:
        pass  # fall through to secondary

    try:
        response = await call_secondary(client, body)
        return response, "secondary"
    except SecondaryTimeout as exc:
        raise BothProvidersFailed("primary and secondary both failed") from exc

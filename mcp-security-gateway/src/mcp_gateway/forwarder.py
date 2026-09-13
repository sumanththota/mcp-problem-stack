"""Forwards a JSON-RPC payload to the downstream server, verbatim.

Takes the original raw dict the client sent, not a re-serialized Pydantic
model -- the downstream server sees exactly what the gateway received,
nothing added, dropped, or reordered by a round trip through a model that
only exists to make the gateway's own routing decision.
"""

from __future__ import annotations

import httpx

DOWNSTREAM_URL = "http://127.0.0.1:8090/rpc"


async def forward(client: httpx.AsyncClient, payload: dict) -> dict:
    response = await client.post(DOWNSTREAM_URL, json=payload)
    return response.json()

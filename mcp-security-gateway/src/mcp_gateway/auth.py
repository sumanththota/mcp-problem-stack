"""Bearer token -> role extraction.

A hardcoded token->role map, deliberately not real auth (no JWT, no
signature check, no expiry) -- a stand-in so the gateway has *something*
to key an authorization decision on.
"""

from __future__ import annotations

from fastapi import Request

_TOKEN_TO_ROLE = {
    "admin-token": "admin",
    "viewer-token": "viewer",
}


def get_role(request: Request) -> str | None:
    """Return the caller's role, or None if missing/malformed/unrecognized."""
    header = request.headers.get("authorization")
    if header is None:
        return None

    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None

    return _TOKEN_TO_ROLE.get(token)

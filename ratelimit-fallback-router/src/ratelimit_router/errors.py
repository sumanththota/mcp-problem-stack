"""One shape for every error the gateway constructs itself.

Whatever actually failed -- the tenant over budget, both providers down, or
something unexpected inside the gateway -- the caller always gets back the
same JSON shape: a machine-readable code, a message safe to show the
caller, and the request id to quote back for support. Never a raw
exception, stack trace, or vendor-specific error object (SPEC.md's
Implementation Decisions, "Error handling").
"""

from __future__ import annotations

from fastapi.responses import JSONResponse

RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
ALL_PROVIDERS_UNAVAILABLE = "ALL_PROVIDERS_UNAVAILABLE"
INTERNAL_ERROR = "INTERNAL_ERROR"

_STATUS_BY_CODE = {
    RATE_LIMIT_EXCEEDED: 429,
    ALL_PROVIDERS_UNAVAILABLE: 502,
    INTERNAL_ERROR: 500,
}


def error_response(code: str, message: str, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=_STATUS_BY_CODE[code],
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
            }
        },
    )

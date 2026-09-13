"""The incoming JSON-RPC envelope.

Deliberately loose: the gateway only needs `method` and, for tools/call,
`params.name` to make its routing/auth decision -- it does not own the
shape of `params` beyond that, the downstream server does. `params` stays
a raw, unvalidated dict, and extra top-level fields are allowed through
rather than rejected, so an allowed request still forwards unmodified.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class RpcRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] | None = None

    @property
    def tool_name(self) -> str | None:
        """params.name, if present -- only meaningful for tools/call."""
        if self.params is None:
            return None
        name = self.params.get("name")
        return name if isinstance(name, str) else None

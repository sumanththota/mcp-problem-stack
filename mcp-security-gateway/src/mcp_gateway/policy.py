"""The authorization decision: is this role allowed to call this tool?

Pure function -- two plain values in, a bool out -- so it's testable and
reasoned about with no server, no request, no httpx involved.
"""

from __future__ import annotations

ADMIN_PREFIX = "admin_"


def is_authorized(role: str | None, tool_name: str | None) -> bool:
    if tool_name is not None and tool_name.startswith(ADMIN_PREFIX):
        return role == "admin"
    return True

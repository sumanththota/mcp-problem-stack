"""Logging setup for the MCP server.

Must be called before any other module does its own logging setup, and
before stdio_server() acquires stdout. stdio transport uses stdout as the
JSON-RPC wire; every non-protocol byte written there corrupts the stream
for the client. All diagnostic output goes to stderr, never stdout.
"""

from __future__ import annotations

import logging
import sys


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stderr,
        force=True,  # override any handler a dependency may have installed on import
    )
    return logging.getLogger("fde_mcp_server")

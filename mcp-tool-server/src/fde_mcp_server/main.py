"""Entrypoint: run the server over stdio.

configure_logging() runs first, before any code path could log to stdout.
stdio_server() then takes ownership of the real stdin/stdout as the JSON-RPC
transport for the lifetime of the process.
"""

from __future__ import annotations

import logging

import anyio
from mcp.server.stdio import stdio_server

from .logging_conf import configure_logging
from .server_app import build_server


async def _run() -> None:
    logger = configure_logging()
    server = build_server()
    logger.info("Starting fde-assignment-server over stdio")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    try:
        anyio.run(_run)
    except KeyboardInterrupt:
        logging.getLogger("fde_mcp_server").info("Interrupted, shutting down")


if __name__ == "__main__":
    main()

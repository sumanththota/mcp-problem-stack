`"""Entrypoint: run the gateway with uvicorn."""

from __future__ import annotations

import logging

import uvicorn


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    uvicorn.run("mcp_gateway.app:app", host="127.0.0.1", port=8080)


if __name__ == "__main__":
    main()

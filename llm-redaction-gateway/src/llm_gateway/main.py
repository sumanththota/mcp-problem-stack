"""Entrypoint: run the gateway with uvicorn."""

from __future__ import annotations

import logging
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

# Path-based, not cwd-relative -- so this finds task3/.env regardless of
# which directory `uv run llm-gateway` was invoked from.
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


def main() -> None:
    load_dotenv(_ENV_FILE)
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    uvicorn.run("llm_gateway.app:app", host="127.0.0.1", port=8080)


if __name__ == "__main__":
    main()

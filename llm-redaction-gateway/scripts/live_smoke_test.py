"""Manual, opt-in retry of Ticket #06's live-content leg: a real request to
the real OpenRouter endpoint (no mock), asking the model to echo text
containing PII, to confirm the gateway's redaction survives genuine wire
behavior end-to-end.

Not part of the pytest suite -- it costs a real API call and its output
depends on how faithfully the model echoes the prompt, so it's a secondary
smoke check (per SPEC.md's testing decisions), not a correctness assertion.
Run manually with:

    uv run python scripts/live_smoke_test.py
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

TASK3_DIR = Path(__file__).resolve().parent.parent
load_dotenv(TASK3_DIR / ".env")

API_KEY = os.environ["OPENROUTER_API_KEY"]
MODEL = os.environ["OPENROUTER_MODEL"]


def _wait_for_port(port: int, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"nothing listening on port {port} after {timeout}s")


def main() -> None:
    gateway_port = 8181
    env = {**os.environ, "OPENROUTER_API_KEY": API_KEY, "OPENROUTER_MODEL": MODEL}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "llm_gateway.app:app",
         "--host", "127.0.0.1", "--port", str(gateway_port)],
        cwd=TASK3_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_for_port(gateway_port, timeout=8.0)

        prompt = (
            "Repeat the following text back to me exactly, character for "
            "character, with no extra commentary, no quotes, and no "
            "markdown: My email is jane.doe@example.com and my card is "
            "4111 1111 1111 1111, thanks."
        )
        response = httpx.post(
            f"http://127.0.0.1:{gateway_port}/v1/chat/completions",
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
            },
            timeout=30.0,
        )
        print(f"HTTP status: {response.status_code}")
        if response.status_code != 200:
            print("Body:", response.text[:2000])
            return

        contents = []
        for line in response.text.splitlines():
            if not line.startswith("data: ") or "[DONE]" in line:
                continue
            payload = json.loads(line.removeprefix("data: "))
            delta = payload["choices"][0]["delta"].get("content")
            if delta:
                contents.append(delta)

        full_text = "".join(contents)
        print("--- Reassembled redacted output ---")
        print(full_text)
        print("--- Chunks ---")
        for c in contents:
            print(repr(c))

        leaked_email = "jane.doe@example.com" in full_text
        leaked_card = "4111 1111 1111 1111" in full_text
        redacted_present = "[REDACTED]" in full_text
        print(f"\nleaked_email={leaked_email} leaked_card={leaked_card} "
              f"redacted_marker_present={redacted_present}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        if proc.stdout:
            out = proc.stdout.read()
            if out.strip():
                print("--- gateway process log ---")
                print(out)


if __name__ == "__main__":
    main()

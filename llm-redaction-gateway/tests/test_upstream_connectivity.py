"""Connectivity tests: does the gateway actually reach what it's pointed
at, and does the Holdback Buffer redact correctly across a real
end-to-end round trip. Two separate concerns, tested two different ways:

- gateway <-> mock: real subprocesses, real HTTP (SPEC.md's primary seam).
  The mock is configured out-of-band via POST /configure first (see
  mock/openrouter_mock.py) -- the gateway's own outgoing payload has no
  field for a test to smuggle a desired delta split through.
- gateway <-> real OpenRouter: an in-process TestClient, used as a context
  manager so `lifespan` actually runs (otherwise app.state.http_client
  never gets created). The outbound call to OpenRouter is still genuinely
  real; only the inbound leg (test -> gateway) is in-process, which is
  what lets a mid-stream upstream failure surface as a real exception
  here instead of the silent 200-with-empty-body a real client would see.
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
import pytest

TASK3_DIR = Path(__file__).resolve().parent.parent


def _wait_for_port(port: int, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"nothing listening on port {port} after {timeout}s")


def _spawn(module: str, port: int, env_overrides: dict[str, str]) -> subprocess.Popen:
    env = {**os.environ, **env_overrides}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", str(port)],
        cwd=TASK3_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    _wait_for_port(port)
    return proc


@pytest.fixture
def mock_and_gateway():
    mock_port, gateway_port = 8195, 8180
    mock_proc = _spawn("mock.openrouter_mock:app", mock_port, {})
    gateway_proc = _spawn(
        "llm_gateway.app:app",
        gateway_port,
        {
            "OPENROUTER_URL": f"http://127.0.0.1:{mock_port}/v1/chat/completions",
            "OPENROUTER_API_KEY": "sk-fake-test-key",
            "OPENROUTER_MODEL": "fake/model-slug",
        },
    )
    yield mock_port, gateway_port
    gateway_proc.terminate()
    mock_proc.terminate()
    gateway_proc.wait(timeout=5)
    mock_proc.wait(timeout=5)


def _extract_contents(sse_body: str) -> list[str | None]:
    contents = []
    for line in sse_body.splitlines():
        if not line.startswith("data: ") or "[DONE]" in line:
            continue
        payload = json.loads(line.removeprefix("data: "))
        contents.append(payload["choices"][0]["delta"].get("content"))
    return contents


def test_gateway_forwards_to_configured_mock(mock_and_gateway):
    mock_port, gateway_port = mock_and_gateway

    # The email is deliberately split across three deltas -- none of which
    # contains a full match on its own -- so this also proves the Holdback
    # Buffer catches it (ADR-0001). Short text like this stays under the
    # 59-char holdback window, so it all flushes at once, at stream end.
    configure = httpx.post(
        f"http://127.0.0.1:{mock_port}/configure",
        json={"deltas": ["sumant", "h@gmail", ".com"]},
    )
    assert configure.status_code == 200

    response = httpx.post(
        f"http://127.0.0.1:{gateway_port}/v1/chat/completions",
        json={
            "model": "fake/model-slug",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )
    assert response.status_code == 200
    assert _extract_contents(response.text) == ["[REDACTED]", None]


def test_credit_card_never_leaks_mid_number(mock_and_gateway):
    mock_port, gateway_port = mock_and_gateway

    # Long enough leading text to push the buffer past the 59-char
    # holdback window WHILE the card number is still arriving -- a short
    # message would never flush anything early regardless of correctness,
    # proving nothing. The split lands right after an internal space
    # (the exact spot the old whitespace-based rule would have leaked
    # "4111 " early -- ADR-0002).
    configure = httpx.post(
        f"http://127.0.0.1:{mock_port}/configure",
        json={
            "deltas": [
                "Here is your card information which you requested earlier today: ",
                "4111 1111 1111 ",
                "1111",
                ". Thanks for banking with us!",
            ]
        },
    )
    assert configure.status_code == 200

    response = httpx.post(
        f"http://127.0.0.1:{gateway_port}/v1/chat/completions",
        json={
            "model": "fake/model-slug",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )
    assert response.status_code == 200

    contents = _extract_contents(response.text)
    # No fragment before the final one may contain any digit of the card.
    for fragment in contents[:-2]:
        assert not any(ch.isdigit() for ch in fragment)
    assert contents == [
        "Here i",
        "s your card inf",
        "ormation which you reque",
        "sted earlier today: [REDACTED]. Thanks for banking with us!",
        None,
    ]


def test_gateway_reaches_real_openrouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake-test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "fake/model-slug")
    monkeypatch.delenv("OPENROUTER_URL", raising=False)  # real OpenRouter, no override

    from fastapi.testclient import TestClient

    from llm_gateway.app import app

    with TestClient(app) as client:
        # A fake key reaching the real API proves genuine network
        # reachability (DNS, TLS, HTTP all succeeded) without needing a
        # real, valid key -- a connection failure would raise a different
        # exception type entirely, not an HTTPStatusError with a real
        # status code from openrouter.ai itself.
        with pytest.raises(httpx.HTTPStatusError, match="401"):
            client.post(
                "/v1/chat/completions",
                json={
                    "model": "fake/model-slug",
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": True,
                },
            )

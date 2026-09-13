"""Integration tests that spawn the real server as a subprocess over stdio.

These exercise the evaluation criteria directly:
- STDIO isolation: every line on stdout must be valid JSON-RPC. read_response()
  enforces this on every single call in every test below -- if any log/print
  statement ever leaks onto stdout, the very next json.loads() call fails
  immediately, in whichever test happens to run next.
- Protocol compliance: invalid tool arguments must come back as a genuine
  JSON-RPC error object (top-level "error", code -32602), not a normal
  result -- distinct from a *valid* call that fails for a business reason
  (e.g. unknown customer_id), which must come back as a normal result with
  result.isError == True.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

PROTOCOL_VERSION = "2025-11-25"


class ServerProcess:
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "fde_mcp_server.main"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._next_id = 0
        self.stderr_output = ""

    def _send(self, obj: dict) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def send_request(self, method: str, params: dict | None = None) -> int:
        self._next_id += 1
        msg = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)
        return self._next_id

    def send_notification(self, method: str, params: dict | None = None) -> None:
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)

    def read_response(self) -> dict:
        assert self.proc.stdout is not None
        line = self.proc.stdout.readline()
        assert line, "server closed stdout before responding"
        # STDOUT ISOLATION: this line must be nothing but the JSON-RPC frame.
        obj = json.loads(line)
        assert obj.get("jsonrpc") == "2.0"
        return obj

    def handshake(self) -> dict:
        self.send_request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "pytest-client", "version": "0.0.1"},
            },
        )
        resp = self.read_response()
        assert "result" in resp, f"initialize failed: {resp}"
        self.send_notification("notifications/initialized")
        return resp

    def close(self) -> None:
        assert self.proc.stdin is not None
        assert self.proc.stderr is not None
        self.proc.stdin.close()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)
        self.stderr_output = self.proc.stderr.read()


@pytest.fixture
def server():
    sp = ServerProcess()
    sp.handshake()
    try:
        yield sp
    finally:
        sp.close()


def test_tools_list_advertises_both_tools(server: ServerProcess):
    server.send_request("tools/list")
    resp = server.read_response()
    assert "result" in resp
    names = {t["name"] for t in resp["result"]["tools"]}
    assert names == {"get_customer_record", "trigger_refund"}


def test_valid_get_customer_record_succeeds(server: ServerProcess):
    server.send_request(
        "tools/call",
        {"name": "get_customer_record", "arguments": {"customer_id": "CUST-10001"}},
    )
    resp = server.read_response()
    assert "result" in resp
    assert resp["result"]["isError"] is False
    assert resp["result"]["structuredContent"]["name"] == "Ada Lovelace"


def test_valid_trigger_refund_succeeds(server: ServerProcess):
    server.send_request(
        "tools/call",
        {
            "name": "trigger_refund",
            "arguments": {"customer_id": "CUST-10001", "amount": 25.5, "reason": "duplicate charge"},
        },
    )
    resp = server.read_response()
    assert "result" in resp
    assert resp["result"]["isError"] is False
    assert resp["result"]["structuredContent"]["amount"] == 25.5


@pytest.mark.parametrize(
    "arguments",
    [
        {"customer_id": "bad-id"},
        {"customer_id": "CUST-1"},
        {"customer_id": "CUST-10001", "unexpected": "field"},
        {},
    ],
)
def test_get_customer_record_invalid_input_is_protocol_error(server: ServerProcess, arguments):
    server.send_request("tools/call", {"name": "get_customer_record", "arguments": arguments})
    resp = server.read_response()
    assert "error" in resp, f"expected a JSON-RPC protocol error, got: {resp}"
    assert resp["error"]["code"] == -32602


@pytest.mark.parametrize(
    "arguments",
    [
        {"customer_id": "CUST-10001", "amount": -5.0, "reason": "duplicate charge"},
        {"customer_id": "CUST-10001", "amount": 0, "reason": "duplicate charge"},
        {"customer_id": "CUST-10001", "amount": 10.0, "reason": "short"},
        {"customer_id": "CUST-10001", "amount": "10.0", "reason": "duplicate charge"},
        {"customer_id": "not-a-real-id", "amount": 10.0, "reason": "duplicate charge"},
    ],
)
def test_trigger_refund_invalid_input_is_protocol_error(server: ServerProcess, arguments):
    server.send_request("tools/call", {"name": "trigger_refund", "arguments": arguments})
    resp = server.read_response()
    assert "error" in resp, f"expected a JSON-RPC protocol error, got: {resp}"
    assert resp["error"]["code"] == -32602


def test_unknown_tool_name_is_protocol_error(server: ServerProcess):
    server.send_request("tools/call", {"name": "not_a_real_tool", "arguments": {}})
    resp = server.read_response()
    assert "error" in resp
    assert resp["error"]["code"] == -32602


def test_unknown_customer_is_a_tool_result_error_not_a_protocol_error(server: ServerProcess):
    """Valid input, but the business operation fails -- this must NOT be a
    JSON-RPC error; it's a normal result with isError=True."""
    server.send_request(
        "tools/call",
        {"name": "get_customer_record", "arguments": {"customer_id": "CUST-99999"}},
    )
    resp = server.read_response()
    assert "result" in resp, f"expected a tool-result error, got a protocol error: {resp}"
    assert resp["result"]["isError"] is True


def test_logs_are_written_to_stderr_not_stdout():
    sp = ServerProcess()
    sp.handshake()
    sp.close()
    assert "Starting fde-assignment-server" in sp.stderr_output

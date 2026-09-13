# Task 2 — MCP Security Gateway Proxy: slice-by-slice plan

Status: **Slices 1-5 done, verified. Grilling pass complete, all findings
fixed and verified.** Task 2 build is done.

### Grilling pass findings (fixed)

- `tools/call` with missing/non-string `params.name` is now rejected
  locally as `-32602 Invalid Params` (with `data={"missing": "params.name"}`),
  before `is_authorized` ever runs -- it's a malformed call, not an
  authorization denial, so it never reaches the mock.
- Missing/malformed/unrecognized `Authorization` header is deliberately
  left as "anonymous" (`role=None`): still allowed for non-`admin_` tools,
  denied for `admin_` tools. No blanket "must authenticate" rule was added
  -- the task only scopes the `admin` requirement to `admin_`-prefixed
  tools.
- The per-request log line now includes `tool_name` (was method-only
  before), so successful `admin_`-prefixed calls leave as complete an
  audit trail as denied ones. The denial log line still repeats
  `tool_name` on purpose, so it reads standalone under `grep`.
Edit this file directly if you want to change the order, add a slice, or
adjust anything below — we'll build against whatever this file says.

## Context

Task 2 asks for an HTTP/JSON-RPC reverse proxy that sits between an AI agent
client and a downstream MCP server, enforcing role-based access: any
`tools/call` whose `params.name` starts with `admin_` must come from a caller
whose Bearer-token role is `admin`, or the gateway answers directly with a
JSON-RPC error (`-32001`) and never contacts the downstream server at all.

Agreed approach: build in **thin, runnable vertical slices**, each ending in
something real to `curl`, rather than one finished implementation followed by
a retroactive line-by-line walkthrough (that was Task 1's approach — right
for mechanical/OOP questions, wrong here because the *architecture itself*,
not the syntax, is the hard part). We pause for questions at each slice
boundary. After slice 5, run the `grilling` skill specifically against the
authorization/error-handling logic, since that maps directly to the task's
own "clean error handling" evaluation criterion.

Stack: **FastAPI + httpx** (async, reuses the event-loop mental model from
the tool server; Pydantic comes along for the JSON-RPC envelope, same
discipline as `../mcp-tool-server/models.py`). We're also building a small
mock downstream MCP server ourselves, since nothing else provides one to
forward to or test against.

## Reusing the tool server's proven patterns

- **Project scaffold**: same `uv` + `src/` layout + `pyproject.toml` with a
  `[project.scripts]` entry, as in `../mcp-tool-server/pyproject.toml`.
- **Pydantic as single source of truth**: the JSON-RPC envelope (`method`,
  `params`, `id`) gets a real Pydantic model, same spirit as
  `../mcp-tool-server/src/fde_mcp_server/models.py` — one declaration
  doubles as validation and as documentation of the shape.
- **Structured JSON-RPC errors**:
  `../mcp-tool-server/src/fde_mcp_server/tools.py`'s
  `McpError(ErrorData(code=..., message=..., data=...))` pattern is the
  template for constructing the `-32001` error object here — same shape,
  different trigger (role check instead of schema validation).
- **Tiered error philosophy**: the tool server drew a hard line between "the
  request itself was invalid" (protocol-level, short-circuits before
  business logic) and "the request was valid but the answer is no" (a
  normal result). The gateway's authorization check is structurally the
  *same kind* of short-circuit as the tool server's "unknown tool name" /
  "invalid params" checks — intercept and answer immediately, never let it
  reach the next layer.
- **Verify on the real wire, not by assumption**: the tool server's
  `tests/test_stdio_protocol.py` spawned the real server and spoke raw
  JSON-RPC to it, asserting on actual bytes. This project's tests do the
  same thing over real HTTP, against a genuinely running gateway + mock.

## Project layout (this repo, sibling to `mcp-tool-server/`)

```
mcp-security-gateway/
  PLAN.md          # this file
  pyproject.toml
  src/mcp_gateway/
    __init__.py
    main.py         # uvicorn entrypoint
    app.py          # FastAPI app, the single POST /rpc route
    rpc.py          # Pydantic models for the JSON-RPC envelope
    auth.py         # Bearer token -> role extraction
    policy.py        # the admin_ prefix authorization decision
    forwarder.py     # httpx.AsyncClient call to the downstream server
    errors.py        # JSON-RPC error object construction (-32001, etc.)
  mock/
    downstream_mock.py   # tiny second FastAPI app: canned tools/list +
                          # tools/call for get_data and admin_reset_key
  tests/
    test_rpc_parsing.py
    test_policy.py
    test_gateway_integration.py
```

## The five slices

Each slice ends in something runnable.

**Slice 1 — Skeleton.** A FastAPI app with one `POST /rpc` route that parses
the JSON body and echoes it back verbatim. No branching, no auth, no
forwarding. Proves the server stands up and JSON parsing works.
*Verify:* `curl -s -X POST localhost:8080/rpc -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'`
returns the same body back.

**Slice 2 — Method branch, fake responses.** Introduce the `rpc.py` Pydantic
model for the envelope. Branch on `method`: `tools/list` vs `tools/call`
(pulling `params.name` out for the latter). Return distinct, synthetic
responses per branch — still no real downstream call. Proves JSON-RPC
literacy translates into real routing.
*Verify:* curl both methods, confirm visibly different canned responses.

**Slice 3 — Real forwarding, against a real mock.** Build
`mock/downstream_mock.py` (its own small FastAPI app, its own port) with
`tools/list` returning `[get_data, admin_reset_key]` and canned `tools/call`
successes for both. Wire `forwarder.py` with `httpx.AsyncClient` to actually
POST the incoming payload downstream and relay its real JSON response back —
for every request, no auth gating yet. This is "Both Ends of the Wire"
Scenario A, made real.
*Verify:* run both processes; curl the gateway; confirm the response body is
one that only the mock could have produced (not synthesized by the gateway),
and that the mock's own logs show it received the request.

**Slice 4 — Auth extraction, unenforced.** Add `auth.py`: parse
`Authorization: Bearer <token>` into a role via a small in-memory
token→role map (a deliberate simplification, not real JWT — worth flagging
as such). Log the extracted role. Nothing is gated yet — every request still
forwards regardless of role.
*Verify:* curl with different bearer tokens, confirm the logged role changes
accordingly, and behavior is otherwise unchanged from Slice 3.

**Slice 5 — The actual security boundary.** `policy.py`'s
`is_authorized(role, tool_name)` (true unless the name starts with `admin_`
and the role isn't `admin`), wired into the `tools/call` branch *before*
`forwarder.py` is ever called. On denial, `errors.py` constructs
`{"error": {"code": -32001, "message": "Unauthorized Tool Call"}}` and that's
returned directly — `httpx` never runs. This is "Both Ends of the Wire"
Scenario B, made real.
*Verify:* three curls — `admin_reset_key` with a viewer token (expect
`-32001`, and the mock's logs show nothing arrived); `admin_reset_key` with
an admin token (expect the mock's real canned success); `get_data` with a
viewer token (expect success — it's not `admin_`-prefixed, so it never needed
the admin role at all).

## After slice 5

Run the `grilling` skill against `policy.py` + the error-handling path
specifically — missing/malformed `Authorization` header, `method` that's
neither `tools/list` nor `tools/call`, missing `params.name`, empty bearer
token — before calling the task done.

## Open questions / things to confirm before or during build

- Token→role map: hardcoded dict for now (e.g. `{"admin-token": "admin", "viewer-token": "viewer"}`) — fine for this exercise, but flag it as a stand-in for a real auth system if that's ever worth noting in the writeup.
- Anything else you want changed about the slice order, the file layout, or scope — edit above and we'll follow it.

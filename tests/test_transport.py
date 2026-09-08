"""MCP Streamable HTTP conformance, spec version 2025-11-25.

Alexa+ requires this transport, so "we used the MCP SDK" is a claim that should
be checked rather than asserted. Each test names the requirement it covers.

The Origin test is the one that matters most. The spec says a server MUST
validate Origin and MUST answer 403 when it is invalid, because otherwise any
web page the user visits can reach a locally-running MCP server. For a server
whose entire contents are things somebody told it in private, that is not a
theoretical concern.

Tests are synchronous and drive the ASGI app through anyio, so no pytest plugin
is required to run them.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import anyio
import httpx
import pytest

from server.app import build_server

GOOD_ORIGIN = "http://127.0.0.1:8000"
ACCEPT_BOTH = "application/json, text/event-stream"

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-11-25",
        "capabilities": {},
        "clientInfo": {"name": "conformance", "version": "0"},
    },
}


def call(coro_fn):
    """Run one async interaction against a fresh server."""

    async def runner():
        store = Path(tempfile.mkdtemp()) / "m.jsonl"
        app = build_server(store).streamable_http_app()
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url=GOOD_ORIGIN
            ) as client:
                return await coro_fn(client)

    return anyio.run(runner)


def headers(**extra) -> dict[str, str]:
    base = {
        "Accept": ACCEPT_BOTH,
        "Content-Type": "application/json",
        "Origin": GOOD_ORIGIN,
    }
    base.update(extra)
    return base


# -- security: the spec's MUST ------------------------------------------


def test_an_invalid_origin_is_refused_with_403():
    """Spec: servers MUST validate Origin and MUST respond 403 when invalid."""

    async def go(client):
        return await client.post(
            "/mcp", json=INITIALIZE, headers=headers(Origin="https://evil.example")
        )

    assert call(go).status_code == 403


def test_a_permitted_origin_is_accepted():
    async def go(client):
        return await client.post("/mcp", json=INITIALIZE, headers=headers())

    assert call(go).status_code == 200


def test_dns_rebinding_protection_is_actually_enabled():
    """A disabled protection and a passing origin test look identical."""
    from server.app import _security_settings

    settings = _security_settings()
    assert settings.enable_dns_rebinding_protection is True
    assert settings.allowed_origins, "an empty allowlist would permit nothing or everything"


# -- the handshake --------------------------------------------------------


def test_initialize_returns_a_session_id():
    """Spec: the server MAY assign a session id via the MCP-Session-Id header."""

    async def go(client):
        return await client.post("/mcp", json=INITIALIZE, headers=headers())

    response = call(go)
    session_id = response.headers.get("mcp-session-id")
    assert session_id
    assert all(0x21 <= ord(c) <= 0x7E for c in session_id), "must be visible ASCII"


def test_a_request_missing_both_accept_types_is_refused():
    """Spec: the client MUST accept both application/json and text/event-stream."""

    async def go(client):
        return await client.post(
            "/mcp", json=INITIALIZE, headers=headers(Accept="application/json")
        )

    assert call(go).status_code == 406


def test_a_get_without_a_session_is_refused():
    """Spec: servers requiring a session SHOULD answer 400 without one."""

    async def go(client):
        return await client.get(
            "/mcp", headers={"Accept": "text/event-stream", "Origin": GOOD_ORIGIN}
        )

    assert call(go).status_code == 400


# -- the tools are actually exposed ---------------------------------------


def test_the_memory_tools_are_advertised():
    """The submission claims memory over MCP. Prove the tools exist on the wire."""

    async def go(client):
        init = await client.post("/mcp", json=INITIALIZE, headers=headers())
        session = init.headers["mcp-session-id"]
        session_headers = headers(**{"mcp-session-id": session})

        await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=session_headers,
        )
        return await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers=session_headers,
        )

    body = call(go).text
    for tool in ("catch_me_up", "remember", "recall", "correct", "forget", "what_changed"):
        assert tool in body, f"{tool} is not advertised over MCP"


def test_the_server_declares_the_expected_protocol_version():
    async def go(client):
        return await client.post("/mcp", json=INITIALIZE, headers=headers())

    assert "2025-11-25" in call(go).text

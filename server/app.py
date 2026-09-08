"""The Alexa+ MCP server: memory tools over Streamable HTTP.

This is a genuine MCP server built on the official SDK, implementing the
Streamable HTTP transport from spec version 2025-11-25 — the transport Alexa+
requires. The SDK is imported and called here rather than described in a
README, which is also what Amazon's submission rule asks for.

Two decisions worth stating plainly:

**DNS rebinding protection is on.** The spec says a server MUST validate the
``Origin`` header and MUST answer 403 when it is invalid, because without it a
web page can reach a locally-running MCP server and read whoever's memory is in
it. For a memory server that is not a hypothetical: the whole point of the
product is that it holds things you told it in private.

**No inference on this path.** Alexa+ requires a round-trip under 500ms. Every
tool here answers deterministically from stored state. A tool that called a
language model could not meet that budget and could not be bounded either, so
the reasoning path is kept separate and separately named.

Run it:

    python -m server.app                    # http://127.0.0.1:8000/mcp
    MCP_ALLOWED_ORIGINS=https://example.com python -m server.app
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from core.store import MemoryStore
from server.tools import MemoryTools

# Where the memory lives. One file, on your machine, in a format you can read
# with `cat`. That is the product position, not an implementation detail.
STORE_PATH = Path(os.environ.get("MEMORY_STORE", "data/memory.jsonl"))

SERVER_NAME = "Memory"
SERVER_INSTRUCTIONS = (
    "Persistent memory that knows when things changed. Use catch_me_up to hear "
    "what is new, remember to store a fact, recall to ask what was true at any "
    "point in time, correct when an answer has changed, and forget when "
    "something was never true. Answers are short because they are spoken aloud."
)


def _security_settings() -> TransportSecuritySettings:
    """Origin allowlist for DNS rebinding protection.

    Defaults to localhost only. A deployment sets MCP_ALLOWED_ORIGINS to the
    origins that may reach it. Defaulting to "anything" would be the convenient
    choice and would hand every page the user visits a channel to this server.
    """
    configured = os.environ.get("MCP_ALLOWED_ORIGINS", "")
    origins = [o.strip() for o in configured.split(",") if o.strip()]
    hosts = [h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_origins=origins or ["http://127.0.0.1:8000", "http://localhost:8000"],
        allowed_hosts=hosts or ["127.0.0.1:8000", "localhost:8000", "127.0.0.1", "localhost"],
    )


def build_server(store_path: Path | None = None) -> FastMCP:
    """Construct the MCP server with the memory tools registered."""
    store = MemoryStore(store_path or STORE_PATH)
    tools = MemoryTools(store)

    mcp = FastMCP(
        name=SERVER_NAME,
        instructions=SERVER_INSTRUCTIONS,
        streamable_http_path="/mcp",
        stateless_http=False,
        json_response=False,
        transport_security=_security_settings(),
    )

    @mcp.tool(description="Catch up on what is new, what changed, and what is still open.")
    def catch_me_up(full: bool = False) -> str:
        return tools.catch_me_up(named=full)

    @mcp.tool(description="Remember a new fact.")
    def remember(fact: str, tags: list[str] | None = None) -> str:
        return tools.remember(fact, tags=tags)

    @mcp.tool(
        description=(
            "Recall what is or was true about something. Give 'when' as a date "
            "like 2026-03-01 or a phrase like 'three months ago' to ask about "
            "the past."
        )
    )
    def recall(about: str, when: str | None = None) -> str:
        return tools.recall(about, when)

    @mcp.tool(
        description=(
            "Record that an answer has changed. The previous value is kept, so "
            "questions about the past still answer correctly."
        )
    )
    def correct(about: str, new_fact: str) -> str:
        return tools.correct(about, new_fact)

    @mcp.tool(
        description=(
            "Withdraw something that was never true. It stops being said, but "
            "the record that it was once believed is kept."
        )
    )
    def forget(about: str, reason: str = "you told me it was wrong") -> str:
        return tools.forget(about, reason)

    @mcp.tool(description="What has changed recently.")
    def what_changed(since: str = "7 days ago") -> str:
        return tools.what_changed(since)

    return mcp


app = build_server().streamable_http_app()


def main() -> None:
    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print(f"MCP (Streamable HTTP, spec 2025-11-25) on http://{host}:{port}/mcp")
    print(f"memory: {STORE_PATH.resolve()}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()

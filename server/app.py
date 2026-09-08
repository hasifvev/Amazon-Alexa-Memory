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
from server.tools import MemoryTools, Timeline

# Where the memory lives. One file, on your machine, in a format you can read
# with `cat`. That is the product position, not an implementation detail.
STORE_PATH = Path(os.environ.get("MEMORY_STORE", "data/memory.jsonl"))
WEB_DIR = Path(__file__).resolve().parent.parent / "web"

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
    _ensure_seeded(store)
    tools = MemoryTools(store)

    mcp = FastMCP(
        name=SERVER_NAME,
        instructions=SERVER_INSTRUCTIONS,
        streamable_http_path="/mcp",
        stateless_http=False,
        json_response=False,
        transport_security=_security_settings(),
    )

    # Tool descriptions are the routing surface, not documentation. Alexa+
    # chooses which tool to invoke from these strings, so each one names the
    # phrasings a person actually uses. A description written for a human
    # reader ("Recalls a stored fact") routes badly; one written for a router
    # ("use when the customer asks what something is, or what it used to be")
    # routes well. Every `who` parameter exists because an Echo is a shared
    # household device.

    @mcp.tool(
        description=(
            "Use when the customer arrives, greets you, or asks to be caught "
            "up: 'catch me up', 'what did I miss', 'good morning', 'anything "
            "new'. Reports what changed since last time, what is still open, "
            "and what was withdrawn. What it leads with depends on the time of "
            "day. Set 'who' when the speaker is not the default person."
        )
    )
    def catch_me_up(
        full: bool = False, hour: int | None = None, who: str | None = None
    ) -> str:
        return tools.for_subject(who).catch_me_up(named=full, hour=hour)

    @mcp.tool(
        description=(
            "Use when the customer states a fact to keep: 'remember that…', "
            "'note that…', 'don't let me forget…'. Pass the fact as a complete "
            "sentence. Tag it 'open' if it is something still outstanding."
        )
    )
    def remember(
        fact: str, tags: list[str] | None = None, who: str | None = None
    ) -> str:
        return tools.for_subject(who).remember(fact, tags=tags)

    @mcp.tool(
        description=(
            "Use when the customer asks what something is, or what it used to "
            "be: 'what time is standup', 'when does the office close', 'what "
            "was it back in June'. Set 'when' for questions about the past — "
            "a date like 2026-03-01, or a phrase like 'three months ago'. "
            "Answers about the past use what was true then, not what is true "
            "now, and say so when nothing was known yet."
        )
    )
    def recall(about: str, when: str | None = None, who: str | None = None) -> str:
        return tools.for_subject(who).recall(about, when)

    @mcp.tool(
        description=(
            "Use when an answer has CHANGED and the old one was true at the "
            "time: 'standup moved to ten', 'change my address to…', 'it's X "
            "now'. The previous value is kept, so questions about earlier "
            "dates still answer correctly. Do not use for something that was "
            "never true — use forget for that."
        )
    )
    def correct(about: str, new_fact: str, who: str | None = None) -> str:
        return tools.for_subject(who).correct(about, new_fact)

    @mcp.tool(
        description=(
            "Use when something was NEVER true and should be withdrawn: "
            "'that's wrong', 'forget that', 'I was mistaken about…'. Distinct "
            "from correct: this says the fact never described reality, so it "
            "will not answer questions about any date. The record that it was "
            "once believed is kept."
        )
    )
    def forget(
        about: str, reason: str = "you told me it was wrong", who: str | None = None
    ) -> str:
        return tools.for_subject(who).forget(about, reason)

    @mcp.tool(
        description=(
            "Use when the customer asks what has moved recently: 'what's "
            "changed', 'what's new since last week', 'anything happen while I "
            "was away'."
        )
    )
    def what_changed(since: str = "7 days ago", who: str | None = None) -> str:
        return tools.for_subject(who).what_changed(since)

    @mcp.tool(
        description=(
            "Use when the customer asks about their own mistakes: 'what have I "
            "been wrong about', 'what did I get wrong', 'have I made mistakes'. "
            "Lists withdrawn beliefs and how long each was carried before being "
            "withdrawn."
        )
    )
    def wrong_about(who: str | None = None) -> str:
        return tools.for_subject(who).wrong_about()

    # -- MCP Apps: a visual timeline for devices with a screen -------------
    #
    # Half the current Echo line-up has a display, and a belief history is a
    # fundamentally visual thing — a sequence with a shape. Reading six dates
    # aloud is a worse version of showing them.
    #
    # This follows the MCP Apps extension (SEP-1865, spec 2026-01-26): a
    # ui:// resource whose HTML the host renders in a sandboxed iframe, linked
    # from a tool through _meta.ui.resourceUri. The tool still returns a spoken
    # line, so one tool serves both a screen and a speaker.

    @mcp.resource(
        "ui://memory/timeline",
        name="memory-timeline",
        description="Visual history of what has been believed about a topic.",
        mime_type="text/html;profile=mcp-app",
        meta={
            "ui": {
                # No external anything. A timeline of somebody's private memory
                # has no business making network requests, and declaring no
                # domains means the host's CSP blocks them outright.
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": [],
                    "frameDomains": [],
                    "baseUriDomains": [],
                },
                "permissions": {},
                "prefersBorder": False,
            }
        },
    )
    def timeline_view() -> str:
        return (WEB_DIR / "timeline.html").read_text(encoding="utf-8")

    @mcp.tool(
        description=(
            "Use when the customer wants the whole history of something rather "
            "than just the current answer: 'show me the history of…', 'how has "
            "this changed', 'what have I believed about…'. On a device with a "
            "screen this renders a timeline; on a speaker it is spoken."
        ),
        meta={
            "ui": {
                "resourceUri": "ui://memory/timeline",
                "visibility": ["model", "app"],
            }
        },
        # Force structured output. A bare `-> dict` gives FastMCP no schema to
        # derive, so it serialises to text only and the view receives nothing
        # to render. The MCP Apps view reads structuredContent.
        structured_output=True,
    )
    def timeline(about: str, who: str | None = None) -> Timeline:
        return tools.for_subject(who).timeline(about)

    # -- the simulated Alexa+ experience ---------------------------------
    #
    # Amazon permits a simulated experience in place of a certified add-on.
    # This is that simulation, and it is deliberately not a mock: the page is
    # an MCP client that speaks the real protocol to the server above, over the
    # same /mcp endpoint an Alexa+ device would use. Judges can watch the
    # JSON-RPC traffic in the page.

    @mcp.custom_route("/", methods=["GET"])
    async def index(_request):
        from starlette.responses import FileResponse

        return FileResponse(WEB_DIR / "index.html")

    @mcp.custom_route("/api/seed", methods=["POST"])
    async def reseed(_request):
        from starlette.responses import JSONResponse

        from server.demo import reset

        fresh = reset(store.path)
        tools.store = fresh
        return JSONResponse({"seeded": len(fresh)})

    return mcp


def _ensure_seeded(store: MemoryStore) -> None:
    """A demo that opens on an empty store demonstrates nothing about time."""
    if len(store) == 0:
        from server.demo import seed

        seed(store)


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

# Devpost entry — paste-ready (Build, Ship, Shape: Amazon Developer Hackathon, Alexa+ track)

Prepared by Aria 2026-10-23. Every claim below is backed by evidence in this repository; items marked **[YOU]** need your account, link or decision. Deadline: **2026-10-24 03:00 MYT** (Oct 23 noon PDT). Rules: https://amazonappdev2026.devpost.com/rules

## Fill-in checklist

| Field | Value | Status |
|---|---|---|
| Project name | Memory | ready |
| Track | Alexa+ | ready |
| Tagline (<=60 chars) | Alexa that remembers what changed, and what was wrong. | ready (54 chars) |
| GitHub repo URL | `https://github.com/hasifvev/Amazon-Alexa-Memory` | **[YOU]** push + make public first |
| Demo video URL | public YouTube/Vimeo, under 3 min | **[YOU]** upload `docs/demo/output/alexa-memory-demo.webm` (1:42) |
| Open-source license | MIT (LICENSE in repo) | ready |
| Testing instructions | see below | ready |
| Toolkit feedback | see below (full log: FRICTION.md) | ready |
| Gallery images | screenshots of timeline, chat, dashboard (re-record with `docs/demo/record_demo.py` or screenshot) | **[YOU]** pick 3 |
| AWS / Open Source mini-challenges | do not tick unless you can show evidence (see bottom) | **[YOU]** decide |

## About the project (Devpost story sections)

### Inspiration
An assistant should know not only today's answer, but what changed, what was wrong, and when nothing was known. A single current value cannot tell a moved meeting from a mistaken recollection. Memory gives remembered facts a history.

### What it does
A browser-based simulated Alexa+ experience backed by a genuine self-hosted MCP server. Twenty deterministic tools remember, correct, withdraw and recall facts, answer "what was true on that date", share synthetic household messages, keep lists, profiles and projects, and give a daily brief. A sandboxed MCP Apps timeline shows replaced, withdrawn, expired and scheduled records. "Changed" and "wrong" are different: a corrected fact keeps its previous value; a withdrawn belief is kept as evidence together with how long it was believed. A scoped dashboard, snapshot export/import, archive-and-reset and optional voice input round out the demo.

### How we built it
Python with the official MCP SDK 1.30.0 over Streamable HTTP (spec 2025-11-25), Starlette/Uvicorn, and a dependency-free local append-only memory core with two timelines: when a fact described the world, and when it was believed. The browser talks to the server with real MCP `initialize`, `tools/call` and `resources/read`; routing and tool execution are measured separately. Optional Amazon Bedrock routing exists but is off by default, with deterministic regex routing as the primary path. Optional Telegram bridge is disabled unless configured.

### Challenges we ran into
- Natural-language routing must never turn a question into a write. We found and fixed a bug where "what is my name" stored the name "what"; routing now resolves read questions before declarations, and ambiguous text asks for clarification instead of writing.
- A fresh install pulled MCP SDK 2, which renamed FastMCP; we pinned and tested from a clean environment.
- The SDK's transport security defaults rejected every origin until we configured Host/Origin allowlists explicitly.
- MCP Apps timeline rendering needed a hand-built `ui/initialize` handshake.

### Accomplishments we're proud of
- All 20 tools verified over real HTTP (24/24 wire scenarios) and 60/60 natural-language routing cases, including read-only cases that must not write.
- 140 automated tests pass in a fresh isolated environment, including real localhost server/browser journeys with reset, import and process restart.
- `pip check` and `pip_audit` report no known vulnerabilities.
- A written friction log of the Alexa+/MCP toolkit experience.

### What we learned
Temporal truth is a product feature, not a storage detail. Strict separation between "intent routing" and "tool execution" makes safety testable. Pinned versions and fresh-install tests catch SDK drift early.

### What's next
Real authentication and per-household identity, retention and deletion controls, multi-process storage and scaled-history benchmarks, and a certified Alexa+ add-on path. None of these are claimed today.

## Built with
python, mcp (Model Context Protocol), starlette, uvicorn, playwright, pytest, javascript, html, css, amazon-bedrock (optional, off by default), telegram-bot-api (optional, off by default)

## Try it out / testing instructions (paste into the testing field)
Requires Python 3.11+. No account, no API key, no cloud service needed.
```
git clone https://github.com/hasifvev/Amazon-Alexa-Memory
cd Amazon-Alexa-Memory
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
export MEMORY_STORE=data/synthetic-demo.jsonl MEMORY_DEMO=1 MEMORY_BEDROCK=0
python -m server.app
```
Open http://127.0.0.1:8000 and try: `what is standup`, `what was standup 100 days ago`, `show me the history of standup`, `change standup to eleven`, `what have I been wrong about`, `tell Aisyah that dinner is at seven`, then click **Aisyah** and ask `what has been shared with me`. Tests: `python -m pip install -r requirements-dev.txt && python -m playwright install chromium && python -m pytest -q` (140 pass). All data is invented. Not a certified Alexa add-on; speaker selection is scoping, not authentication.

## Feedback on the toolkit (required feedback field; full text in FRICTION.md)
What worked: the official SDK's tool schemas and Streamable HTTP session transport made 20 tools straightforward, and the spec is unusually clear about MUSTs.
Friction: (1) default `TransportSecuritySettings()` rejected every Origin with 421/403 until allowlists were set explicitly; (2) "MCP Toolkit available in the United States" does not say what is actually restricted, and the most useful alternative (simulated path) is only in the rules, not the docs; (3) the 500 ms latency requirement is easy to miss; (4) `addon.json` requires six icon sizes listed unsorted; (5) certified add-on requirements are a product launch, not a hackathon task; (6) Streamable HTTP returns SSE by default and the client must handle it; (7) tests need the ASGI lifespan run manually; (8) an unpinned install picked MCP SDK 2 and broke FastMCP imports; (9) MCP Apps works with the SDK but ui/initialize ordering is assembled by hand. Would build with the SDK again: yes, with pinned versions and conformance tests.

## Mini-challenges — only tick what you can prove
- **Open Source:** not claimed here; it needs a separate public contribution URL.
- **AWS Builder:** Bedrock routing exists in code, but no live Bedrock/AWS run was verified in this closure (provider disabled in all tests). Do not tick unless you have your own earlier evidence of it running on AWS.

## Honest-boundaries line (put at the end of the description)
Synthetic simulation, not a certified Alexa add-on or tested Echo device. Speaker selection is not authentication. Voice input was tested with fixtures, not a real microphone. Prior work: baseline commit 582b189 (six interface/API features) predates the window; later commits and CHANGELOG disclose the in-window work.

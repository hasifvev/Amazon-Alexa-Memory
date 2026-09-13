# Memory — an Alexa+ add-on that knows when things changed

**Track: Alexa+** · Build, Ship, Shape: Amazon Developer Hackathon

Alexa+ already remembers things. Ask it to remember your frequent flyer number
and it will; tell it your son's shoe size has changed and it will update it.

What it does not appear to have is a **past tense**. There is no documented way
to ask what a fact used to be, when it changed, or whether it changed because
the world moved on or because you were wrong the first time. A note has one
current value.

This add-on supplies that. It is memory with a history.

```
  "What time is standup?"
      Standup is at ten thirty. That changed on 8 July — before, standup was at nine.

  "What was it back in June?"
      As of 15 June 2026, standup is at nine.

  "When does the office close?"
      I did think the office closes at six, but I withdrew that — you told me it
      is actually seven. So I don't know.

  "What about the spare key, back in March?"
      I didn't know anything about the spare key on 1 March 2026. I only learned
      about it later.

  "What have I been wrong about?"
      You've withdrawn one thing. The longest-standing: the office closes at six —
      you believed that for 145 days, until you told me it is actually seven.
```

And when you ask something you asked before, whose answer has moved since:

```
  "What time is standup?"
      Standup is at ten thirty. That changed on 8 July — before, standup was at
      nine. You asked me this on 11 April too — back then, standup was at nine.
```

That 145-day figure is unavailable to any memory system that deletes what it
retracts: the evidence of having been wrong is the first thing such a system
destroys. Keeping withdrawn beliefs makes the duration simple arithmetic.

That last answer is the one worth pausing on. Admitting a gap is the behaviour
that separates this from an assistant which would confidently answer a March
question with a fact it learned in July.

## Two clocks, not one

Every memory sits on two independent timelines:

| | Meaning |
|---|---|
| **valid time** | when the **world** matched this memory |
| **belief time** | when **we** held it to be true |

That distinction produces two different operations, and conflating them is the
bug that makes most memory systems answer historical questions wrongly:

- **`correct`** — the answer *changed*. Closes the old value's valid window. We
  still believe the old value: it was true then, and it still answers questions
  about then.
- **`forget`** — it was *never* true. Ends belief. The record survives, so the
  assistant can tell you it used to think so, but it never answers as fact again.

Nothing is ever deleted. The log is append-only, and every write is fsynced.

## The time of day changes what you hear

Not the tone — the content and the volume.

| | leads with | items | 
|---|---|---|
| morning | what moved overnight, then what's open | 4 |
| afternoon | what's true now; changes are less urgent mid-flow | 3 |
| evening | what moved today, then what's unresolved | 3 |
| night | what moved. **Open items are dropped entirely** | 2 |

Handing somebody a list of open tasks at midnight is complete rather than
useful, so that section is omitted by choice, not shortened by budget pressure.

Changes are also ranked by how much they should disturb you: a withdrawal (you
have been acting on something false) outranks an answer moving, which outranks a
new fact. That only becomes visible when the list is tight — which is exactly
when it matters.

## On a screen, it draws the timeline

Half the current Echo line-up has a display — Show 8 and Show 11 — and a belief
history is a fundamentally visual thing: a sequence with a shape. Reading six
dates aloud is a worse version of showing them.

So `timeline` is an **MCP App** ([SEP-1865](https://github.com/modelcontextprotocol/ext-apps),
spec `2026-01-26`, the first official MCP extension): a `ui://` resource whose
HTML the host renders in a sandboxed iframe, linked from the tool through
`_meta.ui.resourceUri`, communicating back over JSON-RPC on `postMessage`.

```
  the deploy root is the app folder        [replaced]   Feb 2026 → May 2026
  the deploy root is the web folder        [replaced]   May 2026 → Aug 2026
  the deploy root is the projects folder   [now]        Aug 2026 →
```

The same tool returns a spoken line, so one implementation serves a screen and
a speaker. The view declares **no CSP domains at all** — a timeline of somebody's
private memory has no business making network requests, and declaring nothing
means the host blocks everything.

## An Echo is a shared device

It sits in a kitchen, not on one person's desk. Alexa+ knows who is speaking,
so every tool takes `who`, and each person's memory is separate:

```
  hasif:  "What time is standup?"  →  My standup is at ten.
  aisyah: "What time is standup?"  →  My standup is at eight.
```

## Run it

```bash
pip install -r requirements.txt
python -m server.app
# open http://127.0.0.1:8000
```

The page seeds a demo memory with a real history — a fact that changed, a chain
that changed twice, a belief that was withdrawn, and a gap where nothing was
known yet. Without a past there is nothing to demonstrate.

```bash
python -m pytest -q          # 42 tests
```

## The MCP server is real

This is a genuine MCP server on the [official Python SDK](https://github.com/modelcontextprotocol/python-sdk),
implementing **Streamable HTTP, spec `2025-11-25`** — the transport Alexa+
requires. It is imported and called in [`server/app.py`](server/app.py):

```python
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

mcp = FastMCP(name="Memory", streamable_http_path="/mcp", ...)

@mcp.tool(description="Recall what is or was true about something...")
def recall(about: str, when: str | None = None) -> str:
    return tools.recall(about, when)
```

Seventeen tools are published: `catch_me_up`, `remember`, `remember_for`,
`recall`, `correct`, `forget`, `what_changed`, `wrong_about`, `what_moved`,
`share`, `shared_with_me`, `timeline`, `add_to_list`, `get_list`,
`remove_from_list`, `track`, `my_projects`, `set_profile`, **`daily_brief`**.

**Tool descriptions are the routing surface, not documentation.** Alexa+ picks
which tool to invoke from these strings, so each one names the phrasings people
actually use — "what was it back in June", "that's wrong, forget it" — rather
than describing the function to a human reader.

**Conformance is tested, not asserted** — see
[`tests/test_transport.py`](tests/test_transport.py):

| Spec requirement | Test |
|---|---|
| MUST validate `Origin`, MUST answer 403 | `test_an_invalid_origin_is_refused_with_403` |
| Session id on initialize, visible ASCII | `test_initialize_returns_a_session_id` |
| Client MUST accept json **and** event-stream | `test_a_request_missing_both_accept_types_is_refused` |
| Session-less GET refused | `test_a_get_without_a_session_is_refused` |
| Tools reachable over the wire | `test_the_memory_tools_are_advertised` |

DNS rebinding protection is **on**, with an origin allowlist defaulting to
localhost. The spec requires it, and for a server whose entire contents are
things somebody told it in private, defaulting to permissive would be a real
hole rather than a pedantic one.

## The simulated experience is not a mock

Amazon permits a simulated Alexa+ experience in place of a certified add-on. The
page at `/` is that simulation — and it is a real **MCP client**. Every reply is
an actual `tools/call` over the same `/mcp` endpoint a device would use,
including the `initialize` handshake, session header and SSE parsing. The
protocol pane shows the live JSON-RPC traffic.

We built the certifiable server rather than a chat window that pretends. A
certified add-on additionally needs OAuth 2.1 with PKCE, Protected Resource
Metadata, six icon sizes, a carousel image, a privacy policy and terms URL, and
Amazon's certification review — a queue outside our control. The server is ready
for it; the submission does not depend on it.

## Speed, and why it is achievable

Alexa+ requires a round trip under **500 ms**. Measured over the wire:
**2.4–7.6 ms** per tool call.

That headroom exists because **no language model is called on this path.** Every
answer is assembled deterministically from stored state. A wake is bounded work
by construction: identity is capped, each section is capped, and the whole
briefing has a token ceiling, so the assistant does not get slower every day it
is used.

## Architecture

```
Amazon-Alexa-Memory/
├── server/app.py          MCP server, Streamable HTTP, origin validation, all routes
├── server/tools.py        17 tools and their spoken phrasing
├── server/llm_router.py   Amazon Bedrock (Nova Micro → Claude Haiku) intent router
├── server/demo.py         seeded history worth asking questions about
├── server/telegram_bridge.py  Telegram Bot webhook bridge (Feature 6)
├── web/index.html         simulated experience — MCP client in the browser
├── web/dashboard.html     Memory Health Dashboard — live stats panel (Feature 4)
├── web/timeline.html      MCP App — a ui:// resource rendered on Echo Show
└── tests/                 42 tests: transport conformance and spoken behaviour
```

The memory engine itself is a separate, reusable package:
[**Memory-Substrate-Core**](../Memory-Substrate-Core) — bitemporal append-only
store, tiered wake protocol, **zero third-party dependencies**, 94 tests, and a
reproducible benchmark against load-everything and recency-only baselines.

## Where this fits Amazon's platform

Amazon's add-on examples are service integrations that complete a transaction —
booking a table, buying tickets, calling a plumber. This is a different shape:
not a service, but **infrastructure other add-ons could stand on**.

Every add-on that stores anything about a customer faces the same problem this
solves. A booking add-on that knows your usual table also needs to know when
"usual" changed. A grocery add-on that learns you avoid shellfish needs to know
whether that was a preference that shifted or a fact recorded wrongly. Today
each of them would rebuild a private key-value store and get the temporal part
wrong in the same way.

Memory with a past tense is a horizontal capability, and it is the sort of thing
that is better as one well-tested layer than as fifteen partial ones.

## Developer feedback

[FRICTION.md](FRICTION.md) is the friction log kept while building this: nine
issues hit against the MCP SDK, the Alexa+ documentation and the hackathon
rules, each with what it cost and a concrete suggestion — plus what worked well,
since a friction log with no positives is a complaint rather than a report.

The first entry is a reproducible SDK footgun: constructing
`TransportSecuritySettings()` with its own defaults makes the server answer
**421 to every request**, while omitting the parameter entirely behaves
correctly. There is a regression test guarding against it here.

## New in this build

Six features added beyond the core bitemporal engine:

| Feature | What it adds |
|---|---|
| 🎙️ **Voice Input** | Mic button in the web UI — click or press **Space** to speak. Uses the browser's built-in Speech Recognition API. No dependencies. |
| ⏳ **Proactive Reminders** | `GET /api/reminders?hours=N` returns facts expiring in the next N hours. An amber strip appears in the UI when anything is about to expire. This is how a real Alexa skill would trigger unprompted notifications. |
| 📋 **Daily Brief** | Say **"daily brief"** → Alexa composes one spoken paragraph: greeting by name, local time, open items, memories expiring today, 24-hour changes, shared messages waiting, and active projects. |
| 📊 **Dashboard** | `/dashboard` — a live memory health panel showing per-user stats, correction rates, expiring-soon counts, and memory health score. Auto-refreshes every 30 seconds. |
| 📥 **Export / Import** | `GET /api/export` downloads memory as JSON or Markdown. `POST /api/import` merges an exported file back in. Move memory between devices — your memory travels with you. |
| 🤖 **Telegram Bridge** | `POST /api/webhook/telegram` accepts Telegram Bot API updates. Set `TELEGRAM_BOT_TOKEN` and point `@BotFather` at your server. Each Telegram username gets its own memory namespace, routed through the same LLM pipeline. |

### New endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/reminders` | Facts expiring soon (`?hours=24`, `?who=name`) |
| `GET` | `/api/stats` | Memory health metrics (JSON) |
| `GET` | `/dashboard` | Memory Health Dashboard (HTML) |
| `GET` | `/api/export` | Download memory (`?fmt=json` or `?fmt=md`, `?who=name`) |
| `POST` | `/api/import` | Merge an exported JSON file into the store |
| `GET` | `/api/webhook/telegram` | Webhook health check / setup status |
| `POST` | `/api/webhook/telegram` | Receive Telegram Bot updates |

### Telegram setup

```bash
# 1. Get a bot token — open Telegram, message @BotFather, send /newbot
# 2. Set the env var
export TELEGRAM_BOT_TOKEN=<your-token>

# 3. Start the server
python -m server.app

# 4. Register your webhook with Telegram
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     -d "url=https://YOUR_SERVER/api/webhook/telegram"

# 5. Text your bot — it responds using your Alexa memory
```

## Licence

MIT — see [LICENSE](LICENSE).

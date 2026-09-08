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
python -m pytest -q          # 37 tests
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

Seven tools are published: `catch_me_up`, `remember`, `recall`, `correct`,
`forget`, `what_changed`, `wrong_about`.

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
├── server/app.py     MCP server, Streamable HTTP, origin validation, routes
├── server/tools.py   the six tools, and their spoken phrasing
├── server/demo.py    a seeded history worth asking questions about
├── web/index.html    the simulated experience — an MCP client in the browser
└── tests/            37 tests: transport conformance and spoken behaviour
```

The memory engine itself is a separate, reusable package:
[**Memory-Substrate-Core**](../Memory-Substrate-Core) — bitemporal append-only
store, tiered wake protocol, **zero third-party dependencies**, 94 tests, and a
reproducible benchmark against load-everything and recency-only baselines.

## Developer feedback

[FRICTION.md](FRICTION.md) is the friction log kept while building this: nine
issues hit against the MCP SDK, the Alexa+ documentation and the hackathon
rules, each with what it cost and a concrete suggestion — plus what worked well,
since a friction log with no positives is a complaint rather than a report.

The first entry is a reproducible SDK footgun: constructing
`TransportSecuritySettings()` with its own defaults makes the server answer
**421 to every request**, while omitting the parameter entirely behaves
correctly. There is a regression test guarding against it here.

## Licence

MIT — see [LICENSE](LICENSE).

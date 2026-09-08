# Friction log

Built 2026-09-08 against the MCP Python SDK 1.29.0, the Alexa+ MCP Toolkit
docs, and the hackathon rules. Everything below was actually hit while
building — each item says what happened, what it cost, and what would have
prevented it. Where a claim is testable, there is a reproduction.

Ordered by how much time each one cost.

---

## 1. `TransportSecuritySettings()` with its own defaults bricks the server

**Severity: high — silent, and points you at the wrong header.**

The spec requires MCP servers to validate `Origin` and answer 403. So the
obvious move is to construct the settings object explicitly:

```python
FastMCP(..., transport_security=TransportSecuritySettings())
```

That server answers **421 Misdirected Request to every request**, including
perfectly valid ones. The defaults are `enable_dns_rebinding_protection=True`
with `allowed_hosts=[]` and `allowed_origins=[]` — protection on, allowlist
empty, so nothing passes. And the failure is checked on `Host` first, so the
log says:

```
WARNING  Invalid Host header: 127.0.0.1:8000
HTTP/1.1 421 Misdirected Request
```

You are thinking about `Origin`. The error is about `Host`. The header you
were reasoning about is not mentioned.

Meanwhile, **omitting the parameter entirely** gives correct, sensible
behaviour — 403 for a bad origin, 200 for a good one. So the explicit-security
path is strictly worse than doing nothing, which is the opposite of what a
developer expects when reaching for a security type.

Reproduction:

```python
# 421 for every origin, valid or not
FastMCP(name="p", transport_security=TransportSecuritySettings())

# 403 for a bad origin, 200 for a good one
FastMCP(name="p")
```

**Suggestion:** if `enable_dns_rebinding_protection=True` and both allowlists
are empty, either raise at construction ("protection is enabled but no hosts
or origins are allowed; nothing will be accepted") or fall back to the
localhost defaults the SDK already uses when the parameter is omitted. Failing
closed is right; failing closed silently, on a different header than the one
the developer is configuring, is what costs the hour.

---

## 2. "The MCP Toolkit is available in the United States" — availability of what?

**Severity: high — it changed our architecture.**

The [MCP Toolkit overview](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-overview.html)
states, without elaboration:

> The MCP Toolkit is available in the United States.

It is not clear whether this scopes **customer availability** (where Alexa+
users can install add-ons) or **developer access** (who may build). The
[quickstart](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html)
names no geographic restriction at all, offers a web simulator, and takes
distribution countries as a field in `addon.json` — all of which suggests the
former. But it never says so.

We are building from Malaysia. That single unlabelled sentence was the largest
open risk in the project for several hours, and we ended up designing around
it rather than resolving it.

**Suggestion:** one clause. "Add-ons are available to customers in the United
States; developers may build and test from any country" would have removed the
ambiguity entirely.

---

## 3. The most important alternative is in the rules, not the docs

**Severity: medium.**

The hackathon rules permit *"a simulated Alexa+ experience"* in place of a
certified add-on. That is a very significant option — it removes certification,
LWA onboarding, store listing assets and US distribution from the critical
path — and it appears only in the rules text.

Nothing in the Alexa+ developer documentation mentions that a simulated
experience is an acceptable deliverable, so a developer who starts from the
docs (which is the natural entry point) discovers the full certification
requirements first and may reasonably conclude the track is out of reach.

**Suggestion:** surface the simulated-experience path in the track description
on the hackathon page, next to "self-hosted MCP server or Agent Skill", rather
than only in the rules.

---

## 4. The 500 ms latency requirement is easy to miss

**Severity: medium — it is an architectural constraint, not a detail.**

> Your MCP server must meet a round-trip query response latency of less than 500 ms.

This appears in the quickstart, and not in the hackathon rules or the track
description. It is the single most design-shaping requirement in the whole
track: it effectively rules out calling a language model on the request path,
which changes what an add-on can be.

We found it early and built around it — the entire fast/reasoning path split
exists because of it. A team that found it in week five would have to rebuild.

**Suggestion:** put it in the track requirements, not only in the quickstart.

---

## 5. `addon.json` requires six icon sizes, listed unsorted

**Severity: low, but it reads like a typo.**

> All 6 sizes required: 72x72, 64x64, 88x88, 126x126, 180x180, 241x241

64 comes after 72, and 241 is an unusual number. Both make the list look like
an error rather than a specification, which costs a second read and a moment of
doubt about whether the docs are current.

**Suggestion:** sort them ascending. If 241 is deliberate, a parenthetical
would stop people wondering.

---

## 6. Certified add-on requirements are a product launch, not a hackathon task

**Severity: informational — we chose the other path because of this.**

A certifiable add-on needs, at minimum: OAuth 2.1 authorization-code flow with
PKCE (S256), Protected Resource Metadata at
`/.well-known/oauth-authorization-server`, `401` + `WWW-Authenticate` discovery,
the `resource` parameter on both authorize and token requests, six icons, a
600x900 carousel image, a live privacy policy URL, a live terms of use URL, and
Amazon's certification review.

None of that is unreasonable for a shipping commercial integration. All of it
together, inside a hackathon window, is a different project from the one being
judged — and certification review is a queue outside the entrant's control.

We built the spec-compliant server and presented it through the permitted
simulation. The server is ready for certification; the submission does not
depend on it.

**Suggestion:** a "hackathon minimum" note in the docs — which of these are
needed to *run and test* an add-on, versus to *publish* one — would let people
plan. The two lists are very different sizes and the docs present them as one.

---

## 7. Documentation pages that did not load

**Severity: low, but it forced a research detour.**

- `amazonappdev2026.devpost.com/details/alexaplus` → 404
- Amazon's "About Remember This with Alexa+" help page → **503**, repeatedly,
  across a session

The second one mattered. We were trying to establish what Alexa+ memory can
already do, so as not to claim a gap that does not exist. Unable to reach the
authoritative page, we had to triangulate from secondary sources — one of which
turned out to be an article from **2018**, describing a limitation Amazon has
since fixed. We nearly built positioning on an eight-year-old constraint.

**Suggestion:** none for the 503 beyond uptime. But it is worth knowing that
when the official page is unreachable, the search results that replace it can
be very stale, and stale documentation about a memory product is a specific
hazard.

---

## 8. Streamable HTTP returns SSE by default, and the client has to know

**Severity: low.**

With `json_response=False` (the default), `tools/call` responses come back as
`text/event-stream`, so a browser-based MCP client must parse SSE rather than
`await res.json()`. This is correct per spec — clients MUST handle both — but
the SDK docs are written from the server's point of view, and the client-side
consequence is not called out.

Our simulator handles both content types in about ten lines. Finding out it
needed to took longer than writing it.

**Suggestion:** a short "what your client must handle" note in the Streamable
HTTP section.

---

## 9. Testing needs the lifespan run manually

**Severity: low.**

`streamable_http_app()` returns a Starlette app whose session manager starts in
the lifespan. Driving it with `httpx.ASGITransport` in a test does **not** run
the lifespan, so every request fails until you wrap the client in
`app.router.lifespan_context(app)`. The failure mode does not point at the
lifespan.

**Suggestion:** one line in the testing docs, or a `create_test_client` helper.

---

## What worked well

Worth saying, since a friction log with no positives is not a report, it is a
complaint:

- **The SDK's tool decorator is genuinely pleasant.** Type hints become the
  JSON schema, the docstring becomes the description, and six tools took about
  forty lines. Nothing about it needed looking up twice.
- **Streamable HTTP session handling is invisible in the good way.** Session
  ids, `202 Accepted` for notifications, and SSE framing all worked correctly
  without us touching them, which is why the conformance tests passed first run.
- **The spec itself is unusually clear about MUSTs.** Writing conformance tests
  was mechanical because the requirements are stated as requirements —
  `MUST validate Origin`, `MUST respond 403` — rather than as prose to be
  interpreted.
- **`mcp.custom_route`** made mounting the simulated experience on the same
  origin as the MCP endpoint a two-line job, which is what let the demo page be
  a real MCP client instead of a proxy.

---

## 10. MCP Apps works with the SDK, but you assemble it by hand

**Severity: low — added after implementing the visual timeline.**

The [MCP Apps extension](https://github.com/modelcontextprotocol/ext-apps)
(SEP-1865) is production-ready and Alexa+ supports it, which makes it the right
way to put a visual on an Echo Show. The Python SDK has no helper for it —
there is no `@mcp.ui_resource` or equivalent — but it does not need one:
`@mcp.resource(..., meta=...)` and `@mcp.tool(..., meta=...)` both take
arbitrary metadata, so the whole extension is expressible today:

```python
@mcp.resource("ui://memory/timeline", mime_type="text/html;profile=mcp-app",
              meta={"ui": {"csp": {...}, "permissions": {}}})
def timeline_view() -> str: ...

@mcp.tool(meta={"ui": {"resourceUri": "ui://memory/timeline",
                       "visibility": ["model", "app"]}})
def timeline(about: str) -> Timeline: ...
```

Two things cost time:

**A bare `-> dict` cannot be structured output.** MCP Apps views read
`structuredContent`, so the tool must return something with a schema. Returning
`dict` raises `InvalidSignature: return type <class 'dict'> is not serializable
for structured output` — a good error, once you know that structured output is
what you needed. Nothing connects "my UI receives nothing" to "your return type
has no schema". A Pydantic model fixes it.

**Nothing in the Alexa+ docs shows an MCP App end to end.** The quickstart says
"for visuals, follow the MCP Apps standard", which is correct and is the whole
of it. Given that half the current Echo line-up has a display, a worked example
— server side and view side — would likely change what people build.

**Suggestion:** an MCP Apps example in the Alexa+ docs, and a note in the SDK's
structured-output error pointing at the extension, since that is the most
likely reason someone hits it.

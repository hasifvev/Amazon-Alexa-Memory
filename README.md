# Memory — history-aware memory, simulated Alexa+ presentation

**Alexa+ track · Build, Ship, Shape: Amazon Developer Hackathon · MIT**

A genuine Streamable HTTP MCP server with a browser-based simulated Alexa+ experience. It distinguishes an answer that **changed** from a belief that was **wrong**, answers historical questions, and shows a visual timeline.

**Synthetic demo only. Not an Amazon-certified add-on or tested Echo integration. Speaker selection is not authentication. Do not enter personal information into a publicly shared instance.**

## Run locally

Python 3.11 or later. Verified here on Windows/Python 3.14.7; other runtime/OS combinations require their own checks. Use one process and one worker.

```bash
python -m venv .venv
# Windows Git Bash:
source .venv/Scripts/activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
export MEMORY_STORE=data/synthetic-demo.jsonl
export MEMORY_DEMO=1
export MEMORY_BEDROCK=0
python -m server.app
```

Open http://127.0.0.1:8000. `MEMORY_DEMO=1` explicitly seeds invented history and enables an archive-and-reset button. Without it, no history is seeded and reset is refused. `MEMORY_STORE` must be a dedicated disposable demo path, never a personal log.

MCP 1.30.0 is pinned (it fixes the unbounded stateful-session advisory in 1.29.0, and SDK2 renamed FastMCP). certifi 2026.10.19 and Starlette 1.7.0 are pinned after dependency audit; compatibility and actual server/browser journeys were exercised. Install dev requirements for tests/benchmark:

```bash
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python -m pytest -q
python -m compileall -q core server tests scripts
python -m pip check
python -m pip_audit
python scripts/benchmark_mcp.py
```

## Try it

- “what is standup” — current value with previous value/change date.
- “what was standup 100 days ago” — old value, not today's value.
- “show me the history of standup” — actual MCP resource read and sandboxed timeline.
- “what have I been wrong about” — withdrawn beliefs and duration.
- “change standup to eleven” — keep the old valid window.
- “forget standup” — withdraw belief, retain the record.
- “add oat milk to my shopping list”, then “add milk to my shopping list” — distinct items.
- “remember the visitor code is DemoCase until tomorrow” — subject-local expiry.
- “tell Aisyah dinner is at seven”, switch speaker, “daily brief”.

All preseeded names/values are invented. Historical dates move relative to seed time. Fixed-date transcripts are illustrative, not a claimed current output.

## Real execution path

```text
browser text / optional microphone
 -> /api/chat (selection only; inference off by default)
 -> validated selection or local grammar
 -> MCP initialize / tools/call at /mcp
 -> deterministic MemoryTools -> fsynced append-only log
 -> spoken text + resources/read -> sandboxed timeline
```

The protocol panel shows real MCP requests/responses. Routing time and MCP tool time are measured separately. No assertion that the simulation is identical to Alexa's internals.

The server exposes **20 tools**: catch_me_up, remember, recall, correct, forget, what_changed, wrong_about, remember_for, share, shared_with_me, what_moved, timeline, what_time_is_it, add_to_list, get_list, remove_from_list, track, daily_brief, my_projects, set_profile. `timeline` advertises `ui://memory/timeline` and returns structured data plus spoken text.

## Memory semantics and integrity

- Valid time: when a fact described the world. Belief time: when it was believed.
- Correction closes the earlier value's valid window; withdrawal ends belief without erasing history.
- Correction preserves ephemeral expiry; effective validity uses the earliest deadline/changeover.
- Single-writer OS lease plus in-process RLock prevents competing projections/branching.
- Torn-tail recovery archives the damaged log before repairing the append boundary.
- Demo reset archives the old log and reseeds the same shared holder; auxiliary APIs agree with MCP afterward.
- Current snapshot import/export intentionally **does not preserve correction/retraction event history**. Copy/archive the complete log while the process is stopped for history backup.

## Auxiliary endpoints

| Endpoint | Contract |
|---|---|
| POST /api/chat | Routing selection only; never mutates/executes a tool |
| GET /api/reminders?hours=24&who=default | Current expiring facts; hours0–720, finite |
| GET /api/stats?who=default | Temporally correct selected-subject counts |
| GET /dashboard?who=default | Selected-subject dashboard |
| GET /api/export?fmt=json&who=default | Version1 current snapshot; `fmt=md` readable snapshot |
| POST /api/import?who=default | Complete validation before writes, <=200 records,128KiB body, selected subject only |
| POST /api/seed | Explicit synthetic-demo archive/reset only |
| GET/POST /api/webhook/telegram | Optional bridge status/authenticated webhook |

Missing subject defaults to `default`, never every household member. Export/import is idempotent for identical IDs and refuses conflicts. A disk failure partway through import is not rollback-atomic.

## Safety and limitations

Host/Origin allowlists protect MCP and custom routes. Bodies are capped128KiB, input text2,000characters, requests/rate/concurrency bounded. Default host/origin is localhost; use exact `MCP_ALLOWED_HOSTS` and `MCP_ALLOWED_ORIGINS` when changing origin/port (see [deployment runbook](docs/deployment-runbook.md)). Missing Origin is allowed for native clients; it is not authentication.

The public demo is shared synthetic state, not private household storage. OAuth identity/authorization, certified Alexa onboarding, distributed/multiworker storage and production retention policy are out of scope. A network-exposed deployment additionally requires HTTPS, operational monitoring and explicit approval.

**Bedrock:** optional `MEMORY_BEDROCK=1`, off by default. Nova Micro/Haiku route text; no inference occurs in MCP tool execution. Enabling sends entered text to AWS and can incur charges. Capacity is bounded, not a monetary spend cap. Real provider calls were not exercised in this completion pass; mocks verify handling only.

**Voice:** optional browser SpeechRecognition. Unsupported browsers and permission denial retain typing. Real microphone/transcription quality and external speech-service privacy were not verified here.

**Telegram:** disabled without both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_WEBHOOK_SECRET`. Register webhook with Telegram's `secret_token`; transport verifies `X-Telegram-Bot-Api-Secret-Token` before reading its body. Private chats use stable numeric `tg:<sender_id>` identities. Offline grammar covers remember/recall/withdraw/list/brief; not full browser intent parity. Replay cache is process-local and resets on restart. Real bot configuration/messages were not exercised. Supply credentials through approved secure runtime tooling, never commit them.

## Verification status

Verification on 2026-10-23 in a fresh isolated environment built from `requirements.txt` + `requirements-dev.txt`: **140 tests passed** (backend, HTTP-fixture browser and actual localhost server/browser journeys with reset, snapshot import and process restart). `docs/qa/2026-10-21-verification/verify_catalogue.py` passes **24/24** wire scenarios across all 20 MCP tools and **60/60** natural-language routing cases (47/60 before the routing repairs). `pip check` and `pip_audit` report no broken requirements and no known vulnerabilities. The actual journey uses genuine MCP traffic, not mocked responses. Full functional checkback, explicit core/server compile, dependency consistency and audit passed.

See [QA evidence](docs/qa/2026-10-08-completion.md). Local benchmark covers50 actual localhost `catch_me_up` calls; it is not remote/Echo latency evidence. Benchmark output is reproducible via the command above.

## Layout and submission

- core/: local, dependency-free memory/wake implementation.
- server/app.py: official FastMCP registration/application entry point.
- server/api.py and safety.py: bounded auxiliary routes and transport guards.
- server/tools.py: deterministic voice-shaped operations.
- web/: simulated MCP client, dashboard and MCP Apps timeline.
- tests/: backend, fixture browser and actual localhost journeys.
- docs/: decisions, QA, handoff, submission text and demo script.

Preserved earlier README: [archive](docs/archive/README-before-completion-2026-10-08.md).

[Submission draft](docs/submission.md) · [Demo script](docs/demo-script.md) · [Friction log](FRICTION.md) · [Remaining gates](TODO.md).

No live deployment, Git publication, repository visibility change, video upload or Devpost submission was performed by this local completion pass. Official rules checked2026-10-08 permit a simulated Alexa experience; deadline **23October2026 noonPacific**. Primary-track source can be public or shared privately with required judges; final access/video/submission gates remain owner actions.

MIT — [LICENSE](LICENSE).

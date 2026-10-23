# Alexa Hackathon Completion Implementation Plan

> For agentic workers: implement task-by-task using executing-plans or subagent-driven-development; use test-driven-development and functional-verification. Do not commit, push, deploy, change repository visibility, send Telegram messages, invoke paid cloud APIs, or submit externally without separate explicit authorization.

**Goal:** Finish and verify the existing Alexa+ hackathon simulation and genuine MCP server, with reproducible installation, correct historical memory, safe synthetic-demo boundaries, complete browser journeys, and an evidence-backed submission package.

**Status:** APPROVED by Lord Hasif: “proceed aprove”, recorded 2026-10-08T06:27:24+08:00 in this session. Covers local implementation on the existing working tree, verification, and submission-document preparation; no commits or external actions.
**Owner:** Lord Hasif.
**Parent:** C:/Users/hasif/Documents/Aria-MemoryCore/plans/active/2026-09-08-memory-substrate-dual-hackathon.md (approved v3; Alexa portions only).
**Root:** C:/Users/hasif/Documents/Projects/Projects/Amazon-Alexa-Memory.
**Baseline:** main 582b189; clean tree. Fresh unconstrained install fails collecting transport tests on mcp2.x. With mcp1.29.0/Starlette0.52.1, baseline is 43 passed / 2 failed (bad Origin accepted and rebinding protection off).
**Architecture:** Preserve the official FastMCP v1 Streamable HTTP implementation and deterministic memory tools. Freeform routing returns a validated tool selection only; the browser executes the result through the real MCP endpoint. Keep one process/one worker with coordinated in-process writes, bounded HTTP inputs, and explicit synthetic demo operation. Do not claim authenticated household privacy or certified Alexa/device integration.
**Stack:** Python >=3.11, FastMCP1.29 API, Starlette/Uvicorn, Pydantic, optional boto3 and Telegram, HTML/CSS/JS, pytest/httpx, browser automation.

```text
browser: text / optional mic
  -> routing endpoint (deterministic default; optional Bedrock)
  -> validated selection + pinned speaker
  -> MCP initialize / tools/call / resource read
  -> deterministic MemoryTools -> coordinated append-only store
  -> spoken result + sandboxed timeline

same store holder -> scoped reminders / stats / snapshot transfer
explicit synthetic-demo reset -> archive old log -> reseed -> same holder
optional authenticated Telegram webhook -> stable sender id -> same validated dispatch
```

## Definition of done and scope

- [ ] Fresh isolated dependency installation can start server and collect/run all tests.
- [ ] Complete existing tool inventory verified programmatically, not copied from README counts.
- [ ] Invalid Origin/Host refused for MCP; custom-route mutation guards, body/text limits and rate/concurrency controls tested.
- [ ] Synthetic shared-demo warning explicit. Speaker selection is scoping, not authentication. Personal production and certification excluded.
- [ ] Bedrock disabled by default; no paid traffic during tests. Test fixtures are labeled tests, never represented as real provider evidence.
- [ ] Remember/correct/withdraw/history/expiry/list/profile/share/brief workflows are truthful and stable under repeated or malformed input.
- [ ] Reset never deletes a prior memory log and all API/MCP projections remain consistent afterward.
- [ ] Export/import explicitly labeled current snapshot transfer unless a separately tested event-history backup is implemented. No unsupported history-preservation claim.
- [ ] Telegram disabled unless explicitly configured, webhook authentication required, stable numeric identity, private-chat policy and replay protection tested with local fixtures.
- [ ] Browser text flow, speaker switch, daypart override, dashboard, reminder actions, snapshot import/export, visual timeline, and error/reentrancy paths exercised on desktop/mobile layouts.
- [ ] Voice unsupported/permission errors preserve typing; real microphone/transcription quality remains an owner/device check unless actually exercised.
- [ ] Full pytest, functional checkback, browser assertions, compile and dependency checks recorded; no phantom success.
- [ ] README, changelog, checklist, handoff, session/decision records and submission description/demo script agree with evidence.
- [ ] Live deployment, public video, judge access, repository sharing and final submission separately marked VERIFIED or BLOCKED; local green does not imply external completion.

## Task 1 — Reproducible baseline and completion ledger
**Files:** requirements.txt; create requirements-dev.txt, CHANGELOG.md, TODO.md, docs/handoff.md, docs/sessions/2026-10-08-completion.md, docs/decisions/2026-10-08-simulation-boundary.md.
- [ ] Preserve pre-edit tracked source in a dated scratch Git bundle and record its SHA256; do not copy ignored memory/credential files.
- [ ] Regression: verify declared requirements cannot install MCP2 while code uses FastMCP1 APIs. Preserve the actual fresh-install failure already observed as red evidence.
- [ ] Bound runtime compatibility (`mcp>=1.29,<2`, `starlette>=0.47,<1`) and declare test/browser tooling separately. Pin tested versions where warranted by actual dependency audit.
- [ ] Fresh venv install/run pytest; compare to baseline rather than assuming current scratch packages prove install correctness.
- [ ] Record all remaining acceptance gates in TODO.md and handoff; do not call the project completed.

## Task 2 — Transport and custom API safety
**Files:** server/app.py:64-96 and custom routes; server/llm_router.py:228-274; new server/http_safety.py; tests/test_transport.py; new tests/test_api_safety.py and tests/test_router.py.
- [ ] Run existing failing Origin/enabled-protection tests before restoring protection with explicit localhost/deployment allowlists.
- [ ] Add ASGI tests for bad custom-route Origin/Host, invalid JSON/root shapes/field types, oversized bodies, nonfinite/negative/excessive reminder hours, quota rejection, and concurrency bounds. Unsupported input returns bounded 4xx without store mutation or inference.
- [ ] Implement one reusable validation/guard layer; apply to reset/import/chat/webhook rather than fixing one route only.
- [ ] Validate model output against known tool names and argument types; model-generated `who` cannot override selected speaker. Invalid output falls back safely before execution.
- [ ] Explicit offline routing default and bounded optional inference; move synchronous provider work off event loop. Remove full-user-text router logging and path exposure from stats.
- [ ] Run focused safety/transport/router tests with provider calls prohibited.

## Task 3 — Persistence, reset, and temporal integrity
**Files:** core/store.py:187-285,326-332; server/demo.py:75-87; server/app.py reset/export/import/stats; new tests/test_store_integrity.py and tests/test_api_features.py.
- [ ] Write red tests: supersession before explicit expiry yields only replacement now and correct old value before changeover; torn-tail reopen->append->reopen preserves complete events; concurrent duplicate/correction has one winner and replay matches live state.
- [ ] Use earliest effective validity end; preserve expiry when correcting ephemeral facts. Coordinate writes with a reentrant single-process lock, document and enforce one-worker runtime. Do not claim multiworker durability.
- [ ] Preserve incomplete-tail bytes in dated recovery archive before repairing append position; never silently delete memory evidence.
- [ ] Reset must require explicit synthetic-demo configuration, archive old log, and replace the shared store holder used by all API/tool views; no production/personal reset endpoint.
- [ ] Red ASGI tests: reset clears marker from every view; import after reset visible everywhere and after reopen; expired/future-valid records are not live in per-subject stats.
- [ ] Snapshot transfer: scope reads/writes to selected subject including explicit default; reject malformed version/records/types and conflicting IDs before mutation; idempotent repeat import. Expose the limited current-snapshot contract clearly.
- [ ] Rerun store/features/transport tests after each fix.

## Task 4 — Truthful spoken workflows and optional Telegram
**Files:** server/tools.py:63-165,413-494,845-978,982-1162; server/telegram_bridge.py; new tests/test_tool_features.py and tests/test_telegram.py.
- [ ] Red tests for share appearing in daily brief; exact list item identity; blank removal no mutation; repeated remember/profile/project operations; false “updated” acknowledgement; local-day expiry and valid timezone range; numeric/spoken time references actually advertised.
- [ ] Implement minimal truthful fixes: reuse shared-tag constant; use exact normalized list identity; acknowledge add versus correction honestly; validate timezone/profile keys before write; calculate relative expiry in subject-local fixed-offset time; mark timeline expired/scheduled states distinctly.
- [ ] Telegram tests with all sends/provider calls mocked: reject missing/invalid webhook authorization, numeric sender IDs remain stable across name changes, duplicate update does not write/send twice, group chats refused, malformed updates safe.
- [ ] If Telegram is not configured it remains disabled, and setup docs cannot claim active integration. Remove token-bearing exception logging. No actual tokens/messages used during this task.
- [ ] Run spoken/Telegram feature tests and existing historical-memory tests.

## Task 5 — Real MCP browser execution and safe visual journeys
**Files:** web/index.html:199-252,255-450,453-673; web/dashboard.html:113-181; web/timeline.html:70-153; new tests/test_browser.py and browser support fixtures as needed; server/app.py chat endpoint.
- [ ] Red browser test: routing-only `/api/chat` selection leads to exactly one genuine MCP `tools/call`, on both deterministic and mocked-Bedrock routing paths. Distinct routing/tool timing shown, no fake traffic or guaranteed50ms claim.
- [ ] Add browser red tests for literal HTML/quotes in protocol/reminders/dashboard, speaker-scoped reminders/export/import including default, conversation clearing/partition, selected speaker pinned across delayed requests, busy guard, morning/night parity and visible request/tool/startup/reset/import errors.
- [ ] Render user-derived values with textContent/event listeners instead of unsafe interpolation/inline handlers. Snapshot request speaker/hour; guard all entry points, not just disabled Ask button.
- [ ] Fix regex intent collisions (correction vs project tracking, greeting vs daily brief), preserve original user argument casing, and test explicit displayed suggestions.
- [ ] Timeline resource: genuine resources/read, sandboxed iframe host bridge; initialize success must send initialized notification before size/results. Pin postMessage source and render safe structured data; do not introduce arbitrary network/resource permissions.
- [ ] Voice unsupported/permission denial fixtures must retain accessible keyboard/text flow and persistent feedback. No claimed real speech-service validation from a fixture.
- [ ] Run actual local server against disposable synthetic scratch store, with inference disabled; exercise real browser at desktop and mobile widths. Capture console/page/network failures and test counts in an evidence log.

## Task 6 — Verification and submission-ready package
**Files:** README.md; FRICTION.md append-only clarification; CHANGELOG.md; TODO.md; docs/handoff.md; docs/submission.md; docs/demo-script.md; docs/qa/2026-10-08-completion.md; docs/deployment-runbook.md; optional pinned CI workflow only if justified by tooling discovery.
- [ ] Run full suite with isolated MEMORY_STORE and no paid inference. Run `scripts/audit/checkback.py --path <project> --strict` using isolated interpreter/PATH, plus compile/dependency checks. No hidden skip counted as pass.
- [ ] Independent final review of code diff and browser/protocol evidence; fix regressions with red tests, not claim-by-inspection.
- [ ] README setup, actual tool/test counts, synthetic/privacy boundary, snapshot limitation, one-worker restriction, optional Bedrock/Telegram and simulation-versus-certification statements updated from evidence.
- [ ] Draft English project description, tool feedback, provenance/update disclosure and under3minute demo script emphasizing correction vs withdrawal and genuine MCP traffic.
- [ ] Record current primary-source rules: https://amazonappdev2026.devpost.com/rules — Oct23 2026 12:00 Pacific deadline; primary-track private repo judge-sharing allowed; video public YouTube/Vimeo and <3min; judging access through Nov20. Old Oct24/public-required reminder is superseded, never silently treated as current.
- [ ] Provide deployment runbook with exact tested startup/config and rollback. Live AWS change requires separate explicit approval and AWS skill/credential discovery; do not invent current service state from September notes.
- [ ] Prepare final artifacts and list external gates honestly. Public video/upload, judge invitations, repository visibility and Devpost submission remain owner-approved external actions.

## Verification commands
Run from the Alexa project root, using the scratch venv executable; native Windows forward-slash paths under Git Bash.

```bash
export MEMORY_STORE=C:/Users/hasif/AppData/Local/hermes/cache/scratch/alexa-verification-memory.jsonl
export AWS_EC2_METADATA_DISABLED=true
C:/Users/hasif/AppData/Local/hermes/cache/scratch/alexa-venv/Scripts/python.exe -m pytest -q
C:/Users/hasif/AppData/Local/hermes/cache/scratch/alexa-venv/Scripts/python.exe -m compileall -q core server tests
C:/Users/hasif/AppData/Local/hermes/cache/scratch/alexa-venv/Scripts/python.exe C:/Users/hasif/Documents/Aria-MemoryCore/scripts/audit/checkback.py --path C:/Users/hasif/Documents/Projects/Projects/Amazon-Alexa-Memory --strict
```
Browser command and dependency audit command must be finalized from installed tooling, not guessed. Expected final result is exit0 for each applicable gate, with exact assertion/test counts retained. Any unexecuted gate is explicitly pending.

## Approval gate
Estimated >=12 existing/new code/test files plus required documentation; architectural change is routing-only chat plus single shared store holder/guards. Diagram provided above. No execution of this plan until Lord Hasif approves; approval phrase and timestamp must be appended to this document. Subsequent deployment/publication/submission permissions are separate.

Approval recorded above. Pre-edit tracked-source backup: `C:/Users/hasif/AppData/Local/hermes/cache/scratch/alexa-before-completion-20261008.bundle`; SHA256 `b965fe5b9541215007ce5885db2a85a9c08339e68d002afb8a5860eaf057a3be`. Ignored runtime memory and credentials were not copied.

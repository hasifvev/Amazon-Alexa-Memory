# Submission draft — Memory

**Track:** Alexa+. **Status:** local candidate verified 2026-10-23; not yet pushed or submitted. Intended path: simulated Alexa+ browser experience backed by a genuine self-hosted MCP server.

## Elevator pitch
An assistant should know not only today's answer, but what changed, what was wrong, and when nothing was known. Memory gives remembered facts a history.

## Inspiration
A single current value cannot distinguish a moved meeting from a mistaken recollection. We built two timelines—when a fact described the world and when it was believed—to make those differences observable.

## What it does
The browser uses real MCP initialization, tools/call and resource reads. Twenty deterministic tools remember, correct, withdraw, recall past values, share synthetic household messages, maintain lists/profiles/projects and brief the user. A sandboxed timeline shows replaced, withdrawn, expired and scheduled records. Snapshot transfer, scoped dashboard/reminders and optional voice improve the demo flow.

## How it was built
Python's official MCP SDK 1.30.0 with Streamable HTTP 2025-11-25, Starlette/Uvicorn and a dependency-free local memory core. Stored operations are fsynced; one-writer leases/locks coordinate state. Browser routing and tool execution are separate. Optional Bedrock integration selects tools but is off by default; all browser tool execution uses MCP. Telegram is optional, disabled unless bot and webhook secret are configured.

## Verified locally
140 tests passed in a fresh isolated environment built from the declared requirements (2026-10-23). All 20 MCP tools pass 24/24 wire scenarios over real HTTP, and 60/60 natural-language routing cases pick the expected tool, including read questions that must not write. Host/Origin, malformed/body limits, temporal truth, writer recovery, scoped API and Telegram security cases are tested. `pip check` and `pip_audit` report no known vulnerabilities. Current benchmark is localhost only; no remote/Echo latency claim.

## Significant in-window updates
Baseline Git582b189 introduced six demo/API features. October8 closure added installation bounds/audited framework upgrade, guarded APIs, routing-only chat with actual MCP browser execution, archive reset/shared projection consistency, corrected ephemeral validity/recovery/one-writer semantics, strict snapshot validation, truthful/idempotent spoken operations, stable authenticated optional Telegram, safe rendering/visual handshake and automated browser journeys. Exact Git history and CHANGELOG preserve prior-work disclosure; owner must review originality/provenance before submission.

## Feedback
Official SDK tool schemas/session transport simplify implementation. SDK2 naming changes broke an unbounded dependency install; pinning and fresh-install tests fixed it. Explicit transport Host/Origin allowlists are necessary. Test ASGI lifespan explicitly. MCP Apps structuredContent/initialization ordering needs end-to-end verification. Current framework dependency audit forced a patched Starlette version; handshake and actual browser integration confirmed compatibility. Would build with the SDK again: yes, with pinned versions and conformance tests.

## Honest boundaries
Synthetic shared simulation, not private production or certified/device-tested Alexa add-on. Speaker selector is not identity. Snapshots exclude full event history. Voice fixtures are not real microphone proof. Optional Bedrock/Telegram completion tests did not call cloud/send real messages. No hosted deployment is part of this submission; judges run it locally from the README.

## Mini challenges
AWS Builder: integration exists in code, but claims must be tied to verified prior AWS evidence or a separately authorized live check; do not imply this closure exercised Bedrock/EC2. Open Source: requires additional public contribution URL and ownership verification; no publication performed here.

## Required owner-provided/verified links
- Source repository plus public visibility or required private judge invitations.
- Working candidate demo URL if presenting hosted access; current target unverified.
- Public YouTube/Vimeo video under3min, English, actual functioning footage, licensed assets.
- Additional open-source contribution URL if entering that mini-challenge.

Official rules: https://amazonappdev2026.devpost.com/rules (checkedOctober8). DeadlineOctober23 noonPacific, judging access throughNovember20. Final entry/legal eligibility/platform account acceptance belongs to owner.

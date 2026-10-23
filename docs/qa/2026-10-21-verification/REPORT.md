# Alexa Memory — complete feature inventory and submission review

Prepared by Aria for Lord Hasif on October 21, 2026 (MYT). Application fixes are proposed, not applied. Scope: current Windows checkout, actual isolated localhost service, actual browser journeys, official rules and signed-in GitHub inspection. Personal runtime data was not read.

**Verdict: functioning local prototype, not ready for submission.** All 20 MCP tools work when called with valid explicit arguments. Natural-language routing still produces incorrect writes, the daily brief inflates fact counts, the declared MCP pin has an advisory, and the submitted source/video/access package is incomplete.

Production-audit heuristic: **60/100, blocked for submission in its present state**. This is a prioritization judgment, not a measured probability or production certification. A private household service is outside the approved synthetic-demo architecture.

## Current evidence

| Area | Result | Evidence / limit |
|---|---|---|
| Existing test suite, original environment | PASS | 120 passed, one upstream settings warning, 32.54 s. |
| Declared dependencies after fresh isolated installation | PASS for behavior | Final uncontaminated run: 120 passed, one warning, 22.41 s. See declared-deps-suite.xml. |
| Compile and dependency consistency | PASS | core/server/tests/scripts compile; pip check reports no broken requirements. |
| Full advertised MCP catalogue | PASS | 20/20 tool names enumerated and exercised, 24/24 scenario checks, real HTTP and disposable state. See acceptance-clean.json. |
| Independent official SDK client | PASS | MCP 2025-11-25 initialize, 20 tools, remember/recall and timeline resource read. See official-sdk-client.json. |
| Browser default-language routing | FAIL | 60 targeted cases, 47 selected the expected tool, 13 did not. Includes advertised formulations, natural paraphrases and a contextual phrase; not a statistical accuracy estimate. |
| Actual browser journeys | PASS within tested scope | Genuine MCP calls/resources, timeline handshake, scoping, reset, import and process restart. 19 additional fixture-browser cases are clearly separate from the actual-server journey. |
| Responsive checks | PASS within tested scope | Additional real-server checks covered chat, timeline and dashboard at 375, 768 and 1440 CSS pixels: all 9 surface/width checks passed, no page errors. See responsive-surfaces.json and dashboard screenshots. Visual inspection exposed additional UX issues; layout assertions are not a complete design review. |
| Daily brief fact count | FAIL | One stored fact yields “1 new memory”; two recalls change this to “3 new memorys.” See semantics.json. |
| Original environment dependency audit | FAIL | mcp 1.29.0: CVE-2026-59951; certifi 2026.7.22: PYSEC-2026-4320. |
| Fresh declared dependencies audit | FAIL | Latest transitive certifi resolves its advisory, but mcp remains pinned to affected 1.29.0. One advisory remains. |
| Scratch dependency repair candidate | PASS | mcp 1.30.0, certifi 2026.10.19, Starlette 1.7.0: all 120 tests pass in 23.14 s; no audit advisories; pip check passes. Project requirements were not changed. |
| Localhost fast path | PASS | 50 actual catch_me_up HTTP calls: p50 3.52 ms, p95 4.02 ms, max 5.28 ms. Not Internet/Echo latency or a large-history load test. |
| Source/history credential pattern scan | No matching source patterns | 54 pre-audit current files and 17 reachable commits checked for GitHub token prefixes, AWS key IDs and private-key headers. Pattern scan does not prove absence of every possible secret. |
| Git remote credential | FAIL | A credential is embedded in the local remote URL and was exposed by remote inspection. Its value is omitted from all audit artifacts. Revoke/rotate and remove it; use a credential manager. |
| GitHub published version | FAIL | Signed-in browser shows private repository, main at 10f8c4bc6ab1e86fcb38d106bc7712dba39a6c17. Local HEAD is 582b189 plus 12 modified files and 19 untracked top-level status entries before this audit. |
| Judge access | FAIL in current private state | After owner re-authentication, GitHub Collaborators page showed “0 collaborators” and “You haven't invited any collaborators yet.” Owner subsequently chose public source after checks/audit pass. No invitations or visibility changes made. |
| Hosted candidate | NOT CREATED | Owner confirmed; not a submission requirement for the chosen path. |
| Public demo video | NOT CREATED | Owner confirmed. Recording script is not a video. |
| Devpost project/submission | NOT CREATED | Owner confirmed. Local submission.md is a draft. |
| Real microphone/transcription | NOT VERIFIED | Browser support and permission-error behavior tested; human speech recognition has not been exercised. |
| Live Bedrock inference | NOT VERIFIED | Provider disabled; mocked error/capacity/routing tests do not verify AWS access, model availability, response quality or charges. |
| Live Telegram bot/webhook | NOT VERIFIED | Disabled local configuration confirmed. Authentication/replay/identity tests are local fixtures; no external message was sent. |
| Real Alexa/Echo integration | OUT OF SCOPE | Browser simulation path is deliberate; no certified device claim. |
| Linux / multiple workers / real household privacy | NOT VERIFIED / OUT OF SCOPE | Windows single process only; selected subject is scoping, not authentication. |

## All 20 tools

“Wire pass” means the tool was called over actual HTTP, returned a non-error result, and met the particular observable assertion in acceptance-clean.json. It does not imply every natural-language route reaches that tool.

| Tool | Wire result | Verification |
|---|---|---|
| catch_me_up | PASS | Morning catch-up returns a real seeded briefing. |
| remember | PASS | AlphaCase stored, then recalled. |
| recall | PASS | Original, corrected and withdrawn states checked; existing suite also checks historical answers. |
| correct | PASS | Explicit replacement produces BetaCase and preserves two timeline entries. |
| forget | PASS | Withdrawn marker stops answering current recall. |
| what_changed | PASS | New replacement appears in change report. |
| wrong_about | PASS | Withdrawn BetaCase appears in mistake history. |
| remember_for | PASS | TempCase stored with expiry; subject-local expiry and deadlines covered by suite. |
| share | PASS | Recipient receives the intended synthetic message. |
| shared_with_me | PASS | Aisyah reads SevenCase scoped to her subject. |
| what_moved | PASS | Reports legitimate change history; bounded summary explicitly announces omitted items. |
| timeline | PASS | Two structured versions plus actual ui://memory/timeline resource; browser renders replaced/current states. |
| what_time_is_it | PASS | Nonempty local-time reply; fixed-offset profile behavior also tested. |
| add_to_list | PASS | Oat milk and milk added as separate items. |
| get_list | PASS | Oat milk remains after exact removal of milk. |
| remove_from_list | PASS | Exact removal, not substring removal. |
| track | PASS | Explicit Acceptance project/status accepted. |
| daily_brief | PARTIAL | Valid name/personalized paragraph; separate fact-count regression fails. |
| my_projects | PASS | Explicitly tracked Acceptance project appears. |
| set_profile | PASS for explicit writes | Explicit TestPerson stored; browser incorrectly routes a read question to this write tool. |

Auxiliary endpoints independently checked: stats, reminders, JSON/Markdown snapshot export, Telegram disabled-status and dashboard all returned HTTP 200. Existing tests verify import validation/idempotency, demo-only archival reset, scope, errors and malformed/oversized input.

## Defects that matter before recording

### P1 — a read question overwrites the profile

Input: `what is my name`.

Actual browser selection: `set_profile(key="name", value="what")`. In the running browser this returned “Got it — I'll remember your name is what.” The profile declaration regex at web/index.html:318 accepts the question as if “what” were a name. Read questions must be recognized before declarations, and uncertain text must not fall through to a mutating tool.

Acceptance: asking any profile question leaves the snapshot unchanged; explicit name declarations still store the intended value; cover both browser fallback and provider-selected paths.

### P1 — correction and project intents collide

`standup moved to ten` selects `track(project="standup", status="ten")`; actual browser returned “Tracking standup as 'ten'.” The standup fact is not corrected. Conversely, `update Amazon project to submitted` selects `correct` instead of `track`.

Acceptance: changes to an existing remembered fact preserve its historical chain; explicit project updates modify the project; ambiguity asks a clarifying question without writing. Centralize parsing or share a common contract rather than maintaining divergent browser/Telegram/provider grammars.

### P1 — patch the dependency pin and remove credential exposure

The application's `stateless_http=False` selects the affected stateful transport. The official MCP advisory describes unbounded retained sessions before 1.30.0. Request-rate limits are not a substitute for session expiry/cleanup. Upgrade to the scratch-tested 1.30.0 candidate, explicitly size idle-session limits for the eventual host, and rerun the audit at release. Refresh existing certificate bundles as well.

The local Git remote embeds a GitHub credential. Revoke/rotate it because it appeared in inspection output, then replace the remote with its ordinary credential-free HTTPS URL using a credential manager. The value is never reproduced here. No repository-source token match was found by the bounded pattern scan; that does not retract the configuration exposure.

### P2 — the daily brief invents new-fact counts from read events

At server/tools.py:1155, the recent-memory list includes interaction events. Reproduction with a new disposable store:

1. Remember one fact: daily brief says `1 new memory added in the last 24 hours`.
2. Recall that fact twice.
3. Daily brief says `3 new memorys added in the last 24 hours`.

Acceptance: exclude interaction events from fact/news counts, retain them in the audit history, and pluralize “memories” correctly. Match the event exclusion already used by snapshot/stat APIs.

### P2 — advertised phrasing is broader than the default grammar

Examples: `what did I miss`, `give me the full picture`, `which facts have the longest history`, `I was mistaken about standup`, and `don't let me forget ...` miss their advertised intent. `brief me` reaches the shorter catch-up, not daily_brief. The full case list and outputs are in routing-cases.json. One contextual phrase (`it is eleven now`) lacks an explicit subject; safe clarification is a better acceptance target than guessing a write.

Acceptance: table-driven coverage for all advertised phrases, polite variants, read-only questions and deliberate ambiguities. Include absence-of-write assertions, not only selected tool names.

## Product improvements, ranked

1. **Make the central promise dependable.** Correct routing and truthful brief counts before adding more capabilities. A memory product that changes a name when asked a question damages the entire pitch.
2. **Make the temporal difference visible immediately.** Show “current”, “previously true” and “withdrawn as wrong” as first-class cards with timestamps. Retain provenance and a restart demonstration. Amazon already advertises personal memory; our specific proposition is observable change history and belief correction, not the unsupported claim that Alexa cannot remember.
3. **Give judges one coherent scenario.** An invented household schedule changes from nine to ten-thirty, a past-date question still answers nine, a mistaken fact is withdrawn, another member receives a message, and state survives restart. Keep the recording under three minutes; put transport details behind an expandable inspector.
4. **Improve visual hierarchy.** The current screen has 18 suggestion chips, a full protocol pane and dense small text. The real timeline exists but can be below the conversation viewport because showTimeline appends it without scrolling it into view. Prioritize the answer/timeline, make the protocol inspector optional, and use a short guided sequence.
5. **Make the dashboard truthful and actionable.** “Memory Health” is currently live/total records; legitimate corrections or expiry lower it despite correct operation. Rename it to a factual metric or define genuine health checks. “tap to see which” has no corresponding card click handler; implement the drilldown or remove the instruction. A subject-scoped page should say selected member rather than imply whole-household totals.
6. **Make a clean judge checkout reproducible.** Align README/TODO/changelog/handoff, fix stale “pending” records, include PowerShell setup, freeze verified dependencies and add CI for installation, tests and audit. The README's sibling-repository link happens to exist locally but will not be available beside a standalone judge checkout; use a proper project URL or remove that optional reference.
7. **Keep optional integrations honest.** Bedrock and Telegram can add value only when demonstrated with real evidence. They are not required to establish the core submission. Voice currently provides optional transcription input; there is no speech-synthesis output implementation, so do not imply the browser itself speaks responses aloud.
8. **After the hackathon:** real authentication/authorization, retention/deletion controls appropriate to real users, multi-process storage and scaled-history benchmarks. The JSONL store and wake builders scan growing history; bounded output is not constant-time computation. Do not transfer this demo's privacy/performance assumptions into a production claim.

## Submission gates, checked October 21

Deadline: **October 23, 2026, noon PDT = October 24, 2026, 03:00 MYT**. The official rules permit the simulated Alexa+ path. A clear English description, working source/run instructions, required tool feedback and a public YouTube/Vimeo demonstration under three minutes are the relevant package. Source can be public with an open-source license or privately shared with required reviewers. Judge access must be maintained through the end of judging, November 20. A friction log can earn up to a 10% bonus.

The official FAQ says a locally runnable public repository plus video is sufficient; hosting and physical Echo hardware are not required. The restricted Alexa+ developer console/toolkit is unavailable to ordinary participants. Do not spend this deadline window trying to obtain it.

| Required delivery | Present state | Next action |
|---|---|---|
| Verified source at submitted GitHub revision | FAIL: old main, changes local | Repair/recheck, then owner-authorized commit and push; verify resulting revision in browser. |
| Judge source access | FAIL now; public route chosen | Owner chose public licensed source after checks/audit pass. Verify signed-out access only after the repaired candidate is approved and published. |
| Public video link | NOT CREATED | Record the actual verified build, upload and check signed-out playback/duration. |
| Description, feedback, testing instructions | DRAFT | Update facts/version/results; include clear simulation boundary. |
| Devpost entry | NOT CREATED | Prepare fields and links, obtain owner approval for submission, submit and read back status. |
| Optional AWS/Open Source mini-challenges | NOT VERIFIED | Only claim the chosen challenge when its runtime/contribution evidence and required links exist. |

Primary sources: [Official rules](https://amazonappdev2026.devpost.com/rules), [Official FAQ](https://amazonappdev2026.devpost.com/details/faqs), [MCP advisory](https://github.com/modelcontextprotocol/python-sdk/security/advisories/GHSA-84m7-p3x7-pcfv), [Certifi advisory](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2), [Amazon's Alexa+ feature description](https://www.aboutamazon.com/news/devices/new-alexa-generative-artificial-intelligence).

Owner release decision during this review: **make the repository public after all necessary checks and audit are complete.** This is a conditional release decision; the condition is not met while the reproduced defects/security gates remain open. Private reviewer invitations are therefore not the selected future delivery path.

## Evidence provenance and limitations

- Graph generation 2026-10-21T00:12:44Z; material source paths checked for freshness. Recorded excluded scopes were generated __pycache__ directories. Source reads verified behavioral claims; graph coverage is best effort, not completeness proof.
- All automated service tests used disposable synthetic stores and disabled external inference/messages. The manually inspected UI used a separate synthetic store. No personal log was read or reset.
- The initial fresh-environment run overlapped an experimental package upgrade. Its result is discarded as installation evidence. `declared-deps-suite.xml` is the later uncontaminated declared-version run; `patched-deps-suite.xml` is the completed upgrade experiment. Both are distinct from the original-environment run.
- Preliminary acceptance probes had incorrect harness assumptions: one bounded summary was expected to include an item beyond its visible limit; a rerun reused disposable state. Corrected clean-run evidence is `acceptance-clean.json`. Preliminary files are retained in scratch, not counted as product defects.
- No local app fixes, commit, push, deployment, access grant, credential rotation, paid inference, external Telegram message, video upload or Devpost submission occurred. The isolated dependency experiment does not change the requirements shipped to judges.
- “Verified” here means the named check and environment above. Real voice/provider/bot/OS/access scenarios without evidence remain explicitly unverified. Not every possible input, failure mode, accessibility requirement or load level was proven.

The parameterized `verify_catalogue.py` helper was run from its saved project location: all 24 wire scenarios passed across 20 tools; 47/60 grammar expectations passed. Its exit code is deliberately 1 while known routing failures remain. Run with `--root <checkout> --out <disposable-evidence-folder>` after installing dev requirements. Its default output is a fresh temporary folder. All 54 pre-audit source hashes were compared again after the audit and remained unchanged.

Dashboard visual evidence: [375px](dashboard-375.png), [768px](dashboard-768.png), [1440px](dashboard-1440.png). The displayed 64% “Memory Health” comes from 7 live/11 total records; it illustrates why the metric should not imply system correctness.

Verification skills: codebase-memory, production-audit and bounded secrets-detection completed. Follow-up routing: debugging-protocol for the reproduced product defects, then functional-verification against the repaired candidate. Review outcome remains subject to Lord Hasif's approval.

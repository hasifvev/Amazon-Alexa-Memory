# Verified project learning

## October 21, 2026 — catalogue coverage is not language safety

Observed: all 120 existing tests and all 20 explicit MCP tools pass, while an ordinary read question (`what is my name`) selects a write and changes the profile to `what`. Several documented correction/briefing phrases select another tool. Separately, daily brief counts read interactions as new facts.

Cause: supported tool catalogue, advertised language, browser fallback grammar and fact/event projections have different contracts. Tests cover suggestion chips and selected representative interactions but omit read-question nonmutation and some advertised phrases.

Verification: 24 real HTTP checks spanning all20tools, 60 targeted grammar cases with13expected-tool mismatches, actual browser reproduction, and a one-fact/two-recall counterexample. Full source/evidence is in [the report](qa/2026-10-21-verification/REPORT.md). Current dependency audits also show why an October8 clean audit cannot stand in for an October21 scan.

Reusable decision: retain a parameterized acceptance helper and case ledger next to the report. Adapt the root/output arguments for another MCP catalogue; run against disposable state; add each advertised phrase and read-only nonmutation assertions. Keep explicit tool execution, routing correctness and live-provider evidence separate. Existing production-audit and functional-verification guidance already covers the evidence boundary; no cosmetic skill changes are needed.

Candidate follow-up template: a CI check joining advertised phrases to accepted intent/schema/expected observable outcome, with an explicit mutating-versus-read-only contract. This is a proposed implementation pattern, not a completed safety mechanism.

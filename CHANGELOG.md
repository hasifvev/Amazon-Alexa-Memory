# Changelog

## 2026-10-23 — Verified local candidate

- Fresh isolated environment from declared requirements: 140 tests pass; compileall, `pip check` and `pip_audit` clean (mcp 1.30.0, certifi 2026.10.19, starlette 1.7.0).
- `verify_catalogue.py`: 24/24 wire scenarios over all 20 tools; 60/60 routing cases (was 47/60 on 2026-10-21).
- README, submission draft and runbook updated to current evidence. No commit, push, visibility change or submission performed.

## 2026-10-08 — Completion candidate (in progress)

- Approved bounded local completion plan.
- Fresh install reproduced MCP2/FastMCP incompatibility; runtime targets MCP1.29. Dependency audit exposed Starlette0.x advisories; an actual handshake with Starlette1.7 passes and installed dependency audit reports no known vulnerabilities. Full integration still pending.
- Added isolated browser regression coverage after observing ten pre-fix failures.
- Browser selected tools execute over MCP on both routing paths; separate measured routing/tool timing.
- Literal rendering, subject-scoped auxiliary queries, busy/error handling and sandboxed visual timeline implementation under verification.
- Backend persistence/API/Telegram hardening verified. First independent review exposed four interaction/temporal/snapshot defects; four red regressions and fixes plus saturation/delayed browser/replay checks bring parent suite to120passes. Independent re-review pending; no release/deployment declared.

## Earlier history

Existing Git history is preserved. Main baseline 582b189 added six interface/API features; earlier commits introduced Bedrock routing and deterministic fallback. Historical README/friction claims are not current verification evidence.

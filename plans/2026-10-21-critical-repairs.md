# Critical Alexa repairs — October 21, 2026

Authorized by Lord Hasif: fix the critical failed areas from the verification report, including daily fact counts and original/fresh dependency audits. Public release remains conditional on passing necessary checks and audit.

## Scope and sequence

1. Preserve the existing tracked and nonignored working files in a dated source snapshot; exclude personal runtime data and Git configuration/credentials.
2. Add failing regressions for read questions causing writes, fact/project intent collision, advertised routing phrases, unresolved context, daily-brief event counts/plurals and bounded MCP sessions.
3. Repair browser intent ordering and prevent uncertain/read-only language from reaching write tools; guard provider-selected writes for read questions too. Ask for the missing subject when a correction has no identifiable topic.
4. Exclude interaction events from daily-brief fact counts; fix memory pluralization.
5. Adopt MCP1.30.0 and certifi2026.10.19 or later; bound sessions/idle lifetime. Repair the old verification environment, install a new clean environment, and audit both.
6. Remove embedded credentials from local Git remote configuration. Credential revocation is an account action for Lord Hasif; record it as outstanding until actually verified.
7. Run focused regressions, complete suite/checkback, all20tools/acceptance cases, browser/restart/responsive checks, compile, dependency consistency and advisory scans. Preserve failed logs and bind final evidence to source hashes.
8. Update current README, checklist/changelog/handoff/submission notes and dated evidence. Preserve the earlier failing audit as history.

## Acceptance

- Read questions cannot select a write on local or provider routing paths, including profile questions; explicit writes still work.
- Fact corrections and explicit project updates reach distinct intended tools.
- All60 audit cases have a supported safe behavior; subjectless corrections ask for clarification without a tool write.
- Recall events do not inflate daily fact counts; plural is memories.
- Original repaired environment and fresh declared installation pass the suite, pip check and pip-audit.
- Real MCP operation and restart preserve existing history/scoping/snapshot behavior.
- Remote URL is credential-free; no credential value appears in output/evidence.
- No commit/push, public visibility change, deployment, paid provider calls, external messages or submission as part of these local repairs.

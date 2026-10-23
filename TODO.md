# Completion checklist

Approved plan: plans/2026-10-08-alexa-completion.md. Local engineering only; external actions require separate authorization.

## Engineering
- [x] Preserve pre-edit tracked-source Git bundle; SHA recorded in plan.
- [x] Reproduce fresh-install MCP2 incompatibility and existing two security test failures.
- [x] Install declared runtime/dev requirements in a fresh isolated environment.
- [x] Complete backend transport/input/routing guards and regressions. (60/60 routing cases, 2026-10-23)
- [x] Complete durable write/reset/expiry integrity and regressions.
- [x] Complete spoken feature and optional Telegram regressions.
- [x] Complete real MCP browser execution, safe rendering and visual timeline.
- [x] Run actual local server/browser integration (fixtures are not this gate).
- [x] Full suite (140 passed), compile, pip check and pip_audit clean on fresh venv, 2026-10-23. Independent review of the final candidate still owner-side.
- [x] Update README, submission draft and runbook with final evidence (2026-10-23).

## External gates — not authorized/executed
- [ ] Owner authorizes and verifies a live deployment.
- [ ] Owner chooses public source or required private judge access.
- [ ] Record demo video under three minutes; public YouTube/Vimeo link verified signed-out.
- [ ] Final Devpost submission approved and read back.
- [ ] Optional real microphone/provider/Telegram checks if included in submission claims.

## Deliberate non-goals
No certified Alexa add-on/device integration, personal-data service, OAuth household identity, multiworker deployment, paid inference by default, or automatic Git publishing.

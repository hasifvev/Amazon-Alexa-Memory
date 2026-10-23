# Deployment runbook — local candidate, remote execution not authorized

## Current verified environment
Python3.14.7 on Windows, MCP 1.30.0, Starlette1.7.0. Full tests include an actual random-port localhost server/browser journey and process restart. One process/worker, local filesystem only.

## Local smoke
From project root after README dependency setup:
```bash
export MEMORY_DEMO=1
export MEMORY_STORE=data/synthetic-demo.jsonl
export MEMORY_BEDROCK=0
export HOST=127.0.0.1
export PORT=8000
export MCP_ALLOWED_HOSTS=127.0.0.1:8000,localhost:8000
export MCP_ALLOWED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000
python -m server.app
```
Synthetic data only. Do not use the existing personal/default runtime path. Do not run a second writer process or --reload/--workers. Tests manage disposable stores and shut down their child processes.

## Remote deployment prerequisites
1. Explicit owner approval for exact existing target and rollback; September EC2 note is history, not current state.
2. AWS skill/documentation and account/instance/service discovery; secrets only through approved runtime tooling. No key/token printed.
3. Preserve prior deployment artifact and complete store while service stopped; hash backup. No memory deletion.
4. Install/test candidate in isolated environment; run full suite on target's Python/OS. Linux lease path is implemented but not exercised by Windows verification.
5. One worker; HTTPS reverse proxy; restrict8000 ingress, explicit allowed public Host/Origin. Missing Origin is native-client compatible, not user authentication.
6. Dedicated synthetic store and warning. Disable Bedrock/Telegram unless separately authorized/configured. Request limits are global and process-local, not a spend cap or DDoS service.
7. Promote source only after checks. Read back version/source digest and actual public MCP handshake/tool/resource/browser reset/import journeys, including signed-out/mobile access.
8. Roll back artifact with archived store preserved if any gate fails. Keep judge access through November20.

## History backup/recovery
Current export is a snapshot, not history backup. Stop writer and copy the complete JSONL plus archive files to a protected dated location. Existing torn-tail recovery archives before repair. A reset archives old log. Never delete the lock file to bypass a live writer.

## Owner gates
Remote deployment, Git publication, repo visibility/collaborators, public video and final Devpost submission are not executed here. No current hosted demo URL is asserted.

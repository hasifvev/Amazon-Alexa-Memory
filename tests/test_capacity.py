"""Saturation tests use blocked local fixtures, never a provider."""
import threading
import anyio
import httpx
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from server.safety import SafetyMiddleware


def test_http_concurrency_rejects_saturated_then_recovers():
    async def run():
        started = anyio.Event()
        release = anyio.Event()
        async def slow(scope, receive, send):
            started.set()
            await release.wait()
            await JSONResponse({'ok':True})(scope,receive,send)
        app = SafetyMiddleware(slow,TransportSecuritySettings(allowed_hosts=['localhost'],allowed_origins=['http://localhost']),rate=100,concurrency=1)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://localhost') as client:
            async def first():
                assert (await client.get('/slow')).status_code == 200
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(first)
                await started.wait()
                assert (await client.get('/slow')).status_code == 429
                release.set()
            assert (await client.get('/slow')).status_code == 200
    anyio.run(run)


def test_optional_inference_capacity_held_until_work_finishes(monkeypatch):
    from server import llm_router as router
    monkeypatch.setenv('MEMORY_BEDROCK','1')
    release = threading.Event()
    started = threading.Event()
    lock = threading.Lock()
    count = [0]
    def local_route(*args):
        with lock:
            count[0] += 1
            if count[0] == 2: started.set()
        assert release.wait(10)
        return {'tool':'catch_me_up','args':{}}
    monkeypatch.setattr(router,'route_with_llm',local_route)
    async def run():
        results = []
        async def blocked(): results.append(await router.route_async('synthetic','default'))
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(blocked)
            tasks.start_soon(blocked)
            assert await anyio.to_thread.run_sync(lambda:started.wait(10))
            assert await router.route_async('synthetic','default') is None
            assert count[0] == 2
            release.set()
        assert len(results) == 2
        assert await router.route_async('synthetic','default') is not None
    try: anyio.run(run)
    finally: release.set()

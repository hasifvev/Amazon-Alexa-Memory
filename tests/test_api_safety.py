import anyio
import httpx
from server.app import build_server


def request(tmp_path, method, path, **kwargs):
    async def run():
        app = build_server(tmp_path / 'api.jsonl').streamable_http_app()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:8000') as c:
                return await c.request(method, path, **kwargs)
    return anyio.run(run)


def test_custom_api_rejects_bad_origin(tmp_path):
    r = request(tmp_path, 'POST', '/api/import', json={'version':1,'memories':[]}, headers={'Origin':'https://evil.example'})
    assert r.status_code == 403


def test_chat_routes_without_executing_and_pins_subject(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMORY_BEDROCK','1')
    monkeypatch.setattr('server.llm_router.route_with_llm', lambda *a: {'tool':'remember','args':{'fact':'synthetic','who':'other'}})
    r = request(tmp_path, 'POST', '/api/chat', json={'text':'remember synthetic','who':' Alice '})
    assert r.status_code == 200
    assert r.json()['args'] == {'fact':'synthetic','who':'alice'}
    assert 'response' not in r.json()
    assert not (tmp_path / 'api.jsonl').exists()


def test_chat_bad_root_bounded_4xx(tmp_path):
    assert request(tmp_path,'POST','/api/chat',json=[]).status_code == 400


def test_reminder_nan_rejected(tmp_path):
    assert request(tmp_path,'GET','/api/reminders?hours=nan').status_code == 400


def test_private_reset_disabled(tmp_path):
    assert request(tmp_path,'POST','/api/seed').status_code == 403

def test_rate_limit_returns_429(tmp_path):
    async def run():
        app = build_server(tmp_path/'rate.jsonl').streamable_http_app()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8000') as c:
                for _ in range(120): assert (await c.get('/api/stats')).status_code == 200
                assert (await c.get('/api/stats')).status_code == 429
    anyio.run(run)


def test_host_rebinding_refused(tmp_path):
    assert request(tmp_path,'GET','/api/stats',headers={'Host':'evil.example'}).status_code == 421


def test_mcp_tool_type_validation_precedes_mutation(tmp_path):
    payload = {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'remember','arguments':{'fact':12}}}
    assert request(tmp_path,'POST','/mcp',json=payload).status_code == 400


def test_multiworker_startup_refused(tmp_path,monkeypatch):
    import pytest
    monkeypatch.setenv('WEB_CONCURRENCY','2')
    with pytest.raises(RuntimeError,match='worker'): build_server(tmp_path/'workers.jsonl')


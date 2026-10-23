import anyio
import httpx
import pytest
from server.app import build_server
from server.llm_router import _parse_json, route_with_llm

@pytest.mark.parametrize('raw',['null','[]','12','{"tool":"remember","args":null}'])
def test_bad_json_model_output(raw):
    assert _parse_json(raw) is None


def test_offline_no_client_access():
    assert route_with_llm('synthetic') is None

@pytest.mark.parametrize('result',[{'tool':'unknown','args':{}},{'tool':'remember','args':None},{'tool':'remember','args':{}},{'tool':'remember','args':{'fact':12}},{'tool':'remember','args':{'fact':'synthetic','extra':'bad'}}])
def test_bad_route_falls_back_no_write(tmp_path,monkeypatch,result):
    monkeypatch.setenv('MEMORY_BEDROCK','1')
    monkeypatch.setattr('server.llm_router.route_with_llm',lambda *args:result)
    async def run():
        app=build_server(tmp_path/'s.jsonl').streamable_http_app()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8000') as c:
                r=await c.post('/api/chat',json={'text':'synthetic'})
                assert r.json()=={'fallback':True,'routed_by':'regex'}
                assert len(app.state.memory_tools.store)==0
    anyio.run(run)

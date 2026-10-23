import anyio
import httpx
import pytest
from core.store import Memory
from server.app import build_server


def interact(tmp_path, fn, *, demo=False):
    async def run():
        mcp = build_server(tmp_path/'state.jsonl',demo=demo)
        app = mcp.streamable_http_app()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8000') as c:
                return await fn(c, app.state.memory_tools)
    return anyio.run(run)


def test_import_complete_validation_and_idempotent(tmp_path):
    async def go(c,t):
        m = Memory(text='synthetic import')
        body = {'version':1,'memories':[m.to_dict(),{'text':12}]}
        assert (await c.post('/api/import',json=body)).status_code == 400
        assert len(t.store) == 0
        body['memories'] = [m.to_dict()]
        assert (await c.post('/api/import',json=body)).json()['imported'] == 1
        assert (await c.post('/api/import',json=body)).json()['skipped'] == 1
        altered = m.to_dict(); altered['tags'] = ['conflicting']
        assert (await c.post('/api/import',json={'version':1,'memories':[altered]})).status_code == 400
        assert len(t.store) == 1
    interact(tmp_path,go)


def test_export_reminders_default_is_scoped(tmp_path):
    async def go(c,t):
        t.for_subject('alice').remember_for('synthetic other','tomorrow')
        t.remember_for('synthetic default','tomorrow')
        for path,key in [('/api/export','memories'),('/api/reminders?hours=48','reminders')]:
            rows = (await c.get(path)).json()[key]
            assert len(rows) == 1 and rows[0]['subject'] == 'default'
            rows = (await c.get(path+('&' if '?' in path else '?')+'who= ALICE ')).json()[key]
            assert len(rows) == 1 and rows[0]['subject'] == 'alice'
    interact(tmp_path,go)


def test_reset_archives_and_every_reader_sees_same_holder(tmp_path):
    async def go(c,t):
        t.remember('synthetic old extra')
        old_holder = t.store
        r = await c.post('/api/seed')
        assert r.status_code == 200
        assert t.store is old_holder
        assert list(tmp_path.glob('state.jsonl.archive-*'))
        rows = (await c.get('/api/export')).json()['memories']
        assert not any(m['text'] == 'synthetic old extra' for m in rows)
        stats = (await c.get('/api/stats')).json()
        assert stats['global']['asserted'] == r.json()['seeded']
        assert 'store_path' not in stats
        assert (await c.get('/api/reminders')).json()['count'] == 0
    interact(tmp_path,go,demo=True)

@pytest.mark.parametrize('hours',['-1','721','inf','-inf','NaN','no'])
def test_hours_boundaries(tmp_path,hours):
    async def go(c,t):
        assert (await c.get('/api/reminders?hours='+hours)).status_code == 400
    interact(tmp_path,go)


def test_oversized_body_and_text_no_effect(tmp_path):
    async def go(c,t):
        assert (await c.post('/api/chat',json={'text':'x'*2001})).status_code == 400
        assert (await c.post('/api/import',content=b'x'*131073)).status_code == 413
        assert len(t.store) == 0
    interact(tmp_path,go)


def test_stats_temporally_live(tmp_path):
    async def go(c,t):
        t.store.add(Memory(text='synthetic expired',asserted_at='2020-01-01',valid_from='2020-01-01',valid_until='2020-01-02',tags=('list:shopping',)))
        t.store.add(Memory(text='synthetic scheduled',valid_from='2099-01-01',tags=('project:x',)))
        counts = (await c.get('/api/stats')).json()['subjects'][0]
        assert counts['total']==2 and counts['live']==counts['lists']==counts['projects']==0
    interact(tmp_path,go)

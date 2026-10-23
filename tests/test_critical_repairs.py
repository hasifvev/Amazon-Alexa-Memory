"""Acceptance regressions from the October 21 audit, with synthetic data only."""
import json
from pathlib import Path

import anyio
import httpx
import pytest
from concurrent.futures import ThreadPoolExecutor

from core.store import Kind, Memory, MemoryStore
from server.app import build_server
from server.tools import MemoryTools
from tests.test_browser import browser, ui, ask

ROOT = Path(__file__).resolve().parents[1]
READ_ONLY = {'recall', 'get_list', 'my_projects', 'what_time_is_it', 'catch_me_up',
             'daily_brief', 'what_changed', 'what_moved', 'wrong_about',
             'shared_with_me', 'timeline'}


def test_all_audited_phrases_have_safe_supported_behavior(ui):
    page, _ = ui
    cases = json.loads((ROOT/'docs/qa/2026-10-21-verification/routing-cases.json').read_text())['cases']
    mismatches = []
    for case in cases:
        actual = page.evaluate('text => route(text)', case['phrase'])
        if case['phrase'] == 'it is eleven now':
            assert actual.get('clarification') and not actual.get('tool'), actual
        elif actual.get('tool') != case['expected']:
            mismatches.append((case['phrase'],case['expected'],actual))
    assert not mismatches, mismatches


@pytest.mark.parametrize('phrase',[
    'what is my name', "what's my name", 'what is my location',
    'can you tell me my name', 'what do I need to buy', 'what is on my shopping list',
    'how do I change my name', 'what did you remember about my project',
])
def test_read_questions_cannot_select_mutations(ui,phrase):
    page, state = ui
    ask(page,phrase)
    assert state['calls'] and all(c['name'] in READ_ONLY for c in state['calls']), state['calls']


def test_provider_cannot_turn_profile_question_into_write(ui):
    page, state = ui
    state['provider'] = True
    ask(page,'what is my name')
    assert [c['name'] for c in state['calls']] == ['recall']


def test_missing_correction_subject_clarifies_without_mcp_call(ui):
    page,state=ui
    ask(page,'it is eleven now')
    assert state['calls']==[]
    assert 'which' in page.locator('#conv .her .bubble').last.inner_text().lower()


@pytest.mark.parametrize('phrase,tool',[
    ('standup moved to ten','correct'),
    ('update Amazon project to submitted','track'),
    ('log that EduPlay is in planning','track'),
])
def test_fact_project_changes_execute_the_intended_tool(ui,phrase,tool):
    page,state=ui
    ask(page,phrase)
    assert [c['name'] for c in state['calls']]==[tool]


def test_brief_counts_facts_not_read_interactions(tmp_path):
    tools=MemoryTools(MemoryStore(tmp_path/'synthetic.jsonl'))
    tools.remember('test marker is AlphaCase')
    assert '1 new memory added' in tools.daily_brief()
    tools.recall('test marker'); tools.recall('test marker')
    assert '1 new memory added' in tools.daily_brief()
    tools.remember('test second is BetaCase')
    assert '2 new memories added' in tools.daily_brief()
    assert any(m.kind is Kind.EVENT for m in tools.store.all()), 'retain read history'


def test_empty_brief_never_counts_events_as_known_facts(tmp_path):
    tools=MemoryTools(MemoryStore(tmp_path/'synthetic.jsonl'))
    tools.store.add(Memory(text='synthetic interaction',kind=Kind.EVENT))
    brief=tools.daily_brief()
    assert 'new memory' not in brief
    assert '0 things' in brief


def test_server_rejects_provider_write_for_read_question(tmp_path,monkeypatch):
    monkeypatch.setenv('MEMORY_BEDROCK','1')
    monkeypatch.setattr('server.llm_router.route_with_llm',lambda *a:{'tool':'set_profile','args':{'key':'name','value':'what'}})
    async def run():
        app=build_server(tmp_path/'synthetic.jsonl').streamable_http_app()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8000') as c:
                result=await c.post('/api/chat',json={'text':'what is my name'})
                assert result.json()=={'fallback':True,'routed_by':'regex'}
                assert len(app.state.memory_tools.store)==0
    # Playwright's module fixture may own this thread's event loop.
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(anyio.run,run).result()


def test_mcp_sessions_have_explicit_small_demo_bounds(tmp_path):
    server=build_server(tmp_path/'bounded.jsonl')
    assert server.settings.max_sessions==64
    assert server.settings.session_idle_timeout==300


def test_session_capacity_recovers_after_client_delete(tmp_path):
    from tests.test_transport import INITIALIZE, headers
    async def run():
        server=build_server(tmp_path/'sessions.jsonl')
        server.settings.max_sessions=1
        app=server.streamable_http_app()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8000') as c:
                first=await c.post('/mcp',headers=headers(),json=INITIALIZE)
                assert first.status_code==200
                blocked=await c.post('/mcp',headers=headers(),json=INITIALIZE)
                assert blocked.status_code==503
                closed=await c.delete('/mcp',headers=headers(**{'mcp-session-id':first.headers['mcp-session-id']}))
                assert closed.status_code==200
                await anyio.sleep(0.05)
                reopened=await c.post('/mcp',headers=headers(),json=INITIALIZE)
                assert reopened.status_code==200
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(anyio.run,run).result()


def test_idle_session_expires_and_frees_capacity(tmp_path):
    from tests.test_transport import INITIALIZE, headers
    async def run():
        server=build_server(tmp_path/'idle.jsonl')
        server.settings.max_sessions=1
        server.settings.session_idle_timeout=0.05
        app=server.streamable_http_app()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8000') as c:
                first=await c.post('/mcp',headers=headers(),json=INITIALIZE)
                assert first.status_code==200
                await anyio.sleep(0.2)
                expired=await c.post('/mcp',headers=headers(**{'mcp-session-id':first.headers['mcp-session-id']}),json={'jsonrpc':'2.0','id':2,'method':'tools/list'})
                assert expired.status_code==404
                assert (await c.post('/mcp',headers=headers(),json=INITIALIZE)).status_code==200
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(anyio.run,run).result()

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import pytest
from core.store import MemoryStore
from server.tools import MemoryTools

@pytest.fixture
def tools(tmp_path):
    return MemoryTools(MemoryStore(tmp_path/'tools.jsonl'))

def test_repeated_fact_profile_project_are_idempotent(tools):
    for _ in range(3):
        tools.remember('synthetic fact')
        tools.set_profile('name','Synthetic')
        tools.track('Synthetic','building')
    assert len(tools.store) == 3

def test_list_identity_exact_blank_remove_no_write(tools):
    tools.add_to_list('oat milk')
    tools.add_to_list('milk')
    assert len(tools.store.live()) == 2
    tools.remove_from_list(' ')
    assert len(tools.store.live()) == 2
    tools.remove_from_list('milk')
    assert [m.text for m in tools.store.live()] == ['oat milk']

def test_remember_never_claims_unperformed_update(tools):
    tools.remember('synthetic standup is nine')
    assert 'updated' not in tools.remember('synthetic standup is ten').lower()
    assert len(tools.store.live()) == 2

def test_correct_ephemeral_preserves_expiry(tools):
    tools.remember_for('synthetic code is one','tomorrow')
    expiry = tools.store.live()[0].valid_until
    tools.correct('code','synthetic code is two')
    assert tools.store.live()[0].valid_until == expiry

def test_daily_brief_reports_shared(tools):
    tools.for_subject('alice').share('synthetic shared fact','default')
    assert 'message' in tools.daily_brief()

@pytest.mark.parametrize('value',['UTC+99','nan','UTC-13','UTC+15','Europe/London'])
def test_invalid_timezone_no_mutation(tools,value):
    tools.set_profile('timezone',value)
    assert len(tools.store) == 0

def test_unknown_profile_no_mutation(tools):
    tools.set_profile('unknown','x')
    assert len(tools.store) == 0

def test_expiry_uses_subject_local_day(tools,monkeypatch):
    now = datetime(2026,10,7,20,tzinfo=timezone.utc)
    monkeypatch.setattr('server.tools._now',lambda:now)
    tools.remember_for('synthetic local fact','end of today')
    assert tools.store.get(next(tools.store.all()).id).valid_until == '2026-10-08T23:59:59+08:00'

def test_simultaneous_remembers_deduplicate(tools):
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _:tools.remember('synthetic same'),range(32)))
    assert len(tools.store) == 1

"""Regression findings from independent completion review."""
from core.store import MemoryStore
from tests.test_api_integrity import interact
from server.tools import MemoryTools


def test_reading_before_correction_and_withdrawal_does_not_create_ambiguity(tmp_path):
    tools = MemoryTools(MemoryStore(tmp_path / 'state.jsonl'))
    tools.remember('synthetic marker is Alpha')
    tools.recall('marker')
    assert 'Updated' in tools.correct('marker', 'synthetic marker is Beta')
    tools.recall('marker')
    assert 'withdrawn' in tools.forget('marker')


def test_rapid_corrections_preserve_original_assertion_window(tmp_path):
    tools = MemoryTools(MemoryStore(tmp_path / 'state.jsonl'))
    tools.remember('synthetic marker is Alpha')
    original = next(tools.store.all())
    tools.correct('marker', 'synthetic marker is Beta')
    assert [m.text for m in tools.store.as_of(valid=original.asserted_at)] == [original.text]
    tools.store.close()
    reopened = MemoryStore(tools.store.path)
    assert [m.text for m in reopened.as_of(valid=original.asserted_at)] == [original.text]
    reopened.close()


def test_fact_values_with_different_case_are_not_silently_conflated(tmp_path):
    tools = MemoryTools(MemoryStore(tmp_path / 'state.jsonl'))
    tools.remember('synthetic code is AbC2026')
    tools.remember('synthetic code is abc2026')
    assert len(tools.store) == 2


def test_snapshot_and_fact_counts_exclude_interaction_events(tmp_path):
    async def go(client, tools):
        tools.remember('synthetic marker is Alpha')
        tools.recall('marker')
        tools.timeline('marker')
        snapshot = (await client.get('/api/export')).json()
        assert len(snapshot['memories']) == 1
        assert all(m['kind'] != 'event' for m in snapshot['memories'])
        stats = (await client.get('/api/stats')).json()
        assert stats['global']['asserted'] == stats['global']['true_now'] == 1
    interact(tmp_path, go)

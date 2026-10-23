from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import pytest
from core.store import Memory, MemoryStore


def test_supersession_uses_earliest_end(tmp_path):
    s = MemoryStore(tmp_path / 's.jsonl')
    old = s.add(Memory(text='old', valid_from='2020-01-01', valid_until='2030-01-01'))
    s.supersede(old.id, Memory(text='new', valid_from='2025-01-01'))
    assert s.valid_window(old)[1] == '2025-01-01'


def test_torn_tail_then_append_survives_reopen(tmp_path):
    p = tmp_path / 's.jsonl'
    s = MemoryStore(p)
    old = s.add(Memory(text='complete'))
    with p.open('ab') as f:
        f.write(b'{"event":"assert",\xff')
    if hasattr(s, 'close'): s.close()
    reopened = MemoryStore(p)
    new = reopened.add(Memory(text='after recovery'))
    if hasattr(reopened, 'close'): reopened.close()
    again = MemoryStore(p)
    assert [m.id for m in again.all()] == [old.id, new.id]
    assert list(tmp_path.glob('s.jsonl.damaged-*'))


def test_duplicate_concurrent_add_has_one_event(tmp_path):
    s = MemoryStore(tmp_path / 's.jsonl')
    m = Memory(text='one')
    def add(_):
        try: s.add(m); return True
        except ValueError: return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(add, range(32))) == 1
    assert len(list(s.all())) == 1
    s.close()
    replay = MemoryStore(s.path)
    assert [r.id for r in replay.all()] == [m.id]
    replay.close()


def test_competing_writer_refused(tmp_path):
    s = MemoryStore(tmp_path / 's.jsonl')
    with pytest.raises(RuntimeError, match='writer'):
        MemoryStore(s.path)

def test_concurrent_corrections_have_single_successor(tmp_path):
    s = MemoryStore(tmp_path/'correct.jsonl')
    old = s.add(Memory(text='synthetic initial'))
    def correct(i):
        try: s.supersede(old.id,Memory(text=f'synthetic correction {i}')); return True
        except ValueError: return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(correct,range(32))) == 1
    assert len(s.history(old.id)) == 2
    expected = [m.id for m in s.history(old.id)]
    s.close()
    replay = MemoryStore(s.path)
    assert [m.id for m in replay.history(old.id)] == expected
    assert len(list(replay.all())) == 2
    replay.close()


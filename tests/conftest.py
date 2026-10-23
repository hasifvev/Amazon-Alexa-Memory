"""Isolate collection from real stores and external services."""
import os
import tempfile
from pathlib import Path

_scratch = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'hermes/cache/scratch'
_scratch.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(_scratch)
os.environ['MEMORY_STORE'] = str(Path(tempfile.mkdtemp(prefix='alexa-tests-', dir=_scratch)) / 'module.jsonl')
os.environ['AWS_EC2_METADATA_DISABLED'] = 'true'
os.environ['MEMORY_BEDROCK'] = '0'
os.environ['MEMORY_DEMO'] = '0'

import pytest

@pytest.fixture(autouse=True)
def no_external_services(monkeypatch):
    from server.tools import _tool_arrivals
    _tool_arrivals.clear()
    import server.llm_router as router
    import server.telegram_bridge as telegram
    def forbidden(*a, **k):
        raise AssertionError('External inference is forbidden in tests')
    async def forbidden_send(*a, **k):
        raise AssertionError('External messages are forbidden in tests')
    monkeypatch.setattr(router, '_get_bedrock', forbidden)
    monkeypatch.setattr(telegram, 'send_telegram_message', forbidden_send)

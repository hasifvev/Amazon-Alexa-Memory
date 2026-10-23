"""Reproducible localhost MCP fast-path timing, synthetic data, no inference."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
from tests.test_live_browser import live_server


def percentile(samples, fraction):
    ordered = sorted(samples)
    return ordered[min(len(ordered)-1, max(0, int((len(ordered)-1)*fraction+0.5)))]


def main():
    scratch = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'hermes/cache/scratch'
    scratch.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='alexa-benchmark-', dir=scratch))
    samples = []
    with live_server(folder / 'synthetic.jsonl', folder / 'server.log') as origin:
        with httpx.Client(base_url=origin, timeout=15) as client:
            headers = {'Origin':origin, 'Accept':'application/json, text/event-stream', 'Content-Type':'application/json'}
            init = client.post('/mcp', headers=headers, json={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'benchmark','version':'1'}}})
            init.raise_for_status()
            headers['Mcp-Session-Id'] = init.headers['mcp-session-id']
            client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','method':'notifications/initialized'}).raise_for_status()
            names = client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':2,'method':'tools/list'})
            names.raise_for_status()
            for i in range(50):
                start = time.perf_counter()
                response = client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':i+3,'method':'tools/call','params':{'name':'catch_me_up','arguments':{'who':'default'}}})
                response.raise_for_status()
                body = response.text
                message = json.loads(next(line[6:] for line in body.splitlines() if line.startswith('data: '))) if 'text/event-stream' in response.headers.get('content-type','') else response.json()
                assert not message.get('error') and not message['result'].get('isError'), body
                samples.append((time.perf_counter()-start)*1000)
    output = {'path':'actual localhost HTTP MCP tools/call', 'tool':'catch_me_up','samples':len(samples),'p50_ms':round(percentile(samples,.5),2),'p95_ms':round(percentile(samples,.95),2),'p99_ms':round(percentile(samples,.99),2),'max_ms':round(max(samples),2),'inference':'disabled','data':'synthetic','network_scope':'localhost only; not a remote deployment latency claim','evidence_folder':str(folder)}
    print(json.dumps(output,indent=2))
    assert output['p95_ms'] < 500


if __name__ == '__main__':
    main()
"""Real localhost MCP/browser journeys; no HTTP fixtures or paid providers."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from urllib.request import urlopen

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def live_server(store, log_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    env = {**os.environ, "MEMORY_STORE": str(store), "MEMORY_DEMO": "1", "HOST": "127.0.0.1", "PORT": str(port), "MCP_ALLOWED_HOSTS": f"127.0.0.1:{port}", "MCP_ALLOWED_ORIGINS": origin, "MEMORY_BEDROCK": "0", "AWS_EC2_METADATA_DISABLED": "true", "TELEGRAM_BOT_TOKEN": "", "TELEGRAM_WEBHOOK_SECRET": ""}
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen([sys.executable, "-m", "server.app"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise AssertionError(f"Server exited {proc.returncode}; {log_path}")
                try:
                    with urlopen(origin, timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.1)
            else:
                raise AssertionError(f"Server did not become ready; {log_path}")
            yield origin
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def submit(page, text):
    before = page.locator("#conv .her").count()
    page.fill("#say", text)
    page.click("#send")
    expect(page.locator("#conv .her")).to_have_count(before + 1)
    expect(page.locator("#send")).to_be_enabled()
    reply = page.locator("#conv .her .bubble").last.inner_text()
    assert "Something went wrong" not in reply, reply
    return reply


def test_real_mcp_history_scope_snapshot_reset_and_restart(tmp_path):
    store = tmp_path / "synthetic.jsonl"
    errors, failed, calls = [], [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.add_init_script("window.SpeechRecognition = undefined; window.webkitSpeechRecognition = undefined;")
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("response", lambda r: failed.append((r.url, r.status)) if r.status >= 400 else None)
        page.on("request", lambda r: calls.append(r.post_data_json) if r.url.endswith("/mcp") and r.method == "POST" else None)
        with live_server(store, tmp_path / "live-server.log") as origin:
            page.goto(origin)
            expect(page.locator("#conv .her")).to_have_count(1)
            expect(page.locator("#send")).to_be_enabled()
            assert "nine" in submit(page, "what was standup 100 days ago")
            assert "ten thirty" in submit(page, "what is standup")
            submit(page, "show me the history of standup")
            expect(page.frame_locator('iframe[title="Memory timeline"]').locator("#entries li")).to_have_count(2)
            submit(page, "my name is SyntheticPerson")
            profile_before = page.request.get(origin + "/api/export?who=default").json()['memories']
            assert "SyntheticPerson" in submit(page, "what is my name")
            assert page.request.get(origin + "/api/export?who=default").json()['memories'] == profile_before
            assert "Updated" in submit(page, "standup moved to eleven")
            assert "eleven" in submit(page, "what is standup")
            submit(page, "track Amazon as building")
            submit(page, "update Amazon project to submitted")
            assert "submitted" in submit(page, "what am I working on")
            submit(page, "remember synthetic marker is AlphaCase")
            assert "Updated" in submit(page, "change synthetic marker to BetaCase")
            assert "BetaCase" in submit(page, "what is synthetic marker")
            submit(page, "add oat milk to my shopping list")
            submit(page, "add milk to my shopping list")
            assert "oat milk" in submit(page, "what's on my shopping list")
            submit(page, "remove milk from my shopping list")
            assert "oat milk" in submit(page, "what's on my shopping list")
            submit(page, "remember TempCase just for today")
            expect(page.locator(".expiring-item")).to_contain_text("TempCase")
            submit(page, "tell Aisyah DinnerCase is seven")
            page.click('[data-who="aisyah"]')
            assert "DinnerCase" in submit(page, "what has been shared with me")
            assert "message" in submit(page, "daily brief")
            assert "don't know" in submit(page, "what is synthetic marker")
            page.click('[data-who=""]')
            snapshot = page.request.get(origin + "/api/export?fmt=json&who=default").json()
            assert snapshot["version"] == 1
            assert all(m["subject"] == "default" for m in snapshot["memories"])
            page.goto(origin + "/dashboard?who=default")
            expect(page.locator(".subject-card")).to_have_count(1)
            expect(page.locator("#errorMsg")).not_to_be_visible()
            page.goto(origin)
            expect(page.locator("#send")).to_be_enabled()
            expect(page.locator("#conv .her")).to_have_count(1)
            page.click("#resetBtn")
            expect(page.locator("#conv .her")).to_have_count(1)
            expect(page.locator("#send")).to_be_enabled()
            assert "don't know" in submit(page, "what is synthetic marker")
            page.set_input_files("#importFile", {"name":"snapshot.json", "mimeType":"application/json", "buffer":json.dumps(snapshot).encode()})
            expect(page.locator("#conv .her .bubble").last).to_contain_text("Memory imported")
            expect(page.locator("#send")).to_be_enabled()
            assert "BetaCase" in submit(page, "what is synthetic marker")
            for width in (375, 768, 1440):
                page.set_viewport_size({"width":width,"height":1000})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors, errors
            assert not failed, failed
            assert any(c.get("method") == "resources/read" for c in calls)
            assert len([c for c in calls if c.get("method") == "tools/call"]) >= 15
        with live_server(store, tmp_path / "restarted-server.log") as origin:
            page.goto(origin)
            expect(page.locator("#conv .her")).to_have_count(1)
            expect(page.locator("#send")).to_be_enabled()
            assert "BetaCase" in submit(page, "what is synthetic marker")
        browser.close()

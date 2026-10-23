"""Record the Memory demo as a captioned video from the REAL app and MCP server.

Boots a fresh synthetic server (MEMORY_DEMO=1, Bedrock off, disposable store), drives
the actual browser UI at human pace following docs/demo-script.md, burns narration into
on-screen captions, and saves a .webm. Nothing is mocked. No personal data is touched.

    python docs/demo/record_demo.py --out <folder>

Needs requirements-dev.txt and `python -m playwright install chromium`.
Add a voice-over afterwards (the captions are the script) or upload silent with captions.
"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]

OVERLAY = """
(() => {
  const css = `
    #__cap{position:fixed;left:0;right:0;top:0;z-index:2147483647;padding:14px 32px;
      background:rgba(4,9,18,.94);border-bottom:2px solid #00b8ff;color:#fff;
      font:600 22px/1.35 system-ui,Segoe UI,Arial,sans-serif;text-align:center;
      transition:opacity .25s;letter-spacing:.1px}
    #__cap small{display:block;font:500 14px system-ui;color:#7fd8ff;margin-top:3px}`;
  const mount = () => {
    if (document.getElementById('__cap')) return;
    const s = document.createElement('style'); s.textContent = css; document.head.appendChild(s);
    const d = document.createElement('div'); d.id = '__cap'; document.body.appendChild(d);
    d.innerHTML = window.__pendingCap || '';
  };
  window.__setCap = (html) => {
    window.__pendingCap = html;
    const d = document.getElementById('__cap'); if (d) d.innerHTML = html;
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount); else mount();
})();
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(store: Path, log: Path):
    port = free_port()
    origin = f"http://127.0.0.1:{port}"
    env = {**os.environ, "MEMORY_STORE": str(store), "MEMORY_DEMO": "1", "HOST": "127.0.0.1",
           "PORT": str(port), "MCP_ALLOWED_HOSTS": f"127.0.0.1:{port}", "MCP_ALLOWED_ORIGINS": origin,
           "MEMORY_BEDROCK": "0", "AWS_EC2_METADATA_DISABLED": "true",
           "TELEGRAM_BOT_TOKEN": "", "TELEGRAM_WEBHOOK_SECRET": ""}
    fh = log.open("w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "server.app"], cwd=ROOT, env=env, stdout=fh, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise SystemExit(f"server exited {proc.returncode}; see {log}")
        try:
            with urlopen(origin, timeout=1) as r:
                if r.status == 200:
                    return proc, origin
        except OSError:
            time.sleep(0.15)
    proc.kill()
    raise SystemExit("server not ready")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="folder for the finished video")
    ap.add_argument("--dwell", type=float, default=4.5, help="seconds to hold each answer on screen")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="memory-demo-"))
    proc, origin = start_server(work / "synthetic.jsonl", work / "server.log")
    t_start = time.monotonic()
    video_path = None

    def cap(page, title, sub=""):
        html = title + (f"<small>{sub}</small>" if sub else "")
        page.evaluate("h => window.__setCap(h)", html)

    def say(page, text, title, sub="", dwell=None):
        cap(page, title, sub)
        before = page.locator("#conv .her").count()
        page.click("#say")
        page.type("#say", text, delay=55)
        time.sleep(0.5)
        page.click("#send")
        expect(page.locator("#conv .her")).to_have_count(before + 1, timeout=15000)
        expect(page.locator("#send")).to_be_enabled()
        reply = page.locator("#conv .her .bubble").last.inner_text()
        assert "Something went wrong" not in reply, reply
        page.evaluate("() => { const c = document.querySelector('#conv'); c.scrollTop = c.scrollHeight; }")
        time.sleep(args.dwell if dwell is None else dwell)
        return reply

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            ctx = browser.new_context(
                viewport={"width": args.width, "height": args.height},
                record_video_dir=str(work / "video"),
                record_video_size={"width": args.width, "height": args.height},
            )
            page = ctx.new_page()
            page.add_init_script("window.SpeechRecognition = undefined; window.webkitSpeechRecognition = undefined;")
            page.add_init_script(OVERLAY)
            page.goto(origin)
            expect(page.locator("#send")).to_be_enabled()
            cap(page, "Memory — a simulated Alexa+ with a real MCP server",
                "It remembers today's answer, what changed, and what was wrong. All data is synthetic.")
            time.sleep(7)

            say(page, "what is standup", "Ask what's true now", "Real MCP tools/call — see the traffic pane")
            say(page, "what was standup 100 days ago", "Ask what was true then",
                "The earlier answer is still available inside its valid period")
            say(page, "show me the history of standup", "See the history",
                "A real MCP resource renders this timeline in a sandboxed iframe", dwell=0.5)
            page.locator("iframe[title='Memory timeline']").scroll_into_view_if_needed()
            time.sleep(8)
            say(page, "change standup to eleven", "Changing a fact keeps the old one",
                "Correction preserves the chain; nothing is overwritten")
            say(page, "what is standup", "Now it answers with the new value, and what it replaced")
            say(page, "what have I been wrong about", "Changed is not the same as wrong",
                "Withdrawn beliefs are kept as evidence, with how long they were believed", dwell=7)
            say(page, "add milk to my shopping list", "Everyday workflow", "Lists, shared messages, speakers")
            say(page, "tell Aisyah that dinner is at seven", "Share a message with another household member")
            page.click(".who-btn[data-who='aisyah']")
            say(page, "what was shared with me", "Switch speaker to Aisyah — her view, her messages",
                "Speaker selection is scoping, not authentication")
            page.click(".who-btn[data-who='']")
            say(page, "daily brief", "Daily brief with truthful counts", "Reads never inflate the fact count")
            say(page, "what is my name", "Questions never write",
                "A read question leaves the profile unchanged — a regression we found and fixed", dwell=5)

            cap(page, "Scoped dashboard", "Live memories, corrections and withdrawals; archive/reset; snapshot transfer")
            page.goto(f"{origin}/dashboard")
            cap(page, "Scoped dashboard", "Live memories, corrections and withdrawals; archive and reset; snapshot transfer")
            time.sleep(8)
            cap(page, "Official MCP Streamable HTTP · deterministic tools · append-only record",
                "140 tests, 60/60 routing cases, clean dependency audit. Simulation — not a certified Echo integration.")
            time.sleep(7)

            video = page.video
            ctx.close()
            video_path = Path(video.path())
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    elapsed = time.monotonic() - t_start
    if video_path and video_path.exists():
        dest = out / "alexa-memory-demo.webm"
        shutil.copy2(video_path, dest)
        print(f"VIDEO {dest}  size={dest.stat().st_size/1e6:.1f} MB  wallclock~{elapsed:.0f}s (limit 180s)")
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()

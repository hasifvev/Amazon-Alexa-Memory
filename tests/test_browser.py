"""Browser regression tests. HTTP fixtures here are NOT live-provider evidence."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright, expect

WEB = Path(__file__).resolve().parents[1] / "web"
BASE = "http://127.0.0.1:8000"
TIMELINE = {"about": "standup", "spoken": "Standup is ten now, previously nine.", "footnote": "Changed once.", "entries": [{"text": "standup is nine", "status": "replaced", "starts": "1 March 2026", "ends": "1 July 2026"}, {"text": "standup is ten", "status": "current", "starts": "1 July 2026"}]}


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def ui(browser):
    context = browser.new_context(viewport={"width": 1440, "height": 1100})
    context.add_init_script("window.SpeechRecognition = undefined; window.webkitSpeechRecognition = undefined;")
    page = context.new_page()
    state = {"calls": [], "requests": [], "provider": False, "provider_tool": "remember", "reminders": [], "tool_error": False, "reset_error": False, "chat_error": False, "page_errors": []}
    page.on("pageerror", lambda err: state["page_errors"].append(str(err)))

    def serve(route):
        request = route.request
        path = request.url.removeprefix(BASE).split("?", 1)[0]
        state["requests"].append(request.url)
        if not request.url.startswith(BASE):
            route.abort()
            return
        if path in ("/", "/dashboard"):
            route.fulfill(content_type="text/html", body=(WEB / ("index.html" if path == "/" else "dashboard.html")).read_text(encoding="utf-8"))
            return
        if path == "/api/chat":
            if state["chat_error"]:
                route.fulfill(status=429, json={"error": "request limit reached"})
            else:
                route.fulfill(json={"tool": state["provider_tool"], "args": ({"fact": "ProviderMarker", "who": "aisyah"} if state["provider_tool"] == "remember" else {"who":"aisyah"}), "routed_by": "bedrock", "ms": 8} if state["provider"] else {"fallback": True, "routed_by": "regex"})
            return
        if path == "/mcp":
            data = request.post_data_json
            method = data["method"]
            result = {}
            if method == "initialize":
                result = {"protocolVersion": "2025-11-25", "capabilities": {}, "serverInfo": {"name": "test", "version": "1"}}
            elif method == "tools/call":
                state["calls"].append(data["params"])
                tool = data["params"]["name"]
                args = data["params"]["arguments"]
                result = {"content": [{"type": "text", "text": args.get("fact", "fixture answer")}], "isError": state["tool_error"]}
                if tool == "timeline":
                    result["structuredContent"] = TIMELINE
            elif method == "resources/read":
                result = {"contents": [{"uri": "ui://memory/timeline", "mimeType": "text/html;profile=mcp-app", "text": (WEB / "timeline.html").read_text(encoding="utf-8")} ]}
            if method.startswith("notifications/"):
                route.fulfill(status=202, body="")
            else:
                route.fulfill(headers={"mcp-session-id": "fixture-session"}, json={"jsonrpc": "2.0", "id": data["id"], "result": result})
            return
        if path == "/api/reminders":
            route.fulfill(json={"reminders": state["reminders"]})
        elif path == "/api/seed":
            route.fulfill(status=500 if state["reset_error"] else 200, json={"error": "reset rejected"} if state["reset_error"] else {"seeded": 11})
        elif path == "/api/import":
            route.fulfill(json={"imported": 1, "skipped": 0, "errors": []})
        elif path == "/api/stats":
            route.fulfill(json={"global": {"asserted": 1, "true_now": 1, "retracted": 0, "superseded": 0}, "subjects": [{"subject": '<b id="injected">Literal</b>', "total": 1, "live": 1, "expiring_24h": 0, "projects": 0, "corrections": 0, "retracted": 0, "lists": 0}]})
        else:
            route.fulfill(status=404, json={"error": "unexpected fixture request"})

    context.route("**/*", serve)
    page.goto(BASE)
    expect(page.locator("#send")).to_be_enabled()
    expect(page.locator("#conv .her")).to_have_count(1)
    state["calls"].clear()
    yield page, state
    context.close()


def ask(page, text):
    before = page.locator("#conv .her").count()
    page.fill("#say", text)
    page.click("#send")
    expect(page.locator("#conv .her")).to_have_count(before + 1)
    expect(page.locator("#send")).to_be_enabled()


def test_provider_selection_executes_real_mcp_and_pins_speaker(ui):
    page, state = ui
    state["provider"] = True
    ask(page, "remember ProviderMarker")
    assert len(state["calls"]) == 1
    assert state["calls"][0]["name"] == "remember"
    assert state["calls"][0]["arguments"]["who"] == "default"
    expect(page.locator("#conv .her .bubble").last).to_have_text("ProviderMarker")


def test_protocol_payload_is_literal_not_html(ui):
    page, _ = ui
    ask(page, 'remember <b id="injected">Literal</b>')
    assert page.locator("#injected").count() == 0
    payloads = [json.loads(text) for text in page.locator("#proto pre").all_text_contents()]
    assert any(payload.get("arguments", {}).get("fact") == '<b id="injected">Literal</b>' for payload in payloads)


def test_reminders_are_scoped_safe_and_refresh_on_switch(ui):
    page, state = ui
    state["reminders"] = [{"text": 'Milk "quote" <b id="injected">Literal</b>', "hours_left": 2}]
    page.evaluate("pollReminders()")
    expect(page.locator(".expiring-item")).to_have_count(1)
    assert page.locator("#injected").count() == 0
    assert any("who=default" in url for url in state["requests"] if "/api/reminders" in url)
    page.click('[data-who="aisyah"]')
    expect(page.locator("#conv .turn")).to_have_count(0)
    page.wait_for_function("document.querySelector('#dashBtn').href.includes('who=aisyah')")
    assert any("who=aisyah" in url for url in state["requests"] if "/api/reminders" in url)
    page.click(".expiring-item")
    expect(page.locator("#conv .her")).to_have_count(1)
    assert not state["page_errors"]


def test_dashboard_subject_is_literal(ui):
    page, _ = ui
    page.goto(BASE + "/dashboard?who=default")
    expect(page.locator(".subject-card")).to_have_count(1)
    assert page.locator("#injected").count() == 0
    assert "<b" in page.locator(".subject-name").inner_text()


def test_router_preserves_case_and_correction_is_not_project_tracking(ui):
    page, state = ui
    ask(page, "remember GuestWiFi is AbC2026")
    assert state["calls"][-1]["arguments"]["fact"] == "GuestWiFi is AbC2026"
    ask(page, "change standup to ten")
    assert state["calls"][-1]["name"] == "correct"
    ask(page, "morning summary")
    assert state["calls"][-1]["name"] == "daily_brief"


@pytest.mark.parametrize("provider", [False, True])
def test_daypart_override_applies_to_both_routing_paths(ui, provider):
    page, state = ui
    state["provider"] = provider
    state["provider_tool"] = "catch_me_up"
    page.click('[data-hour="7"]')
    expect(page.locator("#send")).to_be_enabled()
    assert state["calls"][-1]["arguments"]["hour"] == 7
    page.click('[data-hour="23"]')
    expect(page.locator("#send")).to_be_enabled()
    assert state["calls"][-1]["arguments"]["hour"] == 23


def test_delayed_routing_preserves_subject_hour_and_disables_switch(ui):
    page, _ = ui
    page.evaluate("""() => {
      currentWho = 'hasif'; hourOverride = 7;
      const realFetch = window.fetch;
      window.fetch = (url, options) => url === '/api/chat'
        ? new Promise(resolve => { window.releaseRouting = () => resolve(new Response(JSON.stringify({tool:'catch_me_up',args:{who:'aisyah'},routed_by:'fixture'}),{status:200,headers:{'Content-Type':'application/json'}})); })
        : realFetch(url, options);
      say('catch me up');
    }""")
    expect(page.locator('[data-who="aisyah"]')).to_be_disabled()
    expect(page.locator('[data-hour="23"]')).to_be_disabled()
    page.evaluate("releaseRouting()")
    expect(page.locator("#send")).to_be_enabled()
    arguments = page.evaluate("JSON.parse(document.querySelectorAll('#proto pre')[document.querySelectorAll('#proto pre').length-2].textContent)")
    assert arguments['arguments']['who'] == 'hasif'
    assert arguments['arguments']['hour'] == 7


def test_timeline_renders_structured_spoken_and_visual_resource(ui):
    page, state = ui
    ask(page, "show me the history of standup")
    expect(page.locator("#conv .her .bubble").last).to_have_text(TIMELINE["spoken"])
    frame = page.frame_locator('iframe[title="Memory timeline"]')
    expect(frame.locator("#entries li")).to_have_count(2)
    expect(frame.locator("#entries")).to_contain_text("standup is nine")
    assert not state["page_errors"]


def test_reset_failure_preserves_conversation(ui):
    page, state = ui
    state["reset_error"] = True
    page.click("#resetBtn")
    expect(page.locator("#conv .her .bubble").last).to_contain_text("reset")
    assert page.locator("#conv .her").count() >= 2


def test_tool_error_is_not_rendered_as_success(ui):
    page, state = ui
    state["tool_error"] = True
    ask(page, "standup")
    expect(page.locator("#conv .her .bubble").last).to_contain_text("Something went wrong")


def test_rate_limit_does_not_silently_bypass_to_mcp(ui):
    page, state = ui
    state["chat_error"] = True
    ask(page, "remember quota-marker")
    assert not state["calls"]
    expect(page.locator("#conv .her .bubble").last).to_contain_text("request limit")


def test_busy_guard_blocks_duplicate_entrypoints(ui):
    page, state = ui
    page.evaluate("Promise.all([say('remember first'), say('remember second')])")
    expect(page.locator("#send")).to_be_enabled()
    assert len(state["calls"]) == 1


@pytest.mark.parametrize("width", [375, 768, 1440])
def test_layout_has_no_horizontal_overflow(ui, width):
    page, _ = ui
    page.set_viewport_size({"width": width, "height": 1000})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    expect(page.locator("#say")).to_be_visible()


def test_voice_unsupported_retains_keyboard_input(ui):
    page, _ = ui
    expect(page.locator("#micBtn")).to_be_disabled()
    ask(page, "daily brief")
    expect(page.locator("#conv .her .bubble").last).to_have_text("fixture answer")


def test_displayed_suggestions_route_to_intended_tools(ui):
    page, _ = ui
    expected = ["catch_me_up", "daily_brief", "what_time_is_it", "what_changed", "wrong_about", "set_profile", "set_profile", "add_to_list", "get_list", "track", "my_projects", "remember_for", "remember_for", "share", "share", "shared_with_me", "timeline", "what_moved"]
    actual = page.evaluate("SUGGESTIONS.map(s => route(s.text).tool)")
    assert actual == expected


def test_voice_permission_error_remains_visible(browser):
    context = browser.new_context()
    context.add_init_script("""window.SpeechRecognition = class {
      start() { this.onerror({error:'not-allowed'}); this.onend(); }
      stop() {}
    };""")
    page = context.new_page()
    page.route("**/*", lambda r: r.fulfill(content_type="text/html", body=(WEB / "index.html").read_text(encoding="utf-8")) if r.request.url == BASE + "/" else r.fulfill(json={"jsonrpc":"2.0","id":1,"result":{}}))
    page.goto(BASE)
    page.wait_for_function("connected && !busy")
    page.click("#micBtn")
    expect(page.locator("#voiceStatus")).to_contain_text("not-allowed")
    expect(page.locator("#send")).to_be_enabled()
    context.close()

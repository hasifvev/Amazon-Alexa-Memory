"""Telegram Bot webhook bridge for Alexa Memory.

Lets users text the Alexa Memory system via Telegram instead of (or in
addition to) an Echo device. Any message sent to the bot is routed through
the same LLM router and tool dispatch pipeline as the web UI.

Setup (takes 2 minutes):
1. Open Telegram, message @BotFather
2. Send: /newbot
3. Follow prompts, get your token
4. Set env var: TELEGRAM_BOT_TOKEN=<your-token>
5. Set your server's webhook:
   curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \\
        -d "url=https://YOUR_SERVER/api/webhook/telegram"

Then message your bot — it responds using your stored Alexa memory.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

log = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


def get_bot_token() -> str | None:
    """Read the bot token from environment. Returns None if not configured."""
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() or None


async def send_telegram_message(token: str, chat_id: int | str, text: str) -> None:
    """Send a reply to a Telegram chat via the Bot API."""
    try:
        import httpx
        url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json={"chat_id": chat_id, "text": text})
    except ImportError:
        # httpx not installed — fall back to urllib
        import urllib.request
        import urllib.parse
        url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
        try:
            urllib.request.urlopen(url, data, timeout=10)
        except Exception as e:
            log.warning("Telegram send failed (urllib): %s", e)
    except Exception as e:
        log.warning("Telegram send failed: %s", e)


def extract_update(body: dict) -> tuple[int | None, str | None, str | None]:
    """Extract (chat_id, user_text, username) from a Telegram update dict."""
    msg = body.get("message") or body.get("edited_message")
    if not msg:
        return None, None, None
    chat_id = msg.get("chat", {}).get("id")
    text = msg.get("text", "").strip()
    username = (
        msg.get("from", {}).get("username")
        or msg.get("from", {}).get("first_name")
        or "telegram_user"
    )
    return chat_id, text or None, username


async def handle_telegram_update(body: dict, tools_factory) -> str:
    """Process one Telegram update and return the spoken reply.

    ``tools_factory`` is a callable that accepts a subject name and returns
    a MemoryTools instance scoped to that subject — same pattern as
    ``MemoryTools.for_subject()`` in the main server.
    """
    chat_id, text, username = extract_update(body)
    if not chat_id or not text:
        return "ok"

    # Use telegram username as the memory subject so each user gets their own
    # memory namespace, separate from the household default.
    subject = f"tg:{username}".lower()[:32]

    # Route via LLM (same pipeline as /api/chat)
    from server.llm_router import route_with_llm
    route = route_with_llm(text, who=subject)

    if route is None:
        # LLM unavailable — use a simple fallback
        reply = "I'm having trouble connecting to my routing brain. Try again in a moment."
    else:
        tool_name = route["tool"]
        tool_args = route.get("args", {})
        t = tools_factory(subject)

        try:
            tool_map = {
                "catch_me_up": lambda a: t.catch_me_up(named=a.get("full", False)),
                "remember": lambda a: t.remember(a.get("fact", "")),
                "remember_for": lambda a: t.remember_for(a.get("fact", ""), a.get("until", "")),
                "recall": lambda a: t.recall(a.get("about", ""), a.get("when")),
                "correct": lambda a: t.correct(a.get("about", ""), a.get("new_fact", "")),
                "forget": lambda a: t.forget(a.get("about", ""), a.get("reason", "you told me it was wrong")),
                "what_changed": lambda a: t.what_changed(a.get("since", "14 days ago")),
                "wrong_about": lambda a: t.wrong_about(),
                "what_moved": lambda a: t.what_moved(),
                "share": lambda a: t.share(a.get("fact", ""), a.get("with_who", "")),
                "shared_with_me": lambda a: t.shared_with_me(),
                "timeline": lambda a: t.timeline(a.get("about", "")).spoken,
                "what_time_is_it": lambda a: t.what_time_is_it(),
                "add_to_list": lambda a: t.add_to_list(a.get("item", ""), a.get("list_name", "shopping")),
                "get_list": lambda a: t.get_list(a.get("list_name", "shopping")),
                "remove_from_list": lambda a: t.remove_from_list(a.get("item", ""), a.get("list_name", "shopping")),
                "track": lambda a: t.track(a.get("project", ""), a.get("status", ""), a.get("note", "")),
                "my_projects": lambda a: t.my_projects(),
                "set_profile": lambda a: t.set_profile(a.get("key", ""), a.get("value", "")),
                "daily_brief": lambda a: t.daily_brief(),
            }
            fn = tool_map.get(tool_name)
            reply = fn(tool_args) if fn else f"Unknown tool: {tool_name}"
            if hasattr(reply, "spoken"):
                reply = str(reply.spoken)
        except Exception as e:
            reply = f"Something went wrong: {e}"
            log.exception("Telegram tool dispatch error")

    # Send the reply back to Telegram
    token = get_bot_token()
    if token:
        await send_telegram_message(token, chat_id, str(reply))

    return str(reply)

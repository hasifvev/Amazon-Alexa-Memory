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
        except Exception:
            log.warning("Telegram send failed")
    except Exception:
        log.warning("Telegram send failed")


class TelegramBridge:
    """Authenticated at the transport; private numeric identities only.

    At-most-once within this process. Restart clears the bounded replay cache.
    Sending failure is not retried because that could duplicate stored effects.
    """
    def __init__(self, tools_factory):
        from collections import OrderedDict
        self.tools_factory = tools_factory
        self.seen = OrderedDict()
        self.high_water = -1

    def configured(self):
        return bool(get_bot_token() and os.environ.get('TELEGRAM_WEBHOOK_SECRET'))

    async def handle(self, body):
        from server.safety import text
        import re
        if not self.configured(): raise ValueError()
        update = body.get('update_id')
        if type(update) is not int or update < 0: raise ValueError()
        msg = body.get('message')
        if msg is None: return 'ignored'
        if not isinstance(msg,dict): raise ValueError()
        chat, sender = msg.get('chat'), msg.get('from')
        if not isinstance(chat,dict) or not isinstance(sender,dict): raise ValueError()
        if chat.get('type') != 'private': return 'ignored'
        if type(sender.get('id')) is not int or sender['id'] <= 0 or type(chat.get('id')) is not int or chat['id'] != sender['id']: raise ValueError()
        value = text(msg.get('text'))
        if update in self.seen or update <= self.high_water - 4096: return 'duplicate'
        self.seen[update] = True
        self.high_water = max(self.high_water, update)
        if len(self.seen)>4096: self.seen.popitem(last=False)
        scoped = self.tools_factory(f"tg:{sender['id']}")
        reply = "Try 'remember that ...', 'recall ...', or 'shopping list'."
        try:
            for pattern, tool, key in [
                (r'remember(?: that)? (.+)','remember','fact'),
                (r'(?:add|buy) (.+)','add_to_list','item'),
                (r'(?:forget|withdraw) (.+)','forget','about'),
                (r'(?:recall|tell me about) (.+)','recall','about')]:
                match = re.fullmatch(pattern,value,re.I)
                if match:
                    reply = getattr(scoped,tool)(**{key:match.group(1)})
                    break
            else:
                if value.lower() in ('hi','hello','/start','catch me up'): reply = scoped.catch_me_up()
                elif value.lower() in ('daily brief','brief me'): reply = scoped.daily_brief()
                elif value.lower() in ('shopping list','my list'): reply = scoped.get_list()
        except Exception:
            reply = 'Unable to process this request.'
        await send_telegram_message(get_bot_token(),chat['id'],str(reply))
        return str(reply)

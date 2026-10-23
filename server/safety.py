"""Local simulated transport boundaries; these are not user authentication."""
import hmac
import json
import os
import time
from collections import deque
from starlette.responses import JSONResponse

BODY_LIMIT = 128 * 1024
TEXT_LIMIT = 2000


def subject(value=None):
    if value is None: return 'default'
    if not isinstance(value, str) or len(value) > 128:
        raise ValueError('invalid subject')
    return value.strip().lower() or 'default'


def text(value, *, blank=False, limit=TEXT_LIMIT):
    if not isinstance(value, str) or len(value) > limit or (not blank and not value.strip()):
        raise ValueError('invalid text')
    return value.strip()


class SafetyMiddleware:
    """Bound bodies before parsing, requests per minute, and active requests.

    Limits are global to this single worker, so untrusted proxy IP headers cannot
    create unlimited rate buckets. Telegram authentication precedes body reads.
    """
    def __init__(self, app, settings, mcp=None, rate=120, concurrency=8):
        self.app = app
        self.mcp = mcp
        self.settings = settings
        self.rate = rate
        self.concurrency = concurrency
        self.arrivals = deque()
        self.active = 0

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        async def reject(code, message):
            await JSONResponse({'error':message}, status_code=code)(scope, receive, send)
        headers = {k.decode('latin1').lower(): v.decode('latin1') for k,v in scope['headers']}
        if headers.get('host', '') not in self.settings.allowed_hosts:
            return await reject(421, 'host not allowed')
        origin = headers.get('origin')
        if origin is not None and origin not in self.settings.allowed_origins:
            return await reject(403, 'origin not allowed')
        if scope['path'] == '/api/webhook/telegram' and scope['method'] == 'POST':
            secret = os.environ.get('TELEGRAM_WEBHOOK_SECRET', '')
            if not secret or not os.environ.get('TELEGRAM_BOT_TOKEN', ''):
                return await reject(503, 'bridge disabled')
            if not hmac.compare_digest(headers.get('x-telegram-bot-api-secret-token', ''), secret):
                return await reject(403, 'not authorized')
        now = time.monotonic()
        while self.arrivals and self.arrivals[0] <= now - 60:
            self.arrivals.popleft()
        if len(self.arrivals) >= self.rate or self.active >= self.concurrency:
            return await reject(429, 'request limit reached')
        self.arrivals.append(now)
        self.active += 1
        try:
            # GET MCP streams may stay open; there is no request body to buffer.
            if scope['method'] in ('POST', 'PUT', 'PATCH'):
                chunks = []
                size = 0
                while True:
                    event = await receive()
                    if event['type'] == 'http.disconnect': return
                    size += len(event.get('body', b''))
                    if size > BODY_LIMIT:
                        return await reject(413, 'body too large')
                    chunks.append(event.get('body', b''))
                    if not event.get('more_body', False): break
                body = b''.join(chunks)
                # MCP and custom JSON accept objects only, never arrays/scalars.
                if scope['path'] == '/mcp' or scope['path'] in ('/api/chat','/api/import','/api/webhook/telegram'):
                    try:
                        obj = json.loads(body)
                        if not isinstance(obj, dict): raise ValueError()
                    except (ValueError, UnicodeError):
                        return await reject(400, 'invalid JSON object')
                    if scope['path'] == '/mcp' and obj.get('method') == 'tools/call':
                        from server.llm_router import validate_route
                        params = obj.get('params')
                        if not isinstance(params,dict) or not isinstance(params.get('arguments',{}),dict):
                            return await reject(400,'invalid tool arguments')
                        arguments = params.get('arguments',{})
                        try:
                            registry = {t.name:t for t in await self.mcp.list_tools()}
                            valid = validate_route({'tool':params.get('name'),'args':arguments},subject(arguments.get('who')),registry)
                        except (ValueError,TypeError): valid = None
                        if valid is None: return await reject(400,'invalid tool arguments')
                original_receive = receive
                delivered = False
                async def buffered_receive():
                    nonlocal delivered
                    if not delivered:
                        delivered = True
                        return {'type':'http.request','body':body,'more_body':False}
                    return await original_receive()
                receive = buffered_receive
            return await self.app(scope, receive, send)
        finally:
            self.active -= 1

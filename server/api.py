"""Bounded current-snapshot APIs for the simulated household experience."""
import math
import os
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from starlette.responses import JSONResponse, Response
from core.store import Kind, Memory, parse_time
from server.safety import SafetyMiddleware, subject, text


def install_api(mcp, tools, *, demo, web_dir, settings):
    # FastMCP 1.x exposes custom routes and an application factory, not middleware
    # settings. Replace only our API routes before the factory builds Starlette.
    mcp._custom_starlette_routes[:] = [r for r in mcp._custom_starlette_routes if not r.path.startswith('/api/')]
    original = mcp.streamable_http_app
    def application(*args, **kwargs):
        app = original(*args, **kwargs)
        app.add_middleware(SafetyMiddleware, settings=settings, mcp=mcp)
        app.state.memory_tools = tools
        return app
    mcp.streamable_http_app = application

    def route(path, methods):
        def register(fn):
            @wraps(fn)
            async def bounded(request):
                try:
                    return await fn(request)
                except (ValueError, TypeError, KeyError, OverflowError):
                    return JSONResponse({'error':'invalid request'}, status_code=400)
                except Exception:
                    return JSONResponse({'error':'request could not be processed'}, status_code=500)
            mcp.custom_route(path, methods=methods)(bounded)
            return bounded
        return register

    @route('/api/seed', ['POST'])
    async def reset(request):
        if not demo:
            return JSONResponse({'error':'demo reset disabled'}, status_code=403)
        from server.demo import seed
        with tools.store.lock:
            tools.store.archive_reset()
            seed(tools.store)
            return JSONResponse({'seeded':len(tools.store)})

    @route('/api/chat', ['POST'])
    async def chat(request):
        from server import llm_router
        body = await request.json()
        if set(body) - {'text','who'}: raise ValueError()
        value = text(body.get('text'))
        who = subject(body.get('who'))
        start = time.perf_counter()
        result = await llm_router.route_async(value, who)
        if result is None:
            return JSONResponse({'fallback':True,'routed_by':'regex'})
        registered = {t.name:t for t in await mcp.list_tools()}
        validated = llm_router.validate_route(result, who, registered, user_text=value)
        if validated is None:
            return JSONResponse({'fallback':True,'routed_by':'regex'})
        return JSONResponse({**validated,'routed_by':'bedrock','ms':round((time.perf_counter()-start)*1000,1)})

    @route('/api/reminders', ['GET'])
    async def reminders(request):
        hours = float(request.query_params.get('hours','24'))
        if not math.isfinite(hours) or not 0 <= hours <= 720: raise ValueError()
        who = subject(request.query_params.get('who'))
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=hours)
        records = []
        for m in tools.store.live(who):
            if m.valid_until and now <= parse_time(m.valid_until) <= cutoff:
                records.append({'id':m.id,'text':m.text,'subject':m.subject,'expires_at':m.valid_until,'hours_left':round((parse_time(m.valid_until)-now).total_seconds()/3600,1)})
        records.sort(key=lambda r:parse_time(r['expires_at']))
        return JSONResponse({'window_hours':hours,'count':len(records),'reminders':records})

    @route('/api/stats', ['GET'])
    async def stats(request):
        now = datetime.now(timezone.utc)
        who = subject(request.query_params.get('who'))
        store = tools.store
        with store.lock:
            live_ids = {m.id for m in store.live(who) if m.kind is not Kind.EVENT}
            subjects = {}
            for m in store.all():
                if m.subject != who or m.kind is Kind.EVENT: continue
                counts = subjects.setdefault(m.subject, dict(subject=m.subject,total=0,live=0,retracted=0,expiring_24h=0,lists=0,projects=0,corrections=0))
                counts['total'] += 1
                if store.retraction(m.id): counts['retracted'] += 1
                if store.superseded_by(m.id): counts['corrections'] += 1
                if m.id not in live_ids: continue
                counts['live'] += 1
                counts['lists'] += any(t.startswith('list:') for t in m.tags)
                counts['projects'] += any(t.startswith('project:') for t in m.tags)
                if m.valid_until and now <= parse_time(m.valid_until) <= now+timedelta(hours=24): counts['expiring_24h'] += 1
            rows = list(subjects.values())
            totals = {'asserted':sum(r['total'] for r in rows),'retracted':sum(r['retracted'] for r in rows),'superseded':sum(r['corrections'] for r in rows),'true_now':len(live_ids)}
            return JSONResponse({'generated_at':now.isoformat(),'global':totals,'subjects':rows})

    @route('/api/export', ['GET'])
    async def export(request):
        who = subject(request.query_params.get('who'))
        fmt = request.query_params.get('fmt','json')
        memories = [m for m in tools.store.live(who) if m.kind is not Kind.EVENT]
        if fmt == 'md':
            return Response('# Memory current snapshot\n\n'+'\n'.join('- '+m.text for m in memories), media_type='text/markdown')
        if fmt != 'json': raise ValueError()
        return JSONResponse({'version':1,'exported_at':datetime.now(timezone.utc).isoformat(),'memories':[m.to_dict() for m in memories]})

    @route('/api/import', ['POST'])
    async def import_snapshot(request):
        body = await request.json()
        who = subject(request.query_params.get('who'))
        if type(body.get('version')) is not int or body['version'] != 1 or not isinstance(body.get('memories'),list) or len(body['memories']) > 200:
            raise ValueError()
        # Validate the complete transfer before writing a single event.
        candidates = {}
        for entry in body['memories']:
            if not isinstance(entry,dict) or set(entry) != set(Memory(text='schema').to_dict()): raise ValueError()
            m = Memory.from_dict(entry)
            if m.subject != who or m.kind is Kind.EVENT or entry['id'] != m.id: raise ValueError()
            if m.id in candidates and candidates[m.id] != m: raise ValueError()
            candidates[m.id] = m
        store = tools.store
        imported = skipped = 0
        with store.lock:
            for m in candidates.values():
                old = store.get(m.id)
                if old is not None and old != m: raise ValueError()
            for m in candidates.values():
                if store.get(m.id) is not None: skipped += 1
                else: store.add(m); imported += 1
        return JSONResponse({'imported':imported,'skipped':skipped,'errors':[],'total':len(body['memories'])})

    from server.telegram_bridge import TelegramBridge
    bridge = TelegramBridge(tools.for_subject)
    @route('/api/webhook/telegram', ['GET'])
    async def telegram_status(request):
        return JSONResponse({'status':'configured' if bridge.configured() else 'not_configured'})
    @route('/api/webhook/telegram', ['POST'])
    async def telegram(request):
        reply = await bridge.handle(await request.json())
        return JSONResponse({'ok':True,'reply':reply})

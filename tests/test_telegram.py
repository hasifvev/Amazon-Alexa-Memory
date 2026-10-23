import anyio
import httpx
from server.app import build_server


def test_authenticated_numeric_private_and_replay(tmp_path,monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','synthetic-token')
    monkeypatch.setenv('TELEGRAM_WEBHOOK_SECRET','synthetic-secret')
    sent=[]
    async def send(*args):sent.append(args)
    monkeypatch.setattr('server.telegram_bridge.send_telegram_message',send)
    async def run():
        app=build_server(tmp_path/'tg.jsonl').streamable_http_app()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8000') as c:
                body={'update_id':1,'message':{'chat':{'id':123,'type':'private'},'from':{'id':123,'username':'mutable'},'text':'remember synthetic Telegram fact'}}
                assert (await c.post('/api/webhook/telegram',json=body)).status_code==403
                # Authentication must precede malformed/oversized body handling.
                assert (await c.post('/api/webhook/telegram',content=b'x'*140000)).status_code==403
                headers={'X-Telegram-Bot-Api-Secret-Token':'synthetic-secret'}
                assert (await c.post('/api/webhook/telegram',json=body,headers=headers)).status_code==200
                assert (await c.post('/api/webhook/telegram',json=body,headers=headers)).json()['reply']=='duplicate'
                assert len(sent)==1
                assert [m.subject for m in app.state.memory_tools.store.all()]==['tg:123']
                body['update_id']=2;body['message']['chat']['type']='group'
                assert (await c.post('/api/webhook/telegram',json=body,headers=headers)).json()['reply']=='ignored'
                assert len(sent)==1
    anyio.run(run)

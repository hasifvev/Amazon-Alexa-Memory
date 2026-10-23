"""Independent acceptance probe. Uses disposable local state; no providers/messages."""
import json, os, sys, tempfile, time, subprocess, re, hashlib
from pathlib import Path

import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[3])
parser.add_argument('--out',type=Path,default=None)
options=parser.parse_args()
ROOT=options.root.resolve()
OUT=options.out.resolve() if options.out else Path(tempfile.mkdtemp(prefix='alexa-acceptance-'))
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0, str(ROOT))
os.environ.update(MEMORY_STORE=str(OUT/'module-disposable.jsonl'),MEMORY_DEMO='0',MEMORY_BEDROCK='0',AWS_EC2_METADATA_DISABLED='true',TELEGRAM_BOT_TOKEN='',TELEGRAM_WEBHOOK_SECRET='')
from tests.test_live_browser import live_server
import httpx

report = {'scope':'actual disposable localhost HTTP, no cloud inference/messages', 'tools':[], 'auxiliary':[], 'routing':[], 'source':[]}
def parse(response):
    response.raise_for_status()
    if 'text/event-stream' in response.headers.get('content-type',''):
        return json.loads(next(line[6:] for line in response.text.splitlines() if line.startswith('data: ')))
    return response.json()

run_folder=Path(tempfile.mkdtemp(prefix='wire-clean-',dir=OUT))
with live_server(run_folder/'wire-disposable.jsonl',run_folder/'wire-server.log') as origin:
    with httpx.Client(base_url=origin,timeout=20) as client:
        headers={'Origin':origin,'Accept':'application/json, text/event-stream','Content-Type':'application/json','MCP-Protocol-Version':'2025-11-25'}
        i=0
        def rpc(method,params=None):
            global i
            i+=1
            response=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':i,'method':method,'params':params or {}})
            msg=parse(response)
            if method=='initialize': headers['Mcp-Session-Id']=response.headers['mcp-session-id']
            assert not msg.get('error'),msg
            return msg['result']
        init=rpc('initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'independent-acceptance','version':'2026-10-21'}})
        report['protocol']=init['protocolVersion']
        client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','method':'notifications/initialized'}).raise_for_status()
        inventory=rpc('tools/list')['tools']
        report['inventory']=[t['name'] for t in inventory]
        cases=[
            ('catch_me_up',{'hour':8},None),
            ('remember',{'fact':'acceptance marker is AlphaCase'},'AlphaCase'),
            ('recall',{'about':'acceptance marker'},'AlphaCase'),
            ('correct',{'about':'acceptance marker','new_fact':'acceptance marker is BetaCase'},'Updated'),
            ('recall',{'about':'acceptance marker'},'BetaCase'),
            ('what_changed',{'since':'7 days ago'},'BetaCase'),
            ('what_moved',{},'facts changed'),
            ('timeline',{'about':'acceptance marker'},None),
            ('remember_for',{'fact':'disposable code is TempCase','until':'tomorrow'},'TempCase'),
            ('share',{'fact':'acceptance dinner is SevenCase','with_who':'aisyah'},None),
            ('shared_with_me',{'who':'aisyah'},'SevenCase'),
            ('what_time_is_it',{},None),
            ('add_to_list',{'item':'oat milk'},'oat milk'),
            ('add_to_list',{'item':'milk'},None),
            ('get_list',{},'oat milk'),
            ('remove_from_list',{'item':'milk'},None),
            ('get_list',{},'oat milk'),
            ('track',{'project':'Acceptance','status':'building'},None),
            ('my_projects',{},'Acceptance'),
            ('set_profile',{'key':'name','value':'TestPerson'},'TestPerson'),
            ('daily_brief',{},'TestPerson'),
            ('forget',{'about':'acceptance marker'},None),
            ('wrong_about',{},'BetaCase'),
            ('recall',{'about':'acceptance marker'},"don't know"),
        ]
        for name,args,expected in cases:
            start=time.perf_counter()
            result=rpc('tools/call',{'name':name,'arguments':{'who':'default',**args}})
            spoken=result.get('structuredContent',{}).get('spoken') or ' '.join(c.get('text','') for c in result.get('content',[]))
            checks={'name':name,'args':args,'isError':result.get('isError',False),'spoken':spoken,'ms':round((time.perf_counter()-start)*1000,2)}
            if name=='timeline':
                structured=result.get('structuredContent',{})
                checks['entries']=structured.get('entries')
                checks['pass']=not result.get('isError') and len(structured.get('entries',[]))==2
            else:
                checks['pass']=not result.get('isError') and bool(spoken) and (expected is None or expected.lower() in spoken.lower())
            report['tools'].append(checks)
        resource=rpc('resources/read',{'uri':'ui://memory/timeline'})
        report['resource']={'pass':bool(resource.get('contents')),'mimeType':resource['contents'][0].get('mimeType')}
        for path in ['/api/stats?who=default','/api/reminders?who=default','/api/export?who=default','/api/export?fmt=md&who=default','/api/webhook/telegram','/dashboard?who=default']:
            r=client.get(path)
            report['auxiliary'].append({'path':path,'status':r.status_code,'pass':r.status_code==200})
        report['catalogue_complete']=set(report['inventory'])=={c['name'] for c in report['tools']}

# Exercise the browser's pure local grammar with Node, without mocking MCP results.
html=(ROOT/'web/index.html').read_text(encoding='utf8')
functions=html[html.index('function route(said)'):html.index('async function say(text)')]
cases=[
('catch me up','catch_me_up'),('daily brief','daily_brief'),('what time is it','what_time_is_it'),
('what has changed lately','what_changed'),('what have I been wrong about','wrong_about'),
('my name is TestPerson','set_profile'),('I live in Kuala Lumpur','set_profile'),
('my timezone is UTC+8','set_profile'),('call me TestPerson','set_profile'),
('add milk to my shopping list','add_to_list'),('what is on my shopping list','get_list'),
('remove milk from shopping list','remove_from_list'),('I got the eggs','remove_from_list'),
('track Amazon Hackathon as building','track'),('what am I working on','my_projects'),
('remember to buy milk just for today','remember_for'),('note dentist is at 3pm until Friday','remember_for'),
('tell Aisyah the new wifi is Guest2026','share'),('let Hasif know dinner is at seven','share'),
('what has been shared with me','shared_with_me'),('show me the history of standup','timeline'),
('what has moved over time','what_moved'),('what was standup 100 days ago','recall'),
('what is standup','recall'),('change standup to eleven','correct'),('forget standup','forget'),
('remember the marker is AlphaCase','remember'),('good morning','catch_me_up'),
('give me my brief','daily_brief'),('brief me','daily_brief'),('give me the full picture','daily_brief'),
('what is my morning summary','daily_brief'),('what did I miss','catch_me_up'),
('standup moved to ten','correct'),("it is eleven now",'clarify'),
('I was mistaken about standup','forget'),('what did I get wrong','wrong_about'),
('which facts have the longest history','what_moved'),("read my packing list",'get_list'),
('put eggs on the grocery list','add_to_list'),('cross off bread','remove_from_list'),
('update Amazon project to submitted','track'),('log that EduPlay is in planning','track'),
('what goals am I tracking','my_projects'),('what is today\'s date','what_time_is_it'),
('what did someone leave for me','shared_with_me'),("don't let me forget the marker is CaseValue",'remember'),
('remind me about the dentist for the next 2 days','remember_for'),
('what have I believed about standup','timeline'),('is it Friday yet','what_time_is_it'),
('please add Milk to my shopping list','add_to_list'),('can you remember that marker is AlphaCase','remember'),
]
cases += [('what is my name', 'recall'), ('what is my timezone', 'recall'), ('where do I live', 'recall'), ('what is my location', 'recall'), ('can you tell me my name', 'recall'), ('what is standup time', 'recall'), ('show my projects', 'my_projects'), ('what did Hasif share with me', 'shared_with_me')]
js="const currentWho=''; const who=''; const hourOverride=null; const subject=()=> 'default';\n"+functions+'\nconst cases='+json.dumps(cases)+'; console.log(JSON.stringify(cases.map(([phrase,expected])=>{const actual=route(phrase);return {phrase,expected,actual,pass:expected==="clarify" ? Boolean(actual.clarification)&&!actual.tool : actual.tool===expected}})));'
script=OUT/'grammar-check.js';script.write_text(js,encoding='utf8')
r=subprocess.run(['node',str(script)],capture_output=True,text=True)
if r.returncode: report['routing_error']=r.stderr
else: report['routing']=json.loads(r.stdout)

# Secret detection reports only locations, never values. Runtime memory is excluded.
patterns={'github_token':re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}'),'aws_access_key':re.compile(r'AKIA[0-9A-Z]{16}'),'private_key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')}
names=subprocess.run(['git','ls-files','--cached','--others','--exclude-standard'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.splitlines()
for name in names:
    path=ROOT/name
    if not path.is_file() or path.suffix in ('.png','.jpg','.jpeg','.gif','.pdf','.pyc'): continue
    raw=path.read_bytes()
    report['source'].append({'path':name,'sha256':hashlib.sha256(raw).hexdigest()})
    content=raw.decode('utf8',errors='replace')
    for kind,pattern in patterns.items():
        for match in pattern.finditer(content):
            report.setdefault('secret_findings',[]).append({'path':name,'line':content[:match.start()].count('\n')+1,'kind':kind})
from urllib.parse import urlsplit
remote=subprocess.run(['git','config','--get','remote.origin.url'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
u=urlsplit(remote)
report['remote_embedded_credential']=bool(u.username or u.password)
report['remote_safe_url']=f'{u.scheme}://{u.hostname}{u.path}'
report['summary']={'wire_pass':sum(c['pass'] for c in report['tools']),'wire_total':len(report['tools']),'tools_exercised':len({c['name'] for c in report['tools']}),'routing_pass':sum(c['pass'] for c in report['routing']),'routing_total':len(report['routing'])}
(OUT/'acceptance-clean.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report['summary']))
print('Wire failures:',json.dumps([c for c in report['tools'] if not c['pass']]))
print('Routing failures:',json.dumps([c for c in report['routing'] if not c['pass']]))
print('Output:',OUT/'acceptance-clean.json')

if report['summary']['wire_pass'] != report['summary']['wire_total'] or report['summary']['routing_pass'] != report['summary']['routing_total']:
    raise SystemExit(1)

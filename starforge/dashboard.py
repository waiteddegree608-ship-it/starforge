"""Read-only, loopback monitoring. No model requests or worker mutations."""
import argparse
import ast
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import threading
import time

from .budget import day


def read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def redact(text):
    return re.sub(r'(?:gh[pousr]_[A-Za-z0-9_]+|oc_sk_[A-Za-z0-9_-]+|sk-[A-Za-z0-9_-]{16,})', '[redacted]', str(text))


def processes():
    if os.name != 'nt':
        return {'checked': False, 'workers': [], 'agents': []}
    script = "$p=Get-CimInstance Win32_Process; $w=@($p | Where-Object {$_.Name -match '^python' -and $_.CommandLine -match '-m starforge .* loop'}); $a=@($p | Where-Object {$_.Name -eq 'opencode.exe' -and $_.ParentProcessId -in $w.ProcessId}); @{checked=$true;workers=@($w | ForEach-Object {$_.ProcessId});agents=@($a | ForEach-Object {$_.ProcessId})} | ConvertTo-Json -Compress"
    try:
        result = subprocess.run(['powershell', '-NoProfile', '-Command', script], capture_output=True, text=True, timeout=12, creationflags=subprocess.CREATE_NO_WINDOW)
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {'checked': False, 'workers': [], 'agents': []}


def snapshot(config, process_state):
    state = Path(config['state_dir'])
    db = read(state/'state.json', {})
    cycles = db.get('cycles', [])
    publications = db.get('publications', [])
    logs = sorted((state/'logs').glob('*.jsonl'), key=lambda p: p.stat().st_mtime, reverse=True) if (state/'logs').exists() else []
    latest = logs[0] if logs else None
    jobs = []
    folders=sorted((state/'jobs').glob('*'), reverse=True)[:80]
    for index,folder in enumerate(folders):
        if not folder.is_dir():
            continue
        idea = read(folder/'idea.json', {})
        review = read(folder/'review.json', {})
        project = folder/'project'
        files = [{'name': p.name, 'bytes': p.stat().st_size} for p in sorted(project.glob('*')) if p.is_file() and p.name in ('cli.py','test_cli.py','README.md','README.zh-CN.md','example.json')]
        tests = None
        try:
            tree = ast.parse((project/'test_cli.py').read_text(encoding='utf-8'))
            tests = sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('test_') for n in ast.walk(tree))
        except (OSError, SyntaxError, UnicodeError):
            pass
        name = idea.get('name') or folder.name
        pending = db.get('pending') or {}
        published = next((p for p in publications if p['repository'].split('/')[-1] == name), None)
        def event_in_job(e):
            stamp=e.get('at','')[:19].replace('-','').replace(':','')+'Z'
            return stamp>=folder.name and (index==0 or stamp<folders[index-1].name)
        events = [e for e in cycles if e.get('candidate') == name or event_in_job(e)]
        phase = '需求筛选'
        if idea.get('ready') is False: phase = '未入选'
        elif files: phase = '制作中 / 中断待确认'
        if review: phase = '审查通过' if review.get('approved') else '修复 / 审查未通过'
        ownlogs = [p for p in logs if p.name.startswith(folder.name+'-')]
        active = bool(process_state.get('agents')) and latest is not None and latest.name.startswith(folder.name+'-')
        if active:
            suffix = latest.stem[len(folder.name)+1:]
            phase = '正在'+({'scout':'筛选需求','build':'编写代码','review':'审查代码'}.get(suffix, suffix.replace('repair','修复').replace('review','审查')))
        elif events and events[-1]['status'] in ('cycle_rejected','error','review_rejected','candidate_failed_ci','ci_timeout'):
            phase = {'cycle_rejected':'本轮中止','error':'运行错误','review_rejected':'审查拒绝','candidate_failed_ci':'CI 失败','ci_timeout':'CI 超时'}[events[-1]['status']]
        if pending.get('name') == name: phase = '等待 GitHub CI'
        if published: phase = '已发布'
        jobs.append({'id':folder.name,'name':name,'description':idea.get('description',''),'problem':idea.get('problem',''),'phase':phase,'active':active,'files':files,'tests':tests,'evidence':idea.get('evidence_urls',[]),'review':review,'repairs':len(list(folder.glob('review-*.json'))),'repository':published['repository'] if published else None,'branch':pending.get('branch') if pending.get('name')==name else None,'log':ownlogs[0].name if ownlogs else None,'criteria':{'demand_sources':len(set(idea.get('evidence_urls',[]))),'bilingual_docs':all((project/p).exists() for p in ('README.md','README.zh-CN.md')),'review_approved':review.get('approved'),'ci':'通过' if published else '等待' if pending.get('name')==name else '尚未验证'}})
    budget = {'day':day(),'limit':config['daily_budget_cny'],'used':0,'reserved':0,'requests':0,'tokens':0,'history':[]}
    try:
        with sqlite3.connect((state/'budget.sqlite3').as_uri()+'?mode=ro', uri=True, timeout=3) as conn:
            rows = conn.execute('SELECT day,amount,status,usage FROM requests').fetchall()
        totals = {}
        for date, amount, status, usage in rows:
            totals[date] = totals.get(date, 0)+amount
            if date == day():
                budget['used'] += amount; budget['requests'] += 1
                if status=='reserved': budget['reserved'] += amount
                try:
                    u=json.loads(usage); budget['tokens']+=u.get('prompt_tokens',0)+u.get('completion_tokens',0)
                except ValueError: pass
        budget['history']=[{'day':d,'cost':v} for d,v in sorted(totals.items())[-7:]]
    except sqlite3.Error: budget['error']='账本暂不可读'
    metrics = read(state/'dashboard-github.json', {})
    history=read(state/'metrics.json',[])
    recent=history[-1] if history else {}
    if recent.get('at','')>metrics.get('at',''):
        prior={r['name']:r for r in metrics.get('repositories',[])}
        merged=dict(prior)
        for row in recent.get('repositories',[]):
            combined={**prior.get(row['name'],{}),**row}
            if row['name'] in prior:combined['star_delta']=row['stars']-prior[row['name']]['stars']
            merged[row['name']]=combined
        metrics={'at':recent['at'],'repositories':list(merged.values())}
    activity=[]
    if latest:
        # Only expose event type/tool name, never raw model text or tool input.
        for line in latest.read_text(encoding='utf-8',errors='replace').splitlines()[-60:]:
            try:
                e=json.loads(line); part=e.get('part',{})
                activity.append({'type':e.get('type','event'),'tool':part.get('tool'),'timestamp':e.get('timestamp')})
            except ValueError: pass
    pause=read(state/'PAUSE', None)
    return {'at':datetime.now(timezone.utc).isoformat(),'process':process_state,'pause':pause,'budget_wait':db.get('budget_wait_day')==day(),'budget':budget,'jobs':jobs,'publications':publications,'events':cycles[-30:][::-1],'metrics':metrics,'activity':activity[-12:],'latest_log':latest.name if latest else None,'pricing_valid_until':config['pricing']['valid_until'],'owner':config['owner']}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8766)
    args=parser.parse_args()
    cached={'process':processes(),'at':time.monotonic()}
    lock=threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get('Host') not in (f'127.0.0.1:{args.port}',f'localhost:{args.port}'):
                self.send_error(403); return
            if self.path=='/api/status':
                with lock:
                    if time.monotonic()-cached['at']>10:
                        cached.update(process=processes(),at=time.monotonic())
                    cfg=read(args.config,{})
                    payload=json.dumps(snapshot(cfg,cached['process']),ensure_ascii=False)
                data=redact(payload).encode('utf-8'); mime='application/json; charset=utf-8'
            elif self.path in ('/','/index.html'):
                data=(Path(__file__).with_name('dashboard.html')).read_bytes(); mime='text/html; charset=utf-8'
            else:
                self.send_error(404); return
            self.send_response(200)
            self.send_header('Content-Type',mime)
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers(); self.wfile.write(data)
        def log_message(self,*args): pass
    print(f'Starforge dashboard http://127.0.0.1:{args.port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()


if __name__=='__main__': main()

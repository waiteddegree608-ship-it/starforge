"""Optional GitHub snapshot refresh. No LLM calls; no scheduled Codex task."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from starforge.github import GitHub
from starforge.secrets import credential
from starforge.controller import read, save

parser=argparse.ArgumentParser()
parser.add_argument('--config',required=True,type=Path)
args=parser.parse_args()
cfg=read(args.config,{})
state=Path(cfg['state_dir'])
db=read(state/'state.json',{})
previous=read(state/'dashboard-github.json',{}).get('repositories',[])
client=GitHub(credential('github',cfg['secrets_dir']),cfg['owner'])
names=['verbatim-guard','Ekina','paperfect','starforge']+[p['repository'].split('/')[-1] for p in db.get('publications',[])]
rows=[]
for name in dict.fromkeys(names):
    repo=client.api(f"/repos/{cfg['owner']}/{name}")
    row={'name':name,'stars':repo['stargazers_count'],'forks':repo['forks_count'],'open_issues':repo['open_issues_count']}
    old=next((r for r in previous if r['name']==name),None)
    if old:row['star_delta']=row['stars']-old['stars']
    runs=client.api(f"/repos/{cfg['owner']}/{name}/actions/runs?branch=main&per_page=1")['workflow_runs']
    if runs:row.update(ci=runs[0]['conclusion'] or runs[0]['status'],ci_url=runs[0]['html_url'])
    releases=client.api(f"/repos/{cfg['owner']}/{name}/releases?per_page=1")
    if releases:row.update(release=releases[0]['tag_name'],release_url=releases[0]['html_url'])
    rows.append(row)
save(state/'dashboard-github.json',{'at':datetime.now(timezone.utc).isoformat(),'repositories':rows})
print(json.dumps({'refreshed':len(rows)}))

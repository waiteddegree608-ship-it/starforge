import base64
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import urllib.error
import urllib.parse


class GitHub:
    def __init__(self, token, owner):
        self.token, self.owner = token, owner

    def api(self,path,method='GET',data=None):
        req=urllib.request.Request('https://api.github.com'+path,method=method,
            data=None if data is None else json.dumps(data).encode(),
            headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json','User-Agent':'Starforge','Content-Type':'application/json'})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=45) as response:
            return json.load(response)

    def git(self,folder,*args):
        auth=base64.b64encode(('x-access-token:'+self.token).encode()).decode()
        env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='Never',GIT_CONFIG_COUNT='1',
                 GIT_CONFIG_KEY_0='http.https://github.com/.extraheader',GIT_CONFIG_VALUE_0='AUTHORIZATION: basic '+auth)
        r=subprocess.run(['git','-c','credential.helper=',*args],cwd=folder,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
        if r.returncode:raise RuntimeError('Git command failed: '+r.stderr.replace(self.token,'[redacted]').replace(auth,'[redacted]')[:1000])
        return r.stdout.strip()

    def signals(self,queries,page=1):
        rows={}
        for q in queries[:3]:
            data=self.api('/search/issues?q='+urllib.parse.quote(q)+'&sort=updated&order=desc&per_page=8&page='+str(page))
            for x in data.get('items',[]):
                rows[x['html_url']]={'url':x['html_url'],'title':x['title'][:180],'body':(x.get('body') or '')[:1000],
                    'comments':x['comments'],'reactions':x.get('reactions',{}).get('total_count',0),'updated_at':x['updated_at']}
        return list(rows.values())

    def ensure_repo(self,name,description):
        try:r=self.api(f'/repos/{self.owner}/{name}')
        except urllib.error.HTTPError as error:
            if error.code!=404:raise
            r=self.api('/user/repos','POST',{'name':name,'description':description[:300],'private':False,'has_wiki':False})
        if r['owner']['login']!=self.owner or r['private']:raise ValueError('Unexpected repository owner/visibility')
        return r

    def push(self,folder,name,branch):
        folder=Path(folder)
        if not (folder/'.git').exists():
            self.git(folder,'init','-b',branch)
            self.git(folder,'config','user.name','WaitedDegree608')
            self.git(folder,'config','user.email',self.owner+'@users.noreply.github.com')
        self.git(folder,'add','.')
        if self.git(folder,'status','--porcelain'):
            self.git(folder,'commit','-m','feat: evidence-led prototype with tests and bilingual docs')
        remote=f'https://github.com/{self.owner}/{name}.git'
        if not self.git(folder,'remote'):self.git(folder,'remote','add','origin',remote)
        if self.git(folder,'remote','get-url','origin')!=remote:raise ValueError('Unexpected Git remote')
        self.git(folder,'push','origin','HEAD:refs/heads/'+branch)
        return self.git(folder,'rev-parse','HEAD')

    def runs(self,name,sha):
        return self.api(f'/repos/{self.owner}/{name}/actions/runs?head_sha={sha}&per_page=10')['workflow_runs']

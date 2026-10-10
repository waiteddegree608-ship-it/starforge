"""Loopback-only OpenAI adapter. The real provider key never reaches the coding agent."""
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading
import urllib.request
import urllib.error
from .budget import BudgetExhausted


class Gateway:
    def __init__(self, key, budget, pricing, request_limit=24):
        self.key, self.budget, self.pricing = key, budget, pricing
        self.token = secrets.token_urlsafe(32)
        self.limit, self.requests = request_limit, 0
        self.lock = threading.Lock()
        self.stopped = False
        self.budget_blocked = False
        self.cycle_blocked = False
        self.json_output = False

    def complete(self, payload):
        if self.stopped or date.today().isoformat() > self.pricing['valid_until']:
            raise ValueError('Pricing review required or gateway stopped')
        if payload.get('model') != 'deepseek-flash':
            raise ValueError('Only the configured Flash model is permitted')
        with self.lock:
            if self.requests >= self.limit:
                self.cycle_blocked = True
                raise ValueError('Cycle request limit reached')
            self.requests += 1
        # Enforce bounded context/output even if the agent requests larger limits.
        payload = dict(payload)
        payload['stream'] = False
        payload.pop('stream_options', None)
        payload.pop('max_completion_tokens', None)
        payload['max_tokens'] = min(int(payload.get('max_tokens') or 8192),8192)
        if payload['max_tokens'] < 1:
            raise ValueError('Invalid output token limit')
        payload['thinking'] = {'type':'disabled'}
        if self.json_output:
            payload['response_format'] = {'type':'json_object'}
        raw = json.dumps(payload,ensure_ascii=False).encode('utf-8')
        if len(raw) > 180000:
            raise ValueError('Context budget exceeded')
        p=self.pricing
        def cost(i,o):return (i*p['input_usd_per_million']+o*p['output_usd_per_million'])/1e6*p['cny_per_usd_ceiling']*p['safety_multiplier']
        # Byte count plus overhead is intentionally much more conservative than token estimates.
        try:
            reservation = self.budget.reserve(cost(len(raw)+16384,payload['max_tokens']))
        except BudgetExhausted:
            self.budget_blocked = True
            raise
        req=urllib.request.Request('https://api.deepseek.com/chat/completions',data=raw,
            headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        try:
            with urllib.request.build_opener(NoRedirect()).open(req,timeout=180) as response:
                result=json.load(response)
            usage=result['usage']
            measured=cost(int(usage['prompt_tokens']),int(usage['completion_tokens']))
            self.budget.settle(reservation,measured,usage)
            return result
        except Exception:
            # Unknown outcome may have cost money: retain reservation and do not retry this cycle.
            self.stopped=True
            raise

    def start(self):
        gateway=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                if self.path not in ('/v1/chat/completions','/chat/completions') or self.headers.get('Authorization')!='Bearer '+gateway.token:
                    self.send_error(403);return
                try:
                    n=int(self.headers.get('Content-Length','0'))
                    if not 0<n<=200000:raise ValueError('Invalid payload size')
                    payload=json.loads(self.rfile.read(n))
                    streaming=payload.get('stream',False)
                    result=gateway.complete(payload)
                    if streaming:
                        choice=result['choices'][0];message=choice['message']
                        delta={'role':'assistant','content':message.get('content') or ''}
                        if message.get('reasoning_content'):delta['reasoning_content']=message['reasoning_content']
                        if message.get('tool_calls'):
                            delta['tool_calls']=[dict(t,index=i) for i,t in enumerate(message['tool_calls'])]
                        base={k:result[k] for k in ('id','model','created') if k in result}
                        base['object']='chat.completion.chunk'
                        chunks=[dict(base,choices=[{'index':0,'delta':delta,'finish_reason':None}]),
                                dict(base,choices=[{'index':0,'delta':{},'finish_reason':choice['finish_reason']}],usage=result['usage'])]
                        data=(''.join('data: '+json.dumps(c,ensure_ascii=False)+'\n\n' for c in chunks)+'data: [DONE]\n\n').encode('utf-8')
                        content_type='text/event-stream'
                    else:data=json.dumps(result).encode();content_type='application/json'
                    self.send_response(200);self.send_header('Content-Type',content_type)
                    self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
                except Exception as error:
                    # Never return provider bodies or credentials to the agent/log.
                    message=str(error) if isinstance(error,ValueError) else 'Provider request failed; cycle stopped without automatic retry'
                    data=json.dumps({'error':{'message':message,'type':'budget_gateway'}}).encode()
                    self.send_response(429 if isinstance(error,ValueError) else 502)
                    self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)))
                    self.end_headers();self.wfile.write(data)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.url=f'http://127.0.0.1:{self.server.server_port}/v1'
        return self

    def close(self):
        self.server.shutdown();self.server.server_close()

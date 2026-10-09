import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error

from starforge.budget import Budget
from starforge.gateway import Gateway
from starforge.gates import inspect
from starforge.worker import parse_object
from starforge.controller import single_runner

PRICES={'valid_until':'2099-01-01','input_usd_per_million':.3,
        'output_usd_per_million':1.2,'cny_per_usd_ceiling':8,'safety_multiplier':1.25}


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'ledger.db';self.budget=Budget(self.path,20)

    def test_reserve_before_request_and_refuse_overspend(self):
        self.budget.reserve(19)
        with self.assertRaises(ValueError):self.budget.reserve(2)
        self.assertEqual(self.budget.status()['conservative_cost_cny'],19)

    def test_settlement_releases_only_known_unused_reservation(self):
        key=self.budget.reserve(10);self.budget.settle(key,2,{'prompt_tokens':10})
        self.assertEqual(self.budget.status()['conservative_cost_cny'],2)
        self.assertEqual(self.budget.status()['unresolved_requests'],0)

    def test_crash_retains_reservation_after_reopen(self):
        self.budget.reserve(8)
        new=Budget(self.path,20)
        self.assertEqual(new.status()['unresolved_requests'],1)
        self.assertEqual(new.status()['conservative_cost_cny'],8)

    def test_invalid_amounts_rejected(self):
        for value in [-1,0,21,float('nan')]:
            with self.assertRaises(ValueError):self.budget.reserve(value)

    def test_expired_pricing_stops_without_spending(self):
        gateway=Gateway('not-a-real-key',self.budget,dict(PRICES,valid_until='2000-01-01'))
        with self.assertRaises(ValueError):gateway.complete({'model':'deepseek-flash'})
        self.assertEqual(self.budget.status()['requests'],0)

    def test_other_models_rejected_without_spending(self):
        gateway=Gateway('not-a-real-key',self.budget,PRICES)
        with self.assertRaises(ValueError):gateway.complete({'model':'expensive-model'})
        self.assertEqual(self.budget.status()['requests'],0)

    def test_network_error_retains_cost_and_stops_retries(self):
        gateway=Gateway('not-a-real-key',self.budget,PRICES)
        with patch('urllib.request.OpenerDirector.open',side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):gateway.complete({'model':'deepseek-flash','messages':[]})
        with self.assertRaises(ValueError):gateway.complete({'model':'deepseek-flash','messages':[]})
        self.assertEqual(self.budget.status()['unresolved_requests'],1)

    def test_gateway_auth_and_streamed_tool_calls(self):
        gateway=Gateway('not-a-real-key',self.budget,PRICES).start();self.addCleanup(gateway.close)
        payload=json.dumps({'model':'deepseek-flash','stream':True,'messages':[]}).encode()
        with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(urllib.request.Request(gateway.url+'/chat/completions',data=payload))
        response={'id':'test','created':1,'model':'deepseek-flash','choices':[{'index':0,'message':{'content':None,'tool_calls':[{'id':'c1','type':'function','function':{'name':'read','arguments':'{}'}}]},'finish_reason':'tool_calls'}],'usage':{'prompt_tokens':10,'completion_tokens':20}}
        with patch.object(gateway,'complete',return_value=response):
            req=urllib.request.Request(gateway.url+'/chat/completions',data=payload,headers={'Authorization':'Bearer '+gateway.token})
            text=urllib.request.urlopen(req).read().decode()
        self.assertIn('"index": 0',text);self.assertIn('tool_calls',text);self.assertTrue(text.endswith('data: [DONE]\n\n'))

    def test_runner_lock_is_exclusive(self):
        path=Path(self.temp.name)/'lock'
        with single_runner(path):
            with self.assertRaises(RuntimeError):
                with single_runner(path):pass


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        (self.root/'cli.py').write_text('print("prototype")')
        (self.root/'test_cli.py').write_text('import unittest\nclass Tests(unittest.TestCase):\n'+''.join(f'    def test_{i}(self): self.assertEqual(1,1)\n' for i in range(4)))
        (self.root/'README.md').write_text('Documented example. '*40)
        (self.root/'README.zh-CN.md').write_text('中文用途和示例。'*40,encoding='utf-8')

    def test_inspection_never_executes_generated_code(self):
        (self.root/'cli.py').write_text('raise RuntimeError("must not execute locally")')
        self.assertIn('cli.py',inspect(self.root))

    def test_config_files_cannot_cross_publication_boundary(self):
        (self.root/'opencode.json').write_text('{}')
        with self.assertRaises(ValueError):inspect(self.root)

    def test_secret_detection(self):
        (self.root/'cli.py').write_text('key="'+'sk-'+'a'*40+'"')
        with self.assertRaises(ValueError):inspect(self.root)

    def test_syntax_error_rejected(self):
        (self.root/'cli.py').write_text('def broken(')
        with self.assertRaises(SyntaxError):inspect(self.root)

    def test_missing_tests_rejected(self):
        (self.root/'test_cli.py').unlink()
        with self.assertRaises(ValueError):inspect(self.root)

    def test_too_few_tests_rejected(self):
        (self.root/'test_cli.py').write_text('def test_one(): pass')
        with self.assertRaises(ValueError):inspect(self.root)

    def test_model_json_contract(self):
        self.assertEqual(parse_object('```json\n{"ready": false}\n```'),{'ready':False})
        with self.assertRaises(ValueError):parse_object('not JSON')


if __name__=='__main__':unittest.main()

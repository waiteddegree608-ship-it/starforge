import json
from pathlib import Path
import tempfile
import unittest
from starforge.dashboard import snapshot, redact


class DashboardTests(unittest.TestCase):
    def test_no_model_execution_and_no_false_ci_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); job=root/'jobs'/'20261010T010000Z'; project=job/'project'; project.mkdir(parents=True)
            (job/'idea.json').write_text(json.dumps({'name':'sf-example','ready':True,'evidence_urls':['https://github.com/a/b/issues/1','https://github.com/a/b/issues/2']}))
            (project/'test_cli.py').write_text('raise RuntimeError("MUST NOT EXECUTE")\ndef test_example(): pass\n')
            data=snapshot({'state_dir':temp,'daily_budget_cny':20,'pricing':{'valid_until':'2026-10-17'},'owner':'example'}, {'checked':True,'workers':[],'agents':[]})
            self.assertEqual(data['jobs'][0]['tests'],1)
            self.assertEqual(data['jobs'][0]['criteria']['ci'],'尚未验证')
            self.assertFalse(data['jobs'][0]['active'])

    def test_secret_redaction(self):
        self.assertNotIn('ghp_',redact('ghp_'+'a'*30))
        self.assertNotIn('sk-',redact('sk-'+'a'*32))


if __name__=='__main__': unittest.main()

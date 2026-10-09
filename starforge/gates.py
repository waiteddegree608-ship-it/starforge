"""Controller-owned publication boundaries; generated files are never executed locally."""
import ast
import json
from pathlib import Path
import re

ALLOWED={'cli.py','test_cli.py','README.md','README.zh-CN.md','example.json'}
REQUIRED={'cli.py','test_cli.py','README.md','README.zh-CN.md'}
SECRET=re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9_-]{32,}|oc_sk_[A-Za-z0-9_-]{25,})\b|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')


def inspect(folder):
    folder=Path(folder); files={}
    for p in folder.rglob('*'):
        if p.is_symlink():raise ValueError('Symlinks are not distributable')
        if not p.is_file():continue
        rel=p.relative_to(folder).as_posix()
        if rel not in ALLOWED:raise ValueError('Unexpected generated file: '+rel)
        if p.stat().st_size>100000:raise ValueError('Generated file exceeds limit')
        text=p.read_text(encoding='utf-8')
        if SECRET.search(text):raise ValueError('Potential credential in generated files')
        if p.suffix=='.py':ast.parse(text,filename=rel)
        files[rel]=text
    if not REQUIRED<=files.keys():raise ValueError('Missing implementation, tests, or bilingual docs')
    if len(files['README.md'])<600 or len(files['README.zh-CN.md'])<200:raise ValueError('Documentation is too thin')
    tree=ast.parse(files['test_cli.py'])
    if sum(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_') for n in ast.walk(tree))<4:
        raise ValueError('At least four behavior tests required')
    if not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr.startswith('assert') for n in ast.walk(tree)):
        raise ValueError('Tests contain no assertions')
    return files


def workflow(candidate=True):
    directory='candidate' if candidate else '.'
    return f'''name: Prototype checks
on: [push, pull_request]
permissions:
  contents: read
jobs:
  verify:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    strategy:
      matrix:
        python: ['3.10', '3.13']
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - uses: actions/setup-python@v5
        with:
          python-version: ${{{{ matrix.python }}}}
      - name: Run behavior tests
        working-directory: {directory}
        run: python -I -m unittest discover -s . -p test_cli.py -v
      - name: Exercise public commands
        working-directory: {directory}
        run: |
          python -I cli.py --help
          python -I cli.py --demo
'''

"""Conservative reservations survive crashes; ambiguous requests remain charged."""
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
import math
import sqlite3
import uuid

HK = timezone(timedelta(hours=8))


class BudgetExhausted(ValueError):
    """No upstream request was sent; resume after the accounting day changes."""


def day():
    return datetime.now(HK).date().isoformat()


class Budget:
    def __init__(self, path, limit=20):
        self.path, self.limit = str(path), float(limit)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, day TEXT, amount REAL, status TEXT, usage TEXT)')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path, timeout=20)
        try:
            with db:yield db
        finally:db.close()

    def reserve(self, amount):
        if not 0 < amount <= self.limit:
            raise BudgetExhausted('Request exceeds budget')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            used = db.execute('SELECT COALESCE(SUM(amount),0) FROM requests WHERE day=?',(day(),)).fetchone()[0]
            if used + amount > self.limit:
                raise BudgetExhausted('Daily budget exhausted; no upstream request sent')
            key = uuid.uuid4().hex
            db.execute('INSERT INTO requests VALUES (?,?,?,?,?)',(key,day(),amount,'reserved','{}'))
            return key

    def settle(self, key, actual, usage):
        import json
        with self.connect() as db:
            row = db.execute('SELECT amount FROM requests WHERE id=?',(key,)).fetchone()
            if row is None or not math.isfinite(actual) or actual < 0:
                raise ValueError('Invalid settlement')
            exceeded=actual>row[0]
            db.execute('UPDATE requests SET amount=?,status=?,usage=? WHERE id=?',
                       (actual,'overrun' if exceeded else 'measured',json.dumps(usage),key))
        if exceeded:raise ValueError('Usage exceeded reservation; stop and inspect pricing')

    def status(self):
        with self.connect() as db:
            used, count = db.execute('SELECT COALESCE(SUM(amount),0),COUNT(*) FROM requests WHERE day=?',(day(),)).fetchone()
            pending = db.execute("SELECT COUNT(*) FROM requests WHERE day=? AND status='reserved'",(day(),)).fetchone()[0]
        return {'day':day(),'timezone':'Asia/Hong_Kong','budget_cny':self.limit,
                'conservative_cost_cny':round(used,6),'requests':count,'unresolved_requests':pending}

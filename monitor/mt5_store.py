"""Dedicated dnb execution storage; no legacy tracked-account state is imported.

Postgres connections belong to one Flask request. Failures roll back and close;
an ambiguous commit is never automatically retried. Business IDs settle retries.
SQLite is retained only for existing deterministic development tests.
"""
import os
import threading
from flask import g, has_app_context
import fx101

_schema_lock = threading.Lock()
_ready = False

class Postgres:
    def __init__(self, url):
        import psycopg
        from psycopg.rows import dict_row
        self.connection = psycopg.connect(url, connect_timeout=10, sslmode='verify-full',
                                         sslrootcert=os.getenv('DNB_DATABASE_CA_FILE','/etc/ssl/certs/ca-certificates.crt'),
                                         row_factory=dict_row)
        self.connection.execute("SET LOCAL statement_timeout = '25s'")
        self.connection.execute("SET LOCAL lock_timeout = '20s'")

    def execute(self, sql, params=()):
        if self.connection.info.transaction_status == 0:
            self.connection.execute("SET LOCAL statement_timeout = '25s'")
            self.connection.execute("SET LOCAL lock_timeout = '20s'")
        ignored = sql.startswith('INSERT OR IGNORE ')
        sql = sql.replace('INSERT OR IGNORE ', 'INSERT ').replace('?', '%s')
        if ignored: sql += ' ON CONFLICT DO NOTHING'
        return self.connection.execute(sql, params)

    def commit(self): self.connection.commit()
    def rollback(self): self.connection.rollback()
    def close(self): self.connection.close()
    def lock_account(self):
        # Serializes nonce/rate limits and read-check-write decisions across replicas.
        self.execute('SELECT pg_advisory_xact_lock(?)', (315307814,))

def remote(): return bool(os.getenv('DNB_DATABASE_URL'))

def db():
    if not remote():
        if os.getenv('DNB_REQUIRE_DURABLE') == '1':
            raise RuntimeError('durable_storage_required')
        return fx101.db()
    if not has_app_context(): raise RuntimeError('request_context_required')
    if 'dnb_connection' not in g: g.dnb_connection = Postgres(os.environ['DNB_DATABASE_URL'])
    return g.dnb_connection

def lock_account():
    c = db()
    if remote(): c.lock_account()
    return c

def ensure_schema(statements):
    global _ready
    if not remote():
        c = db()
        for sql in statements: c.execute(sql)
        c.commit()
        return
    if _ready: return
    with _schema_lock:
        if _ready: return
        c = db()
        # DDL protected across simultaneous service boots, not merely threads.
        c.lock_account()
        for sql in statements: c.execute(sql)
        c.commit()
        _ready = True

def close_request(_=None):
    c = g.pop('dnb_connection', None)
    if c is not None:
        try: c.rollback()
        finally: c.close()

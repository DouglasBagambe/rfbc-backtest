"""Real remote storage concurrency/reconnect tests on an isolated test branch.

Does not contact MT5 or submit broker requests. Credentials are never printed.
"""
import concurrent.futures
import json
import os
import secrets
import sys
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone
from flask import Flask

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'monitor'))
url=(root/'bridge-private/dnb-test-database-url.txt').read_text().strip()
assert url != (root/'bridge-private/dnb-database-url.txt').read_text().strip()
os.environ.update(DNB_DATABASE_URL=url,DNB_REQUIRE_DURABLE='1',
                  FX101_MT5_BRIDGE_ENABLED='1',FX101_MT5_EXECUTION_MODE='SHADOW',
                  FX101_MT5_KILL_SWITCH='0',FX101_MT5_BRIDGE_TOKEN='a'*64)
import mt5_bridge as bridge
import mt5_store as store
from test_mt5_bridge import snapshot

app=Flask(__name__);app.register_blueprint(bridge.bp)
app.teardown_appcontext(store.close_request)
now=int(time.time());bridge.clock=lambda:now
def req(method,path,body=b'',nonce=None):
    nonce=nonce or secrets.token_hex(32);stamp=str(now)
    headers={'X-FX101-Time':stamp,'X-FX101-Nonce':nonce,
             'X-FX101-Signature':bridge.request_signature(method,path,stamp,nonce,body)}
    with app.test_client() as client:
        return client.open(path,method=method,data=body,headers=headers,base_url='https://localhost')

checkpoint=root/'bridge-private/postgres-validation-checkpoint.json'
if len(sys.argv)>1 and sys.argv[1]=='recover':
    state=json.loads(checkpoint.read_text())
    with app.app_context():
        bridge._ensure_schema()
        row=store.db().execute('SELECT * FROM mt5_v2_commands WHERE id=?',(state['command_id'],)).fetchone()
        assert row and row['ack']==state['ack']
        assert store.db().execute('SELECT nonce FROM mt5_v2_nonces WHERE nonce=?',(state['nonce'],)).fetchone()
    print(json.dumps({'new_process_recovery':True,'command_id':state['command_id'],'nonce_persisted':True}))
    sys.exit(0)

s=snapshot();s['captured_at']=now
for spec in s['symbols'].values(): spec['quote_at']=now
assert req('POST','/fx101/mt5/snapshot',json.dumps(s).encode()).status_code==200

nonce=secrets.token_hex(32)
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    codes=list(pool.map(lambda _:req('GET','/fx101/mt5/status',nonce=nonce).status_code,range(8)))
assert codes.count(200)==1 and codes.count(409)==7,codes

decision={'trade_id':'TEST-'+uuid.uuid4().hex,'symbol':'EURUSD.x','side':'BUY',
          'entry':1.1002,'stop':1.099,'target':1.1022,'risk_pct':.25,
          'valid_until':datetime.fromtimestamp(now+30,timezone.utc).isoformat(),
          'context':{'machine_cancel':{'kind':'price_below','price':1.098}}}
def producer(i):
    with app.app_context():
        d={**decision,'stop':1.099 if i%2==0 else 1.0989}
        try: return bridge._queue_command(d,synthetic=True)['id']
        except bridge.risk.Reject as e:
            assert str(e)=='duplicate_command_conflict';return 'CONFLICT'
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    results=list(pool.map(producer,range(8)))
ids=set(results)-{'CONFLICT'};assert len(ids)==1 and results.count('CONFLICT')==4,results
cid=ids.pop()

def ack(i):
    payload={'command_id':cid,'login':315307814,'server':'GoatFunded-Server',
             'status':'SHADOW_OK','volume':.04 if i%2==0 else .03,
             'risk_usd':5 if i%2==0 else 3.75,'detail':'synthetic_shadow_only'}
    return req('POST','/fx101/mt5/ack',json.dumps(payload).encode()).status_code
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    codes=list(pool.map(ack,range(8)))
assert codes.count(200)==4 and codes.count(400)==4,codes
with app.app_context():
    row=store.db().execute('SELECT ack FROM mt5_v2_commands WHERE id=?',(cid,)).fetchone()
    checkpoint.write_text(json.dumps({'command_id':cid,'ack':row['ack'],'nonce':nonce}))

# A failed transaction must not leak into a later request or leave a partial write.
with app.app_context():
    c=store.db();before=c.execute('SELECT COUNT(*) AS n FROM mt5_v2_commands').fetchone()['n']
    c.execute('INSERT INTO mt5_v2_nonces VALUES (?,?)',('b'*64,now))
    c.rollback()
    assert c.execute('SELECT nonce FROM mt5_v2_nonces WHERE nonce=?',('b'*64,)).fetchone() is None
    assert c.execute('SELECT COUNT(*) AS n FROM mt5_v2_commands').fetchone()['n']==before
print(json.dumps({'real_postgres':True,'concurrent_nonce_unique':True,
                  'concurrent_command_conflicts':True,'concurrent_ack_conflicts':True,
                  'rollback_isolated':True,'command_id':cid,'broker_execution_test':False}))

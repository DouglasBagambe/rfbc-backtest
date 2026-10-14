"""Isolated demo validation journal. Never authorises the funded account."""
import json
import re
import mt5_risk as risk
import mt5_store as store
DEMO_LOGIN=5057377621
DEMO_SERVER='MetaQuotes-Demo'
SCHEMA=('CREATE TABLE IF NOT EXISTS dnb_demo_commands (id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL, ack TEXT, created_at INTEGER NOT NULL)',
        'CREATE TABLE IF NOT EXISTS dnb_demo_snapshots (id TEXT PRIMARY KEY, captured_at INTEGER NOT NULL, received_at INTEGER NOT NULL, payload TEXT NOT NULL)',
        'CREATE TABLE IF NOT EXISTS dnb_demo_snapshot_counter (id TEXT PRIMARY KEY, value INTEGER NOT NULL)',
        'CREATE TABLE IF NOT EXISTS dnb_demo_snapshot_sequence (id TEXT PRIMARY KEY, value INTEGER UNIQUE NOT NULL)')

def snapshot(body,now):
    risk.validate_snapshot(body,now,expected_login=DEMO_LOGIN,expected_server=DEMO_SERVER)
    from mt5_bridge import _ensure_schema
    import uuid
    _ensure_schema();c=store.lock_account()
    identifier=uuid.uuid4().hex
    c.execute("INSERT INTO dnb_demo_snapshot_counter VALUES ('receiver',0) ON CONFLICT(id) DO NOTHING")
    sequence=c.execute("UPDATE dnb_demo_snapshot_counter SET value=value+1 WHERE id='receiver' RETURNING value").fetchone()['value']
    c.execute('INSERT INTO dnb_demo_snapshots VALUES (?,?,?,?)',(identifier,body['captured_at'],now,json.dumps(body,separators=(',',':'),allow_nan=False)))
    c.execute('INSERT INTO dnb_demo_snapshot_sequence VALUES (?,?)',(identifier,sequence))
    epoch=c.execute('SELECT * FROM dnb_demo_epochs ORDER BY created_at DESC LIMIT 1').fetchone()
    if epoch:
        value=json.loads(epoch['payload'])
        peak=max(risk.positive(value['historical_peak']),risk.positive(body['balance']),risk.positive(body['equity']))
        if peak>risk.number(value['historical_peak']):
            value.update(historical_peak=float(peak),peak_snapshot_id=identifier)
            c.execute('UPDATE dnb_demo_epochs SET payload=? WHERE id=?',(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False),epoch['id']))
    c.execute('DELETE FROM dnb_demo_snapshots WHERE received_at<?',(now-86400,))
    c.execute('DELETE FROM dnb_demo_snapshot_sequence WHERE id NOT IN (SELECT id FROM dnb_demo_snapshots)')
    c.commit()
    return {'ok':True,'purpose':'DEMO','live_goat_authorised':False}

def latest(now):
    row=store.db().execute('SELECT s.* FROM dnb_demo_snapshots s LEFT JOIN dnb_demo_snapshot_sequence q ON q.id=s.id ORDER BY s.captured_at DESC,s.received_at DESC,COALESCE(q.value,0) DESC LIMIT 1').fetchone()
    if not row:return None
    out={**dict(row),'payload':json.loads(row['payload'])}
    out['age_seconds']=now-row['captured_at']
    out['fresh']=0<=out['age_seconds']<=15 and out['payload']['terminal_connected']
    return out

def intent(body,now):
    risk.keys(body,{'command_id','login','server','request'})
    if body['login']!=DEMO_LOGIN or body['server']!=DEMO_SERVER:raise risk.Reject('demo_binding')
    if not isinstance(body['command_id'],str) or not re.fullmatch('[a-f0-9]{32}',body['command_id']):raise risk.Reject('invalid_command_id')
    r=body['request'];risk.keys(r,{'symbol','type','volume','entry','sl','tp'})
    if r['symbol']!='EURUSD' or type(r['type']) is not int or r['type'] not in range(8):raise risk.Reject('demo_request')
    if risk.positive(r['volume'])!=risk.number('.01'):raise risk.Reject('demo_volume')
    for k in ('entry','sl','tp'):risk.positive(r[k])
    from mt5_bridge import _ensure_schema
    _ensure_schema();c=store.lock_account()
    payload=json.dumps(body,sort_keys=True,separators=(',',':'))
    old=c.execute('SELECT * FROM dnb_demo_commands WHERE id=?',(body['command_id'],)).fetchone()
    if old:
        if old['payload']!=payload:raise risk.Reject('demo_command_conflict')
        return {'ok':True,'idempotent':True,'state':old['state']}
    c.execute('INSERT INTO dnb_demo_commands VALUES (?,?,?,?,?)',(body['command_id'],payload,'INTENT',None,now));c.commit()
    return {'ok':True,'state':'INTENT'}

def ack(body,now):
    risk.keys(body,{'command_id','login','server','status','order_ticket','deal_ticket'})
    if body['login']!=DEMO_LOGIN or body['server']!=DEMO_SERVER:raise risk.Reject('demo_binding')
    if body['status'] not in {'RECOVERED','REJECTED'}:raise risk.Reject('demo_ack_status')
    from dnb_history import ticket
    ticket(body['order_ticket'],zero=True);ticket(body['deal_ticket'],zero=True)
    from mt5_bridge import _ensure_schema
    _ensure_schema();c=store.lock_account();row=c.execute('SELECT * FROM dnb_demo_commands WHERE id=?',(body['command_id'],)).fetchone()
    if not row:raise risk.Reject('unknown_demo_command')
    payload=json.dumps(body,sort_keys=True,separators=(',',':'))
    if row['ack'] and row['ack']!=payload:raise risk.Reject('demo_ack_conflict')
    c.execute('UPDATE dnb_demo_commands SET state=?,ack=? WHERE id=?',(body['status'],payload,body['command_id']));c.commit()
    return {'ok':True,'state':body['status']}

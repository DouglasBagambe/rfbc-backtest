"""Isolated demo validation journal. Never authorises the funded account."""
import json
import re
import mt5_risk as risk
import mt5_store as store
DEMO_LOGIN=5057377621
DEMO_SERVER='MetaQuotes-Demo'
SCHEMA=('CREATE TABLE IF NOT EXISTS dnb_demo_commands (id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL, ack TEXT, created_at INTEGER NOT NULL)',)

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

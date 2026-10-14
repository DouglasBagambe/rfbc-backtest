"""Authenticated broker history captures; no outcomes inferred from prices."""
import json
import re
from flask import jsonify
import mt5_risk as risk
import mt5_store as store

SCHEMA=(
 'CREATE TABLE IF NOT EXISTS dnb_history_pages (capture_id TEXT NOT NULL, kind TEXT NOT NULL, page INTEGER NOT NULL, payload TEXT NOT NULL, received_at INTEGER NOT NULL, PRIMARY KEY(capture_id,kind,page))',
 'CREATE TABLE IF NOT EXISTS dnb_history_captures (id TEXT PRIMARY KEY, captured_at INTEGER NOT NULL, payload TEXT NOT NULL)',
 'CREATE TABLE IF NOT EXISTS dnb_broker_orders (ticket TEXT PRIMARY KEY, captured_at INTEGER NOT NULL, payload TEXT NOT NULL)',
 'CREATE TABLE IF NOT EXISTS dnb_broker_deals (ticket TEXT PRIMARY KEY, captured_at INTEGER NOT NULL, payload TEXT NOT NULL)',
 'CREATE TABLE IF NOT EXISTS dnb_history_revisions (id TEXT PRIMARY KEY, captured_at INTEGER NOT NULL, kind TEXT NOT NULL, ticket TEXT NOT NULL, prior TEXT NOT NULL, current TEXT NOT NULL)',
)
ORDER_FIELDS={'ticket','position_id','magic','comment','symbol','type','state','reason','volume_initial','volume_current','price','sl','tp','stop_limit','created_at','done_at','expires_at'}
DEAL_FIELDS={'ticket','order_ticket','position_id','magic','comment','symbol','type','entry','reason','volume','price','profit','commission','swap','fee','time'}

def ticket(value,zero=False):
    if not isinstance(value,str) or not re.fullmatch(r'0|[1-9][0-9]{0,19}' if zero else r'[1-9][0-9]{0,19}',value):raise risk.Reject('invalid_ticket')

def validate(body,now):
    risk.keys(body,{'capture_id','login','server','captured_at','from_server_time','to_server_time','kind','page','pages','total','items'})
    if body['login']!=risk.LOGIN or body['server']!=risk.SERVER:raise risk.Reject('account_binding')
    if not isinstance(body['capture_id'],str) or not re.fullmatch('[a-f0-9]{32}',body['capture_id']):raise risk.Reject('invalid_capture_id')
    for key in ('captured_at','from_server_time','to_server_time','page','pages','total'):
        if type(body[key]) is not int or body[key]<0:raise risk.Reject('invalid_history_integer')
    if not 0<=now-body['captured_at']<=3600 or body['to_server_time']<body['from_server_time']:raise risk.Reject('history_time')
    if body['kind'] not in {'orders','deals'} or not 1<=body['pages']<=1000 or body['page']>=body['pages'] or body['total']>100000:raise risk.Reject('history_bounds')
    if not isinstance(body['items'],list) or len(body['items'])>100:raise risk.Reject('history_bounds')
    fields=ORDER_FIELDS if body['kind']=='orders' else DEAL_FIELDS
    seen=set()
    for item in body['items']:
        risk.keys(item,fields);ticket(item['ticket'])
        if item['ticket'] in seen:raise risk.Reject('duplicate_history_ticket')
        seen.add(item['ticket'])
        for key in ('position_id',)+(('order_ticket',) if body['kind']=='deals' else ()):ticket(item[key],zero=True)
        if not isinstance(item['comment'],str) or len(item['comment'])>128 or not isinstance(item['symbol'],str) or not re.fullmatch('[A-Za-z0-9_.]{0,32}',item['symbol']):raise risk.Reject('invalid_history_string')
        integer={'magic','type','state','reason','created_at','done_at','expires_at'} if body['kind']=='orders' else {'magic','type','entry','reason','time'}
        for key in integer:
            if type(item[key]) is not int or item[key]<0:raise risk.Reject('invalid_history_integer')
        numeric={'volume_initial','volume_current','price','sl','tp','stop_limit'} if body['kind']=='orders' else {'volume','price','profit','commission','swap','fee'}
        for key in numeric:risk.number(item[key])
        for key in numeric-{'profit','commission','swap','fee'}:
            if risk.number(item[key])<0:raise risk.Reject('negative_history_value')

def ingest(body,now):
    validate(body,now)
    from mt5_bridge import _ensure_schema
    _ensure_schema();c=store.lock_account()
    canonical=json.dumps(body,sort_keys=True,separators=(',',':'))
    old=c.execute('SELECT payload FROM dnb_history_pages WHERE capture_id=? AND kind=? AND page=?',(body['capture_id'],body['kind'],body['page'])).fetchone()
    if old:
        if old['payload']!=canonical:raise risk.Reject('history_page_conflict')
    else:c.execute('INSERT INTO dnb_history_pages VALUES (?,?,?,?,?)',(body['capture_id'],body['kind'],body['page'],canonical,now))
    rows=list(c.execute('SELECT * FROM dnb_history_pages WHERE capture_id=?',(body['capture_id'],)))
    assembled={}
    for kind in ('orders','deals'):
        pages=[json.loads(r['payload']) for r in rows if r['kind']==kind]
        if not pages:continue
        ref=pages[0]
        stable=('captured_at','from_server_time','to_server_time','pages','total','login','server')
        if any(any(p[k]!=ref[k] for k in stable) for p in pages):raise risk.Reject('history_capture_conflict')
        if len(pages)!=ref['pages']:continue
        if sorted(p['page'] for p in pages)!=list(range(ref['pages'])):raise risk.Reject('history_page_sequence')
        items=[i for p in sorted(pages,key=lambda p:p['page']) for i in p['items']]
        if len(items)!=ref['total'] or len({i['ticket'] for i in items})!=len(items):raise risk.Reject('history_total_conflict')
        assembled[kind]=items
    complete=set(assembled)=={'orders','deals'}
    if complete:
        refs={kind:json.loads(next(r['payload'] for r in rows if r['kind']==kind)) for kind in ('orders','deals')}
        if any(refs['orders'][k]!=refs['deals'][k] for k in ('captured_at','from_server_time','to_server_time','login','server')):raise risk.Reject('history_capture_conflict')
        for kind,items in assembled.items():
            for item in items:
                encoded=json.dumps(item,sort_keys=True,separators=(',',':'))
                table='dnb_broker_'+kind
                old=c.execute(f'SELECT * FROM {table} WHERE ticket=?',(item['ticket'],)).fetchone()
                if kind=='deals':
                    if not old:c.execute('INSERT INTO dnb_broker_deals VALUES (?,?,?)',(item['ticket'],body['captured_at'],encoded))
                    elif old['captured_at']<body['captured_at'] and old['payload']!=encoded:
                        import uuid
                        c.execute('INSERT INTO dnb_history_revisions VALUES (?,?,?,?,?,?)',(uuid.uuid4().hex,body['captured_at'],kind,item['ticket'],old['payload'],encoded))
                        c.execute('UPDATE dnb_broker_deals SET captured_at=?,payload=? WHERE ticket=?',(body['captured_at'],encoded,item['ticket']))
                elif not old:c.execute('INSERT INTO dnb_broker_orders VALUES (?,?,?)',(item['ticket'],body['captured_at'],encoded))
                elif old['captured_at']<body['captured_at']:c.execute('UPDATE dnb_broker_orders SET captured_at=?,payload=? WHERE ticket=?',(body['captured_at'],encoded,item['ticket']))
        summary=json.dumps({'from_server_time':body['from_server_time'],'to_server_time':body['to_server_time'],'orders':len(assembled['orders']),'deals':len(assembled['deals'])})
        c.execute('INSERT OR IGNORE INTO dnb_history_captures VALUES (?,?,?)',(body['capture_id'],body['captured_at'],summary))
    c.commit();return {'ok':True,'complete':complete,'capture_id':body['capture_id']}

def latest():
    row=store.db().execute('SELECT * FROM dnb_history_captures ORDER BY captured_at DESC LIMIT 1').fetchone()
    return None if not row else {**dict(row),'payload':json.loads(row['payload'])}

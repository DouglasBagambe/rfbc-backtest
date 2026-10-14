"""Authenticated broker observation and durable SHADOW commands.

AUTO is deliberately unavailable: untested broker paths and GOAT hosting policy
must be resolved before any order-sending implementation is eligible for use.
The v1 queue is quarantined; no legacy command is imported or executed.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from flask import Blueprint, Response, jsonify, request
import fx101
import mt5_risk as risk
import mt5_store as store

bp = Blueprint('mt5_bridge', __name__)
ACCOUNT_ID = 'goat-stride-2500-instant-hero'
MAX_BYTES = 131072
AUTO_AVAILABLE = False

def clock(): return int(time.time())
def enabled(): return os.getenv('FX101_MT5_BRIDGE_ENABLED','0') == '1'
def mode():
    value = os.getenv('FX101_MT5_EXECUTION_MODE','SHADOW')
    return value if value in {'OFF','OBSERVE','SHADOW'} else 'OFF'
def killed(): return os.getenv('FX101_MT5_KILL_SWITCH','1') != '0'
def secret():
    value = os.getenv('FX101_MT5_BRIDGE_TOKEN','')
    if not re.fullmatch(r'[a-f0-9]{64}',value): raise risk.Reject('credential_not_configured')
    return value.encode('ascii')
def sign(message): return hmac.new(secret(),message,hashlib.sha256).hexdigest()
def request_signature(method,path,stamp,nonce,body):
    return sign(f'{method}\n{path}\n{stamp}\n{nonce}\n'.encode()+body)

def _ensure_schema():
    from dnb_history import SCHEMA as HISTORY_SCHEMA
    from dnb_authority import SCHEMA as AUTHORITY_SCHEMA
    from dnb_demo import SCHEMA as DEMO_SCHEMA
    store.ensure_schema((
        'CREATE TABLE IF NOT EXISTS mt5_v2_nonces (nonce TEXT PRIMARY KEY, received_at INTEGER NOT NULL)',
        'CREATE INDEX IF NOT EXISTS mt5_v2_nonce_time ON mt5_v2_nonces(received_at)',
        'CREATE TABLE IF NOT EXISTS mt5_v2_snapshots (id TEXT PRIMARY KEY, captured_at INTEGER NOT NULL, received_at INTEGER NOT NULL, payload TEXT NOT NULL)',
        'CREATE INDEX IF NOT EXISTS mt5_v2_snapshot_time ON mt5_v2_snapshots(captured_at)',
        'CREATE TABLE IF NOT EXISTS mt5_v2_commands (id TEXT PRIMARY KEY, trade_id TEXT UNIQUE NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, ack TEXT)',
        'CREATE TABLE IF NOT EXISTS mt5_v2_reconciliation (id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, payload TEXT NOT NULL, created_at INTEGER NOT NULL)',
        'CREATE TABLE IF NOT EXISTS dnb_thesis_legs (command_id TEXT PRIMARY KEY, thesis_id TEXT NOT NULL, confirmation_id TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(thesis_id,confirmation_id))',
        'CREATE TABLE IF NOT EXISTS dnb_alert_intents (trade_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, side TEXT NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL, created_at INTEGER NOT NULL, delivery TEXT)',
    )+HISTORY_SCHEMA+AUTHORITY_SCHEMA+DEMO_SCHEMA)

@bp.teardown_request
def close_store(error):
    store.close_request(error)

@bp.before_request
def authenticate():
    # Apply size limit before reading/parsing JSON; server must also bound HTTP headers.
    request.max_content_length = MAX_BYTES
    if request.content_length is not None and request.content_length > MAX_BYTES:
        return jsonify(ok=False,error='request_too_large'),413
    if not request.is_secure: return jsonify(ok=False,error='tls_required'),403
    if not enabled(): return jsonify(ok=False,error='bridge_disabled'),503
    try:
        stamp = request.headers.get('X-FX101-Time','')
        nonce = request.headers.get('X-FX101-Nonce','')
        signature = request.headers.get('X-FX101-Signature','')
        if not re.fullmatch(r'\d{10}',stamp) or not re.fullmatch(r'[a-f0-9]{64}',nonce) or not re.fullmatch(r'[a-f0-9]{64}',signature):
            raise risk.Reject('unauthorized')
        now = clock()
        if abs(now-int(stamp)) > 15: raise risk.Reject('unauthorized')
        expected = request_signature(request.method,request.path,stamp,nonce,request.get_data())
        if not hmac.compare_digest(expected,signature): raise risk.Reject('unauthorized')
        _ensure_schema()
        c = store.lock_account()
        count = c.execute('SELECT COUNT(*) AS count FROM mt5_v2_nonces WHERE received_at>=?',(now-60,)).fetchone()
        count = count['count'] if store.remote() else count[0]
        if count >= 90: return jsonify(ok=False,error='rate_limited'),429
        # Atomic unique nonce insertion protects multiple threads/processes and restarts.
        c.execute('INSERT INTO mt5_v2_nonces VALUES (?,?)',(nonce,now))
        c.execute('DELETE FROM mt5_v2_nonces WHERE received_at<?',(now-120,))
        c.commit()
    except risk.Reject:
        return jsonify(ok=False,error='unauthorized'),401
    except Exception:
        store.db().rollback()
        return jsonify(ok=False,error='replay_or_storage_unavailable'),409

@bp.errorhandler(413)
def too_large(_): return jsonify(ok=False,error='request_too_large'),413

@bp.errorhandler(Exception)
def sanitized_error(_):
    fx101.log('mt5_bridge_error')
    return jsonify(ok=False,error='bridge_unavailable'),503

def strict_json():
    def pairs(values):
        out = {}
        for key,value in values:
            if key in out: raise risk.Reject('duplicate_json_key')
            out[key] = value
        return out
    try:
        return json.loads(request.get_data(), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(risk.Reject('nonfinite_json')))
    except (ValueError,TypeError,UnicodeError) as exc:
        raise risk.Reject('invalid_json') from exc

def latest_snapshot():
    _ensure_schema()
    row = store.db().execute('SELECT * FROM mt5_v2_snapshots ORDER BY captured_at DESC,received_at DESC LIMIT 1').fetchone()
    if not row: return None
    out = dict(row); out['payload'] = json.loads(out['payload'])
    out['age_seconds'] = clock()-out['captured_at']
    out['fresh'] = 0 <= out['age_seconds'] <= 15 and out['payload']['terminal_connected']
    return out

def adapt_symbol(symbol):
    if symbol in risk.SYMBOLS: return symbol
    if isinstance(symbol,str) and len(symbol)==7 and symbol.endswith('c') and symbol[:6]+'.x' in risk.SYMBOLS:
        return symbol[:6]+'.x'
    raise risk.Reject('symbol_unavailable')

def make_command(d):
    now = clock()
    expiry = datetime.fromisoformat(str(d['valid_until']).replace('Z','+00:00'))
    if expiry.tzinfo is None: raise risk.Reject('invalid_command_time')
    context = d.get('context') or {}
    order_type=context.get('order_type',d['side'])
    entry=d['entry']; stop_limit=context.get('stop_limit',0)
    if order_type.endswith('STOP_LIMIT') and 'stop_trigger' in context:
        if 'stop_limit' in context: raise risk.Reject('ambiguous_stop_limit')
        entry=context['stop_trigger']; stop_limit=d['entry']
    return {'command_id':uuid.uuid4().hex,'login':risk.LOGIN,'server':risk.SERVER,'created_at':now,
            'expires_at':min(now+30,int(expiry.timestamp())),'symbol':adapt_symbol(d['symbol']),
            'order_type':order_type,'entry':entry,'sl':d['stop'],'tp':d['target'],
            'risk_pct':d['risk_pct'],'stop_limit':stop_limit,'cancel':context.get('machine_cancel')}

def preflight_decision(d):
    if not enabled(): return ['mt5_bridge_disabled']
    if killed() or mode() in {'OFF','OBSERVE'}: return ['mt5_killed_or_observe']
    snap = latest_snapshot()
    if not snap or not snap['fresh']: return ['mt5_snapshot_missing_or_stale']
    try:
        risk.plan(snap['payload'],make_command(d),clock())
    except (risk.Reject,KeyError,TypeError,ValueError) as exc:
        return [str(exc) if isinstance(exc,risk.Reject) else 'invalid_decision']
    return []

def _queue_command(d, *, synthetic=False):
    """Durable idempotent insertion. Synthetic commands are SHADOW-only, not trades."""
    if not enabled() or killed() or mode() != 'SHADOW': raise risk.Reject('shadow_unavailable')
    _ensure_schema()
    c = store.lock_account()
    unresolved=c.execute("SELECT trade_id FROM dnb_alert_intents WHERE symbol=? AND state IN ('SENDING','SENT','DELIVERY_UNKNOWN','MANUAL_POSSIBLE') LIMIT 1",(adapt_symbol(d['symbol']),)).fetchone()
    if unresolved: raise risk.Reject('manual_alert_requires_broker_history_reconciliation')
    snap = latest_snapshot()
    if not snap or not snap['fresh']: raise risk.Reject('stale_snapshot')
    command = make_command(d)
    quote = risk.plan(snap['payload'],command,clock(),require_anchors=not synthetic)
    payload = {**command,'synthetic':synthetic,'quote':quote,'snapshot_id':snap['id']}
    c = store.lock_account()
    existing=c.execute('SELECT * FROM mt5_v2_commands WHERE trade_id=?',(d['trade_id'],)).fetchone()
    if existing:
        old=json.loads(existing['payload'])
        frozen=('login','server','symbol','order_type','entry','sl','tp','risk_pct','stop_limit','cancel','synthetic')
        if any(old[k]!=payload[k] for k in frozen): raise risk.Reject('duplicate_command_conflict')
        return dict(existing)
    # A duplicate trade ID returns the original command, never a newly sized replacement.
    c.execute('INSERT OR IGNORE INTO mt5_v2_commands VALUES (?,?,?,?,?,?,?)',
              (command['command_id'],d['trade_id'],'QUEUED',json.dumps(payload,separators=(',',':')),clock(),command['expires_at'],None))
    c.commit()
    saved = dict(c.execute('SELECT * FROM mt5_v2_commands WHERE trade_id=?',(d['trade_id'],)).fetchone())
    old = json.loads(saved['payload'])
    frozen = ('login','server','symbol','order_type','entry','sl','tp','risk_pct','stop_limit','cancel','synthetic')
    if any(old[k] != payload[k] for k in frozen): raise risk.Reject('duplicate_command_conflict')
    return saved

def wire(command, nonce):
    # Exact flat ASCII protocol: no permissive substring JSON parser in the EA.
    p = json.loads(command['payload'])
    fields = ['FX101v2',nonce,p['command_id'],str(risk.LOGIN),risk.SERVER,'SHADOW',str(p['created_at']),str(p['expires_at']),
              p['symbol'],p['order_type']]+[format(float(p[k]),'.10f') for k in ('entry','sl','tp','risk_pct','stop_limit')]
    fields += [p['cancel']['kind'],format(float(p['cancel']['price']),'.10f'),'1' if p['synthetic'] else '0']
    body = '|'.join(fields)
    return body+'|'+sign(body.encode('ascii'))

@bp.post('/fx101/mt5/snapshot')
def ingest_snapshot():
    try:
        body = strict_json(); risk.validate_snapshot(body,clock())
        c = store.lock_account(); prior = latest_snapshot()
        if prior and body['captured_at'] <= prior['captured_at']: raise risk.Reject('out_of_order_snapshot')
        # Client assertions cannot establish historical anchors in this validation build.
        body['anchors_verified'] = False
        if prior:
            body['high_water_equity'] = max(body['high_water_equity'],prior['payload']['high_water_equity'],body['equity'],2500)
        else: body['high_water_equity'] = max(body['high_water_equity'],body['equity'],2500)
        sid = uuid.uuid4().hex
        c.execute('INSERT INTO mt5_v2_snapshots VALUES (?,?,?,?)',(sid,body['captured_at'],clock(),json.dumps(body,separators=(',',':'))))
        # Preserve differences as evidence; do not invent closures, fills or P&L from missing tickets.
        previous = {i['ticket']:i for group in ('positions','orders') for i in (prior['payload'][group] if prior else [])}
        current = {i['ticket']:i for group in ('positions','orders') for i in body[group]}
        differences = {'added':[k for k in current if k not in previous],
                       'missing':[k for k in previous if k not in current],
                       'changed':[k for k in current if k in previous and current[k]!=previous[k]],
                       'unresolved_internal_trades':[] if store.remote() else [x['id'] for x in c.execute("SELECT id FROM trades WHERE state IN ('PLACED','OPEN')")]}
        from dnb_alerts import reconnect_candidates
        differences['manual_alert_candidates']=reconnect_candidates(body)
        c.execute('INSERT INTO mt5_v2_reconciliation VALUES (?,?,?,?)',(uuid.uuid4().hex,sid,json.dumps(differences),clock()))
        # Bounded raw observations, separate from permanent command/ACK evidence.
        c.execute('DELETE FROM mt5_v2_snapshots WHERE captured_at<?',(clock()-86400,))
        c.execute('DELETE FROM mt5_v2_reconciliation WHERE created_at<?',(clock()-30*86400,))
        c.commit()
    except (risk.Reject,ValueError,KeyError,TypeError) as exc:
        return jsonify(ok=False,error=str(exc) if isinstance(exc,risk.Reject) else 'invalid_snapshot'),400
    return jsonify(ok=True,snapshot_id=sid,mode=mode(),auto_available=False)

@bp.get('/fx101/mt5/command')
def next_command():
    if request.args: return jsonify(ok=False,error='unexpected_query'),400
    c = store.db(); now = clock()
    c.execute("UPDATE mt5_v2_commands SET state='EXPIRED' WHERE state='QUEUED' AND expires_at<=?",(now,)); c.commit()
    if killed() or mode() != 'SHADOW': return Response('NONE',mimetype='text/plain')
    snap = latest_snapshot()
    if not snap or not snap['fresh']: return Response('NONE',mimetype='text/plain')
    row = c.execute("SELECT * FROM mt5_v2_commands WHERE state='QUEUED' AND expires_at>? ORDER BY created_at,id LIMIT 1",(now,)).fetchone()
    if not row: return Response('NONE',mimetype='text/plain')
    return Response(wire(dict(row),request.headers['X-FX101-Nonce']),mimetype='text/plain')

@bp.post('/fx101/mt5/ack')
def ack_command():
    try:
        body = strict_json()
        risk.keys(body,{'command_id','login','server','status','volume','risk_usd','detail'})
        if body['login']!=risk.LOGIN or body['server']!=risk.SERVER: raise risk.Reject('account_binding')
        if body['status'] not in {'SHADOW_OK','REJECTED'}: raise risk.Reject('live_ack_prohibited')
        if not isinstance(body['detail'],str) or not re.fullmatch(r'[a-z0-9_]{1,64}',body['detail']): raise risk.Reject('invalid_detail')
        for k in ('volume','risk_usd'):
            if risk.number(body[k]) < 0: raise risk.Reject('invalid_ack')
        c = store.lock_account(); row = c.execute('SELECT * FROM mt5_v2_commands WHERE id=?',(body['command_id'],)).fetchone()
        if not row: return jsonify(ok=False,error='unknown_command'),404
        canonical = json.dumps(body,sort_keys=True,separators=(',',':'))
        if row['ack']:
            if row['ack'] != canonical: raise risk.Reject('conflicting_ack')
            return jsonify(ok=True,idempotent=True)
        # Late ACK retained as evidence; it cannot resurrect an expired command.
        c.execute("UPDATE mt5_v2_commands SET state=?,ack=? WHERE id=? AND ack IS NULL",
                  (body['status'],canonical,body['command_id']))
        saved = c.execute('SELECT ack FROM mt5_v2_commands WHERE id=?',(body['command_id'],)).fetchone()
        if saved['ack'] != canonical:
            c.rollback()
            raise risk.Reject('conflicting_ack')
        c.commit()
    except (risk.Reject,ValueError,KeyError,TypeError) as exc:
        return jsonify(ok=False,error=str(exc) if isinstance(exc,risk.Reject) else 'invalid_ack'),400
    return jsonify(ok=True,state=body['status'])

@bp.get('/fx101/mt5/status')
def mt5_status():
    snap = latest_snapshot()
    recent=[{'id':r['id'],'state':r['state'],'expires_at':r['expires_at'],'ack':json.loads(r['ack']) if r['ack'] else None}
            for r in store.db().execute('SELECT * FROM mt5_v2_commands ORDER BY created_at DESC LIMIT 10')]
    return jsonify(ok=True,recent_commands=recent,bridge_enabled=enabled(),mode=mode(),kill_switch=killed(),auto_available=False,
                   connected=bool(snap and snap['fresh']),snapshot=snap,
                   validation_blockers=['historical_anchors','goat_hosted_decisions_policy','broker_execution_paths'])

def install_fx101_hooks():
    # Idempotent registration; preserve frozen analysis and avoid recursive monkey-patching.
    if getattr(fx101.persist_decision,'_mt5_hook',False): return
    original = fx101.persist_decision
    def wrapped(d):
        if not enabled(): return original(d)
        # An execution outage must not erase a valid analysis decision. Alert
        # intent is separate from execution; manual fills remain unconfirmed.
        if os.getenv('DNB_MANUAL_ALERTS_ENABLED','0') == '1':
            import dnb_alerts
            from flask import has_app_context
            if not has_app_context():
                return False,'durable_alert_context_required',{'trade_id':fx101.trade_id(d)}
            try:
                alert=dnb_alerts.prepare({**d,'trade_id':d.get('trade_id') or fx101.trade_id(d)},clock())
                state=dnb_alerts.dispatch(alert['trade_id'],fx101.telegram_send)
                return True,'manual_analysis_'+state.lower(),{'trade_id':alert['trade_id'],'broker_execution':False}
            except risk.Reject as exc:
                return False,str(exc),{'trade_id':fx101.trade_id(d),'errors':[str(exc)]}
        errors = preflight_decision(d)
        if errors: return False,','.join(errors),{'trade_id':fx101.trade_id(d),'errors':errors}
        # No live decision acceptance before anchors and policy gates are satisfied.
        return False,'auto_validation_incomplete',{'trade_id':fx101.trade_id(d),'errors':['auto_validation_incomplete']}
    wrapped._mt5_hook = True
    fx101.persist_decision = wrapped


@bp.post('/fx101/mt5/shadow-test')
def create_shadow_test():
    """Explicit authenticated synthetic probe. Never accepts an executable signal."""
    if request.get_data() not in {b'',b'{}'}:
        return jsonify(ok=False,error='unexpected_payload'),400
    snap = latest_snapshot()
    if not snap or not snap['fresh']:
        return jsonify(ok=False,error='stale_snapshot'),409
    try:
        symbol='EURUSD.x'
        spec=snap['payload']['symbols'][symbol]
        from decimal import Decimal
        entry=risk.number(spec['ask']); tick=risk.positive(spec['tick_size'])
        distance=max(Decimal(200)*tick,Decimal(2)*max(spec['stops_level'],spec['freeze_level'])*risk.positive(spec['point']))
        distance=(distance/tick).to_integral_value(rounding='ROUND_CEILING')*tick
        decision={'trade_id':'SHADOW-'+uuid.uuid4().hex,'symbol':symbol,'side':'BUY',
            'entry':float(entry),'stop':float(entry-distance),'target':float(entry+2*distance),
            'risk_pct':0.25,'valid_until':datetime.fromtimestamp(clock()+30,timezone.utc).isoformat(),
            'context':{'order_type':'BUY','machine_cancel':{'kind':'price_below','price':float(entry-2*distance)}}}
        row=_queue_command(decision,synthetic=True)
        return jsonify(ok=True,command_id=row['id'],synthetic=True,auto_available=False)
    except (risk.Reject,KeyError,ValueError):
        return jsonify(ok=False,error='shadow_preflight_rejected'),409


@bp.post('/fx101/mt5/history')
def broker_history():
    try:
        import dnb_history
        return jsonify(dnb_history.ingest(strict_json(),clock()))
    except risk.Reject as exc:
        store.db().rollback()
        return jsonify(ok=False,error=str(exc)),400

@bp.post('/fx101/mt5/telegram-test')
def telegram_test():
    if request.get_data() not in {b'',b'{}'}: return jsonify(ok=False,error='unexpected_payload'),400
    # Explicit authenticated operator test; never presents a trading instruction.
    try:
        ok,status=fx101.telegram_send('dnb Fx SYSTEM TEST — permanent gateway Telegram delivery. No trading instruction. LIVE AUTO remains blocked.')
        return jsonify(ok=ok,delivery_status=status,broker_order_sent=False),200 if ok else 503
    except Exception:
        return jsonify(ok=False,error='telegram_delivery_unconfirmed',broker_order_sent=False),503


@bp.post('/fx101/mt5/demo/intent')
def demo_intent():
    try:
        import dnb_demo
        return jsonify(dnb_demo.intent(strict_json(),clock()))
    except risk.Reject as exc:
        store.db().rollback();return jsonify(ok=False,error=str(exc)),400

@bp.post('/fx101/mt5/demo/ack')
def demo_ack():
    try:
        import dnb_demo
        return jsonify(dnb_demo.ack(strict_json(),clock()))
    except risk.Reject as exc:
        store.db().rollback();return jsonify(ok=False,error=str(exc)),400

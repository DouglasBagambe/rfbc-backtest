"""Read personally owned analysis; never infer broker fills from market prices.

Source receipts and alert delivery are separate from broker authorisation. A
receipt survives a worker restart; a stale/rejected decision never becomes an
entry merely because the demo executor is available.
"""
import json
from datetime import datetime, timezone
import requests
import mt5_risk as risk
import mt5_store as store

MAILBOX = 'https://api.github.com/repos/DouglasBagambe/rfbc-backtest/contents/runtime/gdesk_decision.json'
SCHEMA = (
    'CREATE TABLE IF NOT EXISTS dnb_source_receipts (id TEXT PRIMARY KEY, source TEXT NOT NULL, generated_at INTEGER NOT NULL, received_at INTEGER NOT NULL, result TEXT NOT NULL, payload TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS dnb_source_health (source TEXT PRIMARY KEY, checked_at INTEGER NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL)',
)

def timestamp(value):
    if not isinstance(value, str): raise risk.Reject('source_timestamp')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None: raise risk.Reject('source_timestamp')
    return int(dt.timestamp())

def fetch_gdesk(now):
    response = requests.get(MAILBOX, params={'ref':'gdesk-runtime', 'cache_bust':now},
                            headers={'Accept':'application/vnd.github.raw+json', 'Cache-Control':'no-cache'}, timeout=15)
    response.raise_for_status()
    if len(response.content) > 131072: raise risk.Reject('source_too_large')
    # Use the same strict decoder without requiring an HTTP request context.
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out: raise risk.Reject('duplicate_source_key')
            out[key] = value
        return out
    return json.loads(response.content, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(risk.Reject('nonfinite_source')))

def gdesk_decisions(body, now):
    if not isinstance(body, dict): raise risk.Reject('source_not_object')
    identifier = body.get('decision_id')
    if not isinstance(identifier, str) or not 1 <= len(identifier) <= 128: raise risk.Reject('source_id')
    generated = timestamp(body.get('generated_at'))
    if not 0 <= now-generated <= 3600: raise risk.Reject('source_stale_or_future')
    result = body.get('result')
    decisions = body.get('decisions')
    if result not in {'TRADE','NO_TRADE','SYSTEM_FAILURE'}: raise risk.Reject('source_result')
    if not isinstance(decisions, list): raise risk.Reject('source_decisions')
    if result != 'TRADE':
        if decisions: raise risk.Reject('nontrade_has_decisions')
        return []
    if len(decisions) != 1: raise risk.Reject('trade_requires_one_decision')
    context = body.get('context', {})
    if (context.get('market_state') != 'MARKET_OPEN' or context.get('freshness') != 'FRESH'
            or context.get('symbols_received') != 18 or context.get('symbols_reported') != 18
            or context.get('validation_errors') != [] or context.get('stale_symbols')):
        raise risk.Reject('source_context_incomplete')
    # Independently check context age and the actual completed-bar timestamp.
    source_at = timestamp(context.get('source_generated_at'))
    expected_bar = (source_at//3600-1)*3600
    if not 0 <= generated-source_at <= 3600 or timestamp(context.get('latest_completed_bar')) != expected_bar:
        raise risk.Reject('source_bar_stale')
    decision = decisions[0]
    if not isinstance(decision, dict) or decision.get('source') != 'G_DESK': raise risk.Reject('source_binding')
    from mt5_bridge import adapt_symbol
    symbol = adapt_symbol(decision.get('symbol'))
    side = decision.get('side')
    entry, stop, target = [risk.positive(decision.get(k)) for k in ('entry','stop','target')]
    if side not in {'BUY','SELL'} or not (stop<entry<target if side=='BUY' else target<entry<stop):
        raise risk.Reject('source_geometry')
    if not now < timestamp(decision.get('valid_until')) <= now+86400: raise risk.Reject('source_expired')
    if not decision.get('cancel_condition'): raise risk.Reject('source_cancellation_missing')
    # Producer volume is never trusted; preserve structure and cap the risk input.
    pct = min(risk.PER_TRADE, risk.positive(decision.get('risk_pct')))
    return [{**decision, 'symbol':symbol, 'risk_pct':float(pct), 'trade_id':identifier,
             'source_receipt_id':identifier}]

def health(source, now, status, detail):
    from mt5_bridge import _ensure_schema
    _ensure_schema()
    c = store.lock_account()
    c.execute('INSERT INTO dnb_source_health VALUES (?,?,?,?) ON CONFLICT(source) DO UPDATE SET checked_at=excluded.checked_at,status=excluded.status,detail=excluded.detail',
              (source, now, status, detail))
    c.commit()

def ingest_gdesk(body, now):
    decisions = gdesk_decisions(body, now)
    from mt5_bridge import _ensure_schema
    _ensure_schema()
    payload = json.dumps(body, sort_keys=True, separators=(',',':'), allow_nan=False)
    c = store.lock_account()
    previous = c.execute('SELECT * FROM dnb_source_receipts WHERE id=?',(body['decision_id'],)).fetchone()
    if previous and previous['payload'] != payload: raise risk.Reject('source_id_conflict')
    c.execute('INSERT OR IGNORE INTO dnb_source_receipts VALUES (?,?,?,?,?,?)',
              (body['decision_id'], 'G_DESK', timestamp(body['generated_at']), now, body['result'], payload))
    c.commit()
    # Repeated polling repairs a crash between receipt and alert preparation.
    import dnb_alerts
    for decision in decisions: dnb_alerts.prepare(decision, now)
    health('G_DESK', now, body['result'], str(body.get('message',''))[:1500])
    return decisions

def rfbc_decisions(results, now):
    """Only frozen strategy entry events qualify. Price-inferred exits do not."""
    from mt5_symbols import RFBC_PAIRS
    out = []
    if not isinstance(results, list) or len(results) != 2: raise risk.Reject('rfbc_universe')
    if {r.get('pair') for r in results} != RFBC_PAIRS: raise risk.Reject('rfbc_universe')
    for row in results:
        action = row.get('action', {})
        if action.get('kind') != 'trade': continue
        close = timestamp(action.get('close_dt'))
        quote = timestamp(action.get('quote_dt'))
        if not 0 <= now-close <= 720 or not 0 <= now-quote <= 60: raise risk.Reject('rfbc_stale')
        side = action.get('direction')
        entry, stop, target = [risk.positive(action.get(k)) for k in ('entry','stop','target')]
        if side not in {'BUY','SELL'} or not (stop<entry<target if side=='BUY' else target<entry<stop): raise risk.Reject('rfbc_geometry')
        identity = f"RFBC:{row['pair']}:{close}:{side}"
        out.append({'trade_id':identity, 'source':'RFBC','symbol':row['pair']+'.x','side':side,
                    'entry':float(entry),'stop':float(stop),'target':float(target),
                    'risk_pct':float(min(risk.PER_TRADE, risk.positive(action.get('risk_pct')))),
                    'valid_until':datetime.fromtimestamp(close+720,timezone.utc).isoformat(),
                    'cancel_condition':'Frozen RFBC entry expires after the eligible completed-H4 window.',
                    'context':{'order_type':side}, 'source_receipt_id':identity})
    return out

def ingest_rfbc(decisions, now):
    """Freeze the first proposal per strategy/bar; later quotes cannot re-enter it."""
    from mt5_bridge import _ensure_schema
    import dnb_alerts
    _ensure_schema()
    out = []
    for decision in decisions:
        c = store.lock_account()
        row = c.execute('SELECT * FROM dnb_source_receipts WHERE id=?',(decision['trade_id'],)).fetchone()
        if row:
            if row['source'] != 'RFBC': raise risk.Reject('source_id_conflict')
            frozen = json.loads(row['payload'])
        else:
            frozen = decision
            payload = json.dumps(decision,sort_keys=True,separators=(',',':'),allow_nan=False)
            c.execute('INSERT INTO dnb_source_receipts VALUES (?,?,?,?,?,?)',
                      (decision['trade_id'],'RFBC',now,now,'TRADE',payload))
        c.commit()
        if timestamp(frozen['valid_until']) > now:
            dnb_alerts.prepare(frozen,now)
            out.append(frozen)
    return out

def status():
    from mt5_bridge import _ensure_schema, clock
    _ensure_schema()
    return [{**dict(r),'check_age_seconds':clock()-r['checked_at']} for r in store.db().execute('SELECT * FROM dnb_source_health ORDER BY source')]

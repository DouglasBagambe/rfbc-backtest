"""Durable manual-alert intent and conservative reconnect quarantine.

Sending a Telegram alert is not evidence of a fill. Until complete broker history
is reconciled, a possibly manually executed alert prohibits automated re-entry.
"""
import json
from datetime import datetime, timezone
import mt5_risk as risk
import mt5_store as store

def require_reconciled(symbol):
    row=store.db().execute("SELECT trade_id FROM dnb_alert_intents WHERE symbol=? AND state IN ('SENDING','SENT','DELIVERY_UNKNOWN','MANUAL_POSSIBLE','MANUAL_BOUND') LIMIT 1",(symbol,)).fetchone()
    if row:raise risk.Reject('manual_alert_requires_broker_history_reconciliation')

def prepare(decision, now):
    from mt5_bridge import _ensure_schema, adapt_symbol
    _ensure_schema()
    if decision.get('source') not in {'G_DESK','RFBC'}: raise risk.Reject('invalid_source')
    symbol=adapt_symbol(decision['symbol']);side=decision['side']
    if side not in {'BUY','SELL'}: raise risk.Reject('invalid_side')
    entry,sl,tp=[risk.positive(decision[k]) for k in ('entry','stop','target')]
    if not (sl<entry<tp if side=='BUY' else tp<entry<sl): raise risk.Reject('sltp_geometry')
    expiry=datetime.fromisoformat(decision['valid_until'].replace('Z','+00:00'))
    if expiry.tzinfo is None or not now < expiry.timestamp() <= now+86400: raise risk.Reject('stale_decision')
    pct=risk.positive(decision['risk_pct'])
    if pct>risk.PER_TRADE: raise risk.Reject('per_trade_risk')
    # A stable producer ID is mandatory; prices alone cannot identify a trade thesis.
    tid=decision.get('trade_id')
    if not isinstance(tid,str) or not 1 <= len(tid) <= 128: raise risk.Reject('decision_id_required')
    payload={k:decision[k] for k in ('source','side','entry','stop','target','risk_pct','valid_until')}
    payload.update(symbol=symbol,trade_id=tid,thesis_id=decision.get('thesis_id',tid),
                   scale_in_number=decision.get('scale_in_number',0),
                   total_thesis_risk_usd=decision.get('total_thesis_risk_usd'),
                   broker_risk_authorised=False)
    canonical=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False)
    c=store.lock_account()
    row=c.execute('SELECT * FROM dnb_alert_intents WHERE trade_id=?',(tid,)).fetchone()
    if row:
        if row['payload']!=canonical: raise risk.Reject('duplicate_alert_conflict')
        return dict(row)
    c.execute('INSERT INTO dnb_alert_intents VALUES (?,?,?,?,?,?,?)',(tid,symbol,side,'PREPARED',canonical,now,None))
    c.commit()
    return dict(c.execute('SELECT * FROM dnb_alert_intents WHERE trade_id=?',(tid,)).fetchone())

def format_alert(payload):
    p=json.loads(payload)
    total=p['total_thesis_risk_usd']
    return '\n'.join(['dnb Fx • manual analysis alert',f"{p['source']} • {p['symbol']} • {p['side']}",
        f"Decision: {p['trade_id']} • Thesis: {p['thesis_id']} • Add-on: {p['scale_in_number']}",
        f"Entry {p['entry']} • Structure SL {p['stop']} • TP {p['target']}",
        f"Maximum risk input {p['risk_pct']}% • Thesis risk: {total if total is not None else 'unverified'} USD",
        f"Valid until {p['valid_until']}",
        'EA unavailable or execution blocked. No lot size is authorised.',
        'Verify current account, news, margin and structure before any manual execution.'])

def dispatch(trade_id, sender):
    """Claim durably before external I/O. Ambiguous Telegram delivery never retries blindly."""
    c=store.lock_account()
    row=c.execute('SELECT * FROM dnb_alert_intents WHERE trade_id=?',(trade_id,)).fetchone()
    if not row: raise risk.Reject('unknown_alert')
    if row['state']!='PREPARED': return row['state']
    from mt5_bridge import clock
    expiry=datetime.fromisoformat(json.loads(row['payload'])['valid_until'].replace('Z','+00:00'))
    if expiry.timestamp() <= clock():
        c.execute("UPDATE dnb_alert_intents SET state='EXPIRED' WHERE trade_id=?",(trade_id,));c.commit()
        return 'EXPIRED'
    c.execute("UPDATE dnb_alert_intents SET state='SENDING' WHERE trade_id=?",(trade_id,));c.commit()
    try:
        ok,detail=sender(format_alert(row['payload']))
        state='SENT' if ok else 'DELIVERY_UNKNOWN'
        # Do not persist arbitrary sender exceptions, URLs, bot tokens or responses.
        delivery='confirmed' if ok else 'not_confirmed'
    except Exception:
        state='DELIVERY_UNKNOWN';delivery='not_confirmed'
    c=store.lock_account()
    c.execute('UPDATE dnb_alert_intents SET state=?,delivery=? WHERE trade_id=?',(state,delivery,trade_id));c.commit()
    import fx101
    fx101.log('dnb_manual_alert_delivery', trade_id=trade_id, state=state, confirmed=state=='SENT')
    return state

def reconnect_candidates(snapshot):
    """Candidates are quarantined, never guessed into command/ticket bindings."""
    rows=store.db().execute("SELECT * FROM dnb_alert_intents WHERE state IN ('SENDING','SENT','DELIVERY_UNKNOWN','MANUAL_POSSIBLE')")
    return [{'trade_id':r['trade_id'],'symbol':r['symbol'],
             'candidate_tickets':[p['ticket'] for p in snapshot['positions']+snapshot['orders']
                                  if p['symbol']==r['symbol']],
             'history_reconciliation_required':True} for r in rows]

"""Explicit operator ticket binding, backed by complete account-bound history.

No similarity search resolves a manual fill. The caller identifies the alert and
broker order; the gateway independently verifies account, side, time and entries.
"""
import json
import mt5_store as store
import mt5_risk as risk
import dnb_history
import dnb_lifecycle
import dnb_sources

SCHEMA = ('CREATE TABLE IF NOT EXISTS dnb_manual_bindings (trade_id TEXT PRIMARY KEY, account_kind TEXT NOT NULL, order_ticket TEXT NOT NULL, created_at INTEGER NOT NULL, payload TEXT NOT NULL, UNIQUE(account_kind,order_ticket))',)


def account_state(now, demo):
    if demo:
        import dnb_demo
        snapshot = dnb_demo.latest(now)
    else:
        from mt5_bridge import latest_snapshot
        snapshot = latest_snapshot()
    capture = dnb_history.latest(demo=demo)
    if not snapshot or not snapshot['fresh'] or not capture or not 0 <= now - capture['captured_at'] <= 60:
        raise risk.Reject('manual_fresh_account_history_required')
    if capture['payload']['from_server_time'] != 0:
        raise risk.Reject('manual_complete_history_required')
    c = dnb_history.HistoryConnection(store.db(), demo)
    orders = [json.loads(r['payload']) for r in c.execute('SELECT payload FROM dnb_broker_orders')]
    deals = [json.loads(r['payload']) for r in c.execute('SELECT payload FROM dnb_broker_deals')]
    return snapshot, capture, orders, deals


def bind(body, now):
    risk.keys(body, {'trade_id', 'account_kind', 'order_ticket'})
    if body['account_kind'] not in {'DEMO', 'GOAT'}:
        raise risk.Reject('manual_account_kind')
    dnb_history.ticket(body['order_ticket'])
    if not isinstance(body['trade_id'], str):raise risk.Reject('manual_trade_id')
    c = store.lock_account()
    alert = c.execute('SELECT * FROM dnb_alert_intents WHERE trade_id=?', (body['trade_id'],)).fetchone()
    if not alert or alert['state'] not in {'SENT', 'SENDING', 'DELIVERY_UNKNOWN', 'MANUAL_POSSIBLE', 'MANUAL_BOUND', 'MANUAL_CLOSED'}:
        raise risk.Reject('manual_delivered_alert_required')
    old = c.execute('SELECT * FROM dnb_manual_bindings WHERE trade_id=?', (body['trade_id'],)).fetchone()
    if old:
        if old['account_kind'] != body['account_kind'] or old['order_ticket'] != body['order_ticket']:
            raise risk.Reject('manual_binding_conflict')
        return {'ok': True, 'idempotent': True, 'proof': json.loads(old['payload'])}
    snap, capture, orders, deals = account_state(now, body['account_kind'] == 'DEMO')
    order = next((o for o in orders if o['ticket'] == body['order_ticket']), None)
    if not order:raise risk.Reject('manual_order_history_required')
    proposal = json.loads(alert['payload'])
    symbol = proposal['symbol'][:-2] if body['account_kind'] == 'DEMO' else proposal['symbol']
    if order['symbol'] != symbol or order['type'] % 2 != (0 if proposal['side'] == 'BUY' else 1):
        raise risk.Reject('manual_order_proposal_conflict')
    entries = [d for d in deals if d['order_ticket'] == order['ticket'] and d['entry'] == 0]
    if not entries or order['magic'] != 0 or order['reason'] not in {0, 1, 2}:
        raise risk.Reject('manual_entry_identity_required')
    if any(d['magic'] != 0 or d['reason'] not in {0, 1, 2} or d['symbol'] != symbol or d['type'] != order['type'] % 2 for d in entries):
        raise risk.Reject('manual_entry_identity_required')
    offset = capture['payload']['to_server_time'] - capture['captured_at']
    start, end = alert['created_at'], dnb_sources.timestamp(proposal['valid_until'])
    if not start <= order['created_at'] - offset <= end or any(not start <= d['time'] - offset <= end for d in entries):
        raise risk.Reject('manual_entry_outside_alert_window')
    ids = {d['position_id'] for d in entries}
    if '0' in ids or len(ids) != 1 or any(d['position_id'] in ids and d['entry'] in {0, 2} and d['order_ticket'] != order['ticket'] for d in deals):
        raise risk.Reject('manual_mixed_position_unresolved')
    projected = dnb_lifecycle.project(order, deals, snap['payload']['positions'], snap['payload']['orders'])
    if projected['state'] not in {'OPEN', 'PARTIAL_OPEN', 'CLOSED'}:
        raise risk.Reject('manual_lifecycle_unresolved')
    proof = {'operator_binding': body, 'history_capture_id': capture['id'],
             'snapshot_id': snap['id'], 'broker': projected}
    # A unique order cannot resolve two alerts. Never use INSERT OR IGNORE here.
    if c.execute('SELECT trade_id FROM dnb_manual_bindings WHERE account_kind=? AND order_ticket=?',
                 (body['account_kind'], body['order_ticket'])).fetchone():raise risk.Reject('manual_order_already_bound')
    c.execute('INSERT INTO dnb_manual_bindings VALUES (?,?,?,?,?)',
              (body['trade_id'], body['account_kind'], body['order_ticket'], now, json.dumps(proof, sort_keys=True)))
    state = 'MANUAL_CLOSED' if projected['state'] == 'CLOSED' else 'MANUAL_BOUND'
    c.execute('UPDATE dnb_alert_intents SET state=? WHERE trade_id=?', (state, body['trade_id']))
    c.commit()
    return {'ok': True, 'state': state, 'proof': proof, 'live_auto_authorised': False}


def reconcile(now):
    for kind in ('DEMO', 'GOAT'):
        c = store.lock_account()
        rows = list(c.execute('SELECT * FROM dnb_manual_bindings WHERE account_kind=?', (kind,)))
        if not rows:continue
        try:snap, capture, orders, deals = account_state(now, kind == 'DEMO')
        except risk.Reject:continue
        for row in rows:
            order = next((o for o in orders if o['ticket'] == row['order_ticket']), None)
            if not order:continue
            projection = dnb_lifecycle.project(order, deals, snap['payload']['positions'], snap['payload']['orders'])
            # Netting additions after binding break attribution; keep quarantine.
            if any(d['position_id'] in projection['position_ids'] and d['entry'] in {0, 2} and d['order_ticket'] != order['ticket'] for d in deals):
                state = 'MANUAL_POSSIBLE'
            else:
                state = {'CLOSED': 'MANUAL_CLOSED', 'OPEN': 'MANUAL_BOUND', 'PARTIAL_OPEN': 'MANUAL_BOUND'}.get(projection['state'], 'MANUAL_POSSIBLE')
            proof = json.loads(row['payload'])
            proof.update(broker=projection, history_capture_id=capture['id'], snapshot_id=snap['id'])
            c.execute('UPDATE dnb_manual_bindings SET payload=? WHERE trade_id=?', (json.dumps(proof, sort_keys=True), row['trade_id']))
            c.execute('UPDATE dnb_alert_intents SET state=? WHERE trade_id=?', (state, row['trade_id']))
        c.commit()

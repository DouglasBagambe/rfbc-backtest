"""Evidence-bound prospective demo resets, on a fixed 22:00 UTC test clock.

This clock is a demo policy, not a claim about the funded firm's reset timezone.
An outage never manufactures a boundary valuation or clears any reservations.
"""
import json
import mt5_risk as risk
import mt5_store as store
import dnb_history

SCHEMA = ('CREATE TABLE IF NOT EXISTS dnb_demo_reset_proofs (boundary INTEGER PRIMARY KEY, epoch_id TEXT NOT NULL, payload TEXT NOT NULL)',)


def next_boundary(now):
    return ((now - 22 * 3600) // 86400 + 1) * 86400 + 22 * 3600


def boundary_proof(boundary, now):
    capture = dnb_history.latest(demo=True)
    if not capture or not 0 <= now - capture['captured_at'] <= 60:
        raise risk.Reject('demo_reset_fresh_history_required')
    # Full broker history is required, including balance operations and trades
    # which opened and closed between two otherwise flat observations.
    if capture['payload']['from_server_time'] != 0:
        raise risk.Reject('demo_reset_complete_history_required')
    rows = store.db().execute('SELECT * FROM dnb_demo_snapshots WHERE captured_at BETWEEN ? AND ? ORDER BY captured_at,received_at',
                              (boundary - 15, boundary + 15))
    snapshots = [{**dict(r), 'payload': json.loads(r['payload'])} for r in rows]
    snapshots = [r for r in snapshots if r['payload']['terminal_connected'] and
                 0 <= r['received_at'] - r['captured_at'] <= 15]
    before = [r for r in snapshots if r['captured_at'] < boundary]
    after = [r for r in snapshots if r['captured_at'] >= boundary]
    if not before or not after:
        raise risk.Reject('demo_epoch_reset_requires_verified_boundary')
    for timestamp in {r['captured_at'] for r in snapshots}:
        versions = {json.dumps({k: r['payload'][k] for k in ('balance','equity','floating_pnl','positions','orders')},sort_keys=True)
                    for r in snapshots if r['captured_at']==timestamp}
        if len(versions)>1:raise risk.Reject('demo_reset_conflicting_boundary_observation')
    pre, post = before[-1], after[0]
    if capture['captured_at'] < post['captured_at']:
        raise risk.Reject('demo_reset_history_not_through_boundary')
    # Open exposure requires a separate exact boundary valuation protocol. Do
    # not estimate floating equity from neighbouring quotes after an outage.
    if any(r['payload']['positions'] or r['payload']['orders'] for r in (pre, post)):
        raise risk.Reject('demo_reset_open_exposure_valuation_required')
    for r in (pre, post):
        p = r['payload']
        if risk.number(p['balance']) != risk.number(p['equity']) or risk.number(p['floating_pnl']) != 0:
            raise risk.Reject('demo_reset_flat_valuation_conflict')
    if risk.number(pre['payload']['balance']) != risk.number(post['payload']['balance']):
        raise risk.Reject('demo_reset_balance_changed')
    offset = capture['payload']['to_server_time'] - capture['captured_at']
    # Pad the server/UTC conversion for collection clock skew. Any deal in the
    # entire bracket defeats flat continuity, including a zero-profit round trip.
    for r in store.db().execute('SELECT payload FROM dnb_demo_broker_deals'):
        deal = json.loads(r['payload'])
        if pre['captured_at'] + offset - 2 <= deal['time'] <= post['captured_at'] + offset + 2:
            raise risk.Reject('demo_reset_boundary_activity')
    return {'policy': 'DEMO_FIXED_22_UTC_FLAT_CONTINUITY', 'boundary': boundary,
            'daily_anchor': float(risk.positive(post['payload']['balance'])),
            'before_snapshot_id': pre['id'], 'after_snapshot_id': post['id'],
            'history_capture_id': capture['id']}


def advance(row, value, now):
    boundary = value['valid_until']
    if now >= next_boundary(boundary):
        raise risk.Reject('demo_reset_multiple_boundaries_missing')
    proof = boundary_proof(boundary, now)
    c = store.lock_account()
    current = c.execute('SELECT payload FROM dnb_demo_epochs WHERE id=?', (row['id'],)).fetchone()
    current_value = json.loads(current['payload'])
    if current_value != value:
        raise risk.Reject('demo_reset_concurrent_revision')
    # Peak, initial balance, thesis limits, commands and uncertain intents stay.
    updated = {**value, 'daily_anchor': proof['daily_anchor'],
               'valid_until': next_boundary(boundary), 'reset_proof': proof}
    encoded = json.dumps(updated, sort_keys=True, separators=(',', ':'), allow_nan=False)
    c.execute('INSERT INTO dnb_demo_reset_proofs VALUES (?,?,?)',
              (boundary, row['id'], json.dumps(proof, sort_keys=True)))
    c.execute('UPDATE dnb_demo_epochs SET payload=? WHERE id=?', (encoded, row['id']))
    c.commit()
    return updated

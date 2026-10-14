"""Bounded scale-in planning. Requires broker-confirmed thesis membership.

Planning support is not native execution support. No strategy stop is modified.
"""
from decimal import Decimal
import re
import mt5_risk as risk

MAX_SCALE_INS = 2

def validate_scale_in(snapshot, command, proof, now):
    risk.keys(proof, {'thesis_id','initial_risk_pct','legs','confirmation_at',
                      'confirmation_id','structure_valid','broker_history_verified'})
    if not isinstance(proof['thesis_id'],str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',proof['thesis_id']):
        raise risk.Reject('invalid_thesis_id')
    if proof['structure_valid'] is not True or proof['broker_history_verified'] is not True:
        raise risk.Reject('thesis_or_broker_history_unverified')
    if type(proof['confirmation_at']) is not int or not 0 <= now-proof['confirmation_at'] <= 30:
        raise risk.Reject('stale_scale_confirmation')
    if not isinstance(proof['confirmation_id'],str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',proof['confirmation_id']):
        raise risk.Reject('invalid_confirmation_id')
    legs=proof['legs']
    if not isinstance(legs,list) or not 1 <= len(legs) <= MAX_SCALE_INS:
        raise risk.Reject('scale_in_limit')
    if risk.positive(command['risk_pct']) > risk.positive(proof['initial_risk_pct']):
        raise risk.Reject('scale_in_risk_increase')
    side='BUY' if command['order_type'].startswith('BUY') else 'SELL'
    actual=[p for p in snapshot['positions'] if p['symbol']==command['symbol']]
    if any(p['symbol']==command['symbol'] for p in snapshot['orders']):
        raise risk.Reject('unresolved_same_symbol_pending')
    by_ticket={p['ticket']:p for p in actual}
    if len(actual)!=len(legs): raise risk.Reject('manual_or_unmapped_same_symbol')
    seen=set(); confirmations=set()
    for leg in legs:
        risk.keys(leg,{'ticket','command_id','thesis_id','entry','side','commission','created_at','confirmation_id','risk_pct'})
        if leg['ticket'] in seen: raise risk.Reject('duplicate_thesis_leg')
        seen.add(leg['ticket']);confirmations.add(leg['confirmation_id'])
        p=by_ticket.get(leg['ticket'])
        if not p or leg['thesis_id']!=proof['thesis_id'] or p['side']!=side or leg['side']!=side:
            raise risk.Reject('thesis_binding')
        if not re.fullmatch(r'[a-f0-9]{32}',str(leg['command_id'])) or leg['command_id']==command['command_id']:
            raise risk.Reject('duplicate_command')
        if risk.number(leg['entry'])!=risk.number(p['entry']): raise risk.Reject('thesis_entry_mismatch')
        if type(leg['created_at']) is not int or proof['confirmation_at'] <= leg['created_at']:
            raise risk.Reject('confirmation_not_new')
        if risk.number(leg['commission'])>0: raise risk.Reject('invalid_commission')
        if risk.number(p['profit'])+risk.number(p['swap'])+risk.number(leg['commission']) <= 0:
            raise risk.Reject('no_adding_to_losing_leg')
        quote=snapshot['symbols'][command['symbol']]
        current=risk.number(quote['bid'] if side=='BUY' else quote['ask'])
        entry=risk.number(command['entry']);old=risk.number(p['entry'])
        if not (current>old and entry>old if side=='BUY' else current<old and entry<old):
            raise risk.Reject('no_averaging_down')
        if risk.positive(leg['risk_pct'])>risk.positive(proof['initial_risk_pct']):
            raise risk.Reject('scale_in_risk_increase')
    if seen != set(by_ticket): raise risk.Reject('manual_or_unmapped_same_symbol')
    if proof['confirmation_id'] in confirmations: raise risk.Reject('duplicate_scale_confirmation')
    entry=risk.positive(command['entry']);sl=risk.positive(command['sl']);tp=risk.positive(command['tp'])
    if not (sl<entry<tp if side=='BUY' else tp<entry<sl): raise risk.Reject('sltp_geometry')
    if abs(tp-entry)/abs(entry-sl) < Decimal('1.5'): raise risk.Reject('scale_in_reward_risk')
    return seen

def plan_scale_in(snapshot, command, proof, now):
    allowed=validate_scale_in(snapshot,command,proof,now)
    result=risk.plan(snapshot,command,now,scale_in_tickets=allowed)
    result.update(thesis_id=proof['thesis_id'],scale_in_number=len(proof['legs']),
                  total_thesis_risk_usd=float(risk.portfolio_risk({**snapshot,
                    'positions':[p for p in snapshot['positions'] if p['ticket'] in allowed], 'orders':[]},now))+result['risk_usd'])
    return result

def reserve_scale_in(snapshot,command,proof,now):
    """Durable confirmation and lifetime leg limit, including closed/uncertain legs.

Reserved legs are never removed on an ACK outage. Broker reconciliation is
required before changing their lifecycle; retry returns the same reservation.
This library is not connected to native submission in the current build.
"""
    import json
    import mt5_store as store
    from mt5_bridge import _ensure_schema
    _ensure_schema();c=store.lock_account()
    result=plan_scale_in(snapshot,command,proof,now)
    rows=list(c.execute('SELECT * FROM dnb_thesis_legs WHERE thesis_id=?',(proof['thesis_id'],)))
    by_id={r['command_id']:r for r in rows}
    encoded=json.dumps({'command':command,'thesis_id':proof['thesis_id'],
                        'confirmation_id':proof['confirmation_id'],'quote':result},sort_keys=True,separators=(',',':'))
    old=by_id.get(command['command_id'])
    if old:
        if old['payload']!=encoded: raise risk.Reject('duplicate_thesis_command_conflict')
        c.commit();return result
    confirmed_ids={leg['command_id'] for leg in proof['legs']}
    if any('command' in json.loads(r['payload']) and r['command_id'] not in confirmed_ids for r in rows):
        raise risk.Reject('unresolved_thesis_submission')
    for leg in proof['legs']:
        if leg['command_id'] not in by_id:
            payload=json.dumps(leg,sort_keys=True,separators=(',',':'))
            c.execute('INSERT INTO dnb_thesis_legs VALUES (?,?,?,?)',
                      (leg['command_id'],proof['thesis_id'],leg['confirmation_id'],payload))
            by_id[leg['command_id']]={'confirmation_id':leg['confirmation_id']}
    if len(by_id)>=1+MAX_SCALE_INS: raise risk.Reject('scale_in_limit')
    if any(r['confirmation_id']==proof['confirmation_id'] for r in by_id.values()):
        raise risk.Reject('duplicate_scale_confirmation')
    c.execute('INSERT INTO dnb_thesis_legs VALUES (?,?,?,?)',
              (command['command_id'],proof['thesis_id'],proof['confirmation_id'],encoded));c.commit()
    return result

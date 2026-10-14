"""Broker-derived scale-in proof. Source producers cannot supply ticket membership."""
import hashlib
import json
from decimal import Decimal
import mt5_risk as risk
import mt5_store as store
import dnb_sources

def proof(snapshot,command,decision,now):
    thesis=decision.get('thesis_id')
    if not isinstance(thesis,str):raise risk.Reject('scale_thesis_required')
    rows=list(store.db().execute('SELECT * FROM dnb_demo_strategy_commands ORDER BY created_at,id'))
    members=[r for r in rows if r['id']!=command['command_id'] and json.loads(r['payload'])['thesis_id']==thesis]
    if not members:raise risk.Reject('scale_thesis_unknown')
    if len(members)>=3:raise risk.Reject('scale_in_limit')
    if any(r['state'] not in {'OPEN','PARTIAL_OPEN','CLOSED'} for r in members):raise risk.Reject('unresolved_thesis_submission')
    initial=json.loads(members[0]['payload'])
    if command['risk_pct']>initial['risk_pct']:raise risk.Reject('scale_in_risk_increase')
    initial_risk=risk.positive(initial['quote']['risk_usd'])
    # The actual publication is the confirmation, not a fresh timestamp
    # invented by the polling worker. Stale scale-ins never become new entries.
    receipt=store.db().execute('SELECT * FROM dnb_source_receipts WHERE id=?',(decision['source_receipt_id'],)).fetchone()
    if not receipt or not 0<=now-receipt['generated_at']<=30:raise risk.Reject('stale_scale_confirmation')
    raw=json.loads(receipt['payload'])
    if receipt['source']=='G_DESK':
        bar_end=dnb_sources.timestamp(raw.get('context',{}).get('latest_completed_bar'))+3600
        if any(bar_end<=r['created_at'] for r in members):raise risk.Reject('confirmation_not_new_bar')
    if decision.get('context',{}).get('thesis_valid') is not True or decision.get('context',{}).get('fresh_structure_confirmed') is not True:
        raise risk.Reject('thesis_or_structure_unverified')
    confirmation=hashlib.sha256(decision['source_receipt_id'].encode()).hexdigest()[:32]
    if any(json.loads(r['payload']).get('confirmation_id')==confirmation for r in members):raise risk.Reject('duplicate_scale_confirmation')
    if decision.get('scale_in_number')!=len(members):raise risk.Reject('scale_in_sequence')
    side='BUY' if command['order_type'].startswith('BUY') else 'SELL'
    if any(p['symbol']==command['symbol'] for p in snapshot['orders']):raise risk.Reject('unresolved_same_symbol_pending')
    actual=[p for p in snapshot['positions'] if p['symbol']==command['symbol']]
    if not actual or any(p['side']!=side for p in actual):raise risk.Reject('thesis_binding')
    if initial['symbol']!=command['symbol'] or not initial['order_type'].startswith(side):raise risk.Reject('thesis_binding')
    orders=[json.loads(r['payload']) for r in store.db().execute('SELECT payload FROM dnb_demo_broker_orders')]
    deals=[json.loads(r['payload']) for r in store.db().execute('SELECT payload FROM dnb_demo_broker_deals')]
    legs=[];known_ids=set();known_orders=set();known_positions=set()
    for member in members:
        p=json.loads(member['payload']);identifier=member['id']
        if p['source']!=decision['source']:raise risk.Reject('thesis_source_binding')
        magic=int(hashlib.sha256(('dnb:'+identifier).encode()).hexdigest()[:15],16)
        roots=[o for o in orders if o['magic']==magic and o['comment']=='dnb:'+identifier[:24] and o['symbol']==command['symbol'][:-2]]
        if len(roots)!=1:raise risk.Reject('thesis_broker_identity_unresolved')
        root=roots[0];entries=[d for d in deals if d['order_ticket']==root['ticket'] and d['entry']==0]
        if not entries:raise risk.Reject('thesis_fill_unverified')
        volume=sum((risk.number(d['volume']) for d in entries),Decimal(0))
        if volume<=0:raise risk.Reject('thesis_fill_unverified')
        entry=sum((risk.number(d['price'])*risk.number(d['volume']) for d in entries),Decimal(0))/volume
        ids={d['position_id'] for d in entries};ids.discard('0')
        if len(ids)!=1:raise risk.Reject('thesis_position_identity_unresolved')
        pid=next(iter(ids));known_ids.add(identifier);known_orders.add(root['ticket'])
        position=next((x for x in actual if x.get('identifier',x['ticket'])==pid),None)
        if member['state']=='CLOSED':continue
        if not position:raise risk.Reject('thesis_position_identity_unresolved')
        known_positions.add(position['ticket'])
        quote=snapshot['symbols'][command['symbol']]
        current=risk.number(quote['bid'] if side=='BUY' else quote['ask'])
        new_entry=risk.number(command['entry'])
        if not (current>entry and new_entry>entry if side=='BUY' else current<entry and new_entry<entry):raise risk.Reject('no_averaging_down')
        pnl=(current-entry if side=='BUY' else entry-current)/risk.positive(quote['tick_size'])*risk.positive(quote['tick_value_profit'])*volume
        costs=sum((risk.number(d['commission'])+risk.number(d['fee'])+min(Decimal(0),risk.number(d['swap'])) for d in entries),Decimal(0))
        # Charge actual commissions/fees and all negative position swap to each
        # leg, conservatively, rather than allocate it optimistically. Future
        # fee allowance remains part of the admission risk budget.
        if pnl+costs+min(Decimal(0),risk.number(position['swap']))<=0:raise risk.Reject('no_adding_to_losing_leg')
        if risk.number(position['profit'])+risk.number(position['swap'])<=0:raise risk.Reject('no_adding_to_losing_leg')
        if receipt['generated_at']<=member['created_at']:raise risk.Reject('confirmation_not_new')
        legs.append({'command_id':identifier,'position_id':pid,'ticket':position['ticket'],
                     'entry':float(entry),'volume':float(volume),'sl':position['sl'],'tp':position['tp']})
    if not legs or known_positions!={p['ticket'] for p in actual}:raise risk.Reject('manual_or_unmapped_same_symbol')
    for d in deals:
        if d['position_id'] in {l['position_id'] for l in legs} and d['entry'] in {0,2} and d['order_ticket'] not in known_orders:
            raise risk.Reject('manual_or_unmapped_same_symbol')
    if snapshot.get('account_margin_mode',2)!=2:
        if len(actual)!=1:raise risk.Reject('netting_thesis_position_count')
        if risk.number(command['sl'])!=risk.number(actual[0]['sl']) or risk.number(command['tp'])!=risk.number(actual[0]['tp']):raise risk.Reject('netting_leg_protection_change')
        # Partial exits cannot be allocated to independent netting legs by guess.
        if any(d['entry'] in {1,2,3} and d['position_id']==legs[0]['position_id'] for d in deals):raise risk.Reject('netting_partial_exit_requires_reconciliation')
        if sum((risk.number(l['volume']) for l in legs),Decimal(0))!=risk.number(actual[0]['volume']):raise risk.Reject('netting_leg_volume_mismatch')
    entry,sl,tp=[risk.positive(command[k]) for k in ('entry','sl','tp')]
    if abs(tp-entry)/abs(entry-sl)<Decimal('1.5'):raise risk.Reject('scale_in_reward_risk')
    return {'thesis_id':thesis,'scale_in_number':len(members),'confirmation_id':confirmation,
            'confirmation_at':receipt['generated_at'],'initial_risk_usd':float(initial_risk),'legs':legs,
            'allowed_tickets':{p['ticket'] for p in actual}}

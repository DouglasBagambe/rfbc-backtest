"""Genuine strategy-command ledger for the explicitly bound demo account.

This ledger never changes funded authority. New broker submissions require an
execution epoch with prospective anchors, fresh complete history and fresh native
state. Uncertain submissions remain reserved until exact broker reconciliation.
"""
import hashlib
import json
import os
import uuid
from decimal import Decimal
from datetime import datetime, timezone
import mt5_risk as risk
import mt5_store as store
import dnb_demo
import dnb_history

SCHEMA=(
 'CREATE TABLE IF NOT EXISTS dnb_demo_epochs (id TEXT PRIMARY KEY, created_at INTEGER NOT NULL, payload TEXT NOT NULL)',
 'CREATE TABLE IF NOT EXISTS dnb_demo_strategy_commands (id TEXT PRIMARY KEY, trade_id TEXT UNIQUE NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, ack TEXT)',
 'CREATE TABLE IF NOT EXISTS dnb_demo_execution_events (id TEXT PRIMARY KEY, command_id TEXT NOT NULL, created_at INTEGER NOT NULL, payload TEXT NOT NULL)',
 'CREATE TABLE IF NOT EXISTS dnb_demo_submission_intents (command_id TEXT PRIMARY KEY, created_at INTEGER NOT NULL, payload TEXT NOT NULL)',
)

def enabled():
    return os.getenv('DNB_DEMO_EXECUTION_ENABLED','0')=='1' and os.getenv('DNB_DEMO_KILL_SWITCH','1')=='0'

def execution_status(now):
    row=store.db().execute('SELECT * FROM dnb_demo_epochs ORDER BY created_at DESC LIMIT 1').fetchone()
    value=json.loads(row['payload']) if row else None
    valid=bool(row and row['created_at']<=now<value['valid_until'])
    counts={r['state']:r['n'] for r in store.db().execute('SELECT state,COUNT(*) AS n FROM dnb_demo_strategy_commands GROUP BY state')}
    return {'enabled':enabled(),'new_risk_blocked':not enabled() or not valid,
            'epoch_valid':valid,'epoch':value,'command_counts':counts,
            'live_goat_authorised':False,'native_executor_attached_verified':False}

def status_wire(now,nonce):
    from mt5_bridge import sign
    try:_,a=epoch(now)
    except risk.Reject:a={'daily_anchor':0,'historical_peak':0,'valid_until':0}
    killed=not enabled() or a['valid_until']<=now
    fields=['DNBdemoState1',nonce,str(now),str(dnb_demo.DEMO_LOGIN),dnb_demo.DEMO_SERVER,'DEMO',
            '1' if killed else '0',format(a['daily_anchor'],'.10f'),format(a['historical_peak'],'.10f'),str(a['valid_until'])]
    body='|'.join(fields)
    return body+'|'+sign(body.encode('ascii'))

def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)

def existing_proposal(row,decision):
    p=json.loads(row['payload'])
    if p.get('source_proposal')!=decision:raise risk.Reject('demo_duplicate_proposal_conflict')
    return dict(row)

def epoch(now):
    row=store.db().execute('SELECT * FROM dnb_demo_epochs ORDER BY created_at DESC LIMIT 1').fetchone()
    if not row:raise risk.Reject('demo_epoch_missing')
    value=json.loads(row['payload'])
    # Explicit prospective test session, not an invented GOAT historical anchor.
    if now<row['created_at']:raise risk.Reject('demo_epoch_expired')
    if now>=value['valid_until']:
        if value.get('reset_clock')!='DEMO_FIXED_22_UTC':raise risk.Reject('demo_epoch_expired')
        import dnb_demo_reset
        value=dnb_demo_reset.advance(row,value,now)
    return dict(row),value

def initialise_epoch(now):
    """Operator action: start a prospective, flat-account validation session.

    Existing command reservations and history are preserved. It cannot reset
    losses or uncertainty away; an unexpired epoch cannot be replaced.
    """
    from mt5_bridge import _ensure_schema
    _ensure_schema();c=store.lock_account()
    snap=dnb_demo.latest(now);history=dnb_history.latest(demo=True)
    if not snap or not snap['fresh'] or not history or not 0<=now-history['captured_at']<=60:raise risk.Reject('demo_fresh_history_required')
    if 'account_margin_mode' not in snap['payload']:raise risk.Reject('demo_margin_model_unverified')
    if snap['payload']['positions'] or snap['payload']['orders']:raise risk.Reject('demo_epoch_requires_flat_account')
    prior=c.execute('SELECT * FROM dnb_demo_epochs ORDER BY created_at DESC LIMIT 1').fetchone()
    if prior:
        value=json.loads(prior['payload'])
        if now<value['valid_until']:return {**dict(prior),'payload':value}
        # Automatic reset must use independently proven boundary state, not a
        # current balance. A new validation epoch requires a separate operator.
        raise risk.Reject('demo_epoch_reset_requires_verified_boundary')
    if c.execute("SELECT id FROM dnb_demo_strategy_commands WHERE state NOT IN ('REJECTED','CLOSED','EXPIRED') LIMIT 1").fetchone():raise risk.Reject('demo_unresolved_submission')
    p=snap['payload'];basis=min(risk.positive(p['balance']),risk.positive(p['equity']))
    # Mirror GOAT's fixed-$125 drawdown and $12.50 buffer, with a prospective
    # starting anchor. The initial cap is a policy input, not a claimed GOAT high.
    import dnb_demo_reset
    payload={'purpose':'DEMO_PROSPECTIVE_VALIDATION','login':dnb_demo.DEMO_LOGIN,'server':dnb_demo.DEMO_SERVER,
             'daily_anchor':float(basis),'historical_peak':float(max(Decimal('2500'),basis)),
             'initial_balance':float(basis),'peak_policy':'prospective_simulated_goat_initial_2500',
             'valid_until':dnb_demo_reset.next_boundary(now),'reset_clock':'DEMO_FIXED_22_UTC',
             'snapshot_id':snap['id'],'history_capture':history['id']}
    identifier=uuid.uuid4().hex;c.execute('INSERT INTO dnb_demo_epochs VALUES (?,?,?)',(identifier,now,encode(payload)));c.commit()
    return {'id':identifier,'created_at':now,'payload':payload}

def effective_snapshot(now):
    row,value=epoch(now);snap=dnb_demo.latest(now);history=dnb_history.latest(demo=True)
    if not snap or not snap['fresh'] or not history or not 0<=now-history['captured_at']<=60:raise risk.Reject('demo_fresh_history_required')
    p=dict(snap['payload'])
    if 'account_margin_mode' not in p:raise risk.Reject('demo_margin_model_unverified')
    peak=max(risk.positive(value['historical_peak']),risk.positive(p['balance']),risk.positive(p['equity']))
    # Observations only advance the prospective peak; they never reset it.
    if peak>risk.number(value['historical_peak']):
        value['historical_peak']=float(peak)
        c=store.lock_account();c.execute('UPDATE dnb_demo_epochs SET payload=? WHERE id=?',(encode(value),row['id']));c.commit()
    p.update(daily_anchor=value['daily_anchor'],high_water_equity=float(peak),anchors_verified=True)
    return p,value

def queue(decision,now):
    from mt5_bridge import _ensure_schema,make_command
    _ensure_schema()
    if not enabled():raise risk.Reject('demo_execution_killed')
    c=store.lock_account()
    expire_queued(c,now)
    old=c.execute('SELECT * FROM dnb_demo_strategy_commands WHERE trade_id=?',(decision['trade_id'],)).fetchone()
    if old:return existing_proposal(old,decision)
    if c.execute("SELECT id FROM dnb_demo_strategy_commands WHERE state IN ('QUEUED','INTENT','UNRESOLVED','PARTIAL','ACCEPTED','PLACED') LIMIT 1").fetchone():raise risk.Reject('demo_submission_or_lifecycle_unresolved')
    s,authority=effective_snapshot(now)
    # Protect the target; this never increases risk to catch up to it.
    if risk.number(s['balance'])>=Decimal('2650'):raise risk.Reject('payout_target_pause')
    import dnb_alerts
    dnb_alerts.require_reconciled(decision['symbol'])
    if c.execute('SELECT trade_id FROM dnb_manual_bindings WHERE trade_id=?',(decision['trade_id'],)).fetchone():
        raise risk.Reject('decision_already_manually_executed')
    receipt=c.execute('SELECT * FROM dnb_source_receipts WHERE id=?',(decision.get('source_receipt_id'),)).fetchone()
    if not receipt or receipt['source']!=decision['source'] or receipt['result']!='TRADE':raise risk.Reject('genuine_source_receipt_required')
    if not 0<=now-receipt['generated_at']<=3600:raise risk.Reject('source_stale_or_future')
    import dnb_sources
    trusted=json.loads(receipt['payload'])
    if receipt['source']=='G_DESK':trusted=dnb_sources.gdesk_decisions(trusted,now)[0]
    frozen=('trade_id','source','symbol','side','entry','stop','target','risk_pct','valid_until','context','thesis_id','scale_in_number')
    if any(decision.get(k)!=trusted.get(k) for k in frozen):raise risk.Reject('source_proposal_conflict')
    # Intentionally no source-supplied boolean can bypass thesis validation.
    scale_number=decision.get('scale_in_number',0)
    if type(scale_number) is not int or not 0<=scale_number<=2:raise risk.Reject('invalid_scale_in_number')
    command=make_command(decision);command.update(login=dnb_demo.DEMO_LOGIN,server=dnb_demo.DEMO_SERVER,created_at=now)
    command['expires_at']=min(command['expires_at'],now+30)
    # RFBC's structure stop is its objective invalidation. G_DESK must supply its
    # own machine-readable cancellation; no natural-language condition is guessed.
    if decision['source']=='RFBC':command['cancel']={'kind':'price_below' if decision['side']=='BUY' else 'price_above','price':decision['stop']}
    scale=None
    if scale_number:
        import dnb_demo_scale
        scale=dnb_demo_scale.proof(s,command,decision,now)
    elif any(json.loads(r['payload'])['thesis_id']==decision['thesis_id'] for r in c.execute('SELECT payload FROM dnb_demo_strategy_commands')):
        raise risk.Reject('thesis_reentry_requires_new_id')
    quote=risk.plan(s,command,now,expected_login=dnb_demo.DEMO_LOGIN,expected_server=dnb_demo.DEMO_SERVER,
                    fee_per_lot=Decimal('12'),scale_in_tickets=frozenset(scale['allowed_tickets']) if scale else frozenset())
    if scale:
        # Equal/smaller monetary risk, including fees, without changing structure.
        unit=risk.number(quote['risk_usd'])/risk.number(quote['volume']);step=risk.positive(s['symbols'][command['symbol']]['volume_step'])
        volume=(min(risk.number(quote['risk_usd']),risk.number(scale['initial_risk_usd']))/unit/step).to_integral_value(rounding='ROUND_FLOOR')*step
        if volume<risk.positive(s['symbols'][command['symbol']]['volume_min']):raise risk.Reject('scale_in_lot_minimum')
        quote['risk_usd']=float(unit*volume);quote['volume']=float(volume)
    spec=s['symbols'][command['symbol']]
    # Until a trusted news feed is mapped to the firm's calendar, constrain
    # planned TP money to the published 1%-of-initial news-profit allowance.
    unit_tp=(abs(risk.number(command['tp'])-risk.number(quote['entry']))/risk.positive(spec['tick_size'])+5)*risk.positive(spec['tick_value_profit'])
    step=risk.positive(spec['volume_step']);max_volume=(Decimal('25')/unit_tp/step).to_integral_value(rounding='ROUND_FLOOR')*step
    volume=min(risk.number(quote['volume']),max_volume)
    if volume<risk.positive(spec['volume_min']):raise risk.Reject('news_profit_cap_lot_minimum')
    quote['risk_usd']=float(risk.number(quote['risk_usd'])*volume/risk.number(quote['volume']));quote['volume']=float(volume)
    valid_until=int(datetime.fromisoformat(decision['valid_until'].replace('Z','+00:00')).timestamp())
    thesis=decision.get('thesis_id') or hashlib.sha256(decision['trade_id'].encode()).hexdigest()[:32]
    if not isinstance(thesis,str) or not 1<=len(thesis)<=64 or any(ch not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for ch in thesis):raise risk.Reject('invalid_thesis_id')
    payload={**command,'source':decision['source'],'thesis_id':thesis,'quote':quote,'valid_until':valid_until,
             'snapshot_id':dnb_demo.latest(now)['id'],'authority':authority,'synthetic':False,'source_proposal':decision,
             'scale_in_number':scale_number,'confirmation_id':scale['confirmation_id'] if scale else hashlib.sha256(decision['source_receipt_id'].encode()).hexdigest()[:32]}
    if scale:
        payload['scale_proof']={k:v for k,v in scale.items() if k!='allowed_tickets'}
    c=store.lock_account()
    # Peak advancement can commit a transaction. Reacquire the account lock and
    # re-read the reservation before inserting so concurrent producers cannot
    # reserve different signals against the same unconsumed account snapshot.
    dnb_alerts.require_reconciled(decision['symbol'])
    if c.execute('SELECT trade_id FROM dnb_manual_bindings WHERE trade_id=?',(decision['trade_id'],)).fetchone():
        raise risk.Reject('decision_already_manually_executed')
    old=c.execute('SELECT * FROM dnb_demo_strategy_commands WHERE trade_id=?',(decision['trade_id'],)).fetchone()
    if old:return existing_proposal(old,decision)
    if c.execute("SELECT id FROM dnb_demo_strategy_commands WHERE state IN ('QUEUED','INTENT','UNRESOLVED','PARTIAL','ACCEPTED','PLACED') LIMIT 1").fetchone():raise risk.Reject('demo_submission_or_lifecycle_unresolved')
    if scale:
        members=[r for r in c.execute('SELECT payload FROM dnb_demo_strategy_commands') if json.loads(r['payload'])['thesis_id']==thesis]
        if len(members)!=scale_number or len(members)>=3:raise risk.Reject('scale_in_reservation_conflict')
    c.execute('INSERT INTO dnb_demo_strategy_commands VALUES (?,?,?,?,?,?,?)',
       (command['command_id'],decision['trade_id'],'QUEUED',encode(payload),now,command['expires_at'],None));c.commit()
    return dict(c.execute('SELECT * FROM dnb_demo_strategy_commands WHERE id=?',(command['command_id'],)).fetchone())

def expire_queued(c,now):
    # Expiration only releases requests which never acquired a remote intent.
    # An uncertain submission remains reserved regardless of lease age.
    c.execute("UPDATE dnb_demo_strategy_commands SET state='EXPIRED' WHERE state='QUEUED' AND expires_at<=? AND id NOT IN (SELECT command_id FROM dnb_demo_submission_intents)",(now,))

def next_command(now,nonce):
    if not enabled():return 'NONE'
    c=store.lock_account();expire_queued(c,now);c.commit()
    row=store.db().execute("SELECT * FROM dnb_demo_strategy_commands WHERE state IN ('QUEUED','INTENT','UNRESOLVED') ORDER BY created_at LIMIT 1").fetchone()
    if not row:return 'NONE'
    p=json.loads(row['payload']);a=p['authority']
    if row['state']=='QUEUED':
        # Daily leases are evaluated again; a yesterday command never carries
        # its old daily anchor through a reset. Recovery keeps its original proof.
        try:_,a=epoch(now)
        except risk.Reject:return 'NONE'
    # Native execution gets a distinct protocol and exact demo binding. The
    # existing funded SHADOW command parser cannot mistake it for permission.
    fields=['DNBdemo1',nonce,p['command_id'],str(dnb_demo.DEMO_LOGIN),dnb_demo.DEMO_SERVER,'DEMO',
            str(p['created_at']),str(p['expires_at']),p['symbol'],p['order_type']]
    fields += [format(float(p[k]),'.10f') for k in ('entry','sl','tp','risk_pct','stop_limit')]
    fields += [p['cancel']['kind'],format(float(p['cancel']['price']),'.10f'),'0',p['thesis_id'],
               str(p['valid_until']),format(p['quote']['volume'],'.10f'),format(a['daily_anchor'],'.10f'),
               format(a['historical_peak'],'.10f'),str(a['valid_until']),row['state'],format(p['quote']['risk_usd'],'.10f'),p['source'],row['trade_id']]
    scale=p.get('scale_proof',{});legs=scale.get('legs',[])
    fields += [str(p.get('scale_in_number',0)),','.join(l['command_id'] for l in legs) or '-',
               p['confirmation_id'],str(scale.get('confirmation_at',p['created_at'])),
               format(scale.get('initial_risk_usd',p['quote']['risk_usd']),'.10f'),
               ','.join(format(float(l['sl']),'.10f') for l in legs) or '-',
               ','.join(format(float(l['tp']),'.10f') for l in legs) or '-']
    from mt5_bridge import sign
    body='|'.join(fields)
    return body+'|'+sign(body.encode('ascii'))

def submission_intent(body,now):
    risk.keys(body,{'command_id','login','server','fingerprint','symbol','order_type','volume','entry','sl','tp'})
    if body['login']!=dnb_demo.DEMO_LOGIN or body['server']!=dnb_demo.DEMO_SERVER:raise risk.Reject('demo_binding')
    import re
    if not isinstance(body['fingerprint'],str) or not re.fullmatch('[a-f0-9]{64}',body['fingerprint']):raise risk.Reject('invalid_intent_fingerprint')
    from mt5_bridge import _ensure_schema
    _ensure_schema();c=store.lock_account()
    row=c.execute('SELECT * FROM dnb_demo_strategy_commands WHERE id=?',(body['command_id'],)).fetchone()
    if not row:raise risk.Reject('unknown_demo_command')
    old=c.execute('SELECT * FROM dnb_demo_submission_intents WHERE command_id=?',(body['command_id'],)).fetchone()
    canonical=encode(body)
    if old:
        if old['payload']!=canonical:raise risk.Reject('demo_intent_conflict')
        c.commit();return {'ok':True,'state':row['state'],'idempotent':True}
    if not enabled() or row['state']!='QUEUED' or row['expires_at']<=now:raise risk.Reject('demo_submission_unavailable')
    p=json.loads(row['payload'])
    if body['symbol']!=p['symbol'] or body['order_type']!=p['order_type'] or risk.number(body['sl'])!=risk.number(p['sl']) or risk.number(body['tp'])!=risk.number(p['tp']):raise risk.Reject('demo_request_conflict')
    s,_=effective_snapshot(now)
    import dnb_alerts
    dnb_alerts.require_reconciled(p['symbol'])
    cmd={k:p[k] for k in ('command_id','login','server','created_at','expires_at','symbol','order_type','entry','sl','tp','risk_pct','stop_limit','cancel')}
    scale=None
    if p.get('scale_in_number'):
        import dnb_demo_scale
        scale=dnb_demo_scale.proof(s,cmd,p['source_proposal'],now)
    quote=risk.plan(s,cmd,now,expected_login=dnb_demo.DEMO_LOGIN,expected_server=dnb_demo.DEMO_SERVER,
                    fee_per_lot=Decimal('12'),scale_in_tickets=frozenset(scale['allowed_tickets']) if scale else frozenset())
    spec=s['symbols'][p['symbol']]
    volume=risk.positive(body['volume']);step=risk.positive(spec['volume_step'])
    if volume>min(risk.number(quote['volume']),risk.number(p['quote']['volume'])) or volume<risk.positive(spec['volume_min']) or volume/step!=(volume/step).to_integral_value():raise risk.Reject('demo_request_volume')
    if abs(risk.positive(body['entry'])-risk.positive(quote['entry']))/risk.positive(spec['tick_size'])>5:raise risk.Reject('demo_request_price')
    # effective_snapshot may commit its monotonic peak. Recheck under the lock.
    c=store.lock_account();old=c.execute('SELECT * FROM dnb_demo_submission_intents WHERE command_id=?',(body['command_id'],)).fetchone()
    if old:
        if old['payload']!=canonical:raise risk.Reject('demo_intent_conflict')
        c.commit();return {'ok':True,'state':'INTENT','idempotent':True}
    dnb_alerts.require_reconciled(p['symbol'])
    row=c.execute('SELECT * FROM dnb_demo_strategy_commands WHERE id=?',(body['command_id'],)).fetchone()
    if row['state']!='QUEUED' or row['expires_at']<=now:raise risk.Reject('demo_submission_unavailable')
    c.execute('INSERT INTO dnb_demo_submission_intents VALUES (?,?,?)',(body['command_id'],now,canonical))
    c.execute("UPDATE dnb_demo_strategy_commands SET state='INTENT' WHERE id=?",(body['command_id'],));c.commit()
    return {'ok':True,'state':'INTENT'}

def acknowledge(body,now):
    risk.keys(body,{'command_id','login','server','status','order_ticket','deal_ticket','volume','risk_usd','detail'})
    if body['login']!=dnb_demo.DEMO_LOGIN or body['server']!=dnb_demo.DEMO_SERVER:raise risk.Reject('demo_binding')
    allowed={'REJECTED','UNRESOLVED','ACCEPTED','PLACED','PARTIAL','RECOVERED'}
    if body['status'] not in allowed:raise risk.Reject('demo_ack_status')
    dnb_history.ticket(body['order_ticket'],zero=True);dnb_history.ticket(body['deal_ticket'],zero=True)
    if not isinstance(body['detail'],str) or not 1<=len(body['detail'])<=64 or any(ch not in 'abcdefghijklmnopqrstuvwxyz_0123456789' for ch in body['detail']):raise risk.Reject('demo_ack_detail')
    if risk.number(body['volume'])<0 or risk.number(body['risk_usd'])<0:raise risk.Reject('demo_ack_risk')
    c=store.lock_account();row=c.execute('SELECT * FROM dnb_demo_strategy_commands WHERE id=?',(body['command_id'],)).fetchone()
    if not row:raise risk.Reject('unknown_demo_command')
    p=json.loads(row['payload']);canonical=encode(body)
    if row['ack']==canonical:return {'ok':True,'idempotent':True,'state':row['state']}
    if row['ack']:
        previous=json.loads(row['ack'])
        if body['status']!='RECOVERED' or previous['status'] not in {'UNRESOLVED','ACCEPTED','PLACED','PARTIAL'}:raise risk.Reject('demo_ack_conflict')
        if previous['order_ticket']!='0' and previous['order_ticket']!=body['order_ticket']:raise risk.Reject('demo_ack_conflict')
        if previous['deal_ticket']!='0' and previous['deal_ticket']!=body['deal_ticket']:
            deal=c.execute('SELECT payload FROM dnb_demo_broker_deals WHERE ticket=?',(body['deal_ticket'],)).fetchone()
            if not deal or json.loads(deal['payload'])['order_ticket']!=body['order_ticket']:raise risk.Reject('demo_ack_conflict')
    if body['status']!='REJECTED':
        intent=c.execute('SELECT * FROM dnb_demo_submission_intents WHERE command_id=?',(body['command_id'],)).fetchone()
        if not intent:raise risk.Reject('demo_intent_required')
        if risk.number(body['volume'])>risk.number(p['quote']['volume']) or risk.number(body['risk_usd'])>risk.number(p['quote']['risk_usd']):raise risk.Reject('demo_ack_risk')
    event_id=hashlib.sha256(canonical.encode()).hexdigest()
    c.execute('INSERT OR IGNORE INTO dnb_demo_execution_events VALUES (?,?,?,?)',(event_id,body['command_id'],now,canonical))
    confirmed=any('position_ids' in json.loads(r['payload']) for r in c.execute('SELECT payload FROM dnb_demo_execution_events WHERE command_id=?',(body['command_id'],)))
    state=row['state'] if confirmed else body['status']
    c.execute('UPDATE dnb_demo_strategy_commands SET state=?,ack=? WHERE id=?',(state,canonical,body['command_id']));c.commit()
    # A receipt is not authoritative broker placement; history reconciliation
    # must confirm the exact command identity before announcing an actual trade.
    return {'ok':True,'state':state,'broker_history_confirmation_required':not confirmed}

def reconcile(now):
    """Bind exact broker entry identity; exits follow its position ID, not prices."""
    import dnb_lifecycle
    import dnb_notifications
    snap=dnb_demo.latest(now);capture=dnb_history.latest(demo=True)
    if not snap or not snap['fresh'] or not capture or not 0<=now-capture['captured_at']<=60:return []
    c=store.lock_account()
    orders=[json.loads(r['payload']) for r in c.execute('SELECT payload FROM dnb_demo_broker_orders')]
    deals=[json.loads(r['payload']) for r in c.execute('SELECT payload FROM dnb_demo_broker_deals')]
    rows=list(c.execute("SELECT * FROM dnb_demo_strategy_commands WHERE state NOT IN ('REJECTED','EXPIRED')"))
    notices=[]
    for row in rows:
        if not c.execute('SELECT command_id FROM dnb_demo_submission_intents WHERE command_id=?',(row['id'],)).fetchone():continue
        p=json.loads(row['payload']);magic=int(hashlib.sha256(('dnb:'+row['id']).encode()).hexdigest()[:15],16)
        roots=[o for o in orders if o['magic']==magic and o['comment']=='dnb:'+row['id'][:24] and o['symbol']==p['symbol'][:-2]]
        if not roots:
            # Working pending orders are not yet in MT5's historical-order list.
            # Snapshot identity can root them, but never imply an entry fill.
            for pending_order in snap['payload']['orders']:
                if pending_order.get('magic')==magic and pending_order.get('comment')=='dnb:'+row['id'][:24] and pending_order['symbol']==p['symbol']:
                    roots.append({'ticket':pending_order['ticket'],'position_id':'0',
                                  'volume_initial':pending_order['volume'],'state':1})
        if len(roots)!=1:continue # Missing or ambiguous identity never frees a reservation.
        projected=dnb_lifecycle.project(roots[0],deals,snap['payload']['positions'],snap['payload']['orders'])
        # Store only actual broker states. A late transport receipt cannot turn
        # a closed broker lifecycle back into an accepted/open command.
        actual=[x for x in snap['payload']['positions'] if x.get('identifier',x['ticket']) in projected['position_ids']]
        pending=[x for x in snap['payload']['orders'] if x['ticket']==roots[0]['ticket']]
        protection=[{k:x.get(k) for k in ('ticket','identifier','sl','tp','volume','entry','expires_at','order_type','stop_limit')} for x in actual+pending]
        key=hashlib.sha256(encode({'command_id':row['id'],'broker':projected,'protection':protection}).encode()).hexdigest()
        prior=c.execute('SELECT id FROM dnb_demo_execution_events WHERE id=?',(key,)).fetchone()
        if prior:continue
        exposure={**snap['payload'],'positions':actual,'orders':pending}
        try:thesis_risk=float(risk.portfolio_risk(exposure,now))+12*sum(float(x['volume']) for x in actual+pending)
        except risk.Reject:thesis_risk=None
        # Unknown downside needs an explicit incident, not a fabricated zero.
        if thesis_risk is None:continue
        payload={'purpose':'DEMO AUTO','command_id':row['id'],'source':p['source'],'symbol':p['symbol'],
                 'side':'BUY' if p['order_type'].startswith('BUY') else 'SELL','entry':p['entry'],'sl':p['sl'],'tp':p['tp'],
                 'risk_pct':p['risk_pct'],'thesis_id':p['thesis_id'],'scale_in_number':p.get('scale_in_number',0),'plan':p['quote'],
                 'thesis_volume':sum(float(x['volume']) for x in actual+pending),'thesis_risk_usd':thesis_risk,'broker':projected,
                 'current_protection':protection}
        c.execute('INSERT INTO dnb_demo_execution_events VALUES (?,?,?,?)',(key,row['id'],now,encode(projected)))
        c.execute('UPDATE dnb_demo_strategy_commands SET state=? WHERE id=?',(projected['state'],row['id']))
        # prepare() commits the event, lifecycle and notification in this same
        # connection/transaction; a crash cannot strand a confirmed fill without
        # a corresponding durable notification intent.
        dnb_notifications.prepare(key,payload,now)
        notices.append(key);c=store.lock_account()
    c.commit()
    return notices

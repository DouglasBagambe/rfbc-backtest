"""Durable broker-confirmed notification outbox; ambiguous delivery is retained."""
import json
import mt5_store as store

SCHEMA=('CREATE TABLE IF NOT EXISTS dnb_broker_notifications (id TEXT PRIMARY KEY, created_at INTEGER NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL, delivery TEXT)',)

def prepare(identifier,payload,now):
    canonical=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False)
    c=store.lock_account();row=c.execute('SELECT * FROM dnb_broker_notifications WHERE id=?',(identifier,)).fetchone()
    if row:
        # A lifecycle event identifies a specific revision, never a mutable scan.
        if row['payload']!=canonical:raise ValueError('notification_identity_conflict')
        return dict(row)
    c.execute('INSERT INTO dnb_broker_notifications VALUES (?,?,?,?,?)',(identifier,now,'PREPARED',canonical,None));c.commit()
    return {'id':identifier,'state':'PREPARED','payload':canonical}

def format_message(payload):
    p=json.loads(payload);q=p['plan'];actual=p['broker']
    return '\n'.join([f"dnb Fx • {p['purpose']} • broker {actual['state']}",
        f"{p['source']} • {p['symbol']} • {p['side']}",
        f"Entry {p['entry']} • SL {p['sl']} • TP {p['tp']}",
        'Current broker protection: '+json.dumps(p.get('current_protection',[]),separators=(',',':')),
        f"Lots planned {q['volume']} • entry filled {actual['filled_volume']} • broker position {actual['remaining_volume']}",
        f"Planned maximum risk ${q['risk_usd']:.2f} • risk input {p['risk_pct']}%",
        f"Thesis {p['thesis_id']} • add-on {p['scale_in_number']}",
        f"Thesis exposure {p['thesis_volume']} lots • current downside ${p['thesis_risk_usd']:.2f}",
        f"Command {p['command_id']} • order {actual['order_ticket']} • deals {','.join(actual['deal_tickets']) or 'none'}",
        f"Realised net ${actual['realised_net_usd']:.2f}",
        'DEMO account only. This broker notification is not a GOAT entry instruction.' if p['purpose']=='DEMO AUTO' else 'Broker-confirmed lifecycle update.'])

def dispatch(identifier,sender):
    c=store.lock_account();row=c.execute('SELECT * FROM dnb_broker_notifications WHERE id=?',(identifier,)).fetchone()
    if not row:return 'UNKNOWN'
    if row['state']!='PREPARED':return row['state']
    c.execute("UPDATE dnb_broker_notifications SET state='SENDING' WHERE id=?",(identifier,));c.commit()
    try:
        ok,_=sender(format_message(row['payload']))
    except Exception:ok=False
    state='SENT' if ok else 'DELIVERY_UNKNOWN'
    c=store.lock_account();c.execute('UPDATE dnb_broker_notifications SET state=?,delivery=? WHERE id=?',(state,'confirmed' if ok else 'not_confirmed',identifier));c.commit()
    return state

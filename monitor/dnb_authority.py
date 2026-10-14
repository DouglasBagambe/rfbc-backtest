"""Persisted evidence gates. No historical anchor is seeded from a snapshot."""
import json
import re
import mt5_risk as risk
import mt5_store as store

SCHEMA=('CREATE TABLE IF NOT EXISTS dnb_authority (id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at INTEGER NOT NULL)',)
GATES={'compliance','native_broker_validation','telegram','producers','news','infrastructure','controlled_live_authorisation'}
FIELDS={'login','server','daily_anchor','historical_peak','payout_cycle','daily_reset_utc','valid_until','payout_eligible_utc','payout_pending','gates','evidence'}

def validate(record,now):
    risk.keys(record,FIELDS)
    if record['login']!=risk.LOGIN or record['server']!=risk.SERVER:raise risk.Reject('account_binding')
    risk.positive(record['daily_anchor']);risk.positive(record['historical_peak'])
    for key in ('daily_reset_utc','valid_until','payout_eligible_utc'):
        if type(record[key]) is not int or record[key]<0:raise risk.Reject('invalid_authority_time')
    if not record['daily_reset_utc']<=now<record['valid_until'] or record['valid_until']>record['daily_reset_utc']+86400:raise risk.Reject('expired_daily_anchor')
    if not isinstance(record['payout_cycle'],str) or not re.fullmatch('[a-zA-Z0-9_-]{1,64}',record['payout_cycle']):raise risk.Reject('invalid_payout_cycle')
    if type(record['payout_pending']) is not bool:raise risk.Reject('invalid_authority_flag')
    risk.keys(record['gates'],GATES)
    if any(type(v) is not bool for v in record['gates'].values()):raise risk.Reject('invalid_authority_flag')
    if not isinstance(record['evidence'],dict):raise risk.Reject('authority_evidence_required')
    for key in GATES|{'anchors','reset_timezone','payout_reset'}:
        value=record['evidence'].get(key)
        if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value):raise risk.Reject('authority_evidence_required')
    return record

def latest(now):
    row=store.db().execute('SELECT * FROM dnb_authority ORDER BY created_at DESC LIMIT 1').fetchone()
    if not row:return None
    record=json.loads(row['payload'])
    try:validate(record,now)
    except risk.Reject:return None
    return {'id':row['id'],**record}

def blockers(now):
    record=latest(now)
    if not record:return ['verified_account_anchors_and_authority_missing']
    missing=[key for key,value in record['gates'].items() if not value]
    if record['payout_pending']:missing.append('payout_pending')
    return missing

# Deliberately no bridge HTTP endpoint installs approvals or anchor evidence.
# This must be an operator-reviewed migration with the actual dashboard/support
# evidence; an EA or analysis producer cannot self-certify these facts.

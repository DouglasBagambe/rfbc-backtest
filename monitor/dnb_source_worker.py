"""Permanent analysis consumer. Trading execution is a separate gated consumer."""
import json
import os
import subprocess
import sys
import threading
import time
import requests
from datetime import datetime, timezone
import dnb_sources
import dnb_alerts
import mt5_store
import mt5_bridge
import fx101

def scan_rfbc(equity):
    # Isolate the frozen module's environment input from concurrent requests.
    # Inferred market-price management events are never broker acknowledgements.
    env = {**os.environ, 'RFBC_EQUITY_USD':str(equity), 'FX101_MT5_BRIDGE_ENABLED':'0',
           'FX101_LEGACY_OVERLAYS':'0'}
    script = "import json; from datetime import datetime,timezone; import rfbc_monitor_live as r; print(json.dumps(r.evaluate_all(datetime.now(timezone.utc)),default=lambda x:x.isoformat()))"
    result = subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True,timeout=120,check=True)
    if len(result.stdout) > 131072: raise ValueError('rfbc_output_size')
    return json.loads(result.stdout)

def dispatch_prepared():
    if os.getenv('DNB_MANUAL_ALERTS_ENABLED','0') != '1': return
    ids = [r['trade_id'] for r in mt5_store.db().execute("SELECT trade_id FROM dnb_alert_intents WHERE state='PREPARED' ORDER BY created_at LIMIT 10")]
    for identifier in ids: dnb_alerts.dispatch(identifier, fx101.telegram_send)

def offer_demo(decisions,now):
    import dnb_demo_execution
    if not dnb_demo_execution.enabled():return
    for decision in decisions:
        try:
            row=dnb_demo_execution.queue(decision,now)
            dnb_sources.health('DEMO_EXECUTION',now,row['state'],row['id'])
        except mt5_bridge.risk.Reject as exc:
            mt5_store.db().rollback()
            dnb_sources.health('DEMO_EXECUTION',now,'BLOCKED',str(exc))

def reconcile_demo(now):
    import dnb_demo_execution,dnb_notifications
    dnb_demo_execution.reconcile(now)
    if os.getenv('DNB_BROKER_NOTIFICATIONS_ENABLED','0')!='1':return
    ids=[r['id'] for r in mt5_store.db().execute("SELECT id FROM dnb_broker_notifications WHERE state='PREPARED' ORDER BY created_at LIMIT 10")]
    for identifier in ids:dnb_notifications.dispatch(identifier,fx101.telegram_send)

def cycle(now, *, rfbc=False):
    mt5_bridge._ensure_schema()
    try:
        gdesk=dnb_sources.ingest_gdesk(dnb_sources.fetch_gdesk(now), now)
    except Exception as exc:
        # Persist only controlled reason codes; transport errors may contain secrets.
        if isinstance(exc,mt5_bridge.risk.Reject):detail=str(exc)
        elif isinstance(exc,requests.HTTPError):detail='source_http_'+str(exc.response.status_code)
        elif isinstance(exc,requests.Timeout):detail='source_timeout'
        elif isinstance(exc,requests.exceptions.SSLError):detail='source_tls_failed'
        elif isinstance(exc,requests.RequestException):detail='source_network_failed'
        elif isinstance(exc,(ValueError,TypeError,KeyError)):detail='source_schema_invalid'
        else:detail='source_storage_or_consumer_failed'
        mt5_store.db().rollback()
        dnb_sources.health('G_DESK',now,'UNAVAILABLE',detail)
        gdesk=[]
    offer_demo(gdesk,int(time.time()))
    if rfbc:
        snap = mt5_bridge.latest_snapshot()
        # The demo account is observed separately; it never replaces funded risk
        # evidence. Its equity may be the input to a demo RFBC strategy scan.
        import dnb_demo
        demo = dnb_demo.latest(now)
        if demo and demo['fresh']: snap=demo
        if not snap or not snap['fresh']:
            dnb_sources.health('RFBC',now,'BLOCKED','fresh_account_equity_required')
        else:
            try:
                equity = min(snap['payload']['balance'],snap['payload']['equity'])
                rows = scan_rfbc(equity)
                decisions = dnb_sources.rfbc_decisions(rows, int(time.time()))
                frozen=dnb_sources.ingest_rfbc(decisions,int(time.time()))
                offer_demo(frozen,int(time.time()))
                summary = json.dumps([{'pair':r['pair'],'action':r['action'].get('kind')} for r in rows],sort_keys=True)
                dnb_sources.health('RFBC',int(time.time()),'TRADE' if decisions else 'NO_TRADE',summary)
            except Exception:
                mt5_store.db().rollback()
                dnb_sources.health('RFBC',int(time.time()),'UNAVAILABLE','frozen_scan_failed')
    dispatch_prepared()
    reconcile_demo(int(time.time()))

def start(app):
    if os.getenv('DNB_PRODUCERS_ENABLED','0') != '1': return None
    stop = threading.Event()
    def work():
        last_rfbc = 0
        while not stop.is_set():
            now = int(time.time())
            try:
                with app.app_context():
                    run_rfbc = os.getenv('DNB_RFBC_PRODUCER_ENABLED','0') == '1' and now-last_rfbc >= 60
                    cycle(now,rfbc=run_rfbc)
                    if run_rfbc: last_rfbc = now
            except Exception:
                # Database failure must not terminate the consumer permanently.
                fx101.log('dnb_source_cycle_failed')
            stop.wait(15)
    thread = threading.Thread(target=work,name='dnb-analysis-consumer',daemon=True)
    thread.start()
    return stop

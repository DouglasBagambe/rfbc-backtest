"""Durable hourly analysis reports; these messages never authorise a broker order."""
import json
from datetime import datetime, timezone
import mt5_store as store

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS dnb_gdesk_reports (id TEXT PRIMARY KEY, result TEXT NOT NULL, payload TEXT NOT NULL, created_at INTEGER NOT NULL, state TEXT NOT NULL)",
)

def prepare(identifier, result, message, now):
    from mt5_bridge import _ensure_schema
    _ensure_schema()
    text = "dnb Fx • " + result.replace("_", " ") + "\n" + str(message)[:1200]
    c = store.lock_account()
    c.execute("INSERT OR IGNORE INTO dnb_gdesk_reports VALUES (?,?,?,?,?)", (identifier, result, text, now, "PREPARED"))
    c.commit()

def dispatch(sender):
    import fx101
    rows = list(store.db().execute("SELECT * FROM dnb_gdesk_reports WHERE state<>'SENT' ORDER BY created_at LIMIT 10"))
    for row in rows:
        try:
            ok, status = sender(row["payload"])
        except Exception:
            ok, status = False, "transport_unconfirmed"
        fx101.log("dnb_hourly_report_delivery", decision_id=row["id"], result=row["result"], ok=ok, status=status)
        if ok:
            c = store.lock_account()
            c.execute("UPDATE dnb_gdesk_reports SET state='SENT' WHERE id=?", (row["id"],))
            c.commit()

def watchdog(now):
    import pandas as pd
    import g_desk_adapter
    instant = datetime.fromtimestamp(now, timezone.utc)
    if instant.minute < 40 or not g_desk_adapter._is_trading_hour("EURUSD", pd.Timestamp(instant)):
        return
    start = now // 3600 * 3600
    c = store.db()
    delivered = c.execute("SELECT 1 FROM dnb_gdesk_reports WHERE created_at>=? AND created_at<? AND state='SENT' LIMIT 1", (start, start+3600)).fetchone()
    if not delivered:
        delivered = c.execute("SELECT 1 FROM dnb_source_receipts r JOIN dnb_alert_intents a ON a.trade_id=r.id WHERE r.generated_at>=? AND r.generated_at<? AND a.state='SENT' LIMIT 1", (start, start+3600)).fetchone()
    if not delivered:
        prepare("GDESK-MISSED-"+instant.strftime("%Y-%m-%dT%H"), "SYSTEM_FAILURE",
                "The hourly analysis report has not been delivered. No executable decision is authorised; checking again automatically.", now)

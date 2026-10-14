"""Fixture-only remote state/recovery verification on the existing test branch.

Creates an isolated schema; no MT5 requests, broker orders, or Telegram I/O.
Run without arguments, then run with `recover` in a new process. The private
checkpoint preserves the schema identity for audit and repeat recovery.
"""
import json,os,sys,time,uuid
from pathlib import Path
from datetime import datetime,timezone
from flask import Flask
import psycopg
from psycopg import sql
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'monitor'))
url=(root/'bridge-private/dnb-test-database-url.txt').read_text().strip()
funded=(root/'bridge-private/dnb-database-url.txt').read_text().strip()
from psycopg.conninfo import conninfo_to_dict
assert conninfo_to_dict(url)['host'].replace('-pooler','') != conninfo_to_dict(funded)['host'].replace('-pooler','')
os.environ.update(DNB_DATABASE_URL=url,DNB_REQUIRE_DURABLE='1',FX101_MT5_BRIDGE_ENABLED='1',FX101_MT5_EXECUTION_MODE='SHADOW',FX101_MT5_KILL_SWITCH='1',DNB_DEMO_EXECUTION_ENABLED='1',DNB_DEMO_KILL_SWITCH='0',FX101_MT5_BRIDGE_TOKEN='a'*64)
import mt5_store as store,mt5_bridge as bridge,dnb_demo,dnb_history,dnb_sources,dnb_demo_execution as execution,dnb_alerts,dnb_manual,dnb_demo_reset
import test_mt5_bridge as fixture
checkpoint=root/'bridge-private/continuation-validation.json'
recover=len(sys.argv)>1 and sys.argv[1]=='recover'
schema=json.loads(checkpoint.read_text())['schema'] if recover else 'continuation_'+uuid.uuid4().hex
if not recover:
    with psycopg.connect(url,sslmode='verify-full',sslrootcert='/etc/ssl/certs/ca-certificates.crt') as admin:
        admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
base=store.Postgres
class Isolated(base):
    def __init__(self,url):
        super().__init__(url)
        self.connection.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(schema)))
    def execute(self,query,params=()):
        if self.connection.info.transaction_status==0:
            self.connection.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(schema)))
        return super().execute(query,params)
store.Postgres=Isolated
app=Flask(__name__);app.register_blueprint(bridge.bp);app.teardown_appcontext(store.close_request)
iso=lambda at:datetime.fromtimestamp(at,timezone.utc).isoformat()
now=int(time.time());bridge.clock=lambda:now
def snap(at,balance=2476.17,positions=None):
    s=fixture.snapshot();s.update(login=dnb_demo.DEMO_LOGIN,server=dnb_demo.DEMO_SERVER,captured_at=at,account_margin_mode=0,balance=balance,equity=balance,free_margin=balance,positions=positions or [])
    for v in s['symbols'].values():v['quote_at']=at
    dnb_demo.snapshot(s,at)
def history(at,orders=None,deals=None):
    cid=uuid.uuid4().hex
    for kind,items in [('orders',orders or []),('deals',deals or [])]:
        dnb_history.ingest(dict(capture_id=cid,login=dnb_demo.DEMO_LOGIN,server=dnb_demo.DEMO_SERVER,captured_at=at,from_server_time=0,to_server_time=at,kind=kind,page=0,pages=1,total=len(items),items=items),at,demo=True)
with app.app_context():
    bridge._ensure_schema()
    if recover:
        state=json.loads(checkpoint.read_text());c=store.db()
        assert c.execute('SELECT state FROM dnb_demo_strategy_commands WHERE id=?',(state['command_id'],)).fetchone()['state']=='INTENT'
        assert c.execute('SELECT command_id FROM dnb_demo_submission_intents WHERE command_id=?',(state['command_id'],)).fetchone()
        assert c.execute('SELECT state FROM dnb_alert_intents WHERE trade_id=?',('MANUAL-FIXTURE',)).fetchone()['state']=='MANUAL_CLOSED'
        assert c.execute('SELECT COUNT(*) AS n FROM dnb_demo_reset_proofs').fetchone()['n']==1
        print(json.dumps({'new_process_recovery':True,'remote_intent_preserved':True,'manual_binding_preserved':True,'daily_reset_proof_preserved':True,'broker_orders_sent':0,'fixture_data_only':True}))
    else:
        snap(now);history(now);epoch=execution.initialise_epoch(now)
        def proposal(identifier):
            return {'decision_id':identifier,'generated_at':iso(now),'result':'TRADE','decisions':[dict(source='G_DESK',symbol='EURUSD.x',side='BUY',entry=1.1002,stop=1.099,target=1.1022,risk_pct=.25,valid_until=iso(now+30),cancel_condition='fixture',context={'order_type':'BUY','machine_cancel':{'kind':'price_below','price':1.098}})],'context':dict(market_state='MARKET_OPEN',freshness='FRESH',symbols_received=18,symbols_reported=18,validation_errors=[],source_generated_at=iso(now),latest_completed_bar=iso((now//3600-1)*3600))}
        decision=dnb_sources.ingest_gdesk(proposal('REMOTE-EXECUTION-FIXTURE'),now)[0];row=execution.queue(decision,now);p=json.loads(row['payload'])
        body=dict(command_id=row['id'],login=dnb_demo.DEMO_LOGIN,server=dnb_demo.DEMO_SERVER,fingerprint='a'*64,symbol=p['symbol'],order_type=p['order_type'],volume=p['quote']['volume'],entry=p['quote']['entry'],sl=p['sl'],tp=p['tp'])
        execution.submission_intent(body,now)
        assert execution.submission_intent(body,now)['idempotent']
        manual=dnb_sources.ingest_gdesk(proposal('MANUAL-FIXTURE'),now)[0]
        assert dnb_alerts.dispatch(manual['trade_id'],lambda _:(True,'fixture'))=='SENT'
        order=dict(ticket='700',position_id='900',magic=0,comment='manual',symbol='EURUSD',type=0,state=4,reason=0,volume_initial=.01,volume_current=0,price=1.1002,sl=1.099,tp=1.1022,stop_limit=0,created_at=now,done_at=now,expires_at=0)
        deal=dict(ticket='800',order_ticket='700',position_id='900',magic=0,comment='manual',symbol='EURUSD',type=0,entry=0,reason=0,volume=.01,price=1.1002,profit=0,commission=-.07,swap=0,fee=0,time=now)
        history(now,[order],[deal,{**deal,'ticket':'801','order_ticket':'701','entry':1,'profit':2}])
        result=dnb_manual.bind(dict(trade_id='MANUAL-FIXTURE',account_kind='DEMO',order_ticket='700'),now)
        assert result['state']=='MANUAL_CLOSED'
        boundary=epoch['payload']['valid_until'];snap(boundary-5);snap(boundary+5);history(boundary+5)
        updated=execution.epoch(boundary+5)[1];assert updated['valid_until']==boundary+86400
        checkpoint.write_text(json.dumps(dict(schema=schema,command_id=row['id'])))
        print(json.dumps({'real_postgres':True,'isolated_test_branch_and_schema':True,'intent_idempotency':True,'explicit_manual_binding':True,'evidence_bound_daily_reset':True,'broker_orders_sent':0,'fixture_data_only':True}))

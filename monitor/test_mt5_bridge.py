"""Deterministic SHADOW safety tests; no simulated test is broker execution proof."""
import copy
import importlib
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from flask import Flask
import mt5_risk as risk
from mt5_symbols import BROKER_SYMBOLS

NOW = 1791986400

def spec():
    return {'tick_size':0.00001,'tick_value_loss':1,'tick_value_profit':1,'contract_size':100000,
            'volume_min':0.01,'volume_max':100,'volume_step':0.01,'stops_level':10,'freeze_level':0,
            'trade_mode':4,'order_mode':127,'bid':1.1001,'ask':1.1002,'point':0.00001,'quote_at':NOW,
            'margin_buy':2200,'margin_sell':2200}

def snapshot():
    return {'login':315307814,'server':'GoatFunded-Server','currency':'USD','captured_at':NOW,
            'balance':2476.17,'equity':2476.17,'free_margin':2476.17,'margin':0,'floating_pnl':0,
            'terminal_connected':True,'positions':[],'orders':[],'symbols':{'EURUSD.x':spec(),'GBPUSD.x':spec()},
            'daily_anchor':2500,'high_water_equity':2500,'anchors_verified':True,'day_key':'2026-10-14'}

def command():
    return {'command_id':'a'*32,'login':315307814,'server':'GoatFunded-Server','created_at':NOW,'expires_at':NOW+30,
            'symbol':'EURUSD.x','order_type':'BUY','entry':1.1002,'sl':1.099,'tp':1.1022,'risk_pct':0.25,
            'stop_limit':0,'cancel':{'kind':'price_below','price':1.098}}

def item(symbol='GBPUSD.x',side='BUY',volume=0.01,sl=1.099):
    return {'ticket':'12345','symbol':symbol,'side':side,'order_type':side,'volume':volume,'entry':1.1002,
            'sl':sl,'tp':1.1022,'profit':0,'swap':0,'magic':0,'comment':'manual','stop_limit':0,'expires_at':0}

class RiskTests(unittest.TestCase):
    def setUp(self): self.s=snapshot(); self.c=command()
    def rejected(self, reason):
        with self.assertRaisesRegex(risk.Reject,'^'+reason+'$'): risk.plan(self.s,self.c,NOW)
    def test_clean_order_rounds_down(self):
        p=risk.plan(self.s,self.c,NOW); self.assertEqual(p['volume'],0.04); self.assertEqual(p['risk_usd'],5.0); self.assertFalse(p['auto_authorised'])
    def test_eighteen_symbol_universe(self):
        self.assertEqual(len(BROKER_SYMBOLS),18); self.assertIn('XAUUSD.x',BROKER_SYMBOLS); self.assertIn('GBPCAD.x',BROKER_SYMBOLS)
    def test_wrong_account(self): self.s['login']=1; self.rejected('wrong_account')
    def test_wrong_server(self): self.s['server']='Exness'; self.rejected('wrong_server')
    def test_wrong_command_account(self): self.c['login']=1; self.rejected('wrong_account')
    def test_wrong_command_server(self): self.c['server']='other'; self.rejected('wrong_server')
    def test_stale_snapshot(self): self.s['captured_at']=NOW-16; self.rejected('stale_snapshot')
    def test_future_snapshot(self): self.s['captured_at']=NOW+1; self.rejected('stale_snapshot')
    def test_stale_command(self): self.c['expires_at']=NOW; self.rejected('stale_command')
    def test_future_command(self): self.c['created_at']=NOW+1; self.rejected('stale_command')
    def test_oversized_ttl(self): self.c['expires_at']=NOW+31; self.rejected('stale_command')
    def test_duplicate_symbol(self): self.s['positions']=[item('EURUSD.x')]; self.rejected('duplicate_symbol')
    def test_opposite_position(self): self.s['positions']=[item('EURUSD.x','SELL')]; self.rejected('hedging')
    def test_manual_position_counts(self):
        self.s['positions']=[item(volume=.1)]; p=risk.plan(self.s,self.c,NOW); self.assertEqual(p['existing_risk_usd'],11); self.assertEqual(p['volume'],.03)
    def test_manual_pending_counts(self):
        pending=item(volume=.1); pending['order_type']='BUY_LIMIT'; self.s['orders']=[pending]
        p=risk.plan(self.s,self.c,NOW); self.assertEqual(p['existing_risk_usd'],12); self.assertEqual(p['volume'],.02)
    def test_no_sl_position(self): self.s['positions']=[item(sl=0)]; self.rejected('existing_exposure_without_sl')
    def test_no_sl_pending(self): self.s['orders']=[item(sl=0)]; self.rejected('existing_exposure_without_sl')
    def loss(self, amount):
        self.s.update(equity=2476.17-amount,free_margin=2476.17-amount,floating_pnl=-amount)
    def test_floating_loss(self): self.loss(18); self.rejected('floating_loss')
    def test_daily_drawdown(self): self.s['daily_anchor']=2600; self.rejected('daily_drawdown')
    def test_trailing_drawdown_uncapped(self): self.s['high_water_equity']=2700; self.rejected('trailing_drawdown')
    def test_per_trade_risk(self): self.c['risk_pct']=.26; self.rejected('per_trade_risk')
    def test_aggregate_risk(self): self.s['positions']=[item(volume=.2)]; self.rejected('aggregate_risk')
    def test_minimum_lot(self): self.c['risk_pct']=.001; self.rejected('lot_minimum')
    def test_arbitrary_lot_step_rounds_down(self):
        self.s['symbols']['EURUSD.x'].update(volume_min=.025,volume_step=.025)
        self.assertEqual(risk.plan(self.s,self.c,NOW)['volume'],.025)
    def test_margin(self): self.s['symbols']['EURUSD.x']['margin_buy']=100000; self.rejected('margin')
    def test_stop_level(self): self.s['symbols']['EURUSD.x']['stops_level']=200; self.rejected('stop_freeze_level')
    def test_freeze_level(self): self.s['symbols']['EURUSD.x']['freeze_level']=200; self.rejected('stop_freeze_level')
    def test_spread(self): self.s['symbols']['EURUSD.x']['ask']=1.101; self.rejected('spread')
    def test_stale_quote(self): self.s['symbols']['EURUSD.x']['quote_at']=NOW-11; self.rejected('stale_quote')
    def test_tick_value_missing(self): self.s['symbols']['EURUSD.x']['tick_value_loss']=0; self.rejected('nonpositive_number')
    def test_nonfinite(self): self.s['equity']=float('nan'); self.rejected('nonfinite_number')
    def test_unverified_anchors(self): self.s['anchors_verified']=False; self.rejected('historical_anchors_unverified')
    def test_disconnected_terminal(self): self.s['terminal_connected']=False; self.rejected('terminal_disconnected')
    def test_close_only_symbol(self): self.s['symbols']['EURUSD.x']['trade_mode']=3; self.rejected('symbol_trade_mode')
    def test_legacy_symbol_rejected_at_execution(self): self.c['symbol']='EURUSDc'; self.rejected('symbol_unavailable')
    def test_unsupported_order(self): self.c['order_type']='CLOSE'; self.rejected('order_type')
    def test_inverted_stop(self): self.c['sl']=1.101; self.rejected('sltp_geometry')
    def test_unbounded_cancellation(self): self.c['cancel']={'kind':'structure_invalid','price':1}; self.rejected('unmeasurable_cancellation')
    def test_cancellation_met(self): self.c['cancel']['price']=1.101; self.rejected('cancel_condition_met')
    def test_price_tick_alignment(self): self.c['sl']=1.099001; self.rejected('tick_alignment')
    def test_stop_limit_geometry(self):
        self.c.update(order_type='BUY_STOP_LIMIT',entry=1.101,stop_limit=1.102); self.rejected('stop_limit_geometry')
    def test_all_eight_order_plans(self):
        for order in sorted(risk.ORDER_TYPES):
            with self.subTest(order=order):
                c=command(); c['order_type']=order
                buy=order.startswith('BUY'); c['cancel']={'kind':'price_below' if buy else 'price_above','price':1.08 if buy else 1.12}
                c['sl']=1.09 if buy else 1.11; c['tp']=1.11 if buy else 1.09
                c['entry']=1.1002 if buy else 1.1001
                if order.endswith('LIMIT') and not order.endswith('STOP_LIMIT'): c['entry']=1.099 if buy else 1.101
                if 'STOP' in order: c['entry']=1.101 if buy else 1.099
                if order.endswith('STOP_LIMIT'): c['stop_limit']=1.1009 if buy else 1.0991
                # Broader stops require extra risk budget to fit minimum lot.
                c['sl']=c['entry']-.002 if buy else c['entry']+.002
                c['tp']=c['entry']+.002 if buy else c['entry']-.002
                self.assertGreater(risk.plan(self.s,c,NOW)['volume'],0)

class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'FX101_DB_PATH':str(Path(self.tmp.name)/'bridge.sqlite3'),
            'FX101_MT5_BRIDGE_ENABLED':'1','FX101_MT5_EXECUTION_MODE':'SHADOW','FX101_MT5_KILL_SWITCH':'0',
            'FX101_MT5_BRIDGE_TOKEN':'b'*64},clear=True); self.env.start()
        import fx101,mt5_bridge
        self.fx=importlib.reload(fx101); self.b=importlib.reload(mt5_bridge)
        self.time=patch.object(self.b,'clock',return_value=NOW); self.time.start()
        self.app=Flask(__name__); self.app.register_blueprint(self.b.bp); self.client=self.app.test_client()
    def tearDown(self): self.fx.close_db(); self.time.stop(); self.env.stop(); self.tmp.cleanup()
    def headers(self,method,path,body,nonce=None,stamp=NOW):
        nonce=nonce or uuid.uuid4().hex+uuid.uuid4().hex
        return {'X-FX101-Time':str(stamp),'X-FX101-Nonce':nonce,
                'X-FX101-Signature':self.b.request_signature(method,path,str(stamp),nonce,body)}
    def send(self,path,body=None,method=None,headers=None,secure=True):
        method=method or ('POST' if body is not None else 'GET')
        raw=b'' if body is None else body if isinstance(body,bytes) else json.dumps(body,separators=(',',':')).encode()
        return self.client.open(path,method=method,data=raw,headers=headers or self.headers(method,path,raw),base_url='https://localhost' if secure else 'http://localhost')
    def ingest(self): self.assertEqual(self.send('/fx101/mt5/snapshot',snapshot()).status_code,200)
    def trade(self):
        c=command(); return {'trade_id':'SYNTHETIC','symbol':c['symbol'],'side':'BUY','entry':c['entry'],'stop':c['sl'],
            'target':c['tp'],'risk_pct':c['risk_pct'],'valid_until':'2026-10-14T14:30:00+00:00',
            'context':{'order_type':'BUY','machine_cancel':c['cancel']}}
    def queue(self): self.ingest(); return self.b._queue_command(self.trade(),synthetic=True)
    def test_snapshot_status_authoritative(self):
        self.ingest(); s=self.send('/fx101/mt5/status').json
        self.assertTrue(s['connected']); self.assertEqual(s['snapshot']['payload']['equity'],2476.17); self.assertFalse(s['snapshot']['payload']['anchors_verified'])
    def test_tls_only(self): self.assertEqual(self.send('/fx101/mt5/status',secure=False).status_code,403)
    def test_bad_signature(self):
        h=self.headers('GET','/fx101/mt5/status',b''); h['X-FX101-Signature']='0'*64
        self.assertEqual(self.send('/fx101/mt5/status',headers=h).status_code,401)
    def test_unsigned(self): self.assertEqual(self.client.get('/fx101/mt5/status',base_url='https://localhost').status_code,401)
    def test_stale_auth(self):
        h=self.headers('GET','/fx101/mt5/status',b'',stamp=NOW-16); self.assertEqual(self.send('/fx101/mt5/status',headers=h).status_code,401)
    def test_replayed_request(self):
        h=self.headers('GET','/fx101/mt5/status',b''); self.assertEqual(self.send('/fx101/mt5/status',headers=h).status_code,200)
        self.assertEqual(self.send('/fx101/mt5/status',headers=h).status_code,409)
    def test_replay_after_backend_restart(self):
        h=self.headers('GET','/fx101/mt5/status',b''); self.send('/fx101/mt5/status',headers=h); self.fx.close_db()
        self.assertEqual(self.send('/fx101/mt5/status',headers=h).status_code,409)
    def test_duplicate_json_key(self):
        self.assertEqual(self.send('/fx101/mt5/snapshot',b'{"login":315307814,"login":1}').status_code,400)
    def test_nonfinite_json(self):
        s=snapshot(); s['equity']=float('nan'); self.assertEqual(self.send('/fx101/mt5/snapshot',s).status_code,400)
    def test_oversized_request(self): self.assertEqual(self.send('/fx101/mt5/snapshot',b' '*131073).status_code,413)
    def test_unknown_snapshot_field(self):
        s=snapshot(); s['password']='synthetic_forbidden_field'; self.assertEqual(self.send('/fx101/mt5/snapshot',s).status_code,400)
    def test_wrong_snapshot_account(self):
        s=snapshot(); s['login']=1; self.assertEqual(self.send('/fx101/mt5/snapshot',s).status_code,400)
    def test_out_of_order_snapshot(self):
        self.ingest(); self.assertEqual(self.send('/fx101/mt5/snapshot',snapshot()).status_code,400)
    def test_durable_duplicate_command(self):
        first=self.queue(); self.fx.close_db(); second=self.b._queue_command(self.trade(),synthetic=True)
        self.assertEqual(first['id'],second['id'])
    def test_duplicate_command_changed_parameters_rejected(self):
        self.queue(); changed=self.trade(); changed['risk_pct']=.20
        with self.assertRaisesRegex(risk.Reject,'duplicate_command_conflict'): self.b._queue_command(changed,synthetic=True)
    def test_synthetic_endpoint_cannot_accept_signal(self):
        self.ingest(); self.assertEqual(self.send('/fx101/mt5/shadow-test',{'side':'BUY'}).status_code,400)
    def test_synthetic_endpoint_creates_shadow_only(self):
        self.ingest(); result=self.send('/fx101/mt5/shadow-test',b'').json
        self.assertTrue(result['ok']); self.assertTrue(result['synthetic']); self.assertFalse(result['auto_available'])
    def test_shadow_backend_does_not_start_workers(self):
        from mt5_shadow_app import app
        self.assertEqual(app.test_client().get('/health').json['auto_available'],False)
    def test_command_signature_and_request_binding(self):
        row=self.queue(); h=self.headers('GET','/fx101/mt5/command',b'')
        wire=self.send('/fx101/mt5/command',headers=h).text; parts=wire.split('|')
        self.assertEqual(len(parts),19); self.assertEqual(parts[1],h['X-FX101-Nonce']); self.assertEqual(parts[2],row['id'])
        self.assertEqual(parts[-1],self.b.sign('|'.join(parts[:-1]).encode()))
    def test_timeout_before_delivery_same_command(self):
        row=self.queue(); a=self.send('/fx101/mt5/command').text; b=self.send('/fx101/mt5/command').text
        self.assertEqual(a.split('|')[2],row['id']); self.assertEqual(b.split('|')[2],row['id'])
    def ack(self,row,status='SHADOW_OK'):
        return {'command_id':row['id'],'login':315307814,'server':'GoatFunded-Server','status':status,'volume':.04,'risk_usd':5,'detail':'synthetic_shadow_only'}
    def test_lost_ack_resubmission_and_restart(self):
        row=self.queue(); ack=self.ack(row)
        self.assertEqual(self.send('/fx101/mt5/ack',ack).status_code,200)
        self.fx.close_db()
        self.assertTrue(self.send('/fx101/mt5/ack',ack).json['idempotent'])
        self.assertEqual(self.send('/fx101/mt5/command').text,'NONE')
    def test_late_durable_shadow_ack_after_expiry(self):
        row=self.queue(); ack=self.ack(row)
        with patch.object(self.b,'clock',return_value=NOW+31):
            raw=json.dumps(ack,separators=(',',':')).encode()
            h=self.headers('POST','/fx101/mt5/ack',raw,stamp=NOW+31)
            self.assertEqual(self.send('/fx101/mt5/ack',raw,headers=h).status_code,200)
            state=self.fx.db().execute('SELECT state FROM mt5_v2_commands WHERE id=?',(row['id'],)).fetchone()[0]
            self.assertEqual(state,'SHADOW_OK')
    def test_conflicting_ack(self):
        row=self.queue(); self.send('/fx101/mt5/ack',self.ack(row)); ack=self.ack(row); ack['volume']=.05
        self.assertEqual(self.send('/fx101/mt5/ack',ack).status_code,400)
    def test_executed_ack_prohibited(self):
        row=self.queue(); self.assertEqual(self.send('/fx101/mt5/ack',self.ack(row,'EXECUTED')).status_code,400)
    def test_server_auto_local_shadow_no_command(self):
        self.queue(); os.environ['FX101_MT5_EXECUTION_MODE']='AUTO'; self.assertEqual(self.send('/fx101/mt5/command').text,'NONE')
    def test_local_auto_has_no_broker_operations(self):
        source=(Path(__file__).parents[1]/'mt5/Fx101GoatBridge.mq5').read_text()
        self.assertIn('InpMode==MODE_AUTO',source); self.assertNotIn('OrderSend(',source); self.assertNotIn('Trade.Buy(',source)
    def test_server_kill(self):
        self.queue(); os.environ['FX101_MT5_KILL_SWITCH']='1'; self.assertEqual(self.send('/fx101/mt5/command').text,'NONE')
    def test_observe_no_command(self):
        self.queue(); os.environ['FX101_MT5_EXECUTION_MODE']='OBSERVE'; self.assertEqual(self.send('/fx101/mt5/command').text,'NONE')
    def test_expired_command_not_delivered(self):
        self.queue()
        with patch.object(self.b,'clock',return_value=NOW+31):
            h=self.headers('GET','/fx101/mt5/command',b'',stamp=NOW+31)
            self.assertEqual(self.send('/fx101/mt5/command',headers=h).text,'NONE')
    def test_reconciliation_records_manual_changes(self):
        self.ingest(); s=snapshot(); s['captured_at']+=1; s['positions']=[item()]
        self.assertEqual(self.send('/fx101/mt5/snapshot',s).status_code,400) # Future-dated broker snapshot rejected.
        with patch.object(self.b,'clock',return_value=NOW+1): self.assertEqual(self.send('/fx101/mt5/snapshot',s).status_code,200)
        row=self.fx.db().execute('SELECT payload FROM mt5_v2_reconciliation ORDER BY created_at DESC LIMIT 1').fetchone()
        self.assertEqual(json.loads(row['payload'])['added'],['12345'])
    def test_no_legacy_queue_execution(self):
        self.ingest(); self.assertEqual(self.send('/fx101/mt5/command').text,'NONE')
    def test_history_cannot_be_client_verified(self):
        self.ingest(); self.assertEqual(self.b.preflight_decision(self.trade()),['historical_anchors_unverified'])
    def test_rate_limit(self):
        for _ in range(90): self.assertEqual(self.send('/fx101/mt5/status').status_code,200)
        self.assertEqual(self.send('/fx101/mt5/status').status_code,429)

if __name__=='__main__': unittest.main()

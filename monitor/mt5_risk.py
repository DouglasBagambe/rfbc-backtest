"""Deterministic SHADOW planning; never authorises broker operations.

Broker metadata is mandatory. An observed peak is not proof of historical peak.
Historical rule anchors remain an explicit validation gate, including after outages.
"""
from __future__ import annotations
from decimal import Decimal, ROUND_FLOOR
import re

LOGIN = 315307814
SERVER = 'GoatFunded-Server'
from mt5_symbols import BROKER_SYMBOLS
SYMBOLS = BROKER_SYMBOLS
ORDER_TYPES = {'BUY','SELL','BUY_LIMIT','SELL_LIMIT','BUY_STOP','SELL_STOP','BUY_STOP_LIMIT','SELL_STOP_LIMIT'}
PER_TRADE = Decimal('0.25')
AGGREGATE = Decimal('0.60')
FLOATING = Decimal('0.70')
DAILY = Decimal('2.50')
TRAILING = Decimal('4.50')
DIRECTIONAL = Decimal('0.40')
METAL = Decimal('0.25')
MAX_SPREAD_TICKS = Decimal('30')

class Reject(ValueError):
    pass

def number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int, str, Decimal)):
        raise Reject('invalid_number')
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise Reject('invalid_number') from exc
    if not result.is_finite():
        raise Reject('nonfinite_number')
    return result

def positive(value):
    result = number(value)
    if result <= 0:
        raise Reject('nonpositive_number')
    return result

def keys(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise Reject('invalid_schema')

def symbol_spec(spec):
    required = {'tick_size','tick_value_loss','tick_value_profit','contract_size','volume_min','volume_max','volume_step',
                'stops_level','freeze_level','trade_mode','order_mode','bid','ask','point','quote_at','margin_buy','margin_sell'}
    keys(spec, required)
    for key in required - {'stops_level','freeze_level','trade_mode','order_mode','quote_at'}:
        positive(spec[key])
    for key in {'stops_level','freeze_level','trade_mode','order_mode','quote_at'}:
        if type(spec[key]) is not int or spec[key] < 0:
            raise Reject('invalid_symbol_spec')
    if number(spec['ask']) < number(spec['bid']) or number(spec['volume_max']) < number(spec['volume_min']):
        raise Reject('invalid_symbol_spec')

def validate_snapshot(s, now):
    required = {'login','server','currency','captured_at','balance','equity','free_margin','margin','floating_pnl',
                'terminal_connected','positions','orders','symbols','daily_anchor','high_water_equity','anchors_verified','day_key'}
    keys(s, required)
    if type(s['login']) is not int or s['login'] != LOGIN:
        raise Reject('wrong_account')
    if s['server'] != SERVER:
        raise Reject('wrong_server')
    if s['currency'] != 'USD':
        raise Reject('account_currency')
    if type(s['captured_at']) is not int or not 0 <= now - s['captured_at'] <= 15:
        raise Reject('stale_snapshot')
    if type(s['terminal_connected']) is not bool or type(s['anchors_verified']) is not bool:
        raise Reject('invalid_schema')
    for key in ('balance','equity','daily_anchor','high_water_equity'):
        positive(s[key])
    for key in ('free_margin','margin','floating_pnl'):
        number(s[key])
    if number(s['margin']) < 0 or not isinstance(s['day_key'], str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',s['day_key']):
        raise Reject('invalid_schema')
    if abs(number(s['equity']) - number(s['balance']) - number(s['floating_pnl'])) > Decimal('1'):
        raise Reject('inconsistent_equity')
    if abs(number(s['equity']) - number(s['margin']) - number(s['free_margin'])) > Decimal('1'):
        raise Reject('inconsistent_margin')
    if not isinstance(s['symbols'],dict) or len(s['symbols']) > 128:
        raise Reject('invalid_symbols')
    for symbol, spec in s['symbols'].items():
        if not re.fullmatch(r'[A-Za-z0-9_.]{1,32}',symbol):
            raise Reject('invalid_symbol')
        symbol_spec(spec)
    tickets = set()
    for kind in ('positions','orders'):
        if not isinstance(s[kind],list) or len(s[kind]) > 128:
            raise Reject('invalid_items')
        for item in s[kind]:
            keys(item, {'ticket','symbol','side','order_type','volume','entry','sl','tp','profit','swap','magic','comment','stop_limit','expires_at'})
            if not isinstance(item['ticket'],str) or not re.fullmatch(r'[1-9][0-9]{0,19}',item['ticket']) or item['ticket'] in tickets:
                raise Reject('invalid_ticket')
            tickets.add(item['ticket'])
            if item['symbol'] not in s['symbols'] or item['side'] not in {'BUY','SELL'} or item['order_type'] not in ORDER_TYPES:
                raise Reject('invalid_item')
            if not item['order_type'].startswith(item['side']):
                raise Reject('invalid_item')
            if type(item['magic']) is not int or type(item['expires_at']) is not int or not isinstance(item['comment'],str) or len(item['comment']) > 128:
                raise Reject('invalid_item')
            for key in ('volume','entry'):
                positive(item[key])
            for key in ('sl','tp','stop_limit'):
                if number(item[key]) < 0: raise Reject('invalid_item')
            for key in ('profit','swap'):
                number(item[key])

def risk_usd(spec, volume, entry, stop):
    return abs(positive(entry)-positive(stop))/positive(spec['tick_size'])*positive(spec['tick_value_loss'])*positive(volume)

def portfolio_risk(s, now=None):
    total = Decimal('0')
    for item in s['positions'] + s['orders']:
        if number(item['sl']) <= 0:
            raise Reject('existing_exposure_without_sl')
        spec = s['symbols'][item['symbol']]
        if now is not None and not 0 <= now-spec['quote_at'] <= 10:
            raise Reject('stale_exposure_quote')
        # From liquidation quote, so profitable positions cannot erase downside risk.
        entry = spec['bid'] if item['side']=='BUY' else spec['ask']
        if item in s['orders']:
            entry = item['stop_limit'] if item['order_type'].endswith('STOP_LIMIT') else item['entry']
        if number(entry) <= 0: raise Reject('invalid_exposure_entry')
        distance = (number(entry)-number(item['sl'])) if item['side']=='BUY' else (number(item['sl'])-number(entry))
        if distance <= 0: raise Reject('exposure_stop_breached')
        total += distance/positive(spec['tick_size'])*positive(spec['tick_value_loss'])*positive(item['volume'])
    return total

def directional_legs(symbol, side):
    if symbol not in SYMBOLS: raise Reject('unsupported_exposure_symbol')
    sign = 1 if side == 'BUY' else -1
    return ((symbol[:3], sign), (symbol[3:6], -sign))

def exposure_budgets(s, symbol, side, basis, now):
    directed = {}; metal = Decimal(0)
    for item in s['positions'] + s['orders']:
        usd = portfolio_risk({**s,'positions':[item],'orders':[]} if item in s['positions']
                             else {**s,'positions':[],'orders':[item]}, now)
        for leg in directional_legs(item['symbol'],item['side']):
            directed[leg] = directed.get(leg,Decimal(0)) + usd
        if item['symbol'] == 'XAUUSD.x': metal += usd
    remaining = min(basis*DIRECTIONAL/100-directed.get(leg,Decimal(0))
                    for leg in directional_legs(symbol,side))
    if remaining <= 0: raise Reject('directional_currency_risk')
    if symbol == 'XAUUSD.x': remaining = min(remaining,basis*METAL/100-metal)
    if remaining <= 0: raise Reject('metal_risk')
    return remaining

def plan(s, command, now, *, require_anchors=True, scale_in_tickets=frozenset()):
    validate_snapshot(s, now)
    required = {'command_id','login','server','created_at','expires_at','symbol','order_type','entry','sl','tp','risk_pct','stop_limit','cancel'}
    keys(command, required)
    if not re.fullmatch(r'[a-f0-9]{32}',str(command['command_id'])):
        raise Reject('invalid_command_id')
    if command['login'] != LOGIN: raise Reject('wrong_account')
    if command['server'] != SERVER: raise Reject('wrong_server')
    if type(command['created_at']) is not int or type(command['expires_at']) is not int or not 0 <= now-command['created_at'] <= 30 or not now < command['expires_at'] <= command['created_at']+30:
        raise Reject('stale_command')
    if not s['terminal_connected']: raise Reject('terminal_disconnected')
    if require_anchors and not s['anchors_verified']: raise Reject('historical_anchors_unverified')
    balance, equity = positive(s['balance']), positive(s['equity'])
    basis = min(balance,equity)
    if number(s['floating_pnl']) <= -balance*FLOATING/100: raise Reject('floating_loss')
    if equity <= positive(s['daily_anchor'])*(1-DAILY/100): raise Reject('daily_drawdown')
    from dnb_policy import conservative_trailing_floor
    trailing = conservative_trailing_floor(s['high_water_equity'])
    if min(balance,equity) <= trailing: raise Reject('trailing_drawdown')
    requested = positive(command['risk_pct'])
    if requested > PER_TRADE: raise Reject('per_trade_risk')
    symbol, order_type = command['symbol'], command['order_type']
    if symbol not in SYMBOLS or symbol not in s['symbols']: raise Reject('symbol_unavailable')
    if order_type not in ORDER_TYPES: raise Reject('order_type')
    side = 'BUY' if order_type.startswith('BUY') else 'SELL'
    for item in s['positions']+s['orders']:
        if item['symbol']==symbol:
            if side != item['side']: raise Reject('hedging')
            if item['ticket'] not in scale_in_tickets: raise Reject('duplicate_symbol')
    existing = portfolio_risk(s, now)
    spec = s['symbols'][symbol]
    mode = spec['trade_mode']
    if mode not in {1,2,4} or mode==1 and side=='SELL' or mode==2 and side=='BUY': raise Reject('symbol_trade_mode')
    required_bit = 1 if order_type in {'BUY','SELL'} else 8 if order_type.endswith('STOP_LIMIT') else 2 if order_type.endswith('LIMIT') else 4
    if not spec['order_mode'] & required_bit or not spec['order_mode'] & 16 or not spec['order_mode'] & 32:
        raise Reject('broker_order_mode')
    if not 0 <= now-spec['quote_at'] <= 10: raise Reject('stale_quote')
    bid,ask,tick = positive(spec['bid']),positive(spec['ask']),positive(spec['tick_size'])
    if (ask-bid)/tick > MAX_SPREAD_TICKS: raise Reject('spread')
    entry = positive(command['entry'])
    if order_type in {'BUY','SELL'}:
        entry = ask if side=='BUY' else bid
        if abs(entry-positive(command['entry']))/tick > 5: raise Reject('entry_moved')
    sl,tp = positive(command['sl']),positive(command['tp'])
    if not (sl<entry<tp if side=='BUY' else tp<entry<sl): raise Reject('sltp_geometry')
    for price in (entry,sl,tp):
        if price/tick != (price/tick).to_integral_value(): raise Reject('tick_alignment')
    distance = max(spec['stops_level'],spec['freeze_level'])*positive(spec['point'])
    reference = bid if side=='BUY' else ask
    if min(abs(entry-sl),abs(tp-entry),abs(reference-sl),abs(tp-reference)) <= distance: raise Reject('stop_freeze_level')
    if order_type not in {'BUY','SELL'}:
        ref = ask if side=='BUY' else bid
        limit = order_type in {'BUY_LIMIT','SELL_LIMIT'}
        if not ((entry<ref if side=='BUY' else entry>ref) if limit else (entry>ref if side=='BUY' else entry<ref)) or abs(entry-ref) <= distance:
            raise Reject('pending_geometry')
    if order_type.endswith('STOP_LIMIT'):
        price = positive(command['stop_limit'])
        if price/tick != (price/tick).to_integral_value() or not (sl<price<=entry<tp if side=='BUY' else tp<entry<=price<sl):
            raise Reject('stop_limit_geometry')
        # Worst allowed stop-limit fill determines sizing.
    elif number(command['stop_limit']) != 0: raise Reject('unexpected_stop_limit')
    cancel = command['cancel']
    keys(cancel, {'kind','price'})
    if cancel['kind'] not in {'price_below','price_above'}: raise Reject('unmeasurable_cancellation')
    cancel_price = positive(cancel['price'])
    if cancel['kind']=='price_below' and bid<=cancel_price or cancel['kind']=='price_above' and ask>=cancel_price:
        raise Reject('cancel_condition_met')
    # Include a conservative 5-tick entry allowance. Fees/gap limits still require verification.
    unit = (abs(entry-sl)+5*tick)/tick*positive(spec['tick_value_loss'])
    budget = min(basis*requested/100, basis*AGGREGATE/100-existing,
                 balance*FLOATING/100+number(s['floating_pnl']),
                 equity-positive(s['daily_anchor'])*(1-DAILY/100),
                 min(balance,equity)-trailing)
    if budget <= 0: raise Reject('aggregate_risk')
    budget = min(budget,exposure_budgets(s,symbol,side,basis,now))
    step = positive(spec['volume_step'])
    volume = (min(budget/unit,positive(spec['volume_max']))/step).to_integral_value(rounding=ROUND_FLOOR)*step
    if volume < positive(spec['volume_min']): raise Reject('lot_minimum')
    exact = unit*volume
    if exact > budget: raise Reject('risk_rounding')
    margin = volume*positive(spec['margin_buy' if side=='BUY' else 'margin_sell'])
    if margin > number(s['free_margin'])*Decimal('0.8'): raise Reject('margin')
    return {'volume':float(volume),'risk_usd':float(exact),'existing_risk_usd':float(existing),'margin_usd':float(margin),
            'entry':float(entry),'auto_authorised':False}

"""Existing 18-market G_DESK universe; RFBC strategy remains frozen to two FX pairs."""
DESK_PAIRS = ('EURUSD','GBPUSD','GBPJPY','USDCAD','EURJPY','AUDUSD','NZDUSD','USDCHF','EURGBP',
              'CADJPY','CHFJPY','EURAUD','GBPAUD','EURCAD','GBPCAD','XAUUSD','USDJPY','AUDJPY')
BROKER_SYMBOLS = frozenset(pair+'.x' for pair in DESK_PAIRS)
RFBC_PAIRS = frozenset({'USDJPY','AUDJPY'})

def broker_symbol(symbol):
    if symbol in BROKER_SYMBOLS: return symbol
    if isinstance(symbol,str) and len(symbol)==7 and symbol.endswith('c') and symbol[:6]+'.x' in BROKER_SYMBOLS:
        return symbol[:6]+'.x'
    raise ValueError('symbol_unavailable')

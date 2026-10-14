"""Explicit broker-observed runtime, replacing historical account mutation overlays."""
import os
import fx101
import fx101_worker
import g_desk_adapter
import mt5_bridge
from mt5_symbols import BROKER_SYMBOLS, DESK_PAIRS
from dukascopy_python import instruments

fx101.DESK_SYMBOLS = set(BROKER_SYMBOLS)
fx101.RFBC_SYMBOLS = {'USDJPY.x','AUDJPY.x'}
fx101.ALL_SYMBOLS = set(BROKER_SYMBOLS)
provider = {}
for pair in DESK_PAIRS:
    matches = {v for v in vars(instruments).values() if isinstance(v,str) and v.upper()==pair[:3]+'/'+pair[3:]}
    if len(matches)==1: provider[pair] = matches.pop()
fx101_worker.PAIR_TO_INSTRUMENT.update(provider)
g_desk_adapter.PAIR_TO_DUKASCOPY.update(provider)
g_desk_adapter.DESK_SYMBOLS[:] = [p+'.x' for p in DESK_PAIRS if p in provider]
# Maintain current production choice to pause RFBC; do not change its strategy.
if os.getenv('RFBC_EXECUTION_ENABLED','0') != '1':
    fx101_worker.scan_rfbc = lambda: None

# Dukascopy prices are market analysis, never evidence of broker fills/closures.
fx101.manage_prices = lambda _: []
fx101.activate_goat_challenge_profile = lambda: None
mt5_bridge.install_fx101_hooks()

def account_text():
    snap = mt5_bridge.latest_snapshot()
    if not snap or not snap['fresh']:
        return 'GOAT Stride / Instant HERO • $2,500 initial\nMT5 disconnected or stale. Execution blocked.'
    s = snap['payload']
    return '\n'.join(['GOAT Stride / Instant HERO',f"MT5 {s['login']} • {s['server']}",
        f"Balance ${s['balance']:.2f} • Equity ${s['equity']:.2f}",
        f"Free margin ${s['free_margin']:.2f} • Floating ${s['floating_pnl']:.2f}",
        f"Positions {len(s['positions'])} • Pending {len(s['orders'])}",
        f"Mode {mt5_bridge.mode()} • Kill switch {mt5_bridge.killed()}",'Historical rule anchors unverified. AUTO unavailable.'])
fx101.accounts_text = account_text

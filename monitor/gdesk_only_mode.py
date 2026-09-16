"""Temporary G_DESK-only production mode.

Pauses RFBC execution without deleting its frozen implementation and moves
USDJPYc/AUDJPYc into the discretionary G_DESK universe. This is reversible by
removing this final runtime overlay.
"""
from __future__ import annotations

import json

from dukascopy_python import instruments

import fx101
import fx101_worker
import g_desk_adapter

PAUSED_RFBC_SYMBOLS = {"USDJPYc", "AUDJPYc"}

# Preserve the frozen strategy implementation, but remove it from live runtime
# ownership while this overlay is loaded.
fx101.PAUSED_RFBC_SYMBOLS = set(PAUSED_RFBC_SYMBOLS)
fx101.RFBC_SYMBOLS = set()

# Promote the two former RFBC-only pairs into G DESK.
provider_additions = {
    "USDJPY": instruments.INSTRUMENT_FX_MAJORS_USD_JPY,
    "AUDJPY": instruments.INSTRUMENT_FX_CROSSES_AUD_JPY,
}
fx101_worker.PAIR_TO_INSTRUMENT.update(provider_additions)
g_desk_adapter.PAIR_TO_DUKASCOPY.update(provider_additions)

for symbol in sorted(PAUSED_RFBC_SYMBOLS):
    if symbol not in g_desk_adapter.DESK_SYMBOLS:
        g_desk_adapter.DESK_SYMBOLS.append(symbol)

fx101.DESK_SYMBOLS = set(g_desk_adapter.DESK_SYMBOLS)
fx101.ALL_SYMBOLS = set(fx101.DESK_SYMBOLS)

# Keep the tracked account eligible for the whole G DESK universe.
try:
    c = fx101.db()
    c.execute(
        "UPDATE accounts SET allowed_symbols=?, updated_at=? WHERE status='active'",
        (json.dumps(sorted(fx101.ALL_SYMBOLS)), fx101.now()),
    )
    c.commit()
except Exception as exc:
    fx101.log("gdesk_only_account_update_failed", error=type(exc).__name__)

# The worker main loop still calls scan_rfbc on its timer; replacing the
# function with a true no-op prevents RFBC data evaluation or trade checks.
def _rfbc_paused() -> None:
    return None

fx101_worker.scan_rfbc = _rfbc_paused

fx101.log(
    "gdesk_only_mode_loaded",
    rfbc_paused=True,
    promoted=sorted(PAUSED_RFBC_SYMBOLS),
    gdesk_symbols=sorted(fx101.DESK_SYMBOLS),
    symbol_count=len(fx101.DESK_SYMBOLS),
)

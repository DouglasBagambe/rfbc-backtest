#!/usr/bin/env python3
"""Offline, read-only RFBC volume verifier using a sanitized MT5 JSON export."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def require_number(source: dict, key: str) -> float:
    value = source.get(key)
    if not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"Missing or non-positive metadata field: {key}")
    return float(value)


def size(metadata: dict, atr: float, risk_pct: float, equity: float | None) -> dict:
    if metadata.get("capture_status") != "captured_from_mt5":
        raise ValueError("Metadata is not a completed MT5 export; do not infer broker values.")
    symbol, account = metadata["symbol"], metadata["account"]
    equity = float(account["equity"] if equity is None else equity)
    if atr <= 0 or equity <= 0:
        raise ValueError("ATR and equity must be positive.")
    tick_size = require_number(symbol, "tick_size")
    tick_value_loss = require_number(symbol, "tick_value_loss")
    minimum, step, maximum = (require_number(symbol, key) for key in ("volume_min", "volume_step", "volume_max"))
    stop_distance = 1.50 * atr
    money_risk = equity * risk_pct / 100.0
    loss_per_lot = stop_distance / tick_size * tick_value_loss
    raw_volume = money_risk / loss_per_lot
    rounded = math.floor((raw_volume + 1e-12) / step) * step
    rounded = min(rounded, maximum)
    actual_risk = rounded * loss_per_lot
    min_risk = minimum * loss_per_lot
    return {
        "account_equity": equity,
        "account_currency": account.get("currency"),
        "risk_percent": risk_pct,
        "atr": atr,
        "stop_distance_1_50_atr": stop_distance,
        "money_risk_target": money_risk,
        "loss_per_lot_at_stop": loss_per_lot,
        "raw_volume": raw_volume,
        "volume_rounded_down": rounded,
        "actual_estimated_risk": actual_risk,
        "minimum_volume": minimum,
        "minimum_volume_risk": min_risk,
        "minimum_lot_exceeds_target_risk": min_risk > money_risk + 1e-12,
        "trade_permitted_at_target_risk": rounded >= minimum,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", type=Path, default=Path("broker_validation/output/usdjpyc_symbol_properties.json"))
    parser.add_argument("--atr", type=float, required=True, help="USDJPY ATR in price units, e.g. 0.85 not pips")
    parser.add_argument("--equity", type=float, help="Override exported equity in account-currency units")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    metadata = json.loads(args.metadata.read_text())
    try:
        results = [size(metadata, args.atr, risk_pct, args.equity) for risk_pct in (0.25, 0.5, 1.0)]
    except ValueError as exc:
        raise SystemExit(f"Position sizing unavailable: {exc}")
    payload = {"symbol": metadata.get("symbol", {}).get("name"), "results": results}
    text = json.dumps(payload, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()

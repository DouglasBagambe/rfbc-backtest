# USDJPYc MT5 broker validation tools

These utilities are read-only. Neither MQL5 file includes trade, order, position, login, or account-modification calls.

## 1. Export live metadata inside MT5

Copy `mql5/ExportUSDJPYcProperties.mq5` into the connected MT5 terminal's `MQL5/Scripts` folder, compile it in MetaEditor, and run it once with `InpSymbol=USDJPYc`. MT5 writes `usdjpyc_symbol_properties.json` to its Common `Files` directory. Copy that file to `broker_validation/output/usdjpyc_symbol_properties.json`; do not add account IDs, server names, or credentials.

The committed JSON is intentionally a pending template because MT5 is not installed on this Linux host.

## 2. Start the native spread logger

Copy `mql5/USDJPYcSpreadLogger.mq5` into `MQL5/Experts`, compile, attach it to any USDJPYc chart, and retain the 60-second interval. It only reads ticks and appends UTC bid/ask snapshots to Common `Files/usdjpyc_spread_log.csv`.

Copy the log to `broker_validation/local_data/usdjpyc_spread_log.csv` when analysis is needed. That folder is ignored by Git.

## 3. Verify volume without trading

After replacing the metadata template with the real export, use a representative ATR in USDJPY price units:

```bash
python3 broker_validation/verify_position_size.py --atr 0.85
```

It reports 0.25%, 0.5%, and 1.0% risk, floors volume to the broker step, and marks minimum-lot risk violations. Do not use it to place an order.

## 4. Analyse local spreads

After enough samples are collected:

```bash
python3 broker_validation/analyze_spread_log.py
```

It produces a safe small summary under `broker_validation/output/`, including UTC-hour, RFBC checkpoint, Friday 16:00 UTC, and configurable rollover-window costs against the Dukascopy H1 reference. Raw logs remain local.

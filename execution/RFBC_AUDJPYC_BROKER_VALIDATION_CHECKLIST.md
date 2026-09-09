# RFBC AUDJPYc Broker Validation Checklist

## Purpose

AUDJPY passed the independent RFBC v1.0 research gate. This document records the broker-specific qualification of `AUDJPYc` on the user's Exness Standard Cent account.

Do not infer broker properties from USDJPYc. Values below were captured directly from MT5 mobile on 9 September 2026.

## Verified broker fields

| Field | Verified value |
|---|---|
| Symbol | `AUDJPYc` |
| Description | Australian Dollar vs Japanese Yen |
| Category | Minors |
| Digits | 3 |
| Point size | 0.001 |
| Contract size | 1,000 AUD |
| Margin currency | AUD |
| Profit currency | JPY |
| Spread | Floating |
| Observed Bid / Ask | 110.812 / 110.823 |
| Observed spread | 0.011 JPY = 1.1 pips |
| Stops level | 0 |
| Chart mode | Bid |
| Trade access | Full access |
| Execution | Market Execution |
| Filling | Fill or Kill / Immediate or Cancel |
| Minimum volume | 0.01 |
| Maximum volume | 200 |
| Volume step | 0.01 |
| Swap type | Points |
| Swap long | -0.2 |
| Swap short | -2.1 |
| Triple swap | Wednesday |
| Sunday session | 21:05-24:00 |
| Mon-Thu sessions | 00:00-24:00 |
| Friday session | 00:00-20:59 |

Machine-readable evidence is saved at:

`broker_validation/output/audjpyc_symbol_properties.json`

## Broker compatibility conclusion

**PASS — broker properties are compatible with frozen RFBC v1.0.**

No broker rule shown in the screenshots requires changing RFBC signal, stop, target, breakeven or Friday-flat logic.

The Friday market remains open well beyond RFBC's frozen 16:00 UTC forced-close checkpoint.

## Fresh account state

Fresh account screenshots on 9 September 2026 show:

- Balance: **1,001.00 USC**
- Equity: **1,001.00 USC**
- Free margin: **1,001.00 USC**
- USD-equivalent equity for risk calculations: **$10.01**
- No open positions at the time of capture

## Small-account risk economics

At 0.01 volume and a 1,000 AUD contract size, the position represents approximately 10 AUD of base notional.

For a JPY-quoted pair, approximate USD risk is:

`risk_usd = (10 * stop_distance_JPY) / USDJPY`

Frozen RFBC stop distance is:

`stop_distance_JPY = 1.50 * signal_ATR`

Using contemporaneous USDJPY near 153.464 and fresh equity of $10.01:

`risk_pct ~= 0.9764 * ATR_JPY`

Therefore the approximate ATR threshold at which minimum-volume risk reaches the 1.00% cap is about:

`ATR ~= 1.024 JPY`

This threshold is only a live-checkpoint approximation. Actual risk must always use current account equity, current USDJPY conversion and the actual RFBC stop distance.

## Functional execution checks

- [x] 0.01 is accepted by the symbol specification.
- [x] Volume step is 0.01.
- [x] Stops level is 0, so normal RFBC SL/TP distances are not structurally blocked.
- [x] Three-digit precision is explicit.
- [x] Friday session is compatible with frozen 16:00 UTC flat rule.
- [x] Swap economics are documented.
- [x] Broker properties do not require a strategy-rule modification.
- [x] Fresh account equity has been captured and mapped to $10.01 for current risk calculations.
- [ ] First live/manual order ticket should be sanity-checked end to end before enabling routine use.

## Final status

Status: **BROKER-QUALIFIED. MONITOR / END-TO-END LIVE WORKFLOW PENDING.**

`AUDJPYc` is approved for inclusion in the deterministic multi-pair monitor subject to the existing 1.00% per-trade and aggregate open-risk overlay. The first actual ticket must still be sanity-checked end to end before routine live use.
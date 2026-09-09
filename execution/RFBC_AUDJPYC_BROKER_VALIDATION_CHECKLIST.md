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

## Small-account risk economics

At 0.01 volume and a 1,000 AUD contract size, the position represents approximately 10 AUD of base notional.

For a JPY-quoted pair, approximate USD risk is:

`risk_usd = (10 * stop_distance_JPY) / USDJPY`

Frozen RFBC stop distance is:

`stop_distance_JPY = 1.50 * signal_ATR`

Using the contemporaneous USDJPY quote near 153.464 and an account around $10 for illustration only:

`risk_pct ~= 0.9774 * ATR_JPY`

Therefore the approximate ATR threshold at which minimum-volume risk reaches the 1.00% cap is about:

`ATR ~= 1.02 JPY`

This is not a permanent threshold because actual risk must use the **fresh account equity and current USDJPY conversion rate at the trade checkpoint**.

## Functional execution checks

- [x] 0.01 is accepted by the symbol specification.
- [x] Volume step is 0.01.
- [x] Stops level is 0, so normal RFBC SL/TP distances are not structurally blocked.
- [x] Three-digit precision is explicit.
- [x] Friday session is compatible with frozen 16:00 UTC flat rule.
- [x] Swap economics are documented.
- [x] Broker properties do not require a strategy-rule modification.
- [ ] Fresh account equity is still required before live sizing.
- [ ] First live/manual order ticket should be sanity-checked end to end before enabling routine use.

## Final status

Status: **BROKER-QUALIFIED, LIVE-RISK-FINALIZATION PENDING**.

`AUDJPYc` may be added to the deterministic monitor once the monitor is updated for multi-pair operation and fresh-equity risk sizing. Do not place a live trade using stale equity.

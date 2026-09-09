# RFBC v1.0 Operational Status

## Purpose

This document separates research qualification from broker/live execution qualification.

## Research-qualified set

RFBC v1.0 is research-qualified only on:

- USDJPY
- AUDJPY

All other tested pairs are rejected for RFBC v1.0.

## Broker/live readiness

### USDJPYc

Status: execution validation substantially completed for the current Exness Standard Cent setup.

Known broker properties from the validation pass include:

- symbol: USDJPYc
- contract size: 1,000 USD
- minimum volume: 0.01
- volume step: 0.01
- digits: 3
- stops level: 0

The existing manual execution specification is `execution/RFBC_USDJPYC_MANUAL_EXECUTION_SPEC.md`.

For the current very small account, execution uses a separate account-risk overlay rather than changing RFBC signal rules:

- minimum executable volume: 0.01
- do not increase above 0.01 while operating under the current small-account constraint
- calculate actual monetary risk from current equity, entry and stop distance before every trade
- skip the trade if estimated account risk exceeds 1.00%
- refresh account equity after closed trades; do not rely indefinitely on a stale balance

This overlay is an execution constraint, not part of frozen RFBC v1.0 strategy logic.

### AUDJPYc

Status: research-qualified, NOT YET broker-qualified.

The required broker-validation procedure is documented at:

`execution/RFBC_AUDJPYC_BROKER_VALIDATION_CHECKLIST.md`

Before enabling AUDJPYc, collect and verify the same Exness symbol properties used for USDJPYc:

- exact symbol name/suffix
- contract size
- minimum volume
- volume step
- digits / point size
- typical spread
- stops level
- swap long
- swap short
- triple-swap day
- trading sessions / Friday close behavior

Then calculate whether 0.01 volume can respect the account-risk cap for realistic RFBC ATR stop distances. If broker economics make the risk overlay impractical, AUDJPY remains research-qualified but is not traded on this account.

## Portfolio execution rule

The deterministic live overlay is documented at:

`execution/RFBC_V10_PORTFOLIO_RISK_OVERLAY.md`

Current small-account rules include:

- 0.01 maximum live volume per RFBC position;
- <= 1.00% risk for any individual entry;
- <= 1.00% aggregate initial open risk across simultaneous RFBC positions;
- chronological signal ordering;
- for same-checkpoint signals that cannot both fit the aggregate cap, prefer the lower-risk trade; use USDJPYc only as the deterministic tie-break if risk is effectively equal;
- daily new-entry stop at -1.00% realized RFBC loss;
- weekly new-entry stop at -2.00% realized RFBC loss;
- 3.00% high-water-mark drawdown warning/review;
- 5.00% high-water-mark hard kill for new RFBC entries.

Both research-qualified pairs contain JPY. Their historical return and drawdown correlations are low, but the aggregate risk cap remains necessary because common JPY event risk can still occur.

## Monitoring architecture

Target live architecture:

1. deterministic RFBC code computes the signal and management state
2. broker-specific execution layer calculates exact manual order fields and actual account risk
3. portfolio overlay applies individual, aggregate, daily, weekly and drawdown gates
4. alert layer tells the user exactly what to place/manage on MT5 mobile
5. ChatGPT is oversight and diagnostics, not the critical strategy execution engine

Required alert vocabulary includes `TRADE`, `SKIP_RISK`, `SKIP_CHASE`, `SKIP_PORTFOLIO_RISK`, `MOVE_BE`, `FRIDAY_CLOSE`, `DAILY_STOP`, `WEEKLY_STOP`, `DRAWDOWN_WARNING`, `HARD_KILL`, `STALE`, and `ERROR`.

The current live path should remain manual/semi-automatic until forward evidence and operational reliability justify anything more automated.

## Live-enable checklist

RFBC v1.0 should be considered operationally finalized for the current account only when all of the following are true:

- USDJPYc broker properties remain verified/current
- AUDJPYc broker properties are verified and saved
- current account equity is refreshed in the risk calculation
- per-pair manual order calculations are deterministic and tested
- simultaneous USDJPYc/AUDJPYc risk overlay is implemented and tested
- daily/weekly/drawdown state tracking is implemented and tested
- monitoring/alert delivery is reliable enough for the H4 checkpoints and management events
- Friday close and breakeven management are tested end to end
- live journal/review procedure is active before the first forward trade

## Expansion policy

Do not retune RFBC v1.0 to force more pairs.

After this execution layer is complete, additional research may begin as a separate strategy family/version. Any new strategy should be developed and validated independently, ideally adding behavior that is meaningfully different from RFBC and improving portfolio diversification rather than duplicating the same breakout/JPY concentration.

New strategies and new validated pair sets should remain separate from the frozen RFBC v1.0 evidence chain.

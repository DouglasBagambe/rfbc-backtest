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

Both research-qualified pairs contain JPY. Their historical return and drawdown correlations are low, but simultaneous exposure can still create common JPY event risk.

Before enabling both live, define and validate a deterministic portfolio overlay for simultaneous signals. The overlay must control total account risk without altering either pair's RFBC entry/exit rules.

Until that overlay is finalized, do not assume two simultaneous 1% trades are automatically acceptable.

## Monitoring architecture

Target live architecture:

1. deterministic RFBC code computes the signal and management state
2. broker-specific execution layer calculates exact manual order fields and actual account risk
3. alert layer tells the user exactly what to place/manage on MT5 mobile
4. ChatGPT is oversight and diagnostics, not the critical strategy execution engine

The current live path should remain manual/semi-automatic until forward evidence and operational reliability justify anything more automated.

## Live-enable checklist

RFBC v1.0 should be considered operationally finalized for the current account only when all of the following are true:

- USDJPYc broker properties remain verified/current
- AUDJPYc broker properties are verified
- current account equity is refreshed in the risk calculation
- per-pair manual order calculations are deterministic and tested
- simultaneous USDJPYc/AUDJPYc risk overlay is defined and tested
- monitoring/alert delivery is reliable enough for the H4 checkpoints and management events
- Friday close and breakeven management are tested end to end

## Expansion policy

Do not retune RFBC v1.0 to force more pairs.

After this execution layer is complete, additional research may begin as a separate strategy family/version. Any new strategy should be developed and validated independently, ideally adding behavior that is meaningfully different from RFBC and improving portfolio diversification rather than duplicating the same breakout/JYP concentration.

New strategies and new validated pair sets should remain separate from the frozen RFBC v1.0 evidence chain.

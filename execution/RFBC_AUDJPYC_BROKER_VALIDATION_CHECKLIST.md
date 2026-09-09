# RFBC AUDJPYc Broker Validation Checklist

## Purpose

AUDJPY passed the independent RFBC v1.0 research gate, but `AUDJPYc` must still be validated on the user's Exness Standard Cent account before it is enabled for live/manual execution.

Do not infer broker properties from USDJPYc. Record the actual `AUDJPYc` properties shown by Exness/MT5.

## Required broker fields

Capture and verify all of the following from MT5 symbol Properties / Specification:

- exact broker symbol: `AUDJPYc` or actual suffix shown
- contract size
- profit calculation currency
- margin calculation currency, if shown
- minimum volume
- maximum volume
- volume step
- digits
- point size
- stops level
- freeze level, if shown
- current/typical spread
- spread type, if shown
- swap long
- swap short
- triple-swap day
- trading sessions for Monday-Friday
- Friday final trading time
- whether the chart/quotes are Bid-based as expected

## Risk validation

After the properties are captured, verify the current 0.01 minimum-volume economics using realistic RFBC stop distances.

For each check:

1. use the actual current account equity;
2. use an actual executable AUDJPYc entry price;
3. use frozen RFBC stop distance = `1.50 * signal ATR(14)`;
4. use the broker contract size and correct JPY-to-account-currency conversion;
5. calculate monetary risk and account-risk percentage at 0.01 volume;
6. confirm the trade is rejected whenever estimated risk exceeds 1.00%;
7. confirm no volume above 0.01 is used in current small-account mode.

## Functional execution checks

Before live-enabling AUDJPYc, confirm manually on MT5 that:

- 0.01 can be entered for the symbol;
- SL and TP can be placed at normal RFBC distances without broker rejection;
- price precision used by the monitor matches MT5 digits;
- Friday session timing is compatible with the frozen 16:00 UTC forced close;
- swap economics are documented even though RFBC normally closes by Friday;
- no broker rule requires changing frozen RFBC signal/exit logic.

If any broker constraint conflicts with frozen RFBC, the correct outcome is to leave AUDJPY research-qualified but execution-disabled on this account. Do not alter RFBC to fit the broker.

## Evidence to save

Save the final verified values to a machine-readable file under:

`broker_validation/output/audjpyc_symbol_properties.json`

Also add a short Markdown broker-validation conclusion documenting:

- PASS / FAIL for execution qualification;
- source/date of the broker properties;
- actual risk examples;
- any material spread/swap/session concerns;
- whether `AUDJPYc` may be enabled in the live monitor.

## Current status

Status: `PENDING USER BROKER EVIDENCE`.

Required next input: current MT5 mobile screenshots of the full AUDJPYc Properties/Specification pages and a fresh account equity/balance snapshot before final live sizing.

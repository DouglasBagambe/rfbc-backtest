# RFBC USDJPYc cloud monitor

This monitor evaluates the frozen USDJPY RFBC survivor from Dukascopy BID/ASK data and sends phone notifications through ntfy.

## Scope

- Symbol mapping: `USDJPYc`
- Frozen RFBC rules are not modified.
- Minimum volume: 0.01
- Hard estimated-risk cap: 1.00% of configured account equity
- Signal checks use completed UTC H4/D1 data.
- Signal notifications are sent only at eligible RFBC checkpoints.
- Manual management notifications are emitted at completed H4 breakeven checkpoints and Friday 16:00 UTC.
- SL/TP remain broker-side orders placed manually in MT5.

## Environment

- `NTFY_TOPIC` — private ntfy topic name; do not commit it.
- `NTFY_SERVER` — defaults to `https://ntfy.sh`.
- `RFBC_EQUITY_USD` — current account equity in USD equivalent; initially approximately 10.01.

## Scheduling

Run at every UTC H4 close:

`0 */4 * * *`

The script itself only opens new signals at frozen eligible close times. The other H4 runs are used for management checks.

## Important limitation

Dukascopy is the monitoring feed while execution is on Exness mobile MT5. A small data/feed/notification delay is therefore unavoidable. The monitor rejects stale signal evaluations and applies the frozen 0.20 ATR no-chase gate to the latest available minute quote before sending a TRADE instruction.

If the phone notification says TRADE, the user still places the order manually in MT5 with the supplied 0.01 volume, SL and TP. No broker credentials or order API are used.

# RFBC v1.0 two-pair cloud monitor

> **Scope:** `USDJPYc` + `AUDJPYc` only  
> **Strategy:** frozen RFBC v1.0  
> **Execution mode:** manual on Exness MT5 mobile  
> **ChatGPT role:** oversight/diagnostics only, not critical execution

---

## What the monitor does

The monitor evaluates both research-qualified RFBC v1.0 pairs from Dukascopy BID/ASK data and produces deterministic manual-order actions.

| Symbol | Research status | Broker status |
|---|---|---|
| `USDJPYc` | Qualified | Qualified |
| `AUDJPYc` | Qualified | Qualified |

It preserves the frozen strategy logic and applies only the documented live-execution overlays.

## Frozen strategy controls

- completed UTC D1/H4 information only;
- exact RFBC 20-H4 breakout logic;
- 1.50 ATR initial stop;
- 2.50R target;
- 0.20 ATR no-chase rule;
- breakeven only after completed H4 close >= +1.50R;
- Friday flat at 16:00 UTC.

## Tiny-account execution overlay

Current account-equivalent equity is configured through `RFBC_EQUITY_USD`.

Current controls:

| Control | Rule |
|---|---:|
| Volume | 0.01 |
| Individual entry risk cap | 1.00% |
| Aggregate initial open-risk cap | 1.00% |
| Same-checkpoint tie | lower estimated risk first |
| Exact-risk tie | USDJPYc deterministic tie-break |

If a valid signal violates the account or portfolio overlay, RFBC itself is not changed; the monitor emits a skip action.

## Action vocabulary

The service may return:

- `TRADE`
- `SKIP_RISK`
- `SKIP_CHASE`
- `SKIP_PORTFOLIO_RISK`
- `MOVE_BE`
- `FRIDAY_CLOSE`
- `STALE`
- `ERROR`
- `NONE`

Daily/weekly/drawdown gates remain part of the documented operational policy. They require reliable execution-state feedback before they can be treated as authoritative automated account state; do not fake them from hypothetical fills.

## HTTP endpoints

### `/`

Service identity and monitored symbols.

### `/health`

Returns service state, current configured equity, risk caps and Telegram configuration state.

### `/check`

Evaluates both pairs, applies the aggregate portfolio gate and returns per-pair actions plus an `actionable` list.

## Environment

- `RFBC_EQUITY_USD` — fresh account equity in USD equivalent. Current verified value: `10.01`.
- `TELEGRAM_BOT_TOKEN` — optional dedicated Telegram bot token for direct alerts from Render.
- `TELEGRAM_CHAT_ID` — destination Telegram chat ID.

Secrets must never be committed.

## Alert architecture

Preferred production path:

```text
Dukascopy -> deterministic RFBC monitor -> direct Telegram alert -> manual MT5 execution
                                      \
                                       -> ChatGPT oversight / diagnostics
```

Direct Telegram delivery removes ChatGPT automation/DNS from the critical alert path.

## Important limitations

- Dukascopy is the monitoring feed while execution occurs on Exness, so small feed/execution differences are possible.
- The monitor rejects stale data and applies the no-chase rule to a recent quote.
- SL/TP are placed broker-side manually in MT5.
- An alert is not permission to override the risk gate or frozen strategy.
- Full automatic broker execution is intentionally deferred until forward evidence and operational reliability justify it.

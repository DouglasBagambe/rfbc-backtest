# G's Fx 101 v2 production notes

## Boundaries

RFBC remains frozen v1.0 for `USDJPYc` and `AUDJPYc`; manual MT5 placement is
the only execution path. G_DESK remains separate for `EURUSDc`, `GBPUSDc`,
`GBPJPYc`, `USDCADc`, and `EURJPYc`. It exposes completed Dukascopy H1 BID/ASK
context at `/gdesk/context`; connected ChatGPT subscription automation decides
TRADE, NO_TRADE, or SYSTEM FAILURE through the isolated GitHub runtime mailbox.
No OpenAI API key, paid model, TaskNotify, or replacement AI provider is part
of the Render blueprint.

## Persistence and accounts

Turso is the production store. Schema creation is idempotent and adds accounts,
ledger, account-trade selection, transition audit events, reconciliation
records, and application metadata without deleting existing trade data.
Accounts use **tracked** balance/equity only: no broker API is implied. A new
decision must select an active eligible account or is rejected. Reconciliation
records drift without rewriting the ledger.

## Operations

Render runs Waitress plus exactly one daemon worker in the single web process.
The worker independently isolates Dukascopy lifecycle polling from frozen RFBC
scans. It only sends actionable RFBC events; `NONE`, `STALE`, and ordinary
open-trade states stay quiet. Lifecycle uses aligned Dukascopy M1 BID/ASK
midpoint snapshots; it cannot reconstruct intrabar broker fills and says so in
the audit record. `/health` is cheap; `/fx101/health` checks persistence.

## Required configuration names

`TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`, `TELEGRAM_WEBHOOK_URL`, `TELEGRAM_WEBHOOK_SECRET`,
`G_DESK_ADAPTER_TOKEN`, `G_DESK_RUNTIME_MODE`, `RFBC_EQUITY_USD`,
`FX101_MAX_TOTAL_RISK_PCT`, `FX101_MAX_POSITIONS`,
`FX101_PRICE_POLL_SECONDS`, `FX101_RFBC_SCAN_SECONDS`, and `LOG_LEVEL`.

## Weekend and recovery

On weekends `/gdesk/context` marks market state and freshness as
`MARKET_CLOSED`; Friday's last H1 bar is not called fresh live data. After a
restart, migrations rerun safely, Telegram webhook registration is attempted
when configured, and `PLACED`/`OPEN` trades resume lifecycle polling. Market
open G_DESK context and lifecycle price verification must be repeated when FX
reopens.

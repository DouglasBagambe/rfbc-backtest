# G's Fx 101 — free G_DESK bridge

## Architecture

The production branch never runs an AI model. Once per UTC hour the Render
worker obtains completed Dukascopy H1 BID/ASK context for `EURUSDc`, `GBPUSDc`,
`GBPJPYc`, `USDCADc`, and `EURJPYc`. It emits one structured context log event
per symbol, followed by a `gdesk_context_ready` marker sharing a unique scan ID.

ChatGPT subscription scheduled automation is the only G_DESK analyst. It reads
that complete context, then writes one decision document to the isolated
`gdesk-runtime` branch at `runtime/gdesk_decision.json`. That branch is a
mailbox only and is never merged into `strategy2-round2-wip`, so mailbox writes
do not redeploy Render.

Render polls GitHub raw content, rejects malformed, future, stale, duplicated,
invalid-risk, invalid-symbol, or invalid-geometry decisions, and records every
accepted or rejected decision in Turso. A decision ID is consumed once across
restarts. It never sends an MT5 order.

## Decision envelope

`decision_id`, `generated_at`, and `result` are required. `result` is exactly
`TRADE`, `NO_TRADE`, or `SYSTEM_FAILURE`. A TRADE contains exactly one fully
specified decision. NO_TRADE is used only after valid context and completed
analysis; SYSTEM_FAILURE is delivered as a system issue, never relabelled as
NO_TRADE.

## Analyze Now

In this free architecture `/analyze` cannot invoke ChatGPT immediately. It
stores an auditable queued request and says when the next hourly ChatGPT scan
is expected in EAT. It does not make a paid API call and does not claim that
analysis has already occurred.

## Operations and limitations

The service is free-tier Render + Turso + Dukascopy + Telegram + GitHub +
ChatGPT subscription. ChatGPT Plus/subscription is not OpenAI API credit.
Weekend context reports `MARKET_CLOSED`; market-open bridge behaviour must be
verified when FX reopens. Trades remain manual MT5 placement followed by
Dukascopy-based lifecycle tracking.

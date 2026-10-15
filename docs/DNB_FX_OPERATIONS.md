# dnb Fx operations — 15 October 2026

## Names

- dnb Fx: complete trading ecosystem
- dnb Desk: discretionary analysis (technical source key `G_DESK`)
- dnb Risk: deterministic risk controls
- dnb EA: MT5 engine (`mt5/DnbEA.mq5`; existing credential paths retained)
- dnb Bot: Telegram interface

## Current deployment

The permanent gateway is https://dnb-fx.onrender.com (Render service `srv-db7nv1t9fdbs73eto5d0`), built from `feature/mt5-goat-auto`.

The gateway publishes all 18 completed-H1 Dukascopy BID/ASK contexts, consumes the owned GitHub decision mailbox, sends Telegram analysis/status reports and serves the authenticated owner-only bot webhook. PostgreSQL stores receipts, alerts, reports and update deduplication. The older RFBC monitor is no longer a scanner or bot dependency.

Telegram's webhook is `/telegram/webhook`, protected by a secret derived from the existing bot credential and restricted to the configured owner chat. Never log that secret or the bot credential.

The ChatGPT automation is **dnb Desk Scanner**, scheduled hourly at **:20 Africa/Kampala**. Every run must publish TRADE, genuine NO_TRADE or SYSTEM_FAILURE. The gateway reports missing hourly delivery after :40. Informational report failures retry; uncertain trade-alert delivery remains quarantined for broker reconciliation.

## Data integrity repair

- Gold's daily 17:00–18:00 New York settlement break is an expected absence, with DST handled.
- Genuine missing trading-hour bars, invalid prices, duplicate timestamps and stale bars still fail validation.
- Cache entries cannot cross an hourly cutoff or make stale candles current.
- Failed context publication retries instead of marking the hour complete.
- A current FRESH label alone is insufficient; actual per-symbol bar timestamps must match the completed trading bucket.

## Account and execution

GOAT Stride / Instant HERO: $2,500 initial account, .x symbols. Do not treat the retired $5K challenge profile or old Exness journal as the current broker account.

Risk input is capped at 0.25%. Producer volume is an untrusted compatibility placeholder. Actual sizing requires fresh broker specifications, quotes, account state and the remaining risk checks.

**Live AUTO remains unavailable. The unfinished demo executor is disabled.** Keep the existing demo observer separate from funded-account authority. Analysis alerts never prove fills or authorise a lot size.

## Verification

- Full monitor suite: 229 tests and 8 subtests passed before consolidation.
- Complete fresh 18-symbol context verified in the current gateway for the 13:00 UTC scan, with completed bars at 12:00 UTC.
- Genuine AUDUSD SELL LIMIT analysis was delivered by the permanent gateway at 12:52:58 UTC / 15:52:58 EAT; durable alert state SENT.
- Telegram accepted dnb Bot's display name, descriptions and the current gateway webhook.
- Independent external health checks returned HTTP 200.
- Installed desktop MT5 binaries cannot be rebuilt from this workspace; compile the canonical EA locally when updating its displayed filename.

These checks do not prove profitability or uninterrupted future delivery. Free Render remains subject to sleep/restarts and shared workspace quotas. The external health-monitor target is https://dnb-fx.onrender.com/health.

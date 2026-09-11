# G's Fx 101 v2 Phase 2 deployment

Deploy on an always-on VPS/container host with Docker Compose, not a sleeping
free service. The `api` service receives Telegram and G_DESK HTTPS callbacks;
the `worker` service polls Twelve Data every 30 seconds and requests G_DESK at
the first poll of every UTC hour. Both use the same named persistent volume.

## Setup

1. Copy `.env.fx101.example` to `.env.fx101`; fill every blank value.
2. Put the service behind an authenticated HTTPS reverse proxy. Restrict
   `/desk/analyze` and `/fx101/prices` to the adapter/proxy, and retain only
   `/telegram/webhook` as Telegram-reachable.
3. Run `docker compose -f docker-compose.fx101.yml up -d --build`.
4. Set Telegram webhook: `https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://HOST/telegram/webhook`.
5. Verify: `curl -fsS https://HOST/fx101/health` and
   `docker compose -f docker-compose.fx101.yml logs --tail=100 worker`.

## G_DESK adapter contract

The worker POSTs this to `G_DESK_ANALYZE_URL`:

```json
{"source":"G_DESK","symbols":["EURJPYc","EURUSDc","GBPJPYc","GBPUSDc","USDCADc"],"requested_at":"..."}
```

Return HTTP 200 and `{ "decisions": [] }` for NO TRADE, or one or more
decisions with `symbol`, `side`, `entry`, `stop`, `target`, `volume`,
`risk_pct`, `valid_until`, `cancel_condition`, `confidence`, `setup_name`,
`regime`, `session`, `news_proximity`, `exposure_note`, `reasoning`, and
optional `context` / `trade_id`. The server validates every field and emits a
Telegram NO TRADE message for an empty response. An adapter may instead POST
the identical body to `/desk/analyze`.

## Operations

`docker compose -f docker-compose.fx101.yml ps` is the watchdog; both services
use `restart: unless-stopped`. `/fx101/health` checks persistent SQLite access.
Worker failures are structured JSON logs and Telegram warnings at failure 1, 5,
and 20. Startup opens the existing database and resumes monitoring all
`PLACED`/`OPEN` trades. No MT5 API or automatic order placement exists.

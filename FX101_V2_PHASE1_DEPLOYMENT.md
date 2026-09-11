# Deployment

Set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `FX101_DB_PATH` (persistent disk),
`FX101_MAX_TOTAL_RISK_PCT`, `FX101_MAX_POSITIONS`, `FX101_STALE_SECONDS`, and the
existing `RFBC_EQUITY_USD`. Start `python monitor/webapp.py`, expose HTTPS, then
set the Telegram webhook to `/telegram/webhook`. ChatGPT/G_DESK must call
`POST /desk/analyze` with a `decisions` list matching the fields validated in
`monitor/fx101.py`; an empty list records a no-trade scan. Do not expose the
endpoint publicly without an upstream authenticated proxy in production.

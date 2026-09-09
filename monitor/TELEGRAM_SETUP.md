# RFBC direct Telegram alerts

The Render monitor can send actionable RFBC events directly to a private Telegram chat, without relying on ChatGPT to deliver the notification.

## Required Render environment variables

Set these only in Render, never in GitHub:

- `TELEGRAM_BOT_TOKEN` — token issued by Telegram BotFather.
- `TELEGRAM_CHAT_ID` — numeric private-chat ID that should receive alerts.

The application reports whether Telegram is configured on `/health` through `telegram_configured`.

## Security

- Never commit the bot token to this repository.
- Never paste the bot token into source files or reports.
- If the token is accidentally exposed, revoke it in BotFather and issue a new one.

## Delivery behavior

`monitor/webapp.py` calls `monitor/telegram_notify.py` whenever `/check` returns an actionable state rather than `NONE`, including TRADE, SKIP, MOVE_BE, FRIDAY_CLOSE, STALE and ERROR states.

Repeated identical actions are suppressed while the service process remains alive. The web response also contains `telegram_configured`, `telegram_sent`, and `telegram_status` for delivery diagnostics.

## Test

After both environment variables are configured, call `/health` first and verify `telegram_configured: true`. Then invoke `/check` at a valid checkpoint. Do not fabricate or force a trading signal merely to test Telegram; delivery can be tested separately by temporarily invoking `telegram_notify.send_message()` from a safe one-off maintenance command or local shell.

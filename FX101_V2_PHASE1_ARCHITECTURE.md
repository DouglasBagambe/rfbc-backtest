# G's Fx 101 v2 Phase 1

RFBC remains unchanged. `monitor.fx101` is a separate SQLite-backed operations
layer for RFBC and externally supplied G_DESK decisions. `POST /desk/analyze`
accepts deterministic JSON decisions from ChatGPT/G_DESK, validates them,
persists them, and sends a Telegram card. It never generates a GPT decision.

Lifecycle is strictly `SIGNALLED -> PLACED/SKIPPED -> OPEN -> WON/LOST/CANCELLED/EXPIRED/MANUAL_CLOSE`.
`/telegram/webhook` supplies idempotent updates and supports `/open`, `/today`,
`/stats`, `/why ID`, and `/analyze`. The latter acknowledges an analysis request;
an external ChatGPT-side service must POST the finished decisions. Signal cards
include a reliable TradingView deep link; no scraping is used.

The server-side portfolio gate checks fixed source/symbol scope, geometry,
idempotency, configured risk, position count, and correlated currencies before
an item becomes actionable. Phase 1 does not fetch broker positions, execute
orders, or fabricate live prices. A price-feed worker is the required next
manual-wiring step for automatic TP/SL/expiry monitoring.

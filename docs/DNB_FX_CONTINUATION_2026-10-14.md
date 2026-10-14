# dnb Fx continuation — 14 October 2026

The requested unattended strategy run is **not commissioned**. The dedicated MetaQuotes demo observation is fresh; this is not proof of a running strategy executor. No broker order was manufactured or placed during this continuation. GOAT remains manual-only and LIVE AUTO remains blocked.

## Verified changes

- Expire only never-submitted queue leases. Committed submission intents and uncertain broker outcomes survive expiration and restart.
- Require a committed submission intent before adopting a matching broker lifecycle; recognise active pending orders before they enter historical-order records.
- Keep manual-alert quarantine in the demo admission and submission paths. Explicitly block a queued decision if it was manually filled and closed before submission. Recheck it after reacquiring account locks. A manually executed decision cannot subsequently be reused by AUTO, even after its position closes.
- Add authenticated explicit manual ticket binding (`POST /fx101/mt5/manual/bind`): require a delivered alert, fresh complete account-bound history, matching symbol/side/window, manual broker identity and unmixed position history. Never infer fills from similar prices. Binding is immutable and unique per account/order. Actual broker exits update the bound alert; uncertain or mixed states retain quarantine. This does not authorise funded AUTO or guarantee the safety of a manual trade.
- Add prospective demo flat-reset continuity on an explicitly labelled fixed 22:00 UTC demo clock. Closely bracketed, flat, equal-balance observations plus complete history and absence of intervening activity provide a durable reset proof. Preserve peaks, initial balance, commands and reservations. Reject missing/conflicting boundary evidence, hidden round trips, changed balances, multiple missed boundaries and open exposure without a boundary valuation. This clock is not verified as the GOAT firm's timezone.
- Expose demo enablement, epoch validity and command counts separately from transport health. Snapshot freshness does not attest the attached executor binary.

## Evidence

`docs/evidence/continuation-backend-tests.log`: 204 backend tests and eight subtests pass. This includes unchanged frozen RFBC regressions; deterministic tests cannot prove broker execution.

`docs/evidence/continuation-remote-write-evidence.json` and `continuation-remote-recovery-evidence.json`: actual Neon Postgres on the existing isolated validation branch, with an isolated fixture schema. Verified committed intent reuse, explicit manual binding, durable reset proof and recovery in a separate process. No MT5 requests, broker orders or Telegram I/O occur in this fixture harness. `tools/validate_dnb_continuation.py` makes these checks reproducible.

`docs/evidence/continuation-gdesk-read.json`: actual owned mailbox read; its decision was an old SYSTEM_FAILURE, rejected as stale. Publication was not changed. The running RFBC consumer reported genuine NO_TRADE/stale-window results.

`docs/evidence/continuation-native-state.json`: native sources remain identical to the checkpoint compilation dependencies. A new compiler invocation did not create a compiler log; Wine terminal launch exited 159. No new native compilation or test execution is claimed, and no strategy executor was installed or armed.

## Remaining blockers

Authenticated native strategy SL/TP modifications and their lost-response recovery; protection and attribution for merged netting scale-ins; exact boundary valuation with open exposure; full native management/scale-in failure tests; final executor installation and commissioning; real genuine-signal entry/exit, notification and manual-fill E2E evidence; backend/terminal restart after actual genuine broker acceptance; extended outage and reboot validation.

G_DESK publication is stale and fails closed. No stale decision was republished and no signal/risk gate was relaxed to obtain a trade. Continuous operation is also not guaranteed by the current free gateway hosting.

GOAT additionally requires written architecture approval and verified historical/daily/payout risk anchors. Those blocks remain independent of demo validation.

Frozen RFBC files, G_DESK publication and automations were not edited. Remote `strategy2-round2-wip` was observed at `b2c372eeeeb2774705b2bc1b82058fec11908a27`; all changes and deployment target only `feature/mt5-goat-auto` and the dedicated dnb gateway.

## Runtime verification after release

Backend implementation commit: `1a00f717e4ad67752e5b91371cd0e9e9897fbb81`, pushed only to `feature/mt5-goat-auto`. Dedicated Render release: `dep-db7t86mk1f9s73culf0g`. The final deployment status and authenticated running state are saved in `docs/evidence/continuation-runtime.json` and `continuation-deploy.json`.

At 22:14:35 Africa/Kampala on 14 October, the permanent health endpoint returned HTTP 200, durable Postgres, SHADOW, AUTO unavailable. Exact demo account `5057377621` / `MetaQuotes-Demo` had a fresh two-second observation, balance/equity $2,476.79, zero positions/orders and 18 contracts. Complete broker history was 25 seconds old with two historical orders and three deals, unchanged from the prior isolated synthetic transport test. No new broker order was sent during this continuation.

The new authenticated demo execution status reported `enabled=false`, `new_risk_blocked=true`, `epoch=null` and empty command counts. This is active observation and analysis consumption, **not a running strategy executor**. RFBC reported NO_TRADE with stale-window outcomes; the G_DESK consumer rejected the old mailbox decision as `source_stale_or_future`.

Funded status remains `kill_switch=true`, SHADOW, `auto_available=false`; its account observation is stale and cannot establish current funded exposure. The native executor was not installed or armed. Frozen sources, the production branch, publication and automations remain unchanged.

Render still reported `update_in_progress` during verification even while the new endpoints served HTTP 200. Deployment completion must be checked separately; no successful final rollout is inferred from application responses. Build-stage customization warnings referenced packages before installation, while the dedicated runtime subsequently served broker state and source health.

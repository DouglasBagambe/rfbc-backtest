# Fx101 MT5 Bridge — GOAT Stride

## Scope

First-party MQL5 EA for the user's GOAT Stride / Instant HERO $2,500 account.

Verified account:
- MT5 login: 315307814
- Server: GoatFunded-Server
- Symbol suffix: .x
- Current build mode: SHADOW by default

The EA never uses the trading password outside MT5 and never sends credentials to Render.

## Safety policy

Firm rules researched on 2026-10-14:
- 3% daily drawdown
- 5% trailing maximum loss
- 1% maximum floating loss
- no hedging
- first-party EA only
- no VPS/VPN/proxy/hosted trading during trading activity

Internal guards are stricter:
- 0.50% max new-trade risk
- 0.75% aggregate open risk
- 0.80% floating-loss guard
- 2.50% daily drawdown guard
- 4.50% trailing drawdown guard

The EA reads manual positions and pending orders and includes them in its risk checks.

## Architecture

G_DESK / RFBC -> Fx101 Render -> authenticated MT5 bridge -> local MT5 terminal.

GitHub remains the G_DESK analysis mailbox only. It is not the live broker execution queue.

## Install for SHADOW validation

1. In MT5 choose File -> Open Data Folder.
2. Copy `mt5/Fx101GoatBridge.mq5` to `MQL5/Experts/`.
3. Open MetaEditor and compile `Fx101GoatBridge.mq5`.
4. In MT5: Tools -> Options -> Expert Advisors -> allow WebRequest for:
   `https://rfbc-usdjpy-monitor.onrender.com`
5. Attach the EA to one chart only.
6. Set:
   - Expected login = 315307814
   - Expected server = GoatFunded-Server
   - Mode = SHADOW
   - Bridge token = the same private token configured in Render
7. Algo Trading may remain OFF during SHADOW testing.

## Promotion gate to AUTO

Do not switch to AUTO until all pass:
- fresh broker snapshot appears in `/fx101/mt5/status`
- balance/equity match MT5 exactly
- all manual positions/orders appear
- wrong-account/server test fails closed
- duplicate/hedge test fails closed
- no-SL existing position fails closed
- stale-command replay cannot place twice
- SHADOW command shows correct calculated lot and monetary risk
- terminal restart resumes safely without duplicate execution

AUTO requires both:
- Render `FX101_MT5_EXECUTION_MODE=AUTO`
- local EA `Mode=AUTO`

Either side remaining SHADOW prevents live execution.

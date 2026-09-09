# Exness USDJPYc Broker-Specific Validation Plan

Target account: Exness Standard Cent, MT5, symbol `USDJPYc`.

## Broker facts to verify from live MT5 symbol properties
Do not trust web averages for execution-critical values. Record directly from MT5:
- symbol name
- digits / point size
- contract size
- minimum volume
- volume step
- maximum volume
- tick size
- tick value / tick value profit / tick value loss
- stop level
- freeze level
- swap long / short and swap mode
- triple-swap day
- trading sessions by weekday
- margin requirements / leverage behavior
- current spread and representative spread distribution

## Current Exness public references
- Standard Cent instruments use suffix `c`.
- Standard accounts use market execution; Standard Cent is available in the Standard account family.
- Exness exposes public tick history with bid and ask and explicitly states buy positions close at Bid and sell positions close at Ask.
- Real-time spreads and calculator values should be checked in the platform at execution time; public web values are indicative/average.

## Validation stages

### 1. Symbol audit
Export MT5 `USDJPYc` symbol properties and compare the pricing/point/volume conventions with the backtester.

### 2. Cost model
Collect at least several trading days of `USDJPYc` bid/ask snapshots, especially around:
- 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC
- Friday 16:00 UTC cutoff
- Asian/London/New York overlap
- rollover period

Report median, P90, P95 and worst observed spread. Do not change strategy rules because of these observations; use them only to stress-test costs.

### 3. Sizing audit
Implement broker-native position sizing from actual MT5 symbol metadata. Risk sizing must target a fixed percentage of account equity based on the frozen 1.50×ATR stop distance, then round DOWN to the broker volume step. If the minimum tradable volume would exceed the risk cap, skip the trade.

### 4. Swap / overnight audit
Quantify historical or representative swap impact for the strategy's holding periods. If swap-free applies to this exact account/instrument, verify it from account/symbol state rather than assuming it.

### 5. Execution stress tests
Re-run Candidate A with:
- observed median spread
- observed P95 spread
- conservative adverse slippage scenarios
- Friday close spread stress
- rollover spread stress where applicable

No parameter retuning.

### 6. Forward shadow mode
Before any live order placement, run the exact frozen detector against `USDJPYc` in alert-only mode for at least 20 qualifying signals or a reasonable calendar window. For every signal record:
- signal timestamp
- D1 regime values
- ATR
- breakout level
- signal true range
- next-H4 open
- chase displacement
- theoretical entry/SL/TP
- observed bid/ask spread
- theoretical R outcome

### 7. Promotion gate
Only consider tiny real-money execution if:
- broker-cost stress tests retain positive expectancy and PF >1
- sizing is exact and minimum lot does not force excess risk
- forward shadow signals match backtest rule evaluation
- no timestamp/session mismatch is discovered
- no operational safety issue remains

## Safety
No real trade should be opened by this validation work. Any later live executor must include duplicate prevention, stale-data lockout, max risk per trade, max daily loss, max total drawdown, max concurrent positions, and a kill switch.

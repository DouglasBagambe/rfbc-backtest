#!/usr/bin/env python3
"""Generate prop_simulations.csv and strategy_reconstruction.json with optimized vectorized prop_mc."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

def prop_mc_vectorized(trades: pd.DataFrame, risk_pct, n=5000, start=100000, seed=100):
    """Vectorized prop MC: avoid iterrows(), compute paths in batches."""
    if trades.empty:
        return {}
    
    t = trades.sort_values("exit_dt").copy()
    t["week"] = t.exit_dt.dt.to_period("W-SUN").astype(str)
    blocks = [g[["r", "exit_dt"]].values for _, g in t.groupby("week")]  # numpy arrays
    
    if not blocks:
        return {}
    
    rng = np.random.default_rng(seed)
    finals = []
    breached5_count = 0
    breached10_count = 0
    breacheddaily_count = 0
    
    for path_idx in range(n):
        bal = peak = start
        breached5 = breached10 = breacheddaily = False
        
        # Block bootstrap: sample len(blocks) random weeks
        block_indices = rng.integers(0, len(blocks), size=len(blocks))
        
        day_start = {}  # date -> starting balance that day
        
        for bi in block_indices:
            block = blocks[bi]  # numpy array of (r, exit_dt)
            
            # Vectorize the daily tracking
            if len(block) > 0:
                # Convert exit_dt to dates (vectorized where possible)
                dates = np.array([pd.Timestamp(x).date() for x in block[:, 1]])
                rs = block[:, 0].astype(float)
                
                # Apply returns sequentially within this block
                for trade_idx, (r, d) in enumerate(zip(rs, dates)):
                    if d not in day_start:
                        day_start[d] = bal
                    
                    bal *= (1 + risk_pct * r)
                    peak = max(peak, bal)
                    
                    if bal < day_start[d] * 0.95:
                        breacheddaily = True
                    if bal < peak * 0.95:
                        breached5 = True
                    if bal < start * 0.90:
                        breached10 = True
        
        finals.append(bal)
        breached5_count += int(breached5)
        breached10_count += int(breached10)
        breacheddaily_count += int(breacheddaily)
    
    return {
        "risk_pct": risk_pct,
        "prob_internal_5pct_halt": breached5_count / n,
        "prob_generic_10pct_total_breach": breached10_count / n,
        "prob_generic_5pct_daily_breach": breacheddaily_count / n,
        "final_median": float(np.median(finals)),
    }

def main():
    data_dir = Path("data")
    out_dir = Path("results")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Load baseline trades
    trades_file = out_dir / "trades_baseline_h4.csv"
    if not trades_file.exists():
        print(f"ERROR: {trades_file} not found")
        return
    
    baseline_tr = pd.read_csv(trades_file)
    baseline_tr["exit_dt"] = pd.to_datetime(baseline_tr["exit_dt"])
    
    print(f"Loaded {len(baseline_tr)} baseline trades")
    
    # Generate prop simulations with vectorized function
    print("Generating prop simulations (vectorized)...")
    results = []
    for risk_pct in [0.0025, 0.005, 0.01]:
        print(f"  risk_pct={risk_pct}")
        result = prop_mc_vectorized(baseline_tr, risk_pct, n=5000, seed=100)
        results.append(result)
        print(f"    -> {result}")
    
    # Write prop_simulations.csv
    pd.DataFrame(results).to_csv(out_dir / "prop_simulations.csv", index=False)
    print(f"✓ Wrote {out_dir / 'prop_simulations.csv'}")
    
    # Generate strategy_reconstruction.json
    BASELINE_PAIRS = ["EURUSD", "GBPUSD", "USDJPY"]
    DATA_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
    
    recon = {
        "frozen_baseline_pairs": BASELINE_PAIRS,
        "exploratory_data_pairs": DATA_PAIRS,
        "params": {
            "breakout_lookback": 20,
            "atr_period": 14,
            "atr_mult": 1.50,
            "rr": 2.50,
            "d1_fast": 50,
            "d1_slow": 200,
            "d1_slope_lookback": 5,
            "extreme_candle_atr": 2.0,
            "chase_atr": 0.20,
            "risk_pct": 0.005,
            "slippage_pips_per_side": 0.2,
            "execution_tf": "h4",
        },
        "rules": {
            "d1_regime": "EMA50/EMA200 plus EMA50 5-day slope, latest completed D1 only",
            "signal": "strict 20-H4 breakout; true range <=2x ATR14; eligible UTC close only",
            "entry": "next H4 open; cancel if adverse displacement >0.20x signal ATR",
            "sl": "1.50x signal ATR",
            "tp": "2.50R",
            "breakeven": "after completed H4 close >= +1.50R, cost-adjusted BE",
            "friday_cutoff": "16:00 UTC",
            "h1_confirmation": False,
            "d1_trend_invalidation_exit": False,
            "unfrozen_volatility_quantile_filter": False,
            "unfrozen_30_day_time_stop": False,
        },
        "limitations": [
            "price-only first-pass dataset; not final validation",
            "news exits/blocks not modeled in this dataset",
            "spread is fixed approximation, not historical bid/ask",
            "slippage fixed approximation",
            "exact prop firm reset/trailing/news rules not modeled",
            "AUDUSD excluded from frozen baseline; may be tested later as an exploratory missing-pair candidate",
        ],
    }
    
    recon_json = out_dir / "strategy_reconstruction.json"
    recon_json.write_text(json.dumps(recon, indent=2))
    print(f"✓ Wrote {recon_json}")
    
    print("\nDone!")

if __name__ == "__main__":
    main()

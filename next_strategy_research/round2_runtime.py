"""Runtime hardening for the frozen Round 2 engine.

Kept separate so the WIP implementation remains auditable. This module patches
only chronology/state construction; it does not alter thresholds or hypotheses.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import round2_exact as core


def freeze_expansion_strict(f: pd.DataFrame) -> pd.DataFrame:
    # Critical chronology correction: shift inside each UTC day/week group, not
    # after the transform, so no previous-day/week terminal value can bleed into
    # the first bar of the next group.
    f["day_hi_prev"] = f.groupby("date").high.transform(lambda s: s.expanding().max().shift(1))
    f["day_lo_prev"] = f.groupby("date").low.transform(lambda s: s.expanding().min().shift(1))
    f["day_range_prev"] = f.day_hi_prev - f.day_lo_prev

    asia = f.hour < 7
    london = (f.hour >= 7) & (f.hour < 16)
    f["asia_hi_prev"] = f.high.where(asia).groupby(f.date).transform(lambda s: s.expanding().max().shift(1))
    f["asia_lo_prev"] = f.low.where(asia).groupby(f.date).transform(lambda s: s.expanding().min().shift(1))
    f["london_hi_prev"] = f.high.where(london).groupby(f.date).transform(lambda s: s.expanding().max().shift(1))
    f["london_lo_prev"] = f.low.where(london).groupby(f.date).transform(lambda s: s.expanding().min().shift(1))

    week = f.index.to_period("W-SUN")
    f["week_hi_prev"] = f.high.groupby(week).transform(lambda s: s.expanding().max().shift(1))
    f["week_lo_prev"] = f.low.groupby(week).transform(lambda s: s.expanding().min().shift(1))
    f["new_week_extreme"] = (f.high > f.week_hi_prev) | (f.low < f.week_lo_prev)

    f["r2_impulse_dir"] = 0
    f["r2_impulse_open"] = np.nan
    f["r2_impulse_extreme"] = np.nan
    f["r2_impulse_time"] = pd.NaT

    for day, labels in f.groupby("date").groups.items():
        pos = f.index.get_indexer(labels)
        day_open = float(f.open.iloc[pos[0]])
        run_hi, run_lo = -np.inf, np.inf
        frozen = False
        for j in pos:
            old_hi, old_lo = run_hi, run_lo
            run_hi = max(run_hi, float(f.high.iloc[j]))
            run_lo = min(run_lo, float(f.low.iloc[j]))
            if frozen:
                continue
            median = f.range_med20.iloc[j]
            if not np.isfinite(median) or run_hi - run_lo < 0.90 * float(median):
                continue
            trend = f.h1_h1_trend.iloc[j]
            trend = int(trend) if np.isfinite(trend) else 0
            set_up_extreme = run_hi > old_hi
            set_down_extreme = run_lo < old_lo
            if trend == 1 and set_up_extreme:
                direction, extreme = 1, run_hi
            elif trend == -1 and set_down_extreme:
                direction, extreme = -1, run_lo
            else:
                continue
            remainder = pos[pos >= j]
            f.iloc[remainder, f.columns.get_loc("r2_impulse_dir")] = direction
            f.iloc[remainder, f.columns.get_loc("r2_impulse_open")] = day_open
            f.iloc[remainder, f.columns.get_loc("r2_impulse_extreme")] = extreme
            f.iloc[remainder, f.columns.get_loc("r2_impulse_time")] = f.index[j]
            frozen = True
    return f


# prepare() resolves this symbol from round2_exact at runtime, so replacing it
# here hardens every subsequent call without touching signal thresholds.
core._freeze_expansion = freeze_expansion_strict

# Re-export public engine API for the compatibility wrapper and tests.
PAIRS=core.PAIRS; USD_DIRECT=core.USD_DIRECT; USD_INVERSE=core.USD_INVERSE; USD_BASKET=core.USD_BASKET; JPY_BASKET=core.JPY_BASKET
DEV_START=core.DEV_START; DEV_END=core.DEV_END; END=core.END; GATE=core.GATE; COLS=core.COLS; Spec=core.Spec; SPECS=core.SPECS
pip=core.pip; tr=core.tr; atr=core.atr; read=core.read; h1_state=core.h1_state; fixed_window_baseline=core.fixed_window_baseline
prepare=core.prepare; synchronized_norm=core.synchronized_norm; build_cross_maps=core.build_cross_maps; attach_cross=core.attach_cross
sided=core.sided; sig=core.sig; execute=core.execute; pf=core.pf; summarize=core.summarize; main=core.main

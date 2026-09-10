"""Runtime hardening for the frozen Round 2 engine.

This module patches chronology/state construction plus the frozen cross-pair
basket integration. It does not alter strategy thresholds or the 2013-2020
screening window.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import round2_exact as core


def freeze_expansion_strict(f: pd.DataFrame) -> pd.DataFrame:
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
    # The source index is UTC-aware; preserve that dtype for frozen impulse
    # timestamps so assignments cannot coerce chronology to naive time.
    f["r2_impulse_time"] = pd.Series(pd.NaT, index=f.index, dtype="datetime64[ns, UTC]")

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


def build_cross_maps_strict(root):
    """Build timestamp-safe frozen S2R2-07/08/09 maps.

    Inner joins only; no forward-fill. Each H1 return is normalized by its own
    trailing ATR. Basket values become available one hour after the source H1
    timestamp.
    """
    usd = core.synchronized_norm(root, core.USD_BASKET)
    u = pd.DataFrame(index=usd.index)
    for p in core.USD_DIRECT:
        u[p] = -usd[p]
    for p in core.USD_INVERSE:
        u[p] = usd[p]
    u["median"] = u[list(core.USD_BASKET)].median(axis=1)
    u["strong_count"] = (u[list(core.USD_BASKET)] > 0).sum(axis=1)
    u["weak_count"] = (u[list(core.USD_BASKET)] < 0).sum(axis=1)
    u["candidate"] = u[list(core.USD_BASKET)].abs().idxmax(axis=1)
    u["direction"] = np.where(u["median"] >= 1.0, 1, np.where(u["median"] <= -1.0, -1, 0))
    u.loc[(u.direction == 1) & (u.strong_count < 3), "direction"] = 0
    u.loc[(u.direction == -1) & (u.weak_count < 3), "direction"] = 0
    u["source_h1"] = u.index
    u["available"] = u.index + pd.Timedelta(hours=1)

    j = core.synchronized_norm(root, core.JPY_BASKET)
    jj = pd.DataFrame(index=j.index)
    for p in core.JPY_BASKET:
        jj[p] = j[p]
    jj["median"] = jj[list(core.JPY_BASKET)].median(axis=1)
    jj["neg_count"] = (jj[list(core.JPY_BASKET)] < 0).sum(axis=1)
    jj["pos_count"] = (jj[list(core.JPY_BASKET)] > 0).sum(axis=1)
    jj["candidate"] = jj[list(core.JPY_BASKET)].abs().idxmax(axis=1)
    # Pair return < 0 means JPY strength; > 0 means JPY weakness.
    jj["direction"] = np.where(jj["median"] <= -0.75, -1, np.where(jj["median"] >= 0.75, 1, 0))
    jj.loc[(jj.direction == -1) & (jj.neg_count < 3), "direction"] = 0
    jj.loc[(jj.direction == 1) & (jj.pos_count < 3), "direction"] = 0
    jj["source_h1"] = jj.index
    jj["available"] = jj.index + pd.Timedelta(hours=1)

    # Frozen dislocation universe is only the four USD-quoted majors; each pair
    # is compared with the other three, not with dynamically selected pairs.
    majors = ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD")
    alln = core.synchronized_norm(root, majors)
    out = {"usd": u, "jpy": jj}
    for pair in core.PAIRS:
        if pair in majors:
            members = [p for p in majors if p != pair]
            x = alln[[pair] + members].copy()
            x["basket_median"] = x[members].median(axis=1)
            x["residual"] = x[pair] - x.basket_median
        else:
            x = pd.DataFrame(index=alln.index, columns=[pair, "basket_median", "residual"], dtype=float)
        x["source_h1"] = x.index
        x["available"] = x.index + pd.Timedelta(hours=1)
        out[f"dis:{pair}"] = x[[pair, "basket_median", "residual", "source_h1", "available"]]
    return out


_original_sig = core.sig

def sig_strict(f, pair, fam):
    # S2R2-06 frozen trigger has no extra basket breadth gate.
    if fam == "daily_expansion":
        h = f.hour
        quiet = f.day_range_prev <= .55 * f.range_med20
        long = (h >= 10) & (h <= 12) & quiet & (f.close > f.prior_day_high) & f.h1_h1_trend.eq(1)
        short = (h >= 10) & (h <= 12) & quiet & (f.close < f.prior_day_low) & f.h1_h1_trend.eq(-1)
        return core.sided(long, short)

    if fam == "usd_basket":
        if pair not in core.USD_BASKET:
            return np.zeros(len(f), dtype=int)
        active = f.usd_candidate.eq(pair) & f.minute.eq(0)
        # USD strength: sell direct USD-quoted majors, buy USD-base pairs.
        long = active & (((f.usd_direction == 1) & (pair in core.USD_INVERSE)) | ((f.usd_direction == -1) & (pair in core.USD_DIRECT)))
        short = active & (((f.usd_direction == 1) & (pair in core.USD_DIRECT)) | ((f.usd_direction == -1) & (pair in core.USD_INVERSE)))
        return core.sided(long, short)

    if fam == "jpy_basket":
        if pair not in core.JPY_BASKET:
            return np.zeros(len(f), dtype=int)
        active = f.jpy_candidate.eq(pair) & f.minute.eq(0)
        # Negative basket direction = JPY strength = short XXXJPY.
        return core.sided(active & (f.jpy_direction == 1), active & (f.jpy_direction == -1))

    if fam == "correlation_dislocation":
        if pair not in ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"):
            return np.zeros(len(f), dtype=int)
        mid = (f.h1_open + f.h1_close) / 2
        first = f.minute.eq(0)
        return core.sided(first & (f.dis_residual <= -1.5) & (f.close >= mid), first & (f.dis_residual >= 1.5) & (f.close <= mid))

    return _original_sig(f, pair, fam)


core._freeze_expansion = freeze_expansion_strict
core.build_cross_maps = build_cross_maps_strict
core.sig = sig_strict

PAIRS=core.PAIRS; USD_DIRECT=core.USD_DIRECT; USD_INVERSE=core.USD_INVERSE; USD_BASKET=core.USD_BASKET; JPY_BASKET=core.JPY_BASKET
DEV_START=core.DEV_START; DEV_END=core.DEV_END; END=core.END; GATE=core.GATE; COLS=core.COLS; Spec=core.Spec; SPECS=core.SPECS
pip=core.pip; tr=core.tr; atr=core.atr; read=core.read; h1_state=core.h1_state; fixed_window_baseline=core.fixed_window_baseline
prepare=core.prepare; synchronized_norm=core.synchronized_norm; build_cross_maps=core.build_cross_maps; attach_cross=core.attach_cross
sided=core.sided; sig=core.sig; execute=core.execute; pf=core.pf; summarize=core.summarize; main=core.main

if __name__ == "__main__":
    main()

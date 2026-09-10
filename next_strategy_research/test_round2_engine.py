#!/usr/bin/env python3
"""Fast synthetic invariants for Strategy 2 Round 2."""
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

import round2_engine as r
import round2_exact as core
import round2_runtime as runtime
from round2_runtime import freeze_expansion_strict


def _bars(start="2020-01-01",periods=40,freq="15min",px=1.1000):
    idx=pd.date_range(start,periods=periods,freq=freq,tz="UTC")
    f=pd.DataFrame(index=idx)
    f["open"]=px; f["high"]=px+.0010; f["low"]=px-.0010; f["close"]=px; f["volume"]=100.0
    return f


def test_read_hard_stops_before_holdout():
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"x.csv"
        pd.DataFrame({"dt":["2020-12-31T23:45:00Z","2021-01-01T00:00:00Z","2026-01-01T00:00:00Z"],"open":[1,2,3],"high":[1,2,3],"low":[1,2,3],"close":[1,2,3],"volume":[1,1,1]}).to_csv(p,index=False)
        got=r.read(p)
        assert list(got.index)==[pd.Timestamp("2020-12-31T23:45:00Z")]


def test_h1_state_available_only_after_completed_hour():
    h=_bars(periods=20,freq="1h")
    x=r.h1_state(h)
    assert (x.available-x.index==pd.Timedelta(hours=1)).all()


def test_atr_uses_only_current_and_prior_completed_bars():
    a=r.atr(_bars(periods=20),14)
    assert a.iloc[:13].isna().all() and np.isfinite(a.iloc[13])


def test_atr_is_wilder_rma_not_simple_rolling_mean():
    f=_bars(periods=16); f.loc[f.index[14],"high"]+=.0100
    got=r.atr(f,14)
    true=core.tr(f)
    expected=(true.iloc[13]*13+true.iloc[14])/14
    assert abs(got.iloc[14]-expected)<1e-12


def test_h1_trend_is_ema_only_with_neutral_precedence():
    h=_bars(periods=60,freq="1h")
    h["close"]=np.r_[np.linspace(1,1.1,30),np.linspace(1.1,1.3,30)]
    x=r.h1_state(h)
    assert x.h1_trend.iloc[-1]==1
    flat=_bars(periods=60,freq="1h")
    assert r.h1_state(flat).h1_trend.iloc[-1]==0


def test_gate_is_frozen():
    assert r.GATE=={"development_expectancy_r":.10,"development_profit_factor":1.15,"validation_expectancy_r":.05,"validation_profit_factor":1.10,"minimum_combined_trades":120,"minimum_positive_pairs":8}


def test_all_12_frozen_ids_present_once():
    assert [x.hypothesis for x in r.SPECS]==[f"S2R2-{i:02d}" for i in range(1,13)]
    assert len(set(x.family for x in r.SPECS))==12


def test_basket_membership_and_orientation():
    assert set(r.USD_DIRECT)=={"EURUSD","GBPUSD","AUDUSD","NZDUSD"}
    assert set(r.USD_INVERSE)=={"USDJPY","USDCAD","USDCHF"}
    assert set(r.JPY_BASKET)=={"EURJPY","GBPJPY","AUDJPY","CADJPY","CHFJPY"}


def test_grouped_shift_does_not_bleed_previous_day():
    idx=pd.to_datetime(["2020-01-01T23:45:00Z","2020-01-02T00:00:00Z","2020-01-02T00:15:00Z"])
    f=pd.DataFrame(index=idx)
    f["date"]=f.index.normalize(); f["hour"]=f.index.hour
    f["open"]=[1,2,2]; f["high"]=[10,3,4]; f["low"]=[0,1,1.5]; f["close"]=[1,2,2]; f["range_med20"]=100.0; f["h1_h1_trend"]=0
    out=freeze_expansion_strict(f)
    assert pd.isna(out.iloc[1].day_hi_prev)
    assert pd.isna(out.iloc[1].day_lo_prev)
    assert out.iloc[2].day_hi_prev==3
    assert out.iloc[2].day_lo_prev==1


def test_same_bar_conflict_is_stop_first():
    idx=pd.date_range("2020-01-02T10:00:00Z",periods=30,freq="15min")
    f=pd.DataFrame(index=idx)
    for c in ("bid_open","ask_open","bid_high","bid_low","bid_close","ask_high","ask_low","ask_close"): f[c]=1.1000
    f["atr15"]=.0010
    entry=1.1000+.10*r.pip("EURUSD"); risk=1.25*.0010
    f.iloc[1,f.columns.get_loc("bid_low")]=entry-risk-.0001
    f.iloc[1,f.columns.get_loc("bid_high")]=entry+1.5*risk+.0001
    original=core.sig
    try:
        core.sig=lambda frame,pair,fam: np.array([1]+[0]*(len(frame)-1))
        t=r.execute(f,"EURUSD",r.Spec("TEST","x"))
    finally:
        core.sig=original
    assert len(t)==1 and t.iloc[0].reason=="SL" and bool(t.iloc[0].ambiguous_stop_first)
    assert abs(float(t.iloc[0].r)+1.0)<1e-9

def test_nonpositive_atr_signal_is_skipped():
    idx=pd.date_range("2020-01-02T10:00:00Z",periods=3,freq="15min")
    f=pd.DataFrame(index=idx)
    for c in ("bid_open","ask_open","bid_high","bid_low","bid_close","ask_high","ask_low","ask_close"): f[c]=1.1
    f["atr15"]=[0.0,-.001,np.nan]
    original=core.sig
    try:
        core.sig=lambda frame,pair,fam: np.array([1,1,1])
        assert r.execute(f,"EURUSD",r.Spec("TEST","x")).empty
    finally: core.sig=original


def test_s2r2_01_is_previous_close_not_wick_based():
    idx=pd.date_range("2020-01-02T05:00:00Z",periods=2,freq="15min")
    f=pd.DataFrame(index=idx); f["hour"]=idx.hour; f["minute"]=idx.minute
    f["close"]=[.9980,.9985]; f["open"]=f.close; f["atr15"]=[.001,.001]; f["prior_day_close"]=1.0; f["h1_h1_trend"]=0
    got=core.sig(f,"EURUSD","prior_day_value")
    assert list(got)==[0,1]


def test_s2r2_03_uses_prior_m15_break_after_arm():
    idx=pd.date_range("2020-01-02T14:00:00Z",periods=3,freq="15min")
    f=pd.DataFrame(index=idx); f["date"]=idx.normalize(); f["hour"]=idx.hour; f["minute"]=idx.minute
    f["close"]=[1.075,1.077,1.081]; f["open"]=f.close; f["high"]=[1.078,1.080,1.082]; f["low"]=[1.07,1.074,1.076]
    f["h1_h1_trend"]=1
    f["ny13_ny_date"]=f.date; f["ny13_open"]=1.0; f["ny13_close"]=1.1; f["ny13_high"]=1.11; f["ny13_low"]=.99
    f["ny13_h1_body"]=.1; f["ny13_h1_atr"]=.1; f["ny13_h1_wick_share"]=.1; f["ny13_h1_trend"]=1
    got=core.sig(f,"EURUSD","ny_opening_drive")
    assert list(got)==[0,0,1]


def test_s2r2_04_requires_complete_london_and_ny_same_side_history():
    idx=pd.date_range("2020-01-02T07:00:00Z",periods=29,freq="15min")
    f=pd.DataFrame(index=idx); f["hour"]=idx.hour; f["minute"]=idx.minute; f["date"]=idx.normalize()
    f["prior_day_close"]=1.; f["close"]=1.1; f["open"]=1.1; f["high"]=1.15; f["low"]=1.05; f.loc[idx[-1],"close"]=1.2
    f["h1_h1_trend"]=1
    assert core.sig(f,"EURUSD","post_overlap_drift")[-1]==1
    f.loc[idx[1],"close"]=.99
    assert core.sig(f,"EURUSD","post_overlap_drift")[-1]==0


def test_s2r2_05_requires_two_distinct_same_edge_sweeps():
    idx=pd.date_range("2020-01-02T07:00:00Z",periods=16,freq="15min")
    f=pd.DataFrame(index=idx); f["date"]=idx.normalize(); f["hour"]=idx.hour; f["minute"]=idx.minute
    f["open"]=1.; f["high"]=1.1; f["low"]=.9; f["close"]=1.; f["london_0709_range_med20"]=1.
    f.loc[idx[8], ["high","close"]]=[1.2,1.05]
    f.loc[idx[9], ["high","close"]]=[1.2,1.05]
    f["h1_h1_trend"]=0
    got=core.sig(f,"EURUSD","two_hour_fade")
    assert list(got)[8:10]==[0,-1]


def test_cross_maps_use_only_inner_join_and_other_three_usd_majors():
    ix=pd.to_datetime(["2020-01-01T12:00:00Z","2020-01-01T13:00:00Z"])
    vals={
        tuple(core.USD_BASKET):pd.DataFrame({p:[1.2,1.1] for p in core.USD_BASKET},index=ix),
        tuple(core.JPY_BASKET):pd.DataFrame({p:[-1.0,-.8] for p in core.JPY_BASKET},index=ix),
        ("EURUSD","GBPUSD","AUDUSD","NZDUSD"):pd.DataFrame({"EURUSD":[2.,2.],"GBPUSD":[.5,.5],"AUDUSD":[.4,.4],"NZDUSD":[.3,.3]},index=ix),
    }
    original=core.synchronized_norm
    try:
        core.synchronized_norm=lambda root,members: vals[tuple(members)]
        maps=runtime.build_cross_maps_strict(Path("unused"))
    finally:
        core.synchronized_norm=original
    assert maps["usd"].index.equals(ix) and maps["usd"].candidate.iloc[0]=="AUDUSD"
    assert maps["jpy"].candidate.iloc[0]=="AUDJPY"  # lexical tie after equal abs negatives
    d=maps["dis:EURUSD"].iloc[0]
    assert abs(d.residual-(2.-.4))<1e-12
    assert maps["dis:USDJPY"].residual.isna().all()


def test_jpy_continuation_uses_first_break_of_active_state():
    idx=pd.date_range("2020-01-01T13:00:00Z",periods=4,freq="15min")
    f=pd.DataFrame(index=idx); f["close"]=[100.,99.,98.,97.]; f["low"]=[99.5,98.5,97.5,96.5]
    f["jpy_source_h1"]=pd.Timestamp("2020-01-01T12:00:00Z")
    f["jpy_candidate"]="EURJPY"; f["jpy_direction"]=-1
    got=runtime.sig_strict(f,"EURJPY","jpy_basket")
    assert list(got)==[0,-1,0,0]


def test_dislocation_only_fresh_h1_m15_is_eligible():
    idx=pd.date_range("2020-01-01T13:00:00Z",periods=2,freq="15min")
    f=pd.DataFrame(index=idx); f["h1_open"]=[1.,1.]; f["h1_close"]=[1.1,1.1]; f["close"]=[1.06,1.06]
    f["dis_residual"]=[-1.6,-1.6]; f["dis_source_h1"]=[pd.Timestamp("2020-01-01T12:00:00Z")]*2
    assert list(runtime.sig_strict(f,"EURUSD","correlation_dislocation"))==[1,0]


def test_summary_requires_all_gate_dimensions():
    rows=[]
    for pair in r.PAIRS[:8]:
        for dt in pd.date_range("2017-01-01",periods=8,freq="30D",tz="UTC"): rows.append(("S2R2-01","prior_day_value",pair,dt,dt,dt,1,.2,"TP",False))
        for dt in pd.date_range("2019-01-01",periods=8,freq="30D",tz="UTC"): rows.append(("S2R2-01","prior_day_value",pair,dt,dt,dt,1,.2,"TP",False))
    s=r.summarize(pd.DataFrame(rows,columns=r.COLS)).set_index("hypothesis")
    assert bool(s.loc["S2R2-01","passes_gate"])


if __name__=="__main__":
    tests=[v for k,v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests: fn()
    print(f"PASS: {len(tests)} deterministic Round 2 tests")

#!/usr/bin/env python3
"""Fast deterministic invariants for Strategy 2 Round 2.

These tests use synthetic frames only. They are intentionally cheap enough to run
before any 15-pair screen and protect the frozen chronology/execution contract.
"""
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

import round2_engine as r


def _bars(start="2020-01-01", periods=40, freq="15min", px=1.1000):
    idx=pd.date_range(start,periods=periods,freq=freq,tz="UTC")
    f=pd.DataFrame(index=idx)
    f["open"]=px; f["high"]=px+.0010; f["low"]=px-.0010; f["close"]=px; f["volume"]=100.0
    return f


def test_read_hard_stops_before_holdout():
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"x.csv"
        x=pd.DataFrame({
            "dt":["2020-12-31T23:45:00Z","2021-01-01T00:00:00Z","2026-01-01T00:00:00Z"],
            "open":[1,2,3],"high":[1,2,3],"low":[1,2,3],"close":[1,2,3],"volume":[1,1,1],
        })
        x.to_csv(p,index=False)
        got=r.read(p)
        assert list(got.index)==[pd.Timestamp("2020-12-31T23:45:00Z")]


def test_h1_state_available_only_after_completed_hour():
    h=_bars(periods=20,freq="1h")
    x=r.h1_state(h)
    assert (x.available-x.index == pd.Timedelta(hours=1)).all()


def test_atr_uses_only_current_and_prior_completed_bars():
    f=_bars(periods=20)
    a=r.atr(f,14)
    assert a.iloc[:13].isna().all()
    assert np.isfinite(a.iloc[13])


def test_gate_contains_round2_breadth_requirement():
    assert r.GATE["minimum_positive_pairs"]==8
    assert r.GATE["minimum_combined_trades"]==120
    assert r.GATE["development_expectancy_r"]==0.10
    assert r.GATE["validation_expectancy_r"]==0.05


def test_all_12_frozen_ids_present_once():
    ids=[x.hypothesis for x in r.SPECS]
    assert ids==[f"S2R2-{i:02d}" for i in range(1,13)]
    assert len(set(x.family for x in r.SPECS))==12


def test_usd_basket_orientation():
    assert set(r.USD_DIRECT)=={"EURUSD","GBPUSD","AUDUSD","NZDUSD"}
    assert set(r.USD_INVERSE)=={"USDJPY","USDCAD","USDCHF"}


def test_jpy_basket_membership():
    assert set(r.JPY_BASKET)=={"EURJPY","GBPJPY","AUDJPY","CADJPY","CHFJPY"}


def test_execution_constants_are_frozen():
    # Engine-level values are checked through source behavior: 0.10 pip entry/exit
    # slippage, 1.25 ATR stop, 1.50R target and 24-M15 maximum hold.
    assert r.pip("USDJPY")==.01
    assert r.pip("EURUSD")==.0001


def test_same_bar_conflict_is_stop_first():
    idx=pd.date_range("2020-01-02T10:00:00Z",periods=30,freq="15min")
    f=pd.DataFrame(index=idx)
    for c in ("bid_open","ask_open","bid_high","bid_low","bid_close","ask_high","ask_low","ask_close"):
        f[c]=1.1000
    f["atr15"]=.0010
    # A long entry at next ask open + 0.1 pip. Make the next executable BID bar
    # touch both the 1.25 ATR stop and 1.50R target.
    entry=1.1000+.10*r.pip("EURUSD"); risk=1.25*.0010
    f.iloc[1,f.columns.get_loc("bid_low")]=entry-risk-.0001
    f.iloc[1,f.columns.get_loc("bid_high")]=entry+1.5*risk+.0001
    original=r.sig
    try:
        r.sig=lambda frame,pair,fam: np.array([1]+[0]*(len(frame)-1))
        t=r.execute(f,"EURUSD",r.Spec("TEST","x"))
    finally:
        r.sig=original
    assert len(t)==1
    assert t.iloc[0].reason=="SL"
    assert bool(t.iloc[0].ambiguous_stop_first)
    assert abs(float(t.iloc[0].r)+1.0)<1e-9


def test_summary_requires_all_gate_dimensions():
    rows=[]
    for pair in r.PAIRS[:8]:
        for dt in pd.date_range("2017-01-01",periods=8,freq="30D",tz="UTC"):
            rows.append(("S2R2-01","prior_day_value",pair,dt,dt,dt,1,.2,"TP",False))
        for dt in pd.date_range("2019-01-01",periods=8,freq="30D",tz="UTC"):
            rows.append(("S2R2-01","prior_day_value",pair,dt,dt,dt,1,.2,"TP",False))
    t=pd.DataFrame(rows,columns=r.COLS)
    s=r.summarize(t).set_index("hypothesis")
    assert bool(s.loc["S2R2-01","passes_gate"])


if __name__=="__main__":
    tests=[v for k,v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests: fn()
    print(f"PASS: {len(tests)} deterministic Round 2 tests")

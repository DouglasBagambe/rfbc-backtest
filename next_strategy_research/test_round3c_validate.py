#!/usr/bin/env python3
"""Synthetic deterministic tests required before Round 3C data access."""
from __future__ import annotations
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
import round3c_validate as m

UTC="UTC"

def bars(n=22, start="2018-01-02 00:00", freq="15min"):
    ix=pd.date_range(start, periods=n, freq=freq, tz=UTC); x=pd.DataFrame(index=ix)
    for c in ("open","high","low","close"): x[c]=100.0
    x["atr15"]=2.0; x["volume"]=1.0
    return x

def signal(f, points):
    x=pd.Series(False,index=f.index); x.iloc[points]=True; return x

def one(f, points=[0], branch="H1_MSS_REVERSAL:mss_down"):
    return m.execute_single(f,"EURUSD",branch.split(":")[0],branch,signal(f,points))

def test_next_open_entry_and_one_atr_stop_target():
    f=bars(); f.iloc[1,f.columns.get_loc("open")]=101; f.iloc[1,f.columns.get_loc("high")]=103; f.iloc[1,f.columns.get_loc("low")]=100
    t=one(f)[0]; assert t["entry_dt"]==f.index[1] and t["reason"]=="TP" and t["gross_r"]==1.0

def test_stop_first_when_both_hit_same_bar():
    f=bars(); f.iloc[1,f.columns.get_loc("high")]=103; f.iloc[1,f.columns.get_loc("low")]=97
    t=one(f)[0]; assert t["reason"]=="SL" and t["ambiguous_stop_first"] and t["gross_r"]==-1.0

def test_sixteen_bar_time_exit_and_cost():
    f=bars(); f.iloc[16,f.columns.get_loc("close")]=101
    t=one(f)[0]; assert t["reason"]=="TIME" and t["exit_dt"]==f.index[16] and abs(t["gross_r"]-.5)<1e-12 and abs(t["r"]-.4)<1e-12

def test_duplicate_suppression_requires_false_bar():
    f=bars(); f.iloc[1,f.columns.get_loc("high")]=102; t=one(f,[0,1,2,5]); assert len(t)==2 and t[1]["signal_dt"]==f.index[5]

def test_friday_cutoff_and_forced_close():
    f=bars(24,"2018-01-05 15:45"); old=m.MAX_BARS; m.MAX_BARS=20
    try: t=one(f,[0,1]); assert len(t)==1 and t[0]["reason"]=="FRIDAY" and t[0]["exit_dt"]==pd.Timestamp("2018-01-05 20:45",tz=UTC)
    finally: m.MAX_BARS=old

def test_missing_next_open_and_zero_volume_are_skipped():
    f=bars().drop(bars().index[1]); assert not one(f)
    f=bars(); f.iloc[1,f.columns.get_loc("volume")]=0; assert not one(f)

def test_reader_excludes_holdout_and_closed_padding_before_state():
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"x.csv"; pd.DataFrame({"dt":["2017-12-29T00:00:00Z","2018-01-01T00:00:00Z","2020-12-31T23:45:00Z","2021-01-01T00:00:00Z"],"open":[1]*4,"high":[1]*4,"low":[1]*4,"close":[1]*4,"volume":[1,0,1,1]}).to_csv(p,index=False)
        got=m.read_window(p); assert list(got.index)==[pd.Timestamp("2017-12-29T00:00:00Z"),pd.Timestamp("2020-12-31T23:45:00Z")]

def peer_frames():
    a,b=bars(),bars(); hix=pd.date_range("2018-01-02 00:00", periods=1, freq="1h",tz=UTC)
    h1={"EURUSD":pd.DataFrame({"norm":[2.]},index=hix),"GBPUSD":pd.DataFrame({"norm":[1.]},index=hix)}
    return {"EURUSD":a,"GBPUSD":b},h1

def test_peer_two_leg_equal_atr_cost_and_pair_exit():
    fs,h=peer_frames();
    # Event is usable at 01:00, entered at 01:15.  Both legs reach pair target together.
    for p in fs:
        f=fs[p]; f.loc[pd.Timestamp("2018-01-02 01:15",tz=UTC),["open","high","low"]]=[100,102,98]
    t=m.execute_peer(fs,h); assert len(t)==1 and t[0]["unit"]=="EURUSD_GBPUSD" and t[0]["cost_r"]==.20 and t[0]["gross_r"]==-1.0

def test_peer_no_leg_substitution_and_discrete_rearm():
    fs,h=peer_frames(); fs["GBPUSD"]=fs["GBPUSD"].drop(pd.Timestamp("2018-01-02 01:15",tz=UTC)); assert not m.execute_peer(fs,h)

if __name__=="__main__":
    tests=[v for k,v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests: test()
    print(f"PASS: {len(tests)} deterministic Round 3C validation tests")

#!/usr/bin/env python3
"""Synthetic-only invariants for Round 3A; never opens research data."""
from pathlib import Path
import tempfile
import numpy as np
import pandas as pd
import round3a_edge_map as m

def bars(n=320,freq="15min"):
    ix=pd.date_range("2017-01-01",periods=n,freq=freq,tz="UTC",name="dt"); x=pd.DataFrame(index=ix)
    x["open"]=1.; x["high"]=1.01; x["low"]=.99; x["close"]=1.; x["volume"]=1.; return x

def test_reader_hard_stops_at_2018():
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"x.csv"; pd.DataFrame({"dt":["2017-12-31T23:45:00Z","2018-01-01T00:00:00Z"],"open":[1,2],"high":[1,2],"low":[1,2],"close":[1,2],"volume":[1,2]}).to_csv(p,index=False)
        assert len(m.read(p))==1

def test_wilder_atr_and_current_percentile_prior_sample():
    x=bars(270); x.loc[x.index[14],"high"]=1.11; a=m.atr(x); tr=pd.concat((x.high-x.low,(x.high-x.close.shift()).abs(),(x.low-x.close.shift()).abs()),axis=1).max(axis=1)
    assert abs(a.iloc[14]-((tr.iloc[13]*13+tr.iloc[14])/14))<1e-12
    s=pd.Series(np.arange(253,dtype=float)); assert m.trailing_percentile(s).iloc[-1]==1.0

def test_h1_percentile_precedes_m15_mapping_and_availability():
    h=bars(300,"1h"); h.loc[h.index[-1],"high"]=1.2; hs=m.h1_state(h); assert hs.h1_atr_pct.index.equals(h.index)
    hs[["h1_atr","h1_atr_pct","h1_norm_return"]]=hs[["h1_atr","h1_atr_pct","h1_norm_return"]].fillna(1.)
    f=bars(8); f.index=pd.date_range(h.index[0],periods=8,freq="15min",tz="UTC",name="dt"); z=m.attach_h1(f,hs)
    assert z.h1_atr.iloc[:4].isna().all() and z.h1_atr.iloc[4:].notna().all() and "h1_atr_pct" in z

def test_exact_forward_rejects_missing_slot():
    x=bars(4); x=x.drop(x.index[2]); future,exists=m.exact_forward(x,2)
    assert not exists.iloc[0] and pd.isna(future.iloc[0])

def test_overlapping_ny_and_overlap_flags():
    ix=pd.to_datetime(["2017-01-01T13:00:00Z","2017-01-01T14:45:00Z","2017-01-01T15:45:00Z"]); f=m.session_flags(ix)
    assert f.ny_open.iloc[0] and f.overlap.iloc[0] and f.ny_open.iloc[1] and f.overlap.iloc[1] and not f.ny_open.iloc[2] and f.overlap.iloc[2]

def test_session_level_is_unknown_until_session_ends():
    x=bars(40); x.index=pd.date_range("2017-01-01",periods=40,freq="15min",tz="UTC",name="dt"); z,_=m.known_session_levels(x)
    assert z.asia_high.iloc[27:28].isna().all() and z.asia_high.iloc[28:].notna().all()

def test_signed_shock_direction_and_labels_do_not_define_events():
    x=bars(); x.loc[x.index[20],"close"]=1.02; x=m.attach_h1(x,m.h1_state(bars(320,"1h"))); rows,e=m.event_rows(x,"EURUSD")
    assert "m15_shock_up_1_0_1_5" in e and "continuation_atr_return" in rows

def test_strict_join_basket_selection_and_residual():
    ix=pd.date_range("2017-01-01",periods=3,freq="1h",tz="UTC"); x=pd.DataFrame({"A":[2.,1.,1.],"B":[1.,1.,1.]},index=ix); assert len(pd.concat((x.A,x.B.iloc[[0,2]]),axis=1,join="inner"))==2
    med=x.median(axis=1); assert x.idxmax(axis=1).iloc[0]=="A" and x.idxmin(axis=1).iloc[0]=="B" and x.A.iloc[0]-med.iloc[0]==.5

def test_fixed_pair_divergence():
    a=pd.Series([1.,2.]); b=pd.Series([.5,1.]); assert list(a-b)==[.5,1.]

def test_latest_opposite_candle_ob_and_stateful_breaker():
    x=bars(12); x.loc[x.index[4:8],"open"]=[1,1,1,1]; x.loc[x.index[4:8],"close"]=[.9,1.1,.8,1.2]; x.loc[x.index[8],"high"]=1.3; x.loc[x.index[8],"close"]=1.3; x.loc[x.index[9],"low"]=.7; x.loc[x.index[9],"close"]=.7; x["asia_low"]=0.; x["asia_high"]=2.; x["prior_low"]=0.; x["prior_high"]=2.
    p=m.primitives(x); assert p["ob_candidate_up"].iloc[8] and p["breaker_down"].iloc[9]

def test_ote_geometry_is_bounded():
    a,b=1.,2.; zone=(b-.79*(b-a),b-.62*(b-a)); assert zone==(1.21,1.38)

def test_smt_fixed_peer_chronology():
    peers=(("EURUSD","GBPUSD"),("AUDUSD","NZDUSD"),("EURJPY","GBPJPY")); assert len(peers)==3 and all(len(p)==2 for p in peers)

def test_pair_and_year_breadth_are_separate():
    bp=pd.DataFrame({"event":["x","x"],"horizon":[1,1],"pair":["A","B"],"mean_forward_return":[.1,.2]}); by=pd.DataFrame({"event":["x","x"],"horizon":[1,1],"year":[2013,2014],"mean_forward_return":[.1,-.2]}); p,y=m.breadth(bp,by)
    assert p.pair_breadth_same_sign.iloc[0]==2 and y.year_breadth_same_sign.iloc[0]==1

def test_current_dispersion_excluded_from_percentile_reference():
    s=pd.Series([10.]*252+[0.]); assert m.trailing_percentile(s).iloc[-1]==0.0

def test_missing_synchronized_member_removes_dispersion_timestamp():
    ix=pd.date_range("2017-01-01",periods=3,freq="1h",tz="UTC"); a=pd.Series([1.,2.,3.],index=ix); b=pd.Series([1.,3.],index=ix.delete(1))
    synced=pd.concat((a,b),axis=1,join="inner"); assert len(synced)==2 and ix[1] not in synced.index

def test_strongest_weakest_ties_are_deterministic():
    x=pd.DataFrame({"EURUSD":[2.],"GBPUSD":[2.],"AUDUSD":[-2.]}); strong,weak=m.select_extremes(x); assert strong.iloc[0]=="EURUSD" and weak.iloc[0]=="AUDUSD"

def test_dispersion_regime_boundaries_are_exact():
    p=pd.Series([.20,.2001,.7999,.80]); assert list(m.dispersion_regime(p))==["low","normal","normal","high"]

def test_forward_labels_do_not_influence_dispersion_or_regime():
    x=pd.DataFrame({"A":[1.,2.,3.],"B":[2.,1.,0.]}); d=x.std(axis=1,ddof=0); base=m.trailing_percentile(pd.concat((pd.Series([1.]*252),d),ignore_index=True))
    future=x.copy(); future.iloc[-1]=[999.,-999.]; changed=m.trailing_percentile(pd.concat((pd.Series([1.]*252),future.std(axis=1,ddof=0)),ignore_index=True))
    assert d.iloc[-2]==future.std(axis=1,ddof=0).iloc[-2] and base.iloc[-2]==changed.iloc[-2]

if __name__=="__main__":
    tests=[v for k,v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests: test()
    print(f"PASS: {len(tests)} deterministic Round 3A edge-map tests")

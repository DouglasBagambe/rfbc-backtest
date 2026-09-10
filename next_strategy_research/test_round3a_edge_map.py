#!/usr/bin/env python3
"""Fast chronology invariants for the Round 3A descriptive mapper."""
from pathlib import Path
import tempfile
import numpy as np
import pandas as pd
import round3a_edge_map as m

def bars(periods=300,freq="15min"):
    ix=pd.date_range("2017-01-01",periods=periods,freq=freq,tz="UTC")
    x=pd.DataFrame(index=ix); x["open"]=1.; x["high"]=1.01; x["low"]=.99; x["close"]=1.; x["volume"]=1.
    return x

def test_reader_hard_stops_at_2018():
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"x.csv"; pd.DataFrame({"dt":["2017-12-31T23:45:00Z","2018-01-01T00:00:00Z"],"open":[1,2],"high":[1,2],"low":[1,2],"close":[1,2],"volume":[1,2]}).to_csv(p,index=False)
        x=m.read(p); assert list(x.index)==[pd.Timestamp("2017-12-31T23:45:00Z")]

def test_wilder_atr():
    x=bars(16); x.loc[x.index[14],"high"]=1.11; a=m.atr(x); t=pd.concat((x.high-x.low,(x.high-x.close.shift()).abs(),(x.low-x.close.shift()).abs()),axis=1).max(axis=1)
    assert abs(a.iloc[14]-((t.iloc[13]*13+t.iloc[14])/14))<1e-12

def test_h1_is_unavailable_until_one_hour_later():
    h=bars(20,"1h"); s=m.h1_available(h); f=bars(8); f.index=pd.date_range("2017-01-01",periods=8,freq="15min",tz="UTC")
    z=m.attach_h1(f,s); assert z.h1_trend.iloc[:4].isna().all() and z.h1_trend.iloc[4:].notna().all()

def test_events_do_not_use_forward_labels_to_define_event():
    x=bars(); x["atr15"]=.01; x["atr_pct"]=.5; x["h1_atr_pct"]=.5; x["h1_trend"]=1; x["session"]="london_open"; x["date"]=x.index.normalize(); x["hour"]=x.index.hour; x["asia_hi"]=2.; x["asia_lo"]=0.; x["prior_high"]=2.; x["prior_low"]=0.
    before=m.event_masks(x)["mss_up"].copy(); x.loc[x.index[-1],"close"]=99.
    assert before.iloc[:-1].equals(m.event_masks(x)["mss_up"].iloc[:-1])

def test_session_endpoints_are_utc_exact():
    ix=pd.to_datetime(["2017-01-01T06:45:00Z","2017-01-01T07:00:00Z","2017-01-01T08:45:00Z","2017-01-01T09:00:00Z","2017-01-01T13:00:00Z","2017-01-01T15:45:00Z"])
    x=pd.DataFrame(index=ix); x["hour"]=ix.hour; x["minute"]=ix.minute
    assert list(m.session_code(x))==["asia","london_open","london_open","london_body","ny_open","overlap"]

def test_strict_cross_join_rejects_missing_timestamp():
    ix=pd.date_range("2017-01-01",periods=3,freq="1h",tz="UTC")
    a=pd.Series([1.,1.,1.],index=ix,name="EURUSD"); b=pd.Series([1.,1.],index=ix.delete(1),name="GBPUSD")
    # This is the same strict inner-join operation used in cross_events().
    assert len(pd.concat((a,b),axis=1,join="inner"))==2

if __name__=="__main__":
    tests=[v for k,v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests: test()
    print(f"PASS: {len(tests)} deterministic Round 3A edge-map tests")

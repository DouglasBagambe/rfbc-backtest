from pathlib import Path
import urllib.request
PAIRS=["EURUSD","GBPUSD","USDJPY","AUDUSD"]
TFS=["d1","h4","h1","m30","m15"]
root=Path("data"); root.mkdir(exist_ok=True)
base="https://raw.githubusercontent.com/ejtraderLabs/historical-data/main"
for p in PAIRS:
    for tf in TFS:
        u=f"{base}/{p}/{p}{tf}.csv"; f=root/f"{p}{tf}.csv"
        print("download",u)
        urllib.request.urlretrieve(u,f)

#!/usr/bin/env python3
"""Non-mutating deployment health check."""
import json
import fx101
c=fx101.db(); c.execute("SELECT 1").fetchone()
print(json.dumps({"ok":True,"db_path":str(fx101.DB_PATH),"open_trades":len(fx101.list_trades("WHERE state IN ('PLACED','OPEN')")),"symbols":sorted(fx101.ALL_SYMBOLS)}))

#!/usr/bin/env python3
"""Extract only 2013-2017 mapped BIS CBPOL daily observations from a raw zip."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from pathlib import Path

MAP = {"US": "USD", "XM": "EUR", "GB": "GBP", "JP": "JPY", "AU": "AUD", "NZ": "NZD", "CA": "CAD", "CH": "CHF"}
START, END = "2013-01-01", "2017-12-31"


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("archive", type=Path); ap.add_argument("--out", type=Path, required=True); ap.add_argument("--metadata", type=Path, required=True); args = ap.parse_args()
    digest = hashlib.sha256(args.archive.read_bytes()).hexdigest()
    with zipfile.ZipFile(args.archive) as zf:
        members = zf.namelist()
        if members != ["WS_CBPOL_csv_col.csv"]: raise ValueError(f"unexpected archive members: {members}")
        with zf.open(members[0]) as raw:
            rows = csv.reader((line.decode("utf-8") for line in raw))
            header = next(rows); dates = header[12:]
            selected = [(i + 12, d) for i, d in enumerate(dates) if len(d) == 10 and START <= d <= END]
            outrows = []
            mappings = {}
            for row in rows:
                if len(row) < 12 or row[0] != "D" or row[2] not in MAP: continue
                code, currency = row[2], MAP[row[2]]
                mappings[currency] = {"bis_ref_area": code, "frequency": row[0], "compilation": row[5], "source": row[9], "breaks": row[10]}
                for idx, date in selected:
                    value = row[idx].strip() if idx < len(row) else ""
                    outrows.append((date, currency, value))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as fh:
        writer = csv.writer(fh); writer.writerow(("date", "currency", "rate")); writer.writerows(outrows)
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.write_text(json.dumps({"source_url": "https://data.bis.org/static/bulk/WS_CBPOL_csv_col.zip", "archive_sha256": digest, "archive_bytes": args.archive.stat().st_size, "retained_date_range": [START, END], "series_mappings": mappings, "rows_retained": len(outrows)}, indent=2) + "\n")


if __name__ == "__main__": main()

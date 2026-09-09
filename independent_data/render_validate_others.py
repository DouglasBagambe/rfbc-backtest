#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path

import requests
from flask import Flask, jsonify

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = [
    "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF",
    "EURJPY", "GBPJPY", "AUDJPY", "CADJPY", "CHFJPY",
    "EURGBP", "EURAUD", "GBPAUD",
]
STATUS = {
    "state": "starting",
    "step": None,
    "pair": None,
    "completed": [],
    "remaining": UNIVERSE.copy(),
    "results": {},
    "error": None,
}
app = Flask(__name__)


def run_cmd(label, cmd):
    STATUS.update(state="running", step=label)
    p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"{label} failed\nSTDOUT:\n{p.stdout[-8000:]}\nSTDERR:\n{p.stderr[-8000:]}")
    return p.stdout


def keepalive():
    url = os.getenv("KEEPALIVE_URL", "").strip()
    if not url:
        return
    while STATUS.get("state") not in {"done", "error"}:
        time.sleep(600)
        try:
            requests.get(url.rstrip("/") + "/health", timeout=30)
        except Exception:
            pass


def worker():
    try:
        for pair in UNIVERSE:
            STATUS.update(pair=pair, remaining=[p for p in UNIVERSE if p not in STATUS["completed"]])
            run_cmd(f"download:{pair}", [
                "python3", "independent_data/download_dukascopy_h1.py",
                "--pairs", pair, "--start", "2013-01-01", "--end", "2026-09-01",
            ])
            run_cmd(f"build_bars:{pair}", [
                "python3", "independent_data/build_bars.py",
                "--pairs", pair, "--start", "2013-01-01", "--end", "2026-09-01",
            ])
            outdir = ROOT / "results_external_discovery" / pair
            stdout = run_cmd(f"validate:{pair}", [
                "python3", "independent_data/run_external_frozen_pairs.py",
                "--pairs", pair, "--out", str(outdir),
            ])
            decisions_path = outdir / "decisions.json"
            metrics_path = outdir / "pair_period_metrics.csv"
            mc_path = outdir / "monte_carlo.csv"
            result = {
                "decision": json.loads(decisions_path.read_text()).get(pair) if decisions_path.exists() else None,
                "metrics_csv": metrics_path.read_text() if metrics_path.exists() else None,
                "monte_carlo_csv": mc_path.read_text() if mc_path.exists() else None,
                "stdout_tail": stdout[-2000:],
            }
            STATUS["results"][pair] = result
            STATUS["completed"].append(pair)
            STATUS["remaining"] = [p for p in UNIVERSE if p not in STATUS["completed"]]

        STATUS.update(state="done", step="complete", pair=None, remaining=[])
    except Exception as exc:
        STATUS.update(state="error", error=f"{type(exc).__name__}: {exc}")


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "service": "rfbc-other-pairs-validator",
        "state": STATUS.get("state"),
        "pair": STATUS.get("pair"),
        "completed": len(STATUS.get("completed", [])),
        "total": len(UNIVERSE),
    })


@app.get("/status")
def status():
    return jsonify(STATUS)


if __name__ == "__main__":
    threading.Thread(target=keepalive, daemon=True).start()
    threading.Thread(target=worker, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)

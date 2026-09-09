#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

from flask import Flask, jsonify

ROOT = Path(__file__).resolve().parents[1]
STATUS = {"state": "starting", "step": None, "error": None}
app = Flask(__name__)


def run_cmd(label, cmd):
    STATUS.update(state="running", step=label)
    p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"{label} failed\nSTDOUT:\n{p.stdout[-8000:]}\nSTDERR:\n{p.stderr[-8000:]}")
    return p.stdout


def worker():
    try:
        pairs = ["EURUSD", "GBPUSD", "AUDUSD"]
        run_cmd("download", [
            "python3", "independent_data/download_dukascopy_h1.py",
            "--pairs", *pairs, "--start", "2013-01-01", "--end", "2026-09-01",
        ])
        run_cmd("build_bars", [
            "python3", "independent_data/build_bars.py",
            "--pairs", *pairs, "--start", "2013-01-01", "--end", "2026-09-01",
        ])
        stdout = run_cmd("validate", [
            "python3", "independent_data/run_external_frozen_pairs.py",
            "--pairs", *pairs,
        ])
        report = ROOT / "results_external_other_pairs" / "decisions.json"
        metrics = ROOT / "results_external_other_pairs" / "pair_period_metrics.csv"
        mc = ROOT / "results_external_other_pairs" / "monte_carlo.csv"
        STATUS.update(
            state="done",
            step="complete",
            decisions=json.loads(report.read_text()) if report.exists() else None,
            metrics_csv=metrics.read_text() if metrics.exists() else None,
            monte_carlo_csv=mc.read_text() if mc.exists() else None,
            stdout_tail=stdout[-4000:],
        )
    except Exception as exc:
        STATUS.update(state="error", error=f"{type(exc).__name__}: {exc}")


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "rfbc-other-pairs-validator", "state": STATUS.get("state")})


@app.get("/status")
def status():
    return jsonify(STATUS)


if __name__ == "__main__":
    threading.Thread(target=worker, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)

"""Analyse aligned input/output recordings of the device experiment.

This is the measurement half of Experiment A. It does not play audio and does
not modify the recordings. It expects one electrical input file and one
acoustic output file per crest condition, as described in
`research/EXPERIMENT_DESIGN.md`.

Manifest:
{
  "band_hz": [3840, 7680],
  "reference_crest": 3,
  "conditions": [
    {"crest": 3,  "input": "in_03.wav",  "output": "out_03.wav"},
    {"crest": 6,  "input": "in_06.wav",  "output": "out_06.wav"}
  ]
}

Run:
    python3 research/experiments/device_measure.py --manifest run.json \
        --out result.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from research import metrics as M  # noqa: E402
from research.experiments import analysis  # noqa: E402

SR = 48000


def _read(path):
    x, sr = sf.read(os.path.expanduser(path), dtype="float64", always_2d=True)
    if sr != SR:
        raise ValueError(f"{path}: {sr} Hz; need {SR}")
    if x.shape[1] > 2:
        x = x[:, :2]
    if x.shape[1] == 1:
        x = np.stack([x[:, 0], x[:, 0]], axis=1)
    return x


def _delay_frames(x_in, x_out):
    a = M.broadband_envelope(x_in)
    b = M.broadband_envelope(x_out)
    n = min(len(a), len(b))
    a, b = a[:n] - a[:n].mean(), b[:n] - b[:n].mean()
    c = np.correlate(b, a, mode="full")
    lag = int(np.argmax(c) - (n - 1))
    return lag


def _body(x, lo, hi, mask_src=None, shift=0):
    e, n, hop = M.band_envelope(x, lo, hi)
    if mask_src is None:
        et = M.broadband_envelope(x)
        mask = M.activity_mask(et)
        mask = M.map_mask(mask, 1024, hop, len(e))
    else:
        mask = M.map_mask(mask_src, 1024, hop, len(e))
    if shift:
        e = np.roll(e, shift)
    ea = e[mask]
    if len(ea) < 100:
        return None, len(ea)
    return float(np.percentile(ea, 75)), len(ea)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--delta", type=float, default=2.0)
    a = ap.parse_args(argv)
    with open(a.manifest) as fh:
        man = json.load(fh)
    lo, hi = man["band_hz"]
    rows, curves = [], []
    ref_crest = man.get("reference_crest")
    for cond in man["conditions"]:
        xin = _read(cond["input"])
        xout = _read(cond["output"])
        n = min(len(xin), len(xout))
        xin, xout = xin[:n], xout[:n]
        lag = _delay_frames(xin, xout)
        et = M.broadband_envelope(xin)
        mask = M.activity_mask(et)
        b_in, n_in = _body(xin, lo, hi, mask, 0)
        b_out, n_out = _body(xout, lo, hi, mask, lag)
        if b_in is None or b_out is None:
            raise SystemExit(f"crest {cond['crest']}: not enough active frames")
        rows.append({"crest": float(cond["crest"]), "B_in": b_in,
                     "B_out": b_out, "n_in": n_in, "n_out": n_out,
                     "lag_frames": lag})
    if ref_crest is None:
        ref_crest = min(r["crest"] for r in rows)
    ref = min(rows, key=lambda r: abs(r["crest"] - ref_crest))
    for r in rows:
        r["pc_db"] = ((r["B_out"] - ref["B_out"])
                      - (r["B_in"] - ref["B_in"]))
        curves.append({"crest": r["crest"], "pc": r["pc_db"]})
    k = analysis.k_from_curve([r["crest"] for r in rows],
                              [r["pc_db"] for r in rows], delta=a.delta)
    out = {"band_hz": [lo, hi], "reference_crest": ref["crest"],
           "delta_db": a.delta, "rows": rows, "k": k}
    text = json.dumps(out, indent=1)
    if a.out:
        with open(a.out, "w") as fh:
            fh.write(text)
        print(f"written: {a.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

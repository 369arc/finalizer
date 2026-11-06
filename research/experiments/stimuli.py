"""Crest-controlled stimuli for the device experiment.

The stimulus is a band-limited noise with a body, a quiet gap and a burst:

    body (8 s) -> gap (1 s) -> burst (1 s) -> ...   period 10 s

The body occupies 80 % of the active frames, so the 75th percentile is the
body; the burst occupies 10 %, so the 99.5th percentile is the burst. The
burst gain is the nominal crest. The script verifies the stimulus with
`research.metrics` and prints the measured C_tail/C_max; it does not modify
any source audio.

This is a *stimulus generator*, not a mastering tool. The output is a test
signal, not a candidate master.

Run:
    python3 research/experiments/stimuli.py --lo 3840 --hi 7680 --crest 9 \
        --out /tmp/probe.wav
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from research import metrics as M  # noqa: E402

SR = 48000


def band_noise(n, lo, hi, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n)
    sos = butter(8, [lo / (SR / 2), min(hi / (SR / 2), 0.99)],
                 btype="band", output="sos")
    y = sosfilt(sos, x)
    return y / (np.sqrt(np.mean(y ** 2)) + 1e-12)


def make_stimulus(lo, hi, crest_db, dur=60.0, period=10.0, body_s=8.0,
                  burst_s=1.0, body_db=-30.0, gap_db=-60.0, bed_db=None,
                  seed=0):
    """Return (stereo signal, metadata). Levels are dBFS, crest is dB."""
    if body_s / period < 0.75:
        raise ValueError("body must occupy >= 75 % of the period for P75 to be the body")
    if burst_s / period < 0.01:
        raise ValueError("burst must occupy >= 1 % of the period for P99.5 to see it")
    n = int(dur * SR)
    base = band_noise(n, lo, hi, seed)
    env = np.ones(n)
    gap_s = max(0.0, period - body_s - burst_s)
    for s in range(0, n, int(period * SR)):
        a = s + int(body_s * SR)
        b = a + int(gap_s * SR)
        c = b + int(burst_s * SR)
        env[a:b] = 10 ** ((gap_db - body_db) / 20)
        env[b:min(c, n)] = 10 ** (crest_db / 20)
    x = base * env * 10 ** (body_db / 20)
    if bed_db is not None:
        bed = band_noise(n, 100, 2000, seed + 1)
        bed = bed / (np.sqrt(np.mean(bed ** 2)) + 1e-12) * 10 ** (bed_db / 20)
        x = x + bed
    x = np.stack([x, x], axis=1).astype(np.float32)
    meta = {"band_hz": [lo, hi], "crest_db": crest_db, "dur_s": dur,
            "period_s": period, "body_s": body_s, "burst_s": burst_s,
            "gap_s": gap_s, "body_db": body_db, "gap_db": gap_db,
            "bed_db": bed_db, "seed": seed,
            "peak_dbfs": float(20 * np.log10(np.abs(x).max() + 1e-30))}
    return x, meta


def verify(x, lo, hi):
    e, _, hop = M.band_envelope(x, lo, hi)
    et = M.broadband_envelope(x)
    m = M.map_mask(M.activity_mask(et), 1024, hop, len(e))
    return M.crest_stats(e, m, hop, n_boot=0, min_frames=50)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lo", type=float, required=True)
    ap.add_argument("--hi", type=float, required=True)
    ap.add_argument("--crest", type=float, required=True)
    ap.add_argument("--dur", type=float, default=60.0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--bed-db", type=float, default=None)
    a = ap.parse_args(argv)
    x, meta = make_stimulus(a.lo, a.hi, a.crest, a.dur, seed=a.seed,
                            bed_db=a.bed_db)
    st = verify(x, a.lo, a.hi)
    meta["measured"] = st
    sf.write(a.out, x, SR, subtype="FLOAT")
    print(json.dumps(meta, indent=1))
    print(f"written: {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

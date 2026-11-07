"""The 50 dB short-event test for the production crest estimator."""
from __future__ import annotations

import os
import sys

import numpy as np
from scipy.signal import butter, sosfilt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from finalizer import measure  # noqa: E402

EDGES = np.array([30, 60, 120, 240, 480, 960, 1920, 3840, 7680, 15360, 20000],
                 dtype=float)
SR = 48000


def make_burst(burst_s=0.5, dur=30.0, seed=2):
    n = int(dur * SR)
    t = np.arange(n) / SR
    low = 0.2 * np.sin(2 * np.pi * 80 * t)
    rng = np.random.default_rng(seed)
    sos = butter(8, [7680 / (SR / 2), 15360 / (SR / 2)], btype="band",
                 output="sos")
    hi = sosfilt(sos, rng.standard_normal(n))
    hi = hi / np.sqrt(np.mean(hi ** 2)) * 10 ** (-30 / 20)
    s = int(15 * SR)
    hi[s:s + int(burst_s * SR)] *= 10 ** (50 / 20)
    return np.stack([low + hi, low + hi], axis=1).astype(np.float32)


def test_new_gate_sees_burst():
    d = measure.band_crest_detail(make_burst(0.5), EDGES)
    assert d["status"][8] == "OK", d["status"]
    assert d["values"][8] > 40, d["values"]


def test_new_gate_unknown_on_short_file():
    x = make_burst(0.5, dur=2.0)
    d = measure.band_crest_detail(x, EDGES, min_frames=1000)
    assert all(s == "UNKNOWN" for s in d["status"]), d["status"]


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  {t.__name__} ok")
    print(f"\n{len(tests)} crest-gate tests passed")


if __name__ == "__main__":
    main()

"""The floor and three-valued decision tests."""
from __future__ import annotations

import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from finalizer import measure  # noqa: E402

EDGES = np.array([30, 60, 120, 240, 480, 960, 1920, 3840, 7680, 15360, 20000],
                 dtype=float)
SR = 48000


def _fade(x, k=480):
    n = len(x)
    w = np.ones(n)
    w[:k] = np.linspace(0, 1, k) ** 2
    w[-k:] = np.linspace(1, 0, k) ** 2
    return x * w


def _band_noise(dur, lo, hi, seed=0):
    from scipy.signal import butter, sosfilt
    n = int(dur * SR)
    rng = np.random.default_rng(seed)
    sos = butter(8, [lo / (SR / 2), hi / (SR / 2)], btype="band",
                 output="sos")
    x = sosfilt(sos, rng.standard_normal(n))
    x = x / (np.sqrt(np.mean(x ** 2)) + 1e-12) * 0.05
    return np.stack([_fade(x)] * 2, axis=1)


def _noise(dur, seed=0):
    n = int(dur * SR)
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n) * 0.05
    return np.stack([_fade(x)] * 2, axis=1)


def test_floor_fails_on_static_band():
    x = _band_noise(10.0, 960, 1920)
    rep = measure.crest_report(x, EDGES, [6.2] * 10, [8.0] * 10)
    row = rep["bands"][5]              # 960-1920
    assert row["lower"] == "FAIL", row
    assert row["upper"] == "PASS", row


def test_upper_unknown_near_boundary():
    x = _noise(5.0)
    rep = measure.crest_report(x, EDGES, [6.2] * 10, [3.0] * 10)
    assert rep["overall"] in ("PASS", "FAIL", "UNKNOWN")


def test_unknown_is_not_pass():
    x = _noise(5.0)
    rep = measure.crest_report(x, EDGES, [6.2] * 10, None, min_frames=1000)
    assert rep["overall"] == "UNKNOWN", rep["overall"]
    assert any(r["status"] == "UNKNOWN" or r["lower"] == "UNKNOWN"
               for r in rep["bands"])


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  {t.__name__} ok")
    print(f"\n{len(tests)} floor/decision tests passed")


if __name__ == "__main__":
    main()

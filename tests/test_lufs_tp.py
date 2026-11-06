"""Loudness and true-peak tests for the production meters."""
from __future__ import annotations

import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from finalizer import dsp  # noqa: E402

SR = 48000


def test_lufs_1khz():
    t = np.arange(5 * SR) / SR
    x = np.stack([0.1 * np.sin(2 * np.pi * 1000 * t)] * 2, axis=1)
    assert abs(dsp.lufs_integrated(x) - (-20.0)) < 0.2


def test_lufs_rejects_other_rate():
    x = np.zeros((1000, 2))
    try:
        dsp.lufs_integrated(x, sr=44100)
    except ValueError:
        return
    raise AssertionError("non-48 kHz must be rejected, not silently mis-weighted")


def test_true_peak_1khz():
    t = np.arange(5 * SR) / SR
    x = np.stack([0.891250938 * np.sin(2 * np.pi * 1000 * t)] * 2, axis=1)
    m = dsp.true_peak_meters(x)
    assert abs(m["annex2"] - (-1.0)) < 0.2, m
    assert abs(m["poly"] - (-1.0)) < 0.2, m
    assert m["max"] == max(m["annex2"], m["poly"])
    assert abs(dsp.true_peak(x) - m["max"]) < 1e-9


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  {t.__name__} ok")
    print(f"\n{len(tests)} loudness/TP tests passed")


if __name__ == "__main__":
    main()

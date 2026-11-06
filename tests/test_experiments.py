"""Tests for the experiment helpers. Run: python3 tests/test_experiments.py."""
from __future__ import annotations

import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from research.experiments import analysis, stimuli  # noqa: E402


def test_k_from_curve_monotone():
    k = analysis.k_from_curve([0, 3, 6, 9, 12], [0, -0.4, -1.2, -2.8, -4.0],
                              delta=2.0)
    assert k["monotonic"] is True
    assert k["k_db"] == 6.0, k


def test_k_from_curve_non_monotone():
    # compression becomes acceptable again at 12 dB; the connected interval
    # from 0 ends at 6, so the later point must not extend K_b
    k = analysis.k_from_curve([0, 3, 6, 9, 12], [0, -0.5, -1.5, -2.5, -1.0],
                              delta=2.0)
    assert k["monotonic"] is False
    assert k["k_db"] == 6.0, k


def test_bootstrap_k():
    rows = []
    for unit in ("a", "b", "c"):
        for c, pc in [(0, 0), (3, 0), (6, -1.0), (9, -3.0)]:
            rows.append({"unit": unit, "crest": c, "pc": pc})
    b = analysis.bootstrap_k(rows, delta=2.0, n_boot=100)
    assert b["ci95"][0] <= b["k_db"] <= b["ci95"][1]
    assert b["n_units"] == 3


def test_stimulus_crest():
    x, meta = stimuli.make_stimulus(3840, 7680, 9.0, dur=20.0, seed=5)
    assert x.shape[1] == 2
    assert meta["gap_s"] == 1.0
    st = stimuli.verify(x, 3840, 7680)
    assert st["status"] == "OK", st
    assert 8.0 <= st["crest_tail_db"] <= 10.0, st
    assert st["body_db"] is not None


def test_stimulus_rejects_short_body():
    try:
        stimuli.make_stimulus(3840, 7680, 9.0, dur=20.0, body_s=5.0)
    except ValueError:
        return
    raise AssertionError("short body must be rejected")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  {t.__name__} ok")
    print(f"\n{len(tests)} experiment tests passed")


if __name__ == "__main__":
    main()

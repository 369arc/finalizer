"""Side/mono metric tests for the production report."""
from __future__ import annotations

import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from finalizer import measure  # noqa: E402

SR = 48000


def test_pure_side():
    t = np.arange(4 * SR) / SR
    s = 0.5 * np.sin(2 * np.pi * 60 * t)
    r = measure.side_metrics(np.stack([s, -s], axis=1))
    assert r["side_mid_db"] > 20, r
    assert r["mono_loss_db"] < -20, r


def test_pure_mid():
    t = np.arange(4 * SR) / SR
    s = 0.5 * np.sin(2 * np.pi * 60 * t)
    r = measure.side_metrics(np.stack([s, s], axis=1))
    assert r["side_mid_db"] < -40, r
    assert abs(r["mono_loss_db"]) < 0.5, r


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  {t.__name__} ok")
    print(f"\n{len(tests)} side tests passed")


if __name__ == "__main__":
    main()

"""Tests for the research metric layer. Run with or without pytest:

    python3 tests/test_metrics.py
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile

import numpy as np
import soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from research import metrics as M  # noqa: E402

SR = 48000


def _noise(n, seed=0):
    return np.random.default_rng(seed).standard_normal(n)


def _band_noise(n, lo, hi, seed=0):
    from scipy.signal import butter, sosfilt
    x = _noise(n, seed)
    sos = butter(8, [lo / (SR / 2), min(hi / (SR / 2), 0.99)],
                 btype="band", output="sos")
    y = sosfilt(sos, x)
    return y / (np.sqrt(np.mean(y ** 2)) + 1e-12)


def test_band_plan():
    plan = M.band_plan()
    assert plan[0][2] == 16384, plan[0]
    assert plan[1][2] == 8192, plan[1]
    assert plan[2][2] == 4096, plan[2]
    assert len(plan) == 10


def test_gain_invariance():
    n = 10 * SR
    x = np.stack([0.1 * _noise(n, 1), 0.1 * _noise(n, 2)], axis=1)
    e1, _, hop = M.band_envelope(x, 960, 1920)
    e2, _, _ = M.band_envelope(x * 2, 960, 1920)
    m1 = M.activity_mask(M.broadband_envelope(x))
    m2 = M.activity_mask(M.broadband_envelope(x * 2))
    s1 = M.crest_stats(e1, m1, hop, n_boot=0, min_frames=50)
    s2 = M.crest_stats(e2, m2, hop, n_boot=0, min_frames=50)
    assert abs((s2["body_db"] - s1["body_db"]) - 20 * math.log10(2)) < 0.01
    assert abs(s2["crest_tail_db"] - s1["crest_tail_db"]) < 0.01


def test_known_crest():
    # 20 s: 80 % body, 10 % burst, 10 % gap; the burst is 12 dB over the body.
    n = 20 * SR
    base = _band_noise(n, 3840, 7680, seed=3)
    env = np.ones(n)
    period = 10 * SR
    for s in range(0, n, period):
        env[s + int(8.0 * SR):s + int(9.0 * SR)] = 10 ** (-60 / 20)
        env[s + int(9.0 * SR):s + int(10.0 * SR)] = 10 ** (12 / 20)
    x = np.stack([0.05 * base * env, 0.05 * base * env], axis=1)
    e, _, hop = M.band_envelope(x, 3840, 7680, 4096, 1024)
    et = M.broadband_envelope(x)
    m = M.map_mask(M.activity_mask(et), 1024, hop, len(e))
    st = M.crest_stats(e, m, hop, n_boot=0, min_frames=100)
    assert st["status"] == "OK", st
    assert 10.5 <= st["crest_tail_db"] <= 13.5, st


def test_short_event_not_hidden():
    # A quiet high band with a 0.5 s burst 50 dB above its body.
    from scipy.signal import butter, sosfilt
    n = 30 * SR
    t = np.arange(n) / SR
    low = 0.2 * np.sin(2 * np.pi * 80 * t)
    hi = _band_noise(n, 7680, 15360, seed=2)
    hi = hi / np.sqrt(np.mean(hi ** 2)) * 10 ** (-30 / 20)
    s = int(15 * SR)
    hi[s:s + int(0.5 * SR)] *= 10 ** (50 / 20)
    x = np.stack([low + hi, low + hi], axis=1)
    e, _, hop = M.band_envelope(x, 7680, 15360, 4096, 1024)
    et = M.broadband_envelope(x)
    m = M.map_mask(M.activity_mask(et), 1024, hop, len(e))
    st = M.crest_stats(e, m, hop, n_boot=0, min_frames=100)
    assert st["status"] == "OK", st
    assert st["crest_tail_db"] > 40, st
    assert st["crest_max_db"] > 40, st


def test_short_signal_unknown():
    n = 2 * SR
    x = np.stack([0.1 * _noise(n, 4), 0.1 * _noise(n, 4)], axis=1)
    e, _, hop = M.band_envelope(x, 960, 1920)
    m = M.activity_mask(M.broadband_envelope(x))
    st = M.crest_stats(e, m, hop, n_boot=0, min_frames=1000)
    assert st["status"] == "UNKNOWN", st


def test_lufs():
    t = np.arange(5 * SR) / SR
    x = np.stack([0.1 * np.sin(2 * np.pi * 1000 * t)] * 2, axis=1)
    L = M.lufs_integrated(x)
    assert abs(L - (-20.0)) < 0.2, L


def test_true_peak():
    t = np.arange(5 * SR) / SR
    x = np.stack([0.891250938 * np.sin(2 * np.pi * 1000 * t)] * 2, axis=1)
    tp = M.true_peak(x)
    assert abs(tp["annex2"] - (-1.0)) < 0.2, tp
    assert abs(tp["poly"] - (-1.0)) < 0.2, tp
    assert tp["max"] == max(tp["annex2"], tp["poly"])


def test_side():
    t = np.arange(4 * SR) / SR
    s = 0.5 * np.sin(2 * np.pi * 60 * t)
    x = np.stack([s, -s], axis=1)
    r = M.side_metrics(x)
    assert r["side_mid_db"] > 20, r          # pure side: mid is near zero
    assert r["mono_loss_db"] < -20, r
    x2 = np.stack([s, s], axis=1)
    r2 = M.side_metrics(x2)
    assert r2["side_mid_db"] < -40, r2        # pure mid: side is zero
    assert abs(r2["mono_loss_db"]) < 0.5, r2


def test_decisions():
    assert M.decide_upper(5.0, (4.0, 6.0), 6.2) == "PASS"
    assert M.decide_upper(7.0, (6.5, 7.5), 6.2) == "FAIL"
    assert M.decide_upper(6.2, (5.8, 6.6), 6.2) == "UNKNOWN"
    assert M.decide_lower(3.0, (2.5, 3.5), 2.5) == "PASS"
    assert M.decide_lower(1.0, (0.5, 1.5), 2.5) == "FAIL"
    assert M.decide_lower(2.5, (2.0, 3.0), 2.5) == "UNKNOWN"


def test_json_report():
    n = 6 * SR
    t = np.arange(n) / SR
    x = np.stack([0.1 * np.sin(2 * np.pi * 220 * t)] * 2, axis=1)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "x.wav")
        sf.write(p, x, SR, subtype="FLOAT")
        r = M.analyse(p, n_boot=0, min_frames=50)
        s = json.dumps(M._jsonable(r))
        assert "NaN" not in s
        assert r["crest_overall"] in ("PASS", "FAIL", "UNKNOWN")
        assert len(r["bands"]) == 10


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  {t.__name__} ok")
    print(f"\n{len(tests)} metric tests passed")


if __name__ == "__main__":
    main()

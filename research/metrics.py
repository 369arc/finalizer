"""Reference measurement layer for the meta. Measurement only: no audio is written.

This module implements the corrected estimators from
`research/METRIC_SPECIFICATION.md`:

  * multi-resolution band envelopes (a longer window for the low bands);
  * a broadband activity mask, so a short event cannot replace the body;
  * the tail crest, the local crest and the maximum crest, reported separately;
  * a moving-block bootstrap interval;
  * BS.1770-4 integrated loudness and a dual true-peak meter
    (BS.1770-4 Annex 2 filter and a polyphase meter, conservatively maxed);
  * side/mid and mono-loss metrics below a stated corner.

It intentionally does not import `finalizer.chain` and never calls a mastering
stage. The production chain is a separate program.

Units:
  E, B, C, side/mid, mono loss : dB
  loudness                     : LUFS
  true peak                    : dBTP
  frequency                    : Hz
  time                         : s

Usage:
    python3 research/metrics.py FILE.wav [--json OUT.json] [--no-bootstrap]
"""
from __future__ import annotations

import argparse
import json
import math
import os
from typing import Any

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

# ---------------------------------------------------------------- constants
FS = 48000
EDGES = np.array([30, 60, 120, 240, 480, 960, 1920, 3840, 7680, 15360, 20000],
                 dtype=float)
EPS = 1e-20

# ITU-R BS.1770-4 K-weighting, 48 kHz.
_B1 = np.array([1.53512485958697, -2.69169618940638, 1.19839281085285])
_A1 = np.array([1.0, -1.69065929318241, 0.73248077421585])
_B2 = np.array([1.0, -2.0, 1.0])
_A2 = np.array([1.0, -1.99004745483398, 0.99007225036621])

# ITU-R BS.1770-4 Annex 2, 48-tap / 4-phase interpolator. Rows are taps,
# columns are phases; the prototype is the row-major flattening.
_ANNEX2_PHASES = np.array([
    [0.0017089843750, -0.0291748046875, -0.0189208984375, -0.0083007812500],
    [0.0109863281250, 0.0292968750000, 0.0330810546875, 0.0148925781250],
    [-0.0196533203125, -0.0517578125000, -0.0582275390625, -0.0266113281250],
    [0.0332031250000, 0.0891113281250, 0.1015625000000, 0.0476074218750],
    [-0.0594482421875, -0.1665039062500, -0.2003173828125, -0.1022949218750],
    [0.1373291015625, 0.4650878906250, 0.7797851562500, 0.9721679687500],
    [0.9721679687500, 0.7797851562500, 0.4650878906250, 0.1373291015625],
    [-0.1022949218750, -0.2003173828125, -0.1665039062500, -0.0594482421875],
    [0.0476074218750, 0.1015625000000, 0.0891113281250, 0.0332031250000],
    [-0.0266113281250, -0.0582275390625, -0.0517578125000, -0.0196533203125],
    [0.0148925781250, 0.0330810546875, 0.0292968750000, 0.0109863281250],
    [-0.0083007812500, -0.0189208984375, -0.0291748046875, 0.0017089843750],
])
_ANNEX2 = _ANNEX2_PHASES.reshape(-1)


# ---------------------------------------------------------------- input
def read_stereo(path: str, fs: int = FS) -> np.ndarray:
    """Read a 48 kHz stereo file as float64 (N, 2). Raise on other formats."""
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    x, sr = sf.read(path, dtype="float64", always_2d=True)
    if sr != fs:
        raise ValueError(f"{path}: {sr} Hz; this metric is defined at {fs} Hz")
    if x.shape[1] != 2:
        raise ValueError(f"{path}: {x.shape[1]} channel(s); stereo is required")
    return x


# ---------------------------------------------------------------- STFT
def _hann(n: int) -> np.ndarray:
    return 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / n)


def stft(x: np.ndarray, n: int, hop: int) -> np.ndarray:
    """(frames, bins, channels) complex64, periodic Hann, zero-padded by n."""
    if x.ndim != 2:
        raise ValueError("x must be (N, channels)")
    w = _hann(n).astype(np.float32)
    pad = n
    xp = np.pad(x.astype(np.float32), ((pad, pad), (0, 0)))
    nframes = 1 + (len(xp) - n) // hop
    bins = n // 2 + 1
    X = np.empty((nframes, bins, xp.shape[1]), dtype=np.complex64)
    chunk = 1024
    for s in range(0, nframes, chunk):
        e = min(s + chunk, nframes)
        idx = np.arange(n)[None, :] + hop * np.arange(s, e)[:, None]
        X[s:e] = np.fft.rfft(xp[idx] * w[None, :, None], axis=1)
    return X


def band_envelope(x: np.ndarray, lo: float, hi: float, n: int | None = None,
                  hop: int | None = None) -> tuple[np.ndarray, int, int]:
    """Band power per frame in dB. Returns (E, n, hop)."""
    if n is None:
        n = max(4096, int(2 ** math.ceil(math.log2(8 * FS / (hi - lo)))))
    if hop is None:
        hop = n // 4
    X = stft(x, n, hop)
    P = (X.real.astype(np.float64) ** 2 + X.imag.astype(np.float64) ** 2).sum(axis=2)
    f = np.fft.rfftfreq(n, 1 / FS)
    sel = (f >= lo) & (f < hi)
    if not sel.any():
        raise ValueError(f"band {lo}-{hi} contains no FFT bin at n={n}")
    e = 10 * np.log10(P[:, sel].sum(axis=1) + EPS)
    return e, n, hop


def broadband_envelope(x: np.ndarray, n: int = 4096, hop: int = 1024) -> np.ndarray:
    """Broadband power in dB over 30-20000 Hz, for the activity mask."""
    X = stft(x, n, hop)
    P = (X.real.astype(np.float64) ** 2 + X.imag.astype(np.float64) ** 2).sum(axis=2)
    f = np.fft.rfftfreq(n, 1 / FS)
    sel = (f >= EDGES[0]) & (f < EDGES[-1])
    return 10 * np.log10(P[:, sel].sum(axis=1) + EPS)


def activity_mask(e_tot: np.ndarray, gate_db: float = 40.0,
                  floor_dbfs: float = -70.0) -> np.ndarray:
    """Broadband programme activity; no per-band maximum is involved."""
    if len(e_tot) == 0:
        return np.zeros(0, dtype=bool)
    return (e_tot >= e_tot.max() - gate_db) & (e_tot >= floor_dbfs)


def map_mask(mask: np.ndarray, hop_src: int, hop_dst: int,
             n_dst: int) -> np.ndarray:
    """Nearest-frame expansion of a mask from one hop grid to another."""
    if len(mask) == 0 or n_dst == 0:
        return np.zeros(n_dst, dtype=bool)
    idx = np.rint(np.arange(n_dst) * hop_dst / hop_src).astype(int)
    idx = np.clip(idx, 0, len(mask) - 1)
    return mask[idx]


def band_plan(edges: np.ndarray = EDGES, fs: int = FS) -> list[tuple[float, float, int, int]]:
    """(lo, hi, n, hop) per band; n is chosen to give >= 8 bins."""
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        n = max(4096, int(2 ** math.ceil(math.log2(8 * fs / (hi - lo)))))
        out.append((float(lo), float(hi), n, n // 4))
    return out


# ---------------------------------------------------------------- statistics
def _p(a: np.ndarray, q: float) -> float:
    return float(np.percentile(a, q))


def crest_stats(e: np.ndarray, mask: np.ndarray, hop: int,
                block_s: float = 10.0, n_boot: int = 200,
                seed: int = 0, min_frames: int = 1000,
                local_s: float = 3.0) -> dict[str, Any]:
    """Body, tail/local/max crest, and a moving-block bootstrap interval."""
    ea = e[mask]
    out: dict[str, Any] = {
        "n_frames": int(len(e)),
        "n_active": int(len(ea)),
        "body_db": None,
        "crest_tail_db": None,
        "crest_local_db": None,
        "crest_max_db": None,
        "ci_tail": None,
        "ci_body": None,
        "status": "UNKNOWN",
    }
    if len(ea) < min_frames:
        out["reason"] = f"only {len(ea)} active frames (need {min_frames})"
        return out

    body = _p(ea, 75)
    tail = _p(ea, 99.5) - body
    out["body_db"] = body
    out["crest_tail_db"] = tail
    out["crest_max_db"] = float(ea.max() - body)

    # local crest: max over sliding windows of (P99 - P75)
    w = max(8, int(round(local_s * FS / hop)))
    step = max(1, int(round(1.0 * FS / hop)))
    if len(ea) >= w:
        vals = []
        for s in range(0, len(ea) - w + 1, step):
            seg = ea[s:s + w]
            vals.append(_p(seg, 99) - _p(seg, 75))
        out["crest_local_db"] = float(np.max(vals)) if vals else None

    # moving-block bootstrap
    if n_boot > 0:
        blk = max(4, int(round(block_s * FS / hop)))
        n = len(ea)
        nb = int(np.ceil(n / blk))
        rng = np.random.default_rng(seed)
        b = np.empty(n_boot)
        c = np.empty(n_boot)
        for k in range(n_boot):
            parts = []
            for _ in range(nb):
                s = int(rng.integers(0, max(1, n - blk)))
                parts.append(ea[s:s + blk])
            idx = np.concatenate(parts)[:n]
            b[k] = _p(idx, 75)
            c[k] = _p(idx, 99.5) - b[k]
        out["ci_body"] = [float(np.percentile(b, 2.5)),
                          float(np.percentile(b, 97.5))]
        out["ci_tail"] = [float(np.percentile(c, 2.5)),
                          float(np.percentile(c, 97.5))]
    out["status"] = "OK"
    return out


# ---------------------------------------------------------------- loudness
def lufs_integrated(x: np.ndarray, fs: int = FS) -> float:
    """ITU-R BS.1770-4 integrated loudness, stereo, 48 kHz."""
    if fs != FS:
        raise ValueError("BS.1770-4 K-weighting here is defined at 48 kHz")
    y = np.empty_like(x, dtype=np.float64)
    for c in range(x.shape[1]):
        y[:, c] = _lfilter(_B2, _A2, _lfilter(_B1, _A1, x[:, c]))
    hop = int(0.1 * fs)
    n = len(y) // hop
    if n < 4:
        return -70.0
    z = (y[:n * hop].reshape(n, hop, -1) ** 2).mean(axis=1).sum(axis=1)
    zb = np.convolve(z, np.ones(4) / 4, mode="valid")
    l = -0.691 + 10 * np.log10(np.maximum(zb, EPS))
    g = l > -70
    if not g.any():
        return -70.0
    rel = -0.691 + 10 * np.log10(zb[g].mean()) - 10
    g2 = l > rel
    return float(-0.691 + 10 * np.log10(zb[g2].mean()))


def _lfilter(b: np.ndarray, a: np.ndarray, x: np.ndarray) -> np.ndarray:
    from scipy.signal import lfilter
    return lfilter(b, a, x, axis=0)


# ---------------------------------------------------------------- true peak
def true_peak_annex2(x: np.ndarray) -> float:
    """BS.1770-4 Annex 2 4x oversampled true peak, dBTP."""
    xx = x if x.ndim > 1 else x[:, None]
    peak = 0.0
    for c in range(xx.shape[1]):
        xu = np.zeros(4 * len(xx), dtype=np.float64)
        xu[::4] = xx[:, c]
        y = np.convolve(xu, _ANNEX2)
        peak = max(peak, float(np.abs(y).max()))
    return 20 * np.log10(peak + EPS)


def true_peak_poly(x: np.ndarray) -> float:
    """The previous generic 4x polyphase meter, dBTP (for comparison)."""
    from scipy.signal import resample_poly
    xx = x if x.ndim > 1 else x[:, None]
    peak = 0.0
    step = 1 << 20
    for i in range(0, len(xx), step):
        seg = xx[i:i + step + 64].astype(np.float32)
        up = resample_poly(seg, 4, 1, axis=0)
        peak = max(peak, float(np.abs(up).max()))
    return 20 * np.log10(peak + EPS)


def true_peak(x: np.ndarray) -> dict[str, float]:
    """Both meters; `max` is the conservative ceiling value."""
    a = true_peak_annex2(x)
    p = true_peak_poly(x)
    return {"annex2": a, "poly": p, "max": max(a, p)}


# ---------------------------------------------------------------- stereo
def side_metrics(x: np.ndarray, fs: int = FS, lo: float = 20.0,
                 hi: float = 120.0) -> dict[str, float]:
    """Side/mid, mono loss, and low-band correlation below `hi` Hz."""
    if fs != FS:
        raise ValueError("side metric is defined at 48 kHz here")
    L, R = x[:, 0], x[:, 1]
    M = (L + R) / 2
    S = (L - R) / 2
    sos = butter(4, [lo / (fs / 2), min(hi / (fs / 2), 0.99)],
                 btype="band", output="sos")
    m = sosfilt(sos, M)
    s = sosfilt(sos, S)
    rms = lambda z: float(np.sqrt(np.mean(z ** 2) + EPS))
    rm, rs = rms(m), rms(s)
    side_mid = 20 * np.log10(rs / rm) if rm > 0 else float("-inf")
    # mono loss: mono sum vs the uncorrelated power sum, in the same band
    l = sosfilt(sos, L)
    r = sosfilt(sos, R)
    unc = math.sqrt((rms(l) ** 2 + rms(r) ** 2) / 2)
    mono_loss = 20 * np.log10(rm / unc) if unc > 0 else float("-inf")
    # low correlation: 2nd-order low-pass at hi, as in the production report
    sos2 = butter(2, hi / (fs / 2), btype="lowpass", output="sos")
    a = sosfilt(sos2, L)
    b = sosfilt(sos2, R)
    corr = float(np.corrcoef(a, b)[0, 1]) if a.std() > 1e-12 and b.std() > 1e-12 else 1.0
    return {"side_mid_db": side_mid, "mono_loss_db": mono_loss,
            "corr_low": corr, "band_hz": [lo, hi]}


# ---------------------------------------------------------------- decisions
def decide_upper(value: float | None, ci: tuple[float, float] | None,
                 limit: float, tol: float = 0.0) -> str:
    if value is None:
        return "UNKNOWN"
    lo, hi = ci if ci is not None else (value - tol, value + tol)
    if hi <= limit:
        return "PASS"
    if lo > limit:
        return "FAIL"
    return "UNKNOWN"


def decide_lower(value: float | None, ci: tuple[float, float] | None,
                 limit: float, tol: float = 0.0) -> str:
    if value is None:
        return "UNKNOWN"
    lo, hi = ci if ci is not None else (value - tol, value + tol)
    if lo >= limit:
        return "PASS"
    if hi < limit:
        return "FAIL"
    return "UNKNOWN"


# ---------------------------------------------------------------- analysis
def analyse(path: str, limits: dict | None = None, n_boot: int = 200,
            gate_db: float = 40.0, floor_dbfs: float = -70.0,
            min_frames: int = 1000) -> dict[str, Any]:
    """Measure one file. `limits` may carry K_tail/F per band from a meta."""
    x = read_stereo(path)
    e_tot = broadband_envelope(x)
    mask = activity_mask(e_tot, gate_db, floor_dbfs)
    bands = []
    for i, (lo, hi, n, hop) in enumerate(band_plan()):
        e, _, _ = band_envelope(x, lo, hi, n, hop)
        m = map_mask(mask, 1024, hop, len(e))
        st = crest_stats(e, m, hop, n_boot=n_boot, min_frames=min_frames)
        row = {"band_hz": [lo, hi], "n": n, "hop": hop, **st}
        if limits:
            k = limits.get("K_tail", [None] * 10)[i]
            f = limits.get("F", [None] * 10)[i]
            row["K_tail_db"] = k
            row["F_db"] = f
            ci = tuple(st["ci_tail"]) if st["ci_tail"] else None
            row["upper_status"] = decide_upper(st["crest_tail_db"], ci, k) \
                if k is not None else "UNKNOWN"
            row["lower_status"] = decide_lower(st["crest_tail_db"], ci, f) \
                if f is not None else "UNKNOWN"
        bands.append(row)

    tp = true_peak(x)
    lufs = lufs_integrated(x)
    side = side_metrics(x)
    statuses = [b.get("upper_status", "UNKNOWN") for b in bands]
    if "FAIL" in statuses:
        crest_overall = "FAIL"
    elif "UNKNOWN" in statuses:
        crest_overall = "UNKNOWN"
    else:
        crest_overall = "PASS"
    return {
        "metric_version": "metric-spec 0.1-draft",
        "file": os.path.abspath(path),
        "sample_rate": FS,
        "duration_s": len(x) / FS,
        "analysis": {"window": "hann-periodic", "activity_gate_db": gate_db,
                     "activity_floor_dbfs": floor_dbfs,
                     "percentile_method": "linear",
                     "band_plan": [{"band_hz": [lo, hi], "n": n, "hop": hop}
                                   for lo, hi, n, hop in band_plan()]},
        "bands": bands,
        "loudness": {"lufs": lufs},
        "true_peak": tp,
        "stereo": side,
        "crest_overall": crest_overall,
    }


def _jsonable(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, float):
        return None if not math.isfinite(o) else o
    return o


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file")
    ap.add_argument("--json", default=None)
    ap.add_argument("--no-bootstrap", action="store_true")
    ap.add_argument("--gate", type=float, default=40.0)
    ap.add_argument("--floor", type=float, default=-70.0)
    ap.add_argument("--min-frames", type=int, default=1000)
    a = ap.parse_args(argv)
    r = analyse(a.file, n_boot=0 if a.no_bootstrap else 200,
                gate_db=a.gate, floor_dbfs=a.floor, min_frames=a.min_frames)
    print(f"{a.file}")
    print(f"  LUFS {r['loudness']['lufs']:.2f}   "
          f"TP {r['true_peak']['max']:.2f} dBTP "
          f"(annex2 {r['true_peak']['annex2']:.2f}, poly {r['true_peak']['poly']:.2f})")
    print(f"  side/mid 20-120 {r['stereo']['side_mid_db']:+.1f} dB   "
          f"mono loss {r['stereo']['mono_loss_db']:+.1f} dB   "
          f"corr {r['stereo']['corr_low']:+.2f}")
    print(f"  {'band':>14s} {'B':>7s} {'Ctail':>7s} {'Cmax':>7s} {'n':>6s}  status")
    for b in r["bands"]:
        print(f"  {b['band_hz'][0]:6.0f}-{b['band_hz'][1]:<7.0f} "
              f"{b['body_db'] if b['body_db'] is not None else float('nan'):7.2f} "
              f"{b['crest_tail_db'] if b['crest_tail_db'] is not None else float('nan'):7.2f} "
              f"{b['crest_max_db'] if b['crest_max_db'] is not None else float('nan'):7.2f} "
              f"{b['n_active']:6d}  {b['status']}")
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(_jsonable(r), fh, indent=1)
        print(f"  written: {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

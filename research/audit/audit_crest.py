"""Audit the v1 crest estimator and compare it with the v2 reference.

v1 is `finalizer.measure.band_crest` at commit af04531: 4096/1024, a per-band
`e > e.max() - 45` gate, and a `top - 45 dB` no-programme gate. v2 is
`research.metrics`: multi-resolution bands, a broadband activity mask, and a
reported tail/local/max crest.

The script is measurement-only. It accepts a manifest of tracks and writes a
JSON file; it never writes audio.

Manifest format:
    {"LABEL": "/path/to/master.wav", ...}

Run:
    python3 research/audit/audit_crest.py --manifest tracks.json \
        --out research/audit/audit_crest.json
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

from finalizer import dsp, measure  # noqa: E402
from research import metrics as M  # noqa: E402

EDGES = M.EDGES
BANDS = [f"{int(EDGES[i])}-{int(EDGES[i + 1])}" for i in range(len(EDGES) - 1)]


def envelope(x, n=4096, hop=1024):
    X = dsp.stft(x, n, hop)
    P = dsp.band_power(X)
    f = np.fft.rfftfreq(n, 1 / dsp.SR)
    E = np.empty((P.shape[0], len(EDGES) - 1))
    for b in range(len(EDGES) - 1):
        sel = (f >= EDGES[b]) & (f < EDGES[b + 1])
        E[:, b] = 10 * np.log10(P[:, sel].sum(axis=1) + 1e-20)
    return E


def crest_v1(E, gate=None):
    out = []
    for b in range(E.shape[1]):
        e = E[:, b]
        if gate == "max45":
            act = e[e > e.max() - 45.0]
        else:
            act = e
        out.append(float(np.percentile(act, 99.5) - np.percentile(act, 75))
                   if len(act) > 20 else float("nan"))
    return np.array(out)


def crest_v1_no_programme(E):
    """The actual measure.band_crest, including the top-45 dB gate."""
    p75 = np.array([np.percentile(E[:, b], 75) for b in range(E.shape[1])])
    top = p75.max()
    out = []
    for b in range(E.shape[1]):
        e = E[:, b]
        if p75[b] < top - 45.0:
            out.append(float("nan"))
            continue
        act = e[e > e.max() - 45.0]
        out.append(float(np.percentile(act, 99.5) - np.percentile(act, 75))
                   if len(act) > 20 else float("nan"))
    return np.array(out)


def bootstrap(E, block_s=10.0, n_boot=200, seed=0):
    hop_s = 1024 / dsp.SR
    blk = max(4, int(round(block_s / hop_s)))
    n = len(E)
    nb = int(np.ceil(n / blk))
    rng = np.random.default_rng(seed)
    vals = np.empty((n_boot, E.shape[1]))
    for k in range(n_boot):
        parts = []
        for _ in range(nb):
            s = int(rng.integers(0, max(1, n - blk)))
            parts.append(np.arange(s, min(n, s + blk)))
        idx = np.concatenate(parts)[:n]
        vals[k] = crest_v1(E[idx], "max45")
    return (np.nanpercentile(vals, 2.5, axis=0),
            np.nanpercentile(vals, 97.5, axis=0),
            np.nanstd(vals, axis=0))


def measure_track(path, do_bootstrap=True):
    x, sr = sf.read(os.path.expanduser(path), dtype="float32", always_2d=True)
    if sr != 48000 or x.shape[1] != 2:
        raise SystemExit(f"{path}: need 48 kHz stereo")
    E = envelope(x)
    raw = crest_v1(E)
    gated = crest_v1(E, "max45")
    v1 = measure.band_crest_legacy(x, EDGES)      # the af04531 estimator
    v1_new = measure.band_crest(x, EDGES)         # corrected broadband gate
    if do_bootstrap:
        lo, hi, sd = bootstrap(E)
    else:
        lo = hi = sd = np.full(E.shape[1], np.nan)
    # window sensitivity
    win = {}
    for n, hop in ((4096, 1024), (8192, 2048), (16384, 4096)):
        win[str(n)] = crest_v1(envelope(x, n, hop)).tolist()
    # duration sensitivity
    dur = {}
    for secs in (30, 60, 120, int(len(x) / sr)):
        dur[str(secs)] = crest_v1(envelope(x[:secs * sr])).tolist()
    # v2 reference
    v2r = M.analyse(path, n_boot=0)
    return {
        "duration_s": len(x) / sr,
        "raw": raw.tolist(),
        "gated": gated.tolist(),
        "v1": v1.tolist(),
        "v1_new": v1_new.tolist(),
        "ci": {"lo": lo.tolist(), "hi": hi.tolist(), "sd": sd.tolist()},
        "window": win,
        "duration": dur,
        "v2": [{"band_hz": b["band_hz"], "C_tail": b["crest_tail_db"],
                "C_local": b["crest_local_db"], "C_max": b["crest_max_db"],
                "status": b["status"]} for b in v2r["bands"]],
        "lufs": v2r["loudness"]["lufs"],
        "tp": v2r["true_peak"],
        "side": v2r["stereo"],
    }


def synthetic_burst():
    """The 50 dB, 0.1-0.5 s burst test from the audit."""
    sr = 48000
    dur = 30
    n = dur * sr
    t = np.arange(n) / sr
    low = 0.2 * np.sin(2 * np.pi * 80 * t)
    rng = np.random.default_rng(2)
    from scipy.signal import butter, sosfilt
    sos = butter(8, [7680 / (sr / 2), 15360 / (sr / 2)], btype="band",
                 output="sos")
    base = sosfilt(sos, rng.standard_normal(n))
    base = base / np.sqrt(np.mean(base ** 2)) * 10 ** (-30 / 20)
    out = {}
    for burst_s in (0.1, 0.25, 0.3, 0.5):
        hi = base.copy()
        s = int(15 * sr)
        hi[s:s + int(burst_s * sr)] *= 10 ** (50 / 20)
        x = np.stack([low + hi, low + hi], axis=1).astype(np.float32)
        E = envelope(x)
        raw = crest_v1(E)[8]
        v1 = measure.band_crest(x, EDGES)[8]
        act_n = int((E[:, 8] > E[:, 8].max() - 45).sum())
        out[str(burst_s)] = {"raw": float(raw), "v1": float(v1),
                             "act_n": act_n}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-bootstrap", action="store_true")
    a = ap.parse_args(argv)
    result = {"bands": BANDS, "tracks": {}, "synthetic": synthetic_burst()}
    if a.manifest:
        with open(a.manifest) as fh:
            manifest = json.load(fh)
        for name, path in manifest.items():
            print(f"measuring {name} ...", flush=True)
            result["tracks"][name] = measure_track(path,
                                                   not a.no_bootstrap)
    if a.out:
        with open(a.out, "w") as fh:
            json.dump(result, fh, indent=1)
        print(f"written: {a.out}")
    else:
        print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

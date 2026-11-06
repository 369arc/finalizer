"""Audit the body/crest dependence, the crest-stage side effect, and the mono filter.

Measurement-only. Writes JSON; never writes audio.

Run:
    python3 research/audit/audit_relations.py --manifest tracks.json \
        --out research/audit/audit_relations.json
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

from finalizer import chain, dsp  # noqa: E402
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


def segments(x, seg_s=10.0):
    sr = dsp.SR
    E = envelope(x)
    seg = int(seg_s * sr / 1024)
    B, C = [], []
    for s in range(0, len(E) - seg + 1, seg):
        e = E[s:s + seg]
        b = np.percentile(e, 75, axis=0)
        B.append(b)
        C.append(np.percentile(e, 99.5, axis=0) - b)
    return np.array(B), np.array(C)


def crest_stage(x, ceiling=6.2):
    E0 = envelope(x)
    b0 = np.percentile(E0, 75, axis=0)
    c0 = np.percentile(E0, 99.5, axis=0) - b0
    y, _ = chain.crest_stage(x, EDGES, np.full(len(EDGES) - 1, ceiling),
                             tau_atk=0.005, tau_rel=0.12)
    E1 = envelope(y)
    b1 = np.percentile(E1, 75, axis=0)
    c1 = np.percentile(E1, 99.5, axis=0) - b1
    return {"B_before": b0.tolist(), "B_after": b1.tolist(),
            "dB": (b1 - b0).tolist(),
            "C_before": c0.tolist(), "C_after": c1.tolist()}


def side_filter():
    sr = 48000
    t = np.arange(4 * sr) / sr
    rows = []
    for hz in (30, 40, 60, 80, 100, 120, 160):
        s = 0.5 * np.sin(2 * np.pi * hz * t)
        x = np.stack([s, -s], axis=1)
        y = chain.stereo_width(x, None, {"centers": dsp.band_grid()[0]}, None,
                               mono_below=120, match=False)
        before = np.sqrt(np.mean(((x[:, 0] - x[:, 1]) / 2) ** 2))
        after = np.sqrt(np.mean(((y[:, 0] - y[:, 1]) / 2) ** 2))
        rows.append({"hz": hz,
                     "attenuation_db": float(20 * np.log10(after / before + 1e-30))})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    out = {"bands": BANDS, "tracks": {}, "side_filter": side_filter()}
    if a.manifest:
        with open(a.manifest) as fh:
            manifest = json.load(fh)
        for name, path in manifest.items():
            print(f"measuring {name} ...", flush=True)
            x, sr = sf.read(os.path.expanduser(path), dtype="float32",
                            always_2d=True)
            if sr != 48000 or x.shape[1] != 2:
                raise SystemExit(f"{path}: need 48 kHz stereo")
            B, C = segments(x)
            corr = [float(np.corrcoef(B[:, b], C[:, b])[0, 1])
                    for b in range(len(EDGES) - 1)]
            pooled = float(np.corrcoef(B.ravel(), C.ravel())[0, 1])
            out["tracks"][name] = {
                "corr_by_band": corr,
                "corr_pooled": pooled,
                "segments": int(len(B)),
                "crest_stage_30s": crest_stage(x[:30 * sr]),
                "side": M.side_metrics(x),
            }
    if a.out:
        with open(a.out, "w") as fh:
            json.dump(out, fh, indent=1)
        print(f"written: {a.out}")
    else:
        print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

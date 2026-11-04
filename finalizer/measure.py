"""Measuring the reference state of a drone.

A drone is not judged by transients, so the state vector is:
  contour   -- long-term band levels (the shape that must be "mathematically right")
  smooth    -- the same after removing resonances (what we actually steer toward)
  width     -- side/mid per band (the "volume" of the image)
  coh       -- low-band correlation (does the bottom stay solid in mono)
  lufs/tp/lra
"""
import numpy as np
import soundfile as sf

from . import dsp

PER_OCT = 3


def load(path):
    import os
    path = os.path.expanduser(path)      # "~/..." survives quoting in shells
    if not os.path.exists(path):
        raise SystemExit(f"no such file: {path}")
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    if sr != dsp.SR:
        raise SystemExit(f"{path}: {sr} Hz, only 48 kHz is supported")
    if x.shape[1] == 1:
        x = np.stack([x[:, 0], x[:, 0]], axis=1)
    return x, sr


def spectrum(sig, centers, edges, nfft=16384):
    return dsp.octave_levels(sig, centers, edges, nfft)


def smooth(levels, octaves=1.0, per_oct=PER_OCT):
    """Gaussian smoothing in log-frequency. sigma in octaves."""
    if octaves <= 0:
        return levels.copy()
    s = octaves * per_oct
    k = int(np.ceil(3 * s))
    x = np.arange(-k, k + 1)
    w = np.exp(-0.5 * (x / s) ** 2)
    w /= w.sum()
    pad = np.pad(levels, k, mode="edge")
    return np.convolve(pad, w, mode="valid")


def features(x, centers=None, edges=None, ref_hz=1000.0, light=False):
    if centers is None:
        centers, edges = dsp.band_grid(per_oct=PER_OCT)
    ms = dsp.mid_side(x)
    mid = spectrum(ms[:, 0], centers, edges)
    side = spectrum(ms[:, 1], centers, edges)
    total = 10 * np.log10(10 ** (mid / 10) + 10 ** (side / 10) + 1e-20)
    ref = int(np.argmin(np.abs(np.log2(centers / ref_hz))))
    lo = np.argmin(np.abs(centers - 100))

    out = {
        "centers": centers,
        "edges": edges,
        "levels": total,
        "rel": total - total[ref],
        "smoothed": smooth(total - total[ref]),
        "width": side - mid,
        "mid": mid,
        "side": side,
        "ref_band": ref,
        "corr_low": _corr_low(x, centers, lo),
    }
    if not light:
        out.update(lufs=dsp.lufs_integrated(x), lra=dsp.lra(x), tp=dsp.true_peak(x))
        # the contour that matters is the BODY (P75), not the mean: crest
        # control moves the mean and would make the two stages fight
        out["rel_sustain"] = sustain_contour(x, centers, edges)
    return out


def _corr_low(x, centers, idx):
    """Inter-channel correlation below ~100 Hz (mono solidity)."""
    from scipy.signal import butter, sosfilt
    sos = butter(2, 120 / (dsp.SR / 2), btype="lowpass", output="sos")
    a = sosfilt(sos, x[:, 0]); b = sosfilt(sos, x[:, 1])
    if a.std() < 1e-9 or b.std() < 1e-9:
        return 1.0
    return float(np.corrcoef(a, b)[0, 1])


def roughness(f, octaves=1.0):
    return f["rel"] - smooth(f["rel"], octaves)


def resonances(f, octaves=1.0, threshold=2.0, min_hz=100.0, max_hz=12000.0):
    r = roughness(f, octaves)
    out = []
    for i in range(1, len(r) - 1):
        if not (min_hz <= f["centers"][i] <= max_hz):
            continue
        if r[i] > threshold and r[i] >= r[i - 1] and r[i] >= r[i + 1]:
            out.append((float(f["centers"][i]), float(r[i])))
    return out


def summary(f, name="", top=None):
    c = f["centers"]
    r = roughness(f)
    sm = smooth(f["rel"])
    rows = [f"  {name}",
            f"    LUFS {f['lufs']:6.2f}   LRA {f['lra']:5.2f}   TP {f['tp']:6.2f}   "
            f"corr<100Hz {f['corr_low']:+.2f}",
            f"    {'Hz':>7s} {'level':>7s} {'rel':>7s} {'smooth':>7s} {'rough':>6s} {'width':>7s}"]
    idx = range(len(c)) if top is None else sorted(np.argsort(-np.abs(r))[:top])
    for i in idx:
        rows.append(f"    {c[i]:7.0f} {f['levels'][i]:7.1f} {f['rel'][i]:7.1f} "
                    f"{sm[i]:7.1f} {r[i]:6.1f} {f['width'][i]:7.1f}")
    res = resonances(f)
    if res:
        rows.append("    resonances: " + ", ".join(f"{hz:.0f}Hz+{amp:.1f}" for hz, amp in res))
    return "\n".join(rows)


def sustain_contour(x, centers, edges, n=16384, hop=4096):
    """The contour defined on the BODY: P75 of each band envelope.

    Orthogonal to crest by construction -- crest control clamps the upper tail
    and leaves P75 untouched, so this contour is invariant under the crest stage.
    """
    X = dsp.stft(x, n, hop)
    P = dsp.band_power(X)
    freqs = np.fft.rfftfreq(n, 1 / dsp.SR)
    # hard band limits: the weight matrix extends the first band to DC, which
    # would let subsonic rumble masquerade as the 25 Hz band
    lv = np.empty(len(centers))
    for i in range(len(centers)):
        sel = (freqs >= edges[i]) & (freqs < edges[i + 1])
        if not sel.any():                 # band narrower than the bin spacing
            j = int(np.argmin(np.abs(freqs - centers[i])))
            sel = np.zeros_like(freqs, dtype=bool)
            sel[j] = True
        e = 10 * np.log10(P[:, sel].sum(axis=1) + 1e-20)
        lv[i] = np.percentile(e, 75)
    ref = int(np.argmin(np.abs(np.log2(centers / 1000.0))))
    return lv - lv[ref]


def band_crest(x, edges, n=4096, hop=1024):
    """Crest per band: P99.5 - P75 of the band envelope over active frames."""
    X = dsp.stft(x, n, hop)
    P = dsp.band_power(X)
    freqs = np.fft.rfftfreq(n, 1 / dsp.SR)
    E = np.empty((P.shape[0], len(edges) - 1))
    for b in range(len(edges) - 1):
        sel = (freqs >= edges[b]) & (freqs < edges[b + 1])
        E[:, b] = 10 * np.log10(P[:, sel].sum(axis=1) + 1e-20)
    p75 = np.array([np.percentile(E[:, b], 75) for b in range(E.shape[1])])
    top = p75.max()
    out = []
    for b in range(len(edges) - 1):
        e = E[:, b]
        if p75[b] < top - 45.0:           # band carries no programme
            out.append(float("nan"))
            continue
        act = e[e > e.max() - 45.0]
        out.append(float(np.percentile(act, 99.5) - np.percentile(act, 75))
                   if len(act) > 20 else float("nan"))
    return np.array(out)


def to_json(f):
    return {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in f.items()}


def from_json(d):
    out = dict(d)
    # a target may carry only what it is about: crest, or contour, or both
    for k in ("centers", "edges", "levels", "rel", "smoothed", "width",
              "mid", "side", "rel_sustain", "crest_edges", "crest_max",
              "crest_octave"):
        if k in d:
            out[k] = np.asarray(d[k], dtype=float)
    return out

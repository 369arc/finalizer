"""Measuring the reference state of sustained material.

This material is not judged by transients, so the state vector is:
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

    Gain-invariant: a constant gain shifts every band by the same amount and
    cancels in the relative contour. It is *not* statistically independent of
    the crest, and a deep/long crest cut can move P75 (see the audit). This is
    a separate estimator from `band_crest`; the two are not the same envelope.
    """
    X = dsp.stft(x, n, hop)
    P = dsp.band_power(X)
    freqs = np.fft.rfftfreq(n, 1 / dsp.SR)
    # hard band limits, so subsonic rumble cannot masquerade as the 25 Hz band
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


def band_crest_legacy(x, edges, n=4096, hop=1024):
    """The pre-audit estimator, kept for comparison (commit b16188b).

    It gates each band on its own maximum (`e > e.max() - 45`), so a short
    event more than 45 dB above a quiet body can replace the body, and it gates
    a band out when its P75 is 45 dB below the loudest band.
    """
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
    for b in range(E.shape[1]):
        e = E[:, b]
        if p75[b] < top - 45.0:           # band carries no programme
            out.append(float("nan"))
            continue
        act = e[e > e.max() - 45.0]
        out.append(float(np.percentile(act, 99.5) - np.percentile(act, 75))
                   if len(act) > 20 else float("nan"))
    return np.array(out)


def band_crest_detail(x, edges, n=4096, hop=1024, min_frames=50,
                      gate_db=40.0, floor_db=-70.0):
    """Per-band body and tail crest with a broadband activity mask.

    The mask is computed once from the total 30 Hz-20 kHz power. It does not
    depend on a band's maximum, so a loud short event cannot replace the body.
    A band is `UNKNOWN` when the file has fewer than `min_frames` active frames
    or when the band's P75 is below `floor_db`. `NaN` means `UNKNOWN`; it must
    never be reported as a pass.

    Returns a dict with `values` (C_tail), `body`, `n_active` and `status`.
    """
    edges = np.asarray(edges, dtype=float)
    X = dsp.stft(x, n, hop)
    P = dsp.band_power(X)
    freqs = np.fft.rfftfreq(n, 1 / dsp.SR)
    E = np.empty((P.shape[0], len(edges) - 1))
    for b in range(len(edges) - 1):
        sel = (freqs >= edges[b]) & (freqs < edges[b + 1])
        E[:, b] = 10 * np.log10(P[:, sel].sum(axis=1) + 1e-20)
    allsel = (freqs >= edges[0]) & (freqs < edges[-1])
    e_tot = 10 * np.log10(P[:, allsel].sum(axis=1) + 1e-20)
    if len(e_tot) == 0:
        mask = np.zeros(0, dtype=bool)
    else:
        mask = ((e_tot >= e_tot.max() - gate_db)
                & (e_tot >= floor_db))
    values, bodies, nactive, status = [], [], [], []
    for b in range(E.shape[1]):
        ea = E[mask, b]
        nactive.append(int(len(ea)))
        if len(ea) < min_frames:
            values.append(float("nan"))
            bodies.append(float("nan"))
            status.append("UNKNOWN")
            continue
        body = float(np.percentile(ea, 75))
        if body < floor_db:
            values.append(float("nan"))
            bodies.append(body)
            status.append("UNKNOWN")
            continue
        values.append(float(np.percentile(ea, 99.5) - body))
        bodies.append(body)
        status.append("OK")
    return {"values": np.array(values), "body": np.array(bodies),
            "n_active": np.array(nactive, dtype=int),
            "status": status}


def band_crest(x, edges, n=4096, hop=1024, min_frames=50):
    """Crest per band: P99.5 - P75 over the broadband active frames.

    `NaN` means the band was not assessed; it is not a pass. Use
    `band_crest_detail` for the status and the body.
    """
    return band_crest_detail(x, edges, n, hop, min_frames)["values"]


def crest_report(x, edges, k_max, k_min=None, tol=0.35, min_frames=50):
    """Three-valued crest/floor decision for one file.

    The point estimate is compared with a fixed measurement margin `tol`.
    This is not a confidence interval; the research metric (`research/metrics.py`)
    provides the bootstrap interval. The rule is deliberately conservative:

      upper: PASS if C <= K; FAIL if C > K + tol; UNKNOWN in between.
      lower: PASS if C >= F; FAIL if C < F - tol; UNKNOWN in between.

    A band with status UNKNOWN makes both decisions UNKNOWN.
    """
    d = band_crest_detail(x, edges, min_frames=min_frames)
    k_max = np.asarray(k_max, dtype=float)
    k_min = None if k_min is None else np.asarray(k_min, dtype=float)
    rows = []
    for i, v in enumerate(d["values"]):
        st = d["status"][i]
        if st != "OK" or not np.isfinite(v):
            up = lo = "UNKNOWN"
        else:
            up = ("PASS" if v <= k_max[i] else
                  "FAIL" if v > k_max[i] + tol else "UNKNOWN")
            if k_min is None:
                lo = "UNKNOWN"
            else:
                lo = ("PASS" if v >= k_min[i] else
                      "FAIL" if v < k_min[i] - tol else "UNKNOWN")
        rows.append({"band_hz": [float(edges[i]), float(edges[i + 1])],
                     "C_db": None if not np.isfinite(v) else float(v),
                     "status": st, "upper": up, "lower": lo,
                     "n_active": int(d["n_active"][i])})
    upper_fail = any(r["upper"] == "FAIL" for r in rows)
    upper_unknown = any(r["upper"] == "UNKNOWN" for r in rows)
    floor_fail = any(r["lower"] == "FAIL" for r in rows)
    if upper_fail:
        overall = "FAIL"
    elif upper_unknown or floor_fail:
        # The floor is provisional (the audit found no empirical basis); a
        # floor failure is reported, but it does not by itself reject a master
        # until the F_b experiment replaces the craft value.
        overall = "UNKNOWN"
    else:
        overall = "PASS"
    return {"bands": rows, "overall": overall, "tol_db": tol,
            "floor_fail": floor_fail, "detail": d}


def side_metrics(x, f_lo=20.0, f_hi=120.0):
    """Side/mid, mono loss and low-band correlation below `f_hi`.

    Side is `(L-R)/2`; mid is `(L+R)/2`. The values are band-limited RMS
    ratios, not an exact-zero test. `side_mid_db` can be very large for a pure
    side signal and very negative for a pure mid signal.
    """
    from scipy.signal import butter, sosfilt
    L, R = x[:, 0], x[:, 1]
    M = (L + R) / 2
    S = (L - R) / 2
    sos = butter(4, [f_lo / (dsp.SR / 2), min(f_hi / (dsp.SR / 2), 0.99)],
                 btype="band", output="sos")
    m = sosfilt(sos, M)
    s = sosfilt(sos, S)
    rms = lambda z: float(np.sqrt(np.mean(z ** 2) + 1e-20))
    rm, rs = rms(m), rms(s)
    side_mid = 20 * np.log10(rs / rm) if rm > 0 else float("inf")
    l = sosfilt(sos, L)
    r = sosfilt(sos, R)
    unc = np.sqrt((rms(l) ** 2 + rms(r) ** 2) / 2)
    mono_loss = 20 * np.log10(rm / unc) if unc > 0 else float("-inf")
    sos2 = butter(2, f_hi / (dsp.SR / 2), btype="lowpass", output="sos")
    a = sosfilt(sos2, L)
    b = sosfilt(sos2, R)
    corr = (float(np.corrcoef(a, b)[0, 1])
            if a.std() > 1e-12 and b.std() > 1e-12 else 1.0)
    return {"side_mid_db": float(side_mid),
            "mono_loss_db": float(mono_loss),
            "corr_low": corr, "band_hz": [f_lo, f_hi]}


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

"""The drone chain.

Order matters and is chosen for cleanliness, not for effect:

    HPF -> contour EQ (min-phase) -> presence bell -> resonance suppression
        -> stereo width -> band crest -> loudness -> slow limiter -> TP trim

Every stage is either linear time-invariant and minimum-phase, or slow.
Nothing here can pump, ring before a transient, or alias. "Linear" here means
LTI -- no harmonics are generated -- not linear-phase: every filter is
minimum-phase on purpose, so nothing rings before a transient.
"""
import numpy as np

from scipy.ndimage import minimum_filter1d
from scipy.signal import lfilter

from . import dsp, measure


def resonance_notches(src, tgt, threshold=2.5, max_depth=4.0, q=5.0,
                      min_hz=100.0, max_hz=12000.0, max_rough=None):
    """Remove peaks that are either rougher than the reference or absolutely rough.

    A drone's low-frequency edge is not a resonance, hence min_hz.
    """
    rs = measure.roughness(src)
    # a meta has no contour, so there is nothing to compare against: fall back
    # to the absolute roughness ceiling only
    rt = measure.roughness(tgt) if "rel" in tgt else np.zeros_like(rs)
    excess = rs - rt
    out = []
    for i in range(1, len(excess) - 1):
        fc = src["centers"][i]
        if not (min_hz <= fc <= max_hz):
            continue
        ref = rs if max_rough is not None else excess
        is_peak = ref[i] >= ref[i - 1] and ref[i] >= ref[i + 1]
        if not is_peak:
            continue
        depth = 0.0
        if excess[i] > threshold:
            depth = excess[i] - threshold + 1.0
        if max_rough is not None and rs[i] > max_rough:
            depth = max(depth, rs[i] - max_rough + 1.0)
        depth = min(depth, max_depth)
        if depth > 0.4:
            out.append((float(fc), -float(depth), q))
    return out


def stereo_width(x, src, tgt, extra=None, max_db=6.0, mono_below=0.0,
                 match=True):
    ms = dsp.mid_side(x)
    m, s = ms[:, 0], ms[:, 1]
    if mono_below:
        s = dsp.highpass(s[:, None], mono_below, order=3)[:, 0]
    if match:
        delta = np.clip(tgt["width"] - src["width"], -max_db, max_db)
        if extra is not None:
            delta = delta + extra
    else:
        delta = np.zeros(len(tgt["centers"]))
    h = dsp.minphase_fir(delta, tgt["centers"], n=8192)
    s = dsp.apply_fir(s[:, None], h)[:, 0]
    return dsp.from_mid_side(np.stack([m, s], axis=1))


def crest_stage(x, edges, crest_max, tau_atk=0.05, tau_rel=0.5, max_cut=18.0,
                lookahead=0.04):
    """Cut peaks that rise more than `crest_max` above the band's own sustain.

    The sustain is the band's P75 over the whole piece -- a fixed number, so a
    quiet section is not mistaken for a peak section and vice versa.
    """
    n, hop = 4096, 1024
    X = dsp.stft(x, n, hop)
    P = dsp.band_power(X)
    freqs = np.fft.rfftfreq(n, 1 / dsp.SR)
    edges = np.asarray(edges, dtype=float)
    # measure on hard bands (so the number we control is the number we report),
    # apply through smooth weights (so the gain has no spectral edges)
    W = dsp.band_weights(freqs, edges)
    # no gain outside the band grid: subsonic and ultrasonic regions are not ours
    W[0][freqs < edges[0]] = 0.0
    W[-1][freqs > edges[-1]] = 0.0
    E = np.empty((P.shape[0], len(edges) - 1))
    for b in range(len(edges) - 1):
        sel = (freqs >= edges[b]) & (freqs < edges[b + 1])
        E[:, b] = 10 * np.log10(P[:, sel].sum(axis=1) + 1e-20)
    base = np.percentile(E, 75, axis=0)
    over = np.maximum(0.0, E - (base + np.asarray(crest_max))[None, :])
    # a band 40 dB below the loudest one carries no programme, only noise:
    # its crest is meaningless and controlling it would just gate the noise
    quiet = base < (base.max() - 45.0)
    over[:, quiet] = 0.0

    hop_s = hop / dsp.SR
    L = max(1, int(lookahead / hop_s))
    a_rel = np.exp(-hop_s / tau_rel)
    target = -over                                   # <= 0, desired gain (dB)
    gr = np.empty_like(over)
    for b in range(over.shape[1]):
        # lookahead: the gain must already be down when the peak arrives, so a
        # short event is either fully clamped or not touched at all -- there is
        # no half-trimmed zone (that zone is what sounds like a flat cake)
        t = minimum_filter1d(target[:, b], size=2 * L + 1, mode="nearest")
        g, _ = lfilter([1 - a_rel], [1, -a_rel], t, zi=[a_rel * t[0]])
        g = minimum_filter1d(g, size=L + 1, mode="nearest")
        g = np.minimum(g, target[:, b])
        gr[:, b] = -g
    gr = np.minimum(gr, max_cut)

    G = -gr
    nframes = len(G)
    chunk = 512
    for s in range(0, nframes, chunk):
        e = min(s + chunk, nframes)
        M = G[s:e] @ W
        X[s:e] *= (10 ** (M / 20))[:, :, None].astype(np.float32)
    y = dsp.istft(X, n, hop, out_len=len(x))
    return y.astype(np.float32), {"crest_gr_mean": float(gr.mean()),
                                  "crest_gr_band": gr.mean(axis=0).tolist(),
                                  "crest_base": base.tolist()}


def render(x, tgt, g_extra=None, g_width=None, p=None, notch_state=None):
    p = p or {}
    y = x.astype(np.float32)
    info = {}
    notch_state = dict(notch_state or {})

    if p.get("hpf"):
        y = dsp.highpass(y, p["hpf"])

    if g_extra is not None and np.any(g_extra):
        h = dsp.minphase_fir(g_extra, tgt["centers"], n=p.get("fir", 8192))
        y = dsp.apply_fir(y, h)

    for fc, (g, q) in notch_state.items():
        y = dsp.peaking(y, fc, q, g)

    f_now = measure.features(y, light=True)
    if p.get("deharsh", True):
        new = resonance_notches(f_now, tgt,
                                p.get("harsh_thr", 2.5),
                                p.get("harsh_max", 4.0),
                                p.get("harsh_q", 5.0),
                                p.get("harsh_min_hz", 100.0),
                                p.get("harsh_max_hz", 12000.0),
                                p.get("max_rough"))
        cap = -abs(p.get("harsh_total", 8.0))
        for fc, g, q in new:
            g0 = notch_state.get(fc, (0.0, q))[0]
            gtot = max(g0 + g, cap)
            notch_state[fc] = (gtot, q)
            if abs(gtot - g0) > 0.05:
                y = dsp.peaking(y, fc, q, gtot - g0)
    info["notches"] = notch_state

    if p.get("width", True):
        y = stereo_width(y, f_now, tgt, g_width,
                         p.get("width_max", 6.0),
                         p.get("mono_below", 0.0),
                         p.get("match_width", True))

    if p.get("crest_max") is not None:
        ce = np.asarray(p["crest_edges"], dtype=float)
        cm_target = np.asarray(p["crest_max"], dtype=float) - float(p.get("crest_margin", 0.0))
        cm = cm_target.copy()
        # OVER is a setpoint error, not a report line: tighten the offending
        # bands by exactly the excess and clamp again. Valid because clamping
        # is idempotent and preserves P75 (the body never moves).
        iters = max(1, int(p.get("crest_iters", 3)))
        for k in range(iters):
            y, ci = crest_stage(y, ce, cm,
                                p.get("crest_atk", 0.005), p.get("crest_rel", 0.12))
            if k == iters - 1:
                break
            cre = measure.band_crest(y, ce)
            excess = np.nan_to_num(cre - np.asarray(p["crest_max"], dtype=float),
                                   nan=-99.0)
            bad = excess > 0.1
            if not bad.any():
                break
            cm = cm - np.where(bad, np.nan_to_num(excess, nan=0.0) + 0.3, 0.0)
            cm = np.maximum(cm, 0.0)
        info.update(ci)
        info["crest_target_eff"] = cm.tolist()

    # midrange guard: no broad coloration beyond the ear's tolerance.
    # The reference is the track's OWN 2-octave trend, so this needs no corpus:
    # it bounds how far a band may deviate from the shape the piece already has.
    if p.get("mid_guard"):
        cc, ee = tgt["centers"], tgt["edges"]
        lv = measure.sustain_contour(y, cc, ee)
        trend = measure.smooth(lv, 2.0)
        dev = lv - trend
        lo, hi = p.get("mid_range", (240.0, 4000.0))
        inr = (cc >= lo) & (cc <= hi)
        tol = float(p["mid_guard"])
        over = np.where(inr, np.sign(dev) * np.maximum(0.0, np.abs(dev) - tol),
                        0.0)
        if np.any(np.abs(over) > 0.01):
            h = dsp.minphase_fir(-over, cc, n=p.get("fir", 8192))
            y = dsp.apply_fir(y, h)
            info["mid_guard_db"] = float(np.abs(over).max())
            info["mid_dev_before"] = float(np.abs(dev[inr]).max())

    # the presence bell goes AFTER the crest stage: a static filter changes a
    # band's level, not its crest, so it cannot push anything over the boundary
    # -- and, placed before, it distorted exactly that measurement
    if p.get("eq_peak"):
        hz, db, q = p["eq_peak"]
        y = dsp.peaking(y, hz, q, db)

    # loudness and ceiling are solved on the pre-limiter signal, so the loop
    # converges instead of fighting the limiter's own gain reduction
    base = y
    g = 1.0
    for _ in range(4):
        z = base * np.float32(g)
        z, gr_max, gr_mean, gr_p99 = dsp.limit(z, p.get("ceiling", -1.0),
                                               lookahead_ms=p.get("lookahead", 20.0),
                                               release_ms=p.get("release", 400.0))
        z, tp = dsp.trim_true_peak(z, p.get("ceiling", -1.0))
        if p.get("lufs") is None:
            break
        cur = dsp.lufs_integrated(z)
        g = g * 10 ** ((p["lufs"] - cur) / 20)
    y = z
    info.update(gr_max=gr_max, gr_mean=gr_mean, gr_p99=gr_p99, tp_before_trim=tp)
    return y, info


def master(x, tgt, p=None, iters=3, verbose=False):
    p = p or {}
    iters = max(1, int(iters))
    nb = len(tgt["centers"])

    if p.get("fit_contour", True) and "rel" not in tgt:
        raise SystemExit("fit_contour needs a target with a contour "
                         "(use --target, not --meta)")

    if not p.get("fit_contour", True):
        # contour-free mode: the artistic curve is not a target, only the
        # invariants (crest, ceiling, loudness, mono) are regulated
        y, info = render(x, tgt, np.zeros(nb), np.zeros(nb), p, {})
        f = measure.features(y)
        f["sustain_contour"] = measure.sustain_contour(y, tgt["centers"], tgt["edges"])
        return {"audio": y, "features": f, "eq_db": np.zeros(nb),
                "width_db": np.zeros(nb), "info": info}

    if p.get("one_shot"):
        # one measurement, one projection, one render: no feedback loop, so
        # there is nothing to oscillate and pull=1.0 means 1.0
        so = p.get("smooth_oct", 1.0)
        mx = float(p.get("max_eq", 9.0))
        y0, i0 = render(x, tgt, np.zeros(nb), np.zeros(nb), p, {})
        f0 = measure.features(y0)
        tc = tgt.get("rel_sustain", tgt["rel"])
        fc = f0.get("rel_sustain", f0["rel"])
        err = float(p.get("pull", 1.0)) * (
            measure.smooth(tc, so) - measure.smooth(fc, so))
        err = np.where(fc > (np.nanmax(fc) - 45.0), err, 0.0)
        g = np.clip(err, -mx, mx)
        y, info = render(x, tgt, g, np.zeros(nb), p, i0["notches"])
        f = measure.features(y)
        f["sustain_contour"] = measure.sustain_contour(y, tgt["centers"], tgt["edges"])
        return {"audio": y, "features": f, "eq_db": g,
                "width_db": np.zeros(nb), "info": info}

    g = np.zeros(nb)
    gw = np.zeros(nb)
    notch = {}
    best = None
    for it in range(iters):
        y, info = render(x, tgt, g, gw, p, notch)
        notch = info["notches"]
        f = measure.features(y)
        tc = tgt.get("rel_sustain", tgt["rel"])
        fc = f.get("rel_sustain", f["rel"])
        err = measure.smooth(tc, p.get("smooth_oct", 1.0)) - \
              measure.smooth(fc, p.get("smooth_oct", 1.0))
        # pull 1.0 = match the target, 0.3 = move a third of the way there.
        # A full match to a speech or catalogue curve would be a filter, not a
        # balance; the fraction keeps the track's own picture in charge.
        err = err * float(p.get("pull", 1.0))
        # never equalise silence upward: a band with no programme cannot be
        # filled without raising noise, so it is simply not a target
        err = np.where(fc > (np.nanmax(fc) - 45.0), err, 0.0)
        tol = p.get("deadband", 0.0)
        tol = np.asarray(tol, dtype=float)
        # deadband: push to the edge of the admissible band, never to its centre
        err_eff = (np.sign(err) * np.maximum(0.0, np.abs(err) - tol / 2)
                   if np.any(tol > 0) else err)
        if "width" in tgt and p.get("match_width", True):
            err_w = np.clip(tgt["width"] - f["width"], -3.0, 3.0)
        else:
            err_w = np.zeros(nb)
        g = np.clip(g + 0.95 * err_eff, -p.get("max_eq", 9.0), p.get("max_eq", 9.0))
        gw = np.clip(gw + 0.8 * err_w, -6.0, 6.0)
        if verbose:
            print(f"    iter {it}: contour max|err| {np.abs(err).max():.2f} dB, "
                  f"width max|err| {np.abs(err_w).max():.1f} dB, "
                  f"limiter {info['gr_max']:.1f}/{info['gr_mean']:.2f} dB (p99.5 {info.get('gr_p99',0):.1f}), "
                  f"notches {len(notch)}")
        best = (y, f, g.copy(), gw.copy(), info)
        if np.abs(err).max() < 0.1:
            break
    y, f, g, gw, info = best
    f["sustain_contour"] = measure.sustain_contour(y, tgt["centers"], tgt["edges"])
    # the loop is always one update behind: spend one more render on the
    # converged gains so the reported state is the delivered state
    if np.abs(err).max() > 0.1:
        y2, info2 = render(x, tgt, g, gw, p, info["notches"])
        f2 = measure.features(y2)
        tc = tgt.get("rel_sustain", tgt["rel"])
        fc2 = f2.get("rel_sustain", f2["rel"])
        e2 = np.abs(measure.smooth(tc, p.get("smooth_oct", 1.0))
                    - measure.smooth(fc2, p.get("smooth_oct", 1.0)))[
                        fc2 > (np.nanmax(fc2) - 45.0)].max()
        fc1 = f.get("rel_sustain", f["rel"])
        e1 = np.abs(measure.smooth(tc, p.get("smooth_oct", 1.0))
                    - measure.smooth(fc1, p.get("smooth_oct", 1.0)))[
                        fc1 > (np.nanmax(fc1) - 45.0)].max()
        if e2 <= e1:
            y, f, info = y2, f2, info2
            f["sustain_contour"] = measure.sustain_contour(y, tgt["centers"], tgt["edges"])
            if verbose:
                print(f"    polish: contour max|err| {e2:.2f} dB")
    return {"audio": y, "features": f, "eq_db": g, "width_db": gw, "info": info}

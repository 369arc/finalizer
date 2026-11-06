"""Core DSP for FINALIZER.

Design constraints for sustained material:
  * no pre-ringing  -> minimum-phase FIR for the static contour, never linear phase
  * no pumping      -> dynamics are slow or absent; the limiter is a safety net
  * no aliasing     -> every stage is either linear or minimum-phase
  * exact ceiling   -> true peak measured and trimmed, not assumed
"""
import numpy as np
from scipy.signal import lfilter, resample_poly, fftconvolve, lfilter_zi
from scipy.ndimage import minimum_filter1d

SR = 48000

# ---------------------------------------------------------------- BS.1770-4
_B1 = np.array([1.53512485958697, -2.69169618940638, 1.19839281085285])
_A1 = np.array([1.0, -1.69065929318241, 0.73248077421585])
_B2 = np.array([1.0, -2.0, 1.0])
_A2 = np.array([1.0, -1.99004745483398, 0.99007225036621])


def k_weight(x):
    y = lfilter(_B1, _A1, x, axis=0)
    return lfilter(_B2, _A2, y, axis=0)


def lufs_integrated(x, sr=SR):
    y = k_weight(x)
    hop = int(0.1 * sr)
    n = len(y) // hop
    if n < 4:
        return -70.0
    z = (y[:n * hop].reshape(n, hop, -1) ** 2).mean(axis=1).sum(axis=1)
    zb = np.convolve(z, np.ones(4) / 4, mode="valid")
    l = -0.691 + 10 * np.log10(np.maximum(zb, 1e-20))
    g = l > -70
    if not g.any():
        return -70.0
    rel = -0.691 + 10 * np.log10(zb[g].mean()) - 10
    g2 = l > rel
    return float(-0.691 + 10 * np.log10(zb[g2].mean()))


def lra(x, sr=SR):
    y = k_weight(x)
    win, hop = 3 * sr, sr
    if len(y) < win:
        return 0.0
    z = np.array([(y[i:i + win] ** 2).mean(axis=0).sum()
                  for i in range(0, len(y) - win, hop)])
    l = -0.691 + 10 * np.log10(np.maximum(z, 1e-20))
    g = l > -70
    if g.sum() < 3:
        return 0.0
    rel = -0.691 + 10 * np.log10(z[g].mean()) - 20
    g2 = l > rel
    if g2.sum() < 3:
        return 0.0
    return float(np.percentile(l[g2], 95) - np.percentile(l[g2], 10))


def true_peak(x, os=4):
    xx = x if x.ndim > 1 else x[:, None]
    peak = 0.0
    step = 1 << 20
    for i in range(0, len(xx), step):
        seg = xx[i:i + step + 64].astype(np.float32)
        up = resample_poly(seg, os, 1, axis=0)
        peak = max(peak, float(np.abs(up).max()))
    return 20 * np.log10(peak + 1e-20)


def rms(x):
    return float(np.sqrt(np.mean(x ** 2)))


# ---------------------------------------------------------------- spectrum
def band_grid(lo=25.0, hi=20000.0, per_oct=3):
    """Fractional-octave centre frequencies and edges."""
    n = int(np.floor(np.log2(hi / lo) * per_oct))
    centers = lo * 2 ** (np.arange(n + 1) / per_oct)
    edges = np.concatenate([[centers[0] / 2 ** (0.5 / per_oct)],
                            centers * 2 ** (0.5 / per_oct)])
    return centers, edges


def octave_levels(x, centers, edges, nfft=16384, gate_db=35.0):
    """Long-term averaged power per fractional-octave band, dB.

    Welch over the whole file, gated on loud frames so silence does not skew it.
    Two passes: the first only measures frame loudness to place the gate.
    """
    xx = x if x.ndim > 1 else x[:, None]
    mono = xx.mean(axis=1)
    w = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(nfft) / nfft)
    starts = range(0, len(mono) - nfft, nfft)

    levels = np.array([10 * np.log10(np.sum(np.abs(np.fft.rfft(mono[i:i + nfft] * w)) ** 2)
                                     + 1e-20) for i in starts])
    if len(levels) == 0:
        return np.zeros(len(centers))
    gate = np.median(levels) - gate_db

    total = np.zeros(nfft // 2 + 1)
    count = 0
    for i, lev in zip(starts, levels):
        if lev >= gate:
            total += np.abs(np.fft.rfft(mono[i:i + nfft] * w)) ** 2
            count += 1
    if count == 0:
        return np.zeros(len(centers))
    P = total / count
    f = np.fft.rfftfreq(nfft, 1 / SR)
    out = np.empty(len(centers))
    for b, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        sel = (f >= lo) & (f < hi)
        out[b] = 10 * np.log10(P[sel].sum() + 1e-20) if sel.any() else -120.0
    return out


# ---------------------------------------------------------------- filters
def minphase_fir(gain_db, centers, n=8192):
    """Minimum-phase FIR realising a smooth dB curve given at band centres.

    No pre-ringing by construction: all energy sits after t=0.
    """
    freqs = np.fft.rfftfreq(n, 1 / SR)
    lf = np.log2(np.maximum(freqs, 1.0))
    lc = np.log2(centers)
    g = np.interp(lf, lc, gain_db, left=gain_db[0], right=gain_db[-1])
    H = 10 ** (g / 20)
    logH = np.log(np.maximum(H, 1e-6))
    c = np.fft.irfft(logH, n)
    w = np.zeros(n)
    w[0] = 1.0
    w[1:n // 2] = 2.0
    w[n // 2] = 1.0
    c = c * w
    h = np.fft.irfft(np.exp(np.fft.rfft(c, n)), n)
    return h.astype(np.float32)


def apply_fir(x, h):
    xx = x if x.ndim > 1 else x[:, None]
    out = np.empty_like(xx)
    for c in range(xx.shape[1]):
        out[:, c] = fftconvolve(xx[:, c], h)[:len(xx)]
    return out.astype(np.float32)


def peaking(x, fc, q, gain_db):
    """Biquad peaking EQ, RBJ cookbook."""
    A = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * fc / SR
    al = np.sin(w0) / (2 * q)
    b = np.array([1 + al * A, -2 * np.cos(w0), 1 - al * A])
    a = np.array([1 + al / A, -2 * np.cos(w0), 1 - al / A])
    b /= a[0]
    a /= a[0]
    return lfilter(b, a, x, axis=0).astype(np.float32)


def highpass(x, hz=20.0, order=2):
    from scipy.signal import butter, sosfilt
    sos = butter(order, hz / (SR / 2), btype="highpass", output="sos")
    return sosfilt(sos, x, axis=0).astype(np.float32)


def mid_side(x):
    l, r = x[:, 0], x[:, 1]
    return np.stack([(l + r) / 2, (l - r) / 2], axis=1)


def from_mid_side(ms):
    m, s = ms[:, 0], ms[:, 1]
    return np.stack([m + s, m - s], axis=1).astype(np.float32)


# ---------------------------------------------------------------- STFT / OLA
def _win(n):
    return 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / n)  # periodic Hann


def stft(x, n=4096, hop=1024):
    """x: (N, ch) -> X: (frames, bins, ch) complex64. Padded by n on both sides."""
    w = _win(n).astype(np.float32)
    pad = n
    xp = np.pad(x.astype(np.float32), ((pad, pad), (0, 0)))
    nframes = 1 + (len(xp) - n) // hop
    bins = n // 2 + 1
    X = np.empty((nframes, bins, xp.shape[1]), dtype=np.complex64)
    chunk = 2048
    for s in range(0, nframes, chunk):
        e = min(s + chunk, nframes)
        idx = np.arange(n)[None, :] + hop * np.arange(s, e)[:, None]
        fr = xp[idx] * w[None, :, None]
        X[s:e] = np.fft.rfft(fr, axis=1)
    return X


def istft(X, n=4096, hop=1024, out_len=None):
    w = _win(n).astype(np.float32)
    nframes, bins, ch = X.shape
    total = (nframes - 1) * hop + n
    y = np.zeros((total, ch), dtype=np.float64)
    chunk = 2048
    for s in range(0, nframes, chunk):
        e = min(s + chunk, nframes)
        fr = np.fft.irfft(X[s:e], n=n, axis=1).astype(np.float64)
        fr *= w[None, :, None]
        for j in range(e - s):
            y[(s + j) * hop:(s + j) * hop + n] += fr[j]
    den = (w.astype(np.float64) ** 2).reshape(-1, hop).sum(axis=0)
    den = np.tile(den, total // hop + 2)[:total]
    y /= den[:, None]
    pad = n
    if out_len is not None:
        return y[pad:pad + out_len]
    return y[pad:total - pad]


def band_power(X):
    """(frames, bins, ch) -> (frames, bins) total power across channels."""
    return (X.real.astype(np.float64) ** 2 + X.imag.astype(np.float64) ** 2).sum(axis=2)


def band_weights(freqs, edges, xfade_oct=0.4):
    """(nb, bins) matrix, columns sum to 1, raised-cosine crossovers."""
    nb = len(edges) - 1
    lf = np.log2(np.maximum(freqs, 1e-6))
    le = np.log2(edges)
    W = np.zeros((nb, len(freqs)))
    x = xfade_oct
    for b in range(nb):
        w = np.ones_like(lf)
        if b > 0:
            t = np.clip((lf - (le[b] - x / 2)) / x, 0, 1)
            w = w * np.sin(t * np.pi / 2) ** 2
        if b < nb - 1:
            t = np.clip(((le[b + 1] + x / 2) - lf) / x, 0, 1)
            w = w * np.sin(t * np.pi / 2) ** 2
        W[b] = w
    W[0][lf < le[0]] = 1.0
    W[-1][lf > le[-1]] = 1.0
    s = W.sum(axis=0)
    return W / np.maximum(s, 1e-9)[None, :]


# ---------------------------------------------------------------- limiter
def limit(x, ceiling_db=-1.0, sr=SR, lookahead_ms=20.0, release_ms=400.0, os=4):
    """Slow lookahead true-peak limiter: a safety net, not a sound.

    Returns (y, max GR dB, mean GR dB).
    """
    if x.ndim == 1:
        x = x[:, None]
    ceil = 10 ** (ceiling_db / 20)
    step = 1 << 19
    env = []
    for i in range(0, len(x), step):
        seg = x[i:i + step].astype(np.float32)
        if len(seg) < 8:
            env.append(np.abs(seg).max(axis=1))
            continue
        up = resample_poly(seg, os, 1, axis=0)
        a = np.abs(up).max(axis=1)
        k = len(seg)
        env.append(a[:k * os].reshape(k, os).max(axis=1))
    env = np.maximum(np.concatenate(env), 1e-9)
    g_req = np.minimum(1.0, ceil / env)

    L = max(1, int(lookahead_ms * 1e-3 * sr))
    g = minimum_filter1d(g_req, size=2 * L + 1, mode="nearest")

    tau = release_ms * 1e-3 * sr
    a = np.exp(-1.0 / tau)
    b = [1 - a]
    zi = lfilter_zi(b, [1, -a]) * g[0]          # <-- steady-state start, no fade-in
    g, _ = lfilter(b, [1, -a], g, zi=zi)
    g = minimum_filter1d(g, size=L + 1, mode="nearest")
    g = np.minimum(g, g_req)

    y = x * g[:, None]
    gr = -20 * np.log10(np.maximum(g, 1e-9))
    return y, float(gr.max()), float(gr.mean()), float(np.percentile(gr, 99.5))


def trim_true_peak(y, ceiling_db=-1.0):
    """Static correction so the measured true peak lands on the ceiling."""
    tp = true_peak(y)
    if tp > ceiling_db:
        y = y * np.float32(10 ** ((ceiling_db - tp) / 20))
    return y, tp


def lowpass(x, hz, order=4):
    from scipy.signal import butter, sosfilt
    sos = butter(order, min(hz / (SR / 2), 0.99), btype="lowpass", output="sos")
    return sosfilt(sos, x, axis=0).astype(np.float32)

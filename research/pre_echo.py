"""Where the high-band crest ceilings actually come from.

The meta's top bands are limited by codec pre-echo, not by cone excursion.
This script measures that limit with real encoders instead of guessing a ramp.

The classic pre-echo case is *quiet before a transient*: the encoder quantises
the window that contains the burst, and the quantisation noise is spread over
the whole window -- including the quiet part just before it, where nothing
masks it. So the test signal is

    body (steady band noise) -> quiet gap -> burst -> body ...

For every crest value the body is identical; only the burst gain changes. What
we report is what the codec *added* to the quiet gap, in dB, and the same
residue relative to the body.

Run:  python3 research/pre_echo.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

SR = 48000
BODY_DB = -30.0
GAP_DB = -60.0
PERIOD = 0.60
BODY_LEN = 0.40
GAP_LEN = 0.10
BURST_LEN = 0.05
CRESTS = (3, 6, 9, 12, 15, 18, 21)
CODECS = {
    "aac128": ["-c:a", "aac", "-b:a", "128k", "-f", "mp4"],
    "aac96": ["-c:a", "aac", "-b:a", "96k", "-f", "mp4"],
    "opus96": ["-c:a", "libopus", "-b:a", "96k", "-f", "ogg"],
}
BANDS = [(1920, 3840), (3840, 7680), (7680, 15360), (15360, 20000)]
FRAME = 128
WINDOW_S = 0.020          # pre-echo lives in the ~20 ms before the transient


def band_noise(lo, hi, n, rng):
    x = rng.standard_normal(n)
    sos = butter(8, [lo / (SR / 2), min(hi / (SR / 2), 0.99)], btype="band",
                 output="sos")
    y = sosfilt(sos, x)
    return y / (np.sqrt(np.mean(y ** 2)) + 1e-12)


def build(lo, hi, crests, seed):
    """One body, one burst grid, several crests -- the only variable is gain."""
    rng = np.random.default_rng(seed)
    n = int((PERIOD * 2 + 0.2) * SR)
    body = band_noise(lo, hi, n, rng) * 10 ** (BODY_DB / 20)
    a, b = int(BODY_LEN * SR), int((BODY_LEN + GAP_LEN) * SR)
    c = b + int(BURST_LEN * SR)
    period = int(PERIOD * SR)
    starts = [s + b for s in range(int(0.1 * SR), n - period, period)]
    gap_gain = 10 ** ((GAP_DB - BODY_DB) / 20)
    out = {}
    for crest in crests:
        env = np.ones(n)
        for s in range(int(0.1 * SR), n - period, period):
            env[s + a:s + b] = gap_gain
            env[s + b:s + c] = 10 ** (crest / 20)
        out[crest] = (body * env).astype(np.float32)
    return out, starts


def envelope(x, lo, hi):
    sos = butter(8, [lo / (SR / 2), min(hi / (SR / 2), 0.99)], btype="band",
                 output="sos")
    y = sosfilt(sos, x)
    k = len(y) // FRAME
    e = np.sqrt(np.mean(y[:k * FRAME].reshape(k, FRAME) ** 2, axis=1) + 1e-20)
    return 20 * np.log10(e)


def gap_window(env, starts, shift_frames):
    look = int(round(WINDOW_S * SR / FRAME))
    vals = []
    for s in starts:
        i = int(round(s / FRAME)) + shift_frames
        w = env[max(0, i - look):max(1, i - 1)]
        if len(w):
            vals.append(float(np.mean(w)))
    return float(np.mean(vals)) if vals else float("nan")


def align(env_dec, env_src, starts):
    """Codec delay: maximise the correlation of the whole envelope.

    Deliberately NOT by matching the quiet gap -- that would cancel exactly the
    residue we are trying to measure.
    """
    a = env_dec - env_dec.mean()
    b = env_src - env_src.mean()
    best, best_c = 0, -1e18
    for d in range(-60, 61):
        if d >= 0:
            x, y = a[d:], b[:len(b) - d]
        else:
            x, y = a[:len(a) + d], b[-d:]
        n = min(len(x), len(y))
        if n < 100:
            continue
        c = float(np.dot(x[:n], y[:n]))
        if c > best_c:
            best_c, best = c, d
    return best


def codec_round(mono, args, tmp):
    src, enc, dec = tmp / "in.wav", tmp / "out.bin", tmp / "dec.wav"
    sf.write(src, np.stack([mono, mono], axis=1), SR, subtype="FLOAT")
    for f in (enc, dec):
        f.unlink(missing_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), *args,
                    str(enc)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(enc),
                    "-c:a", "pcm_f32le", str(dec)], check=True)
    y, _ = sf.read(dec, dtype="float32", always_2d=True)
    return y[:, 0]


def main():
    tmp = Path(tempfile.mkdtemp(prefix="pre_echo_"))
    print("pre-echo added by the codec into the quiet gap, dB re the original "
          "gap\n")
    print(f"{'band':>14s}{'codec':>9s}" + "".join(f"{c:>7d}" for c in CRESTS)
          + f"{'re body':>9s}")
    for bi, (lo, hi) in enumerate(BANDS):
        sigs, starts = build(lo, hi, CRESTS, seed=100 + bi)
        src = envelope(sigs[CRESTS[0]], lo, hi)
        for name, args in CODECS.items():
            row, rel = [], None
            for crest in CRESTS:
                dec = codec_round(sigs[crest], args, tmp)
                ed = envelope(dec, lo, hi)
                d = align(ed, src, starts)
                added = gap_window(ed, starts, d) - gap_window(src, starts, 0)
                row.append(added)
                if crest == CRESTS[-1]:
                    rel = gap_window(ed, starts, d) - BODY_DB
            print(f"{lo:6.0f}-{hi:<7.0f}{name:>9s}"
                  + "".join(f"{v:7.1f}" for v in row) + f"{rel:9.1f}")
    print("\nlast column: gap residue at the highest crest, relative to the "
          "band body\n(a residue 30 dB below the body is inaudible in any "
          "realistic playback)")


if __name__ == "__main__":
    main()

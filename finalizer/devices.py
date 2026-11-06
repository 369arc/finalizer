"""Playback models: a synthetic definition of "translates".

These are hand-set filter/limiter cascades, not measurements of real devices.
They are useful for finding a balance that survives a plausible device, but a
model output is not a device measurement and the 6 dB threshold is a convention.
See research/MASTERING_META_AUDIT.md.
"""
import numpy as np
from scipy.signal import butter, sosfilt

from . import dsp


def _hp(sig, hz, order=4):
    sos = butter(order, hz / (dsp.SR / 2), btype="highpass", output="sos")
    return sosfilt(sos, sig, axis=0)


def _lp(sig, hz, order=4):
    sos = butter(order, min(hz / (dsp.SR / 2), 0.99), btype="lowpass", output="sos")
    return sosfilt(sos, sig, axis=0)


def phone(x):
    """Phone speaker in portrait: almost nothing below 500 Hz, 3 kHz presence."""
    y = _hp(x, 480, 4)
    y = dsp.peaking(y, 3000, 1.2, 4.0)
    y = dsp.peaking(y, 900, 1.5, -2.0)
    return _lp(y, 12000, 2)


def laptop(x):
    """Laptop speakers: no sub, a boxy resonance, slight HF roll."""
    y = _hp(x, 190, 4)
    y = dsp.peaking(y, 420, 1.4, 3.0)
    y = dsp.peaking(y, 1200, 2.0, -1.5)
    return _lp(y, 14000, 2)


def bt_speaker(x):
    """Small Bluetooth box: 120 Hz cut, resonant port, DSP limiter."""
    y = _hp(x, 120, 4)
    y = dsp.peaking(y, 150, 2.0, 4.0)
    y = dsp.peaking(y, 2500, 1.0, 2.5)
    y, _, _, _ = dsp.limit(y, -3.0, lookahead_ms=5, release_ms=120)
    return y


def earbuds(x):
    """Sealed in-ear: bass shelf, no room. The one that rewards sub."""
    y = dsp.peaking(x, 55, 0.7, 5.0)
    y = dsp.peaking(y, 3000, 1.0, 2.0)
    return _hp(y, 25, 2)


def car(x):
    """Car cabin: transfer-function gain around 60 Hz, HF absorption."""
    y = dsp.peaking(x, 60, 0.8, 7.0)
    y = dsp.peaking(y, 200, 1.2, -2.0)
    y = _lp(y, 10000, 2)
    y, _, _, _ = dsp.limit(y, -2.0, lookahead_ms=10, release_ms=200)
    return y


def mono(x):
    """Single speaker: the fold-down every phone and most BT boxes do."""
    m = x.mean(axis=1, keepdims=True)
    return np.repeat(m, x.shape[1], axis=1)


# Flat range of each model, in Hz. Both ends matter: the phone's own 12 kHz
# low-pass used to sit *inside* the measured range, so a master was charged
# for the device's filter. Outside [lo, hi] the device colours by design and
# that colour is not a mastering defect.
DEVICES = {
    "phone":   {"fn": phone,      "lo": 1000.0, "hi": 10000.0},
    "laptop":  {"fn": laptop,     "lo": 400.0,  "hi": 10000.0},
    "bt":      {"fn": bt_speaker, "lo": 250.0,  "hi": 16000.0},
    "earbuds": {"fn": earbuds,    "lo": 30.0,   "hi": 16000.0},
    "car":     {"fn": car,        "lo": 120.0,  "hi": 6000.0},
    "mono":    {"fn": mono,       "lo": 20.0,   "hi": 16000.0},
}

# A band is gated by its share of the programme's energy, not by its distance
# from the loudest band: the loudest band moves with the material, so a gate
# tied to it moves too, and a band sitting on the line flips the whole result.
FLOOR_DB = -55.0      # share of total energy, dB (1/300000 of the power)
WIDTH_DB = 16.0       # soft transition of the gate, dB


def _soft_gate(level_db, floor_db=FLOOR_DB, width_db=WIDTH_DB):
    """Smoothstep: 0 well below the floor, 1 well above, no step in between."""
    z = np.clip((np.asarray(level_db) - (floor_db - width_db / 2)) / width_db,
                0.0, 1.0)
    return z * z * (3.0 - 2.0 * z)


def _k_curve(centers):
    """K-weighting magnitude in dB at each band centre (BS.1770 biquads).

    Raw energy weighting is a bass detector: on sustained material the low bands hold
    almost all the power, so a 3 dB move at 2 kHz disappears. Weighting by how
    loud a band is *heard* is what the metric is actually about.
    """
    w = np.exp(-2j * np.pi * centers / dsp.SR)
    num1 = dsp._B1[0] + dsp._B1[1] * w + dsp._B1[2] * w ** 2
    den1 = dsp._A1[0] + dsp._A1[1] * w + dsp._A1[2] * w ** 2
    num2 = dsp._B2[0] + dsp._B2[1] * w + dsp._B2[2] * w ** 2
    den2 = dsp._A2[0] + dsp._A2[1] * w + dsp._A2[2] * w ** 2
    return 20 * np.log10(np.maximum(np.abs(num1 / den1 * num2 / den2), 1e-9))


def _shares(levels, centers):
    """Per-band fraction of perceived (K-weighted) energy, and its dB."""
    lev = np.asarray(levels, dtype=float) + _k_curve(centers)
    p = 10 ** (lev / 10.0)
    share = p / max(p.sum(), 1e-30)
    return share, 10 * np.log10(np.maximum(share, 1e-30))


def translation(x, meta=None, centers_ref=None, floor_db=FLOOR_DB,
                width_db=WIDTH_DB):
    """How the band balance survives each device, as one continuous number.

      shift -- energy-weighted RMS of the contour change, inside the device's
               flat range, over bands that carry programme. No max, no binary
               gate: a band near the floor fades in smoothly instead of
               switching the whole metric on or off.
      lost  -- bands that carried programme and that the device does not
               reproduce at all.

    A phone always loses the sub; that is physics, not a defect. A phone that
    also reshapes the mids is a mastering defect.
    """
    from . import measure
    centers, edges = dsp.band_grid(per_oct=measure.PER_OCT)
    f0 = measure.features(x, centers, edges, light=True)
    rel0, lev0 = f0["rel"], f0["levels"]
    share0, lvl0 = _shares(lev0, centers)
    gate0 = _soft_gate(lvl0, floor_db, width_db)
    # sqrt of the energy share: a band with 1% of the power counts, but a band
    # with 0.001% cannot decide the number (that was the 16 kHz failure)
    w0 = gate0 * np.sqrt(share0)

    out = {}
    for name, spec in DEVICES.items():
        y = spec["fn"](x).astype(np.float32)
        if y.shape[0] != x.shape[0]:
            y = y[:x.shape[0]]
        f1 = measure.features(y, centers, edges, light=True)
        rel1, lev1 = f1["rel"], f1["levels"]
        share1, lvl1 = _shares(lev1, centers)
        flat = (centers >= spec["lo"]) & (centers <= spec["hi"])
        # denominator is the FULL coverage of the flat range, not the sum of
        # the weights that happened to pass: normalising by the passed weight
        # makes a lone band equal to its own value however small its weight is,
        # which is exactly the cliff we are removing
        cover = float(np.sqrt(share0[flat]).sum())
        d = rel1 - rel0
        if cover > 0:
            shift = float(np.sqrt((w0[flat] * d[flat] ** 2).sum() / cover))
            mean = float((w0[flat] * np.abs(d[flat])).sum() / cover)
        else:
            shift = mean = 0.0
        lost = (gate0 > 0.5) & (lvl1 < floor_db - width_db)
        out[name] = {
            "shift_max": shift,          # kept: same key, new meaning (RMS)
            "shift_mean": mean,
            "lost": int(lost.sum()),
            "lost_hz": [float(c) for c in centers[lost]],
        }
    return out


def report(x, meta, floor_db=FLOOR_DB, width_db=WIDTH_DB):
    from . import measure
    centers, edges = dsp.band_grid(per_oct=measure.PER_OCT)
    t = translation(x, meta, centers, floor_db, width_db)
    worst = max(t.items(), key=lambda kv: kv[1]["shift_max"])
    lines = [f"  {'device':>8s} {'shift':>7s} {'mean':>7s} {'lost':>5s}  bands lost"]
    for k, v in t.items():
        hz = ", ".join(f"{h:.0f}" for h in v["lost_hz"][:6])
        if len(v["lost_hz"]) > 6:
            hz += ", ..."
        lines.append(f"  {k:>8s} {v['shift_max']:7.1f} {v['shift_mean']:7.1f} "
                     f"{v['lost']:5d}  {hz}")
    verdict = "pass" if worst[1]["shift_max"] < 6 else "FAIL"
    lines.append(f"  worst balance shift: {worst[0]} "
                 f"{worst[1]['shift_max']:.1f} dB ({verdict})")
    return "\n".join(lines), t

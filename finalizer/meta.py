"""The meta: a boundary, not a target.

It answers one question -- "can this be released?" -- and says nothing about how
a piece should sound. Inside the boundary the picture is yours.

Four groups of numbers:

1. CREST_MAX -- per octave band, how far a peak may rise above that band's own
   body. Body = P75 of the band envelope; peak = P99.5 - P75. The curve comes
   from the device law (roughly 6 dB of limiter headroom in phones and laptops,
   widening above ~2 kHz where codec pre-echo instead of excursion is the
   limit) and, independently, from the median of eight finished masters, which
   landed on almost the same line.
2. CREST_MIN -- the floor. Below it you are not mastering, you are squashing.
3. LUFS / TP -- absolute. Every streaming service normalises to about -14 LUFS,
   so a hotter master is turned down anyway and keeps only the limiting.
4. MONO_BELOW -- the side channel is high-passed here. Below it the image must
   be solid: phones and most small speakers fold down to one.

What is deliberately NOT here:

  * a contour or a width profile. Matching a spectral shape is a different job
    (--target), and baking one catalogue's median into the meta would turn its
    habits into a rule for every other piece.
  * a preference. How close to sit to the boundary is per track and lives in
    profiles.toml.

These are boundaries. Everything inside them is free.
"""
import numpy as np

# Analysis grid: 1/3-octave centres. Used by the midrange guard and by the
# resonance detector; it is a measuring scale, not a target.
CENTERS = [25.0, 31.5, 39.7, 50.0, 63.0, 79.4, 100.0, 126.0, 158.7, 200.0,
           252.0, 317.5, 400.0, 504.0, 635.0, 800.0, 1007.9, 1269.9, 1600.0,
           2015.9, 2539.8, 3200.0, 4031.7, 5079.7, 6400.0, 8063.5, 10159.4,
           12800.0, 16127.0]

CREST_EDGES = [30, 60, 120, 240, 480, 960, 1920, 3840, 7680, 15360, 20000]

# Ceiling: device headroom (excursion below, codec pre-echo above).
CREST_MAX = [6.2, 6.2, 6.2, 6.2, 6.2, 6.2, 7.2, 8.3, 9.5, 10.3]

# Floor: past this you are not mastering, you are squashing.
CREST_MIN = [2.5, 2.5, 2.5, 3.0, 3.0, 3.0, 3.5, 4.0, 4.5, 5.0]

LUFS = -14.0
TP = -1.0
MONO_BELOW = 120.0

# The calibrated boundary. There used to be two names for it; only one was
# ever used, so the second is gone -- two names for the same job is a trap.
CREST_MAX_CALIBRATED = [6.2, 6.2, 6.2, 6.2, 6.2, 6.2, 7.2, 8.3, 8.0, 10.3]

META = {
    "name": "meta",
    "centers": CENTERS,
    "crest_edges": CREST_EDGES,
    "crest_max": CREST_MAX_CALIBRATED,
    "crest_min": CREST_MIN,
    "lufs": LUFS,
    "tp": TP,
    "mono_below": MONO_BELOW,
}

META_REGISTRY = {"meta": META}

# 7.7-15 kHz = 8.0 dB was confirmed by two blind listening passes: one where
# the two candidates were identical, and one where the change actually engaged
# and was clearly preferred over 9.5. A third candidate cut 15-20 kHz to 5.0 dB
# and lost the same test on the only two tracks where that band carries
# programme, so it is gone: cutting the top octave did not help.
DEFAULT_META = "meta"


def get(name=None):
    """Return a named meta, or None if unknown."""
    return META_REGISTRY.get(name or DEFAULT_META)

NOTES = {
    "crest_max": "Device limiter/excursion headroom below ~2 kHz; above it "
                 "measured pre-echo of real codecs no longer supports it; "
                 "8.0 dB at 7.7-15 kHz came from listening.",
    "crest_min": "2.5-5 dB. Below this a band is static, not dynamic.",
    "lufs": "-14 LUFS: streaming normalises here; louder buys nothing.",
    "tp": "-1 dBTP, measured at 4x oversampling, not sample peak.",
    "mono_below": "side is high-passed here; below it the image must survive "
                  "a single speaker.",
}


def as_target(meta=None):
    """Shape the meta like a measured state so the chain can consume it."""
    meta = meta or META
    centers = np.array(meta["centers"], dtype=float)
    return {
        "name": meta["name"],
        "centers": centers,
        "edges": np.concatenate([[centers[0] / 2 ** (1 / 6)],
                                 centers * 2 ** (1 / 6)]),
        "lufs": meta["lufs"],
        "tp": meta["tp"],
        "mono_below": meta["mono_below"],
        "crest_edges": np.array(meta["crest_edges"], dtype=float),
        "crest_max": np.array(meta["crest_max"], dtype=float),
        "crest_min": np.array(meta["crest_min"], dtype=float),
    }


def table(meta=None):
    meta = meta or META
    lines = [f"  meta: {meta['name']}",
             f"  {'band, Hz':>14s} {'ceiling':>8s} {'floor':>7s}"]
    for i, edge in enumerate(meta["crest_edges"][:-1]):
        lines.append(f"  {edge:6.0f}-{meta['crest_edges'][i + 1]:<7.0f} "
                     f"{meta['crest_max'][i]:8.1f} {meta['crest_min'][i]:7.1f}")
    lines.append("")
    lines.append(f"  absolutes: {meta['lufs']:+.1f} LUFS, "
                 f"{meta['tp']:+.1f} dBTP, mono below {meta['mono_below']:.0f} Hz")
    return "\n".join(lines)

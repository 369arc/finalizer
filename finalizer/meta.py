"""The meta: a boundary, not a target.

It answers one question -- "can this be released?" -- and says nothing about how
a piece should sound. Inside the boundary the picture is yours.

Four groups of numbers:

1. CREST_MAX -- per octave band, how far a peak may rise above that band's own
   body. Body = P75 of the band envelope; crest = P99.5 - P75. Codec-aware
   ceilings optimized for high-density -14 LUFS delivery (pure structural deltas,
   free of artificial headroom buffers).
2. CREST_MIN -- a craft floor. It is displayed but NOT enforced by the chain or
   by `check`: the chain does not add transients to meet it.
3. LUFS / TP -- delivery conventions, not physical boundaries. Platform targets
   differ; the true-peak meter is the larger of BS.1770-4 Annex 2 and a
   polyphase 4x meter, and the report names both.
4. MONO_BELOW -- a high-pass corner for the side channel. The side is
   attenuated, not exactly zero; the report gives side/mid and mono loss below
   the corner.

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

# v0.3.0 Codec-Optimized Crest Ceilings for -14 LUFS (Buffer removed, +0.5 restored)
# Bands: 30-60, 60-120, 120-240, 240-480, 480-960, 960-1920, 1920-3840, 3840-7680, 7680-15360, 15360-20000
CREST_MAX = [5.0, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.5, 10.0, 10.5]

# Craft floor. Not enforced by the chain or by `check`: the chain does not add
# transients to meet it.
CREST_MIN = [2.5, 2.5, 2.5, 3.0, 3.0, 3.0, 3.5, 4.0, 4.5, 5.0]

LUFS = -14.0
TP = -1.0
MONO_BELOW = 120.0

# The standard commercial streaming boundary.
META = {
    "name": "meta",
    "metric_version": "crest-v0.3.0-codec-optimized",
    "centers": CENTERS,
    "crest_edges": CREST_EDGES,
    "crest_max": CREST_MAX,
    "crest_min": CREST_MIN,
    "lufs": LUFS,
    "tp": TP,
    "mono_below": MONO_BELOW,
}

META_REGISTRY = {"meta": META}

# Listening is deliberately absent from this file: a preference is not a
# boundary. Blind comparisons exist in the project history, but they are not
# part of the argument here until a device measurement replaces the estimate.
DEFAULT_META = "meta"


def get(name=None):
    """Return a named meta, or None if unknown."""
    return META_REGISTRY.get(name or DEFAULT_META)

NOTES = {
    "crest_max": "v0.3.0 codec-optimized ceiling for -14 LUFS without artificial buffers. "
                 "Clamps sub-bass (30-60Hz at 5.0 dB) to prevent codec distortion, "
                 "gradually opens up through the mids, and tapers high-end near the ~15k codec cut.",
    "crest_min": "Craft floor; reported by check/master, not enforced by the "
                 "chain. The chain does not add transients to meet it.",
    "lufs": "Delivery convention (-14.0 LUFS streaming target).",
    "tp": "Delivery convention; measured on the larger of BS.1770-4 Annex 2 "
          "and a polyphase 4x meter. Name the meter in a report.",
    "mono_below": "High-pass corner; the side is attenuated, not zero. The "
                  "report gives side/mid and mono loss below the corner.",
}


def as_target(meta=None):
    """Shape the meta like a measured state so the chain can consume it."""
    meta = meta or META
    centers = np.array(meta["centers"], dtype=float)
    return {
        "name": meta["name"],
        "metric_version": meta.get("metric_version"),
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
    lines = [f"  meta: {meta['name']} "
             f"(metric {meta.get('metric_version', 'unknown')}; v0.3.0 codec-optimized)",
             f"  {'band, Hz':>14s} {'ceiling':>8s} {'floor':>7s}"]
    for i, edge in enumerate(meta["crest_edges"][:-1]):
        lines.append(f"  {edge:6.0f}-{meta['crest_edges'][i + 1]:<7.0f} "
                     f"{meta['crest_max'][i]:8.1f} {meta['crest_min'][i]:7.1f}")
    lines.append("")
    lines.append(f"  absolutes: {meta['lufs']:+.1f} LUFS, "
                 f"{meta['tp']:+.1f} dBTP, mono below {meta['mono_below']:.0f} Hz")
    return "\n".join(lines)

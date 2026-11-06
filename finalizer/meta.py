"""The meta: a boundary, not a target.

It answers one question -- "can this be released?" -- and says nothing about how
a piece should sound. Inside the boundary the picture is yours.

Four groups of numbers:

1. CREST_MAX -- per octave band, how far a peak may rise above that band's own
   body. Body = P75 of the band envelope; crest = P99.5 - P75. These are
   PROVISIONAL MODEL ESTIMATES, not measurements. The audit did not reproduce
   the device-law or codec-pre-echo rationale; see research/MASTERING_META_AUDIT.md
   and research/RESULTS.md. The 75 dB SPL reference is not implemented in code.
2. CREST_MIN -- a provisional craft floor. It is displayed but NOT enforced by
   the chain or by `check`; the audit found no empirical basis for a universal
   value. See research/EXPERIMENT_DESIGN.md for the experiment that would
   establish or reject it.
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

# Provisional model estimate. The values were selected under the legacy crest
# estimator (per-band max gate); the current estimator uses a broadband
# activity mask. They are NOT calibrated; see research/MASTERING_META_AUDIT.md.
CREST_MAX = [6.2, 6.2, 6.2, 6.2, 6.2, 6.2, 7.2, 8.3, 8.0, 10.3]

# Provisional craft floor. Not enforced by the chain or by `check`; the audit
# found no empirical basis for a universal value. See the audit and the F_b
# experiment design.
CREST_MIN = [2.5, 2.5, 2.5, 3.0, 3.0, 3.0, 3.5, 4.0, 4.5, 5.0]

LUFS = -14.0
TP = -1.0
MONO_BELOW = 120.0

# The boundary has one name. The values are provisional; see the audit.
META = {
    "name": "meta",
    "metric_version": "crest-v1.1-broadband-gate",
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
    "crest_max": "Provisional model estimate at a 75 dB SPL reference; not "
                 "measured. The codec rationale was not reproduced at "
                 "96-128 kbps; see research/pre_echo.py and the audit.",
    "crest_min": "Provisional craft floor; reported by check/master, not "
                 "enforced by the chain. The audit found no empirical basis; "
                 "see the F_b experiment design.",
    "lufs": "Delivery convention, not a physical boundary; platform targets "
            "differ (Spotify -14, Apple about -16, Deezer -15).",
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
    lines = [f"  meta: {meta['name']}  "
             f"(metric {meta.get('metric_version', 'unknown')}; provisional)",
             f"  {'band, Hz':>14s} {'ceiling':>8s} {'floor':>7s}"]
    for i, edge in enumerate(meta["crest_edges"][:-1]):
        lines.append(f"  {edge:6.0f}-{meta['crest_edges'][i + 1]:<7.0f} "
                     f"{meta['crest_max'][i]:8.1f} {meta['crest_min'][i]:7.1f}")
    lines.append("")
    lines.append(f"  absolutes: {meta['lufs']:+.1f} LUFS, "
                 f"{meta['tp']:+.1f} dBTP, mono below {meta['mono_below']:.0f} Hz")
    return "\n".join(lines)

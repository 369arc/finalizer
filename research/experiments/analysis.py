"""Analysis helpers for the device power-compression experiment.

These functions operate on already measured `PC_b(c)` values. They do not
read or write audio. The measurement harness is `device_measure.py`; the
listening analysis is described in `EXPERIMENT_DESIGN.md`.
"""
from __future__ import annotations

import numpy as np


def k_from_curve(crest, pc, delta=2.0, tol=0.0):
    """Largest crest in the connected interval from c=0 with PC <= delta.

    Parameters
    ----------
    crest : sequence of float
        Input crest values, dB, ascending or unsorted.
    pc : sequence of float
        Power compression, dB (negative = compression).
    delta : float
        Allowed compression magnitude, dB (positive).
    tol : float
        Monotonicity tolerance, dB. A rise larger than `tol` is reported.

    Returns
    -------
    dict with `k_db`, `monotonic`, `reason`, `curve`.
    """
    c = np.asarray(crest, dtype=float)
    p = np.asarray(pc, dtype=float)
    if len(c) != len(p) or len(c) == 0:
        raise ValueError("crest and pc must be non-empty and equal length")
    order = np.argsort(c)
    c, p = c[order], p[order]
    if c[0] > 0:
        c = np.concatenate([[0.0], c])
        p = np.concatenate([[0.0], p])
    # Monotonicity of compression (more crest -> not less compression).
    dp = np.diff(p)
    bad = np.where(dp > tol)[0]
    monotonic = len(bad) == 0
    # Connected interval from c=0.
    ok = p >= -delta
    if not ok[0]:
        return {"k_db": 0.0, "monotonic": monotonic,
                "reason": "reference already exceeds delta", "curve": list(zip(c, p))}
    end = 0
    for i in range(1, len(c)):
        if ok[i]:
            end = i
        else:
            break
    return {"k_db": float(c[end]), "monotonic": monotonic,
            "reason": "ok" if monotonic else f"non-monotone at {c[bad[0]]:.2f} dB",
            "curve": list(zip(c.tolist(), p.tolist()))}


def bootstrap_k(rows, delta=2.0, n_boot=1000, seed=0):
    """Bootstrap `K_b` over units.

    `rows` is a sequence of dicts with keys `unit`, `crest`, `pc`. Units are
    resampled with replacement; within a unit all crests are kept.
    """
    by_unit = {}
    for r in rows:
        by_unit.setdefault(r["unit"], []).append((r["crest"], r["pc"]))
    units = list(by_unit)
    if not units:
        raise ValueError("no rows")
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        pick = rng.choice(units, size=len(units), replace=True)
        c, p = [], []
        for u in pick:
            for cc, pp in by_unit[u]:
                c.append(cc)
                p.append(pp)
        k = k_from_curve(c, p, delta=delta)["k_db"]
        vals.append(k)
    vals = np.asarray(vals, dtype=float)
    return {"k_db": float(np.mean(vals)),
            "ci95": [float(np.percentile(vals, 2.5)),
                     float(np.percentile(vals, 97.5))],
            "sd": float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0,
            "n_units": len(units)}


def mixed_model(rows):
    """Optional mixed-effects fit: pc ~ crest * SPL + (1|unit).

    Requires pandas and statsmodels. Returns the fitted model and a summary
    string. This is a template; the pre-registered model in
    `EXPERIMENT_DESIGN.md` controls the actual analysis.
    """
    import pandas as pd
    import statsmodels.formula.api as smf
    df = pd.DataFrame(rows)
    if "spl" not in df:
        df["spl"] = 75.0
    model = smf.mixedlm("pc ~ crest * C(spl)", df, groups=df["unit"])
    fit = model.fit(reml=True)
    return fit, str(fit.summary())

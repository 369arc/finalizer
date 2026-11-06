"""Regenerate the audit figures from audit_crest.json / audit_relations.json.

If the JSON files are absent, the script falls back to `expected.json`, which
contains the values published in research/RESULTS.md. This makes the figures
reproducible without redistributing the source masters.

Run:
    python3 research/audit/make_figures.py
"""
from __future__ import annotations

import argparse
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def load(path, fallback):
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    with open(fallback) as fh:
        return json.load(fh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crest", default=os.path.join(HERE, "audit_crest.json"))
    ap.add_argument("--relations", default=os.path.join(HERE, "audit_relations.json"))
    ap.add_argument("--expected", default=os.path.join(HERE, "expected.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "research", "figures"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    c = load(a.crest, a.expected)
    r = load(a.relations, a.expected)
    bands = c["bands"]
    x = np.arange(len(bands))
    k = np.array([6.2, 6.2, 6.2, 6.2, 6.2, 6.2, 7.2, 8.3, 8.0, 10.3])
    plt.rcParams.update({"font.size": 9, "axes.grid": True, "grid.alpha": 0.25,
                         "figure.dpi": 160, "savefig.bbox": "tight"})

    # fig1
    fig, ax = plt.subplots(figsize=(8.2, 3.8))
    ax.step(x, k, where="mid", color="black", lw=2, label="K_b (current)")
    for name, t in c["tracks"].items():
        v = np.array(t["v1"], float)
        ax.plot(x, v, "o-", ms=4, lw=1.2, label=name)
    ax.set_xticks(x)
    ax.set_xticklabels(bands, rotation=35, ha="right")
    ax.set_ylabel(r"$C_b$ = P99.5 − P75, dB")
    ax.set_title("Per-band tail crest of five finished masters vs. current ceilings")
    ax.set_ylim(0, 14)
    ax.legend(ncol=3, fontsize=8, frameon=False)
    fig.savefig(os.path.join(a.out, "fig1_crest_vs_meta.png"))
    plt.close(fig)

    # fig2 window
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.5), sharey=True)
    for ax, name in zip(axes, list(c["tracks"])[:2]):
        t = c["tracks"][name]
        for n, vals in t["window"].items():
            ax.plot(x, vals, "o-", ms=3, lw=1.2, label=f"N={n}")
        ax.set_xticks(x)
        ax.set_xticklabels(bands, rotation=45, ha="right", fontsize=7)
        ax.set_title(name)
        ax.set_ylabel(r"$C_b$, dB")
        ax.legend(fontsize=8, frameon=False)
    fig.suptitle("Window sensitivity: a 4096 window does not resolve 30–60 Hz")
    fig.savefig(os.path.join(a.out, "fig2_window_sensitivity.png"))
    plt.close(fig)

    # fig3 duration
    fig, axes = plt.subplots(1, 2, figsize=(8.8, 3.4), sharey=True)
    for ax, name in zip(axes, list(c["tracks"])[:2]):
        t = c["tracks"][name]
        keys = list(t["duration"])
        for b in (0, 5, 8, 9):
            ax.plot([float(key) for key in keys],
                    [t["duration"][key][b] for key in keys],
                    "o-", ms=4, lw=1.2, label=bands[b])
        ax.set_xlabel("excerpt length, s")
        ax.set_title(name)
        ax.set_ylabel(r"$C_b$, dB")
        ax.legend(fontsize=7, frameon=False)
    fig.suptitle("A 30 s excerpt is not a short version of the track")
    fig.savefig(os.path.join(a.out, "fig3_duration.png"))
    plt.close(fig)

    # fig4 bootstrap
    names = list(c["tracks"])[:2]
    fig, axes = plt.subplots(1, 2, figsize=(9.0, 3.4), sharey=True)
    for ax, name in zip(axes, names):
        t = c["tracks"][name]
        mid = np.array(t["v1"], float)
        lo = mid - np.array(t["ci"]["lo"], float)
        hi = np.array(t["ci"]["hi"], float) - mid
        ax.errorbar(x, mid, yerr=[lo, hi], fmt="o", ms=4, capsize=3, lw=1.2)
        ax.step(x, k, where="mid", color="black", lw=2)
        ax.set_xticks(x)
        ax.set_xticklabels(bands, rotation=45, ha="right", fontsize=7)
        ax.set_title(name)
        ax.set_ylabel(r"$C_b$, dB")
    fig.suptitle("Bootstrap 95% intervals are comparable to the band differences")
    fig.savefig(os.path.join(a.out, "fig4_bootstrap.png"))
    plt.close(fig)

    # fig5 correlations
    rel = r.get("tracks", {})
    if rel:
        fig, ax = plt.subplots(figsize=(7.2, 3.4))
        width = 0.8 / max(1, len(rel))
        for i, (name, t) in enumerate(rel.items()):
            ax.bar(x + i * width, t["corr_by_band"], width=width, label=name)
        ax.axhline(0, color="black", lw=0.8)
        ax.set_xticks(x + width * (len(rel) - 1) / 2)
        ax.set_xticklabels(bands, rotation=45, ha="right", fontsize=7)
        ax.set_ylabel("Pearson r(B, C)")
        ax.set_title("Body and crest are not independent (10 s segments)")
        ax.legend(fontsize=7, frameon=False, ncol=2)
        fig.savefig(os.path.join(a.out, "fig5_body_crest_bars.png"))
        plt.close(fig)

    # fig6 side
    sf = r.get("side_filter", [])
    if sf:
        fig, ax = plt.subplots(figsize=(6.4, 3.6))
        ax.semilogx([v["hz"] for v in sf], [v["attenuation_db"] for v in sf],
                    "o-", lw=1.5)
        ax.axvline(120, color="black", ls="--", lw=1)
        ax.axhline(0, color="black", lw=0.8)
        ax.set_xlabel("frequency, Hz")
        ax.set_ylabel("side attenuation, dB")
        ax.set_title("The mono-below filter is a high-pass, not a zero")
        ax.set_ylim(-40, 2)
        ax.grid(True, which="both", alpha=0.25)
        fig.savefig(os.path.join(a.out, "fig6_side_highpass.png"))
        plt.close(fig)

    print(f"figures written to {a.out}")


if __name__ == "__main__":
    main()

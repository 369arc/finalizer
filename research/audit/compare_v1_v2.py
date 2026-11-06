#!/usr/bin/env python3
"""Compare the pre-audit sensor and chain (v1, af04531) with the current one (v2).

Measurement only. The script reads audio, writes synthetic signals and renders
into a work directory (never into the repository) and writes one JSON file.
Every measured table in research/V1_VS_V2.md is backed by a key of that JSON; the JSON records
the commits, the function fingerprints, the environment and the commands.

    python3 research/audit/compare_v1_v2.py \\
        --tracks T2=/path/to/T2.wav \\
                 T4=/path/to/T4.wav \\
                 T5=/path/to/T5.wav \\
        --work /tmp/opencode/fin_compare \\
        --out research/audit/compare_v1_v2.json

v1 is materialised with `git archive`, so the repository keeps no worktree
metadata. --skip-renders measures without rendering masters.

Fingerprints are SHA-256 of the function's AST with the docstring and the name
removed: two functions with the same fingerprint have the same logic.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
V1 = "af04531"
SR = 48000
EDGES = [30, 60, 120, 240, 480, 960, 1920, 3840, 7680, 15360, 20000]
NB = len(EDGES) - 1
MARGIN = 0.35                      # the fixed tolerance used by check and master
BURST_BAND = 8                     # 7680-15360 Hz, where the burst is placed
BURSTS = [(30, 0.1), (30, 0.25), (30, 0.5), (60, 0.1), (60, 0.25), (60, 0.5),
          (120, 0.1), (120, 0.25), (120, 0.5)]
VARIANTS = {
    "v1_shipped": ("v1", []),
    "v1_meter": ("v1", ["--no-deharsh"]),
    "v2_shipped": ("v2", []),
    "v2_meter": ("v2", ["--no-deharsh"]),
}
SINES = {
    "sine_1k_m3dBFS": (10 ** (-3 / 20), 1000.0, 0.0),
    "sine_12k_0dBFS": (1.0, 12000.0, 0.0),
    "sine_19k_0dBFS": (1.0, 19000.0, 0.0),
    "sine_fs4_45deg_0dBFS": (1.0, SR / 4, math.pi / 4),
}


# --------------------------------------------------------------- child side
# These run inside a subprocess that has inserted one tree (v1 or v2) first on
# sys.path, so each measurement uses exactly that tree's code.

def _fingerprint(fn):
    import inspect
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    node = tree.body[0]
    node.name = "f"
    body = node.body
    if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        node.body = body[1:]
    return hashlib.sha256(ast.dump(node).encode()).hexdigest()[:12]


def _nl(a):
    return [None if not np.isfinite(v) else round(float(v), 4)
            for v in np.asarray(a, dtype=float).ravel()]


def child(root, task):
    sys.path.insert(0, root)
    import soundfile as sf
    from finalizer import chain, dsp, measure, meta

    def load(path):
        x, sr = sf.read(path, dtype="float32", always_2d=True)
        if sr != SR or x.shape[1] != 2:
            raise ValueError(f"{path}: need 48 kHz stereo")
        return x

    def estimators(x):
        out = {"band_crest": _nl(measure.band_crest(x, EDGES))}
        if hasattr(measure, "band_crest_legacy"):
            out["legacy"] = _nl(measure.band_crest_legacy(x, EDGES))
        if hasattr(measure, "band_crest_detail"):
            d = measure.band_crest_detail(x, EDGES)
            out["detail"] = {"values": _nl(d["values"]), "body": _nl(d["body"]),
                             "n_active": [int(v) for v in d["n_active"]],
                             "status": list(d["status"])}
        return out

    kind = task["kind"]
    if kind == "identity":
        fns = {
            "measure.band_crest": measure.band_crest,
            "measure.band_crest_legacy": getattr(measure, "band_crest_legacy", None),
            "measure.band_crest_detail": getattr(measure, "band_crest_detail", None),
            "measure.crest_report": getattr(measure, "crest_report", None),
            "measure.sustain_contour": measure.sustain_contour,
            "measure.features": measure.features,
            "measure.side_metrics": getattr(measure, "side_metrics", None),
            "chain.crest_stage": chain.crest_stage,
            "chain.render": chain.render,
            "chain.stereo_width": chain.stereo_width,
            "chain.resonance_notches": chain.resonance_notches,
            "dsp.stft": dsp.stft,
            "dsp.band_power": dsp.band_power,
            "dsp.lufs_integrated": dsp.lufs_integrated,
            "dsp.true_peak": dsp.true_peak,
            "dsp.true_peak_poly": getattr(dsp, "true_peak_poly", None),
            "dsp.true_peak_annex2": getattr(dsp, "true_peak_annex2", None),
            "dsp.trim_true_peak": dsp.trim_true_peak,
            "dsp.limit": dsp.limit,
        }
        return {
            "fingerprints": {k: (None if v is None else _fingerprint(v)) for k, v in fns.items()},
            "constants": {"CREST_MAX": list(meta.CREST_MAX), "CREST_MIN": list(meta.CREST_MIN),
                          "LUFS": meta.LUFS, "TP": meta.TP, "MONO_BELOW": meta.MONO_BELOW,
                          "CREST_EDGES": list(meta.CREST_EDGES)},
            "has_crest_max_calibrated": hasattr(meta, "CREST_MAX_CALIBRATED"),
            "has_metric_version": "metric_version" in meta.META,
        }

    if kind == "estimator":
        return {name: estimators(load(path)) for name, path in task["files"].items()}

    if kind == "control":
        import soundfile as sf_out
        out = {}
        for name, path in task["files"].items():
            x = load(path)
            y, _ = chain.crest_stage(x, EDGES, np.full(NB, 6.2), tau_atk=0.005, tau_rel=0.12)
            y = y.astype(np.float32)
            dest = os.path.join(task["out_dir"], f"cs_{task['tag']}_{name}.wav")
            sf_out.write(dest, y, SR, subtype="FLOAT")
            out[name] = {"path": dest, "estimators": estimators(y)}
        return out

    if kind == "side":
        out = {}
        t = np.arange(4 * SR) / SR
        tgt = {"centers": dsp.band_grid()[0]}
        for hz in task["freqs"]:
            s = 0.5 * np.sin(2 * np.pi * hz * t)
            x = np.stack([s, -s], axis=1).astype(np.float32)
            y = chain.stereo_width(x, None, tgt, None, mono_below=120, match=False)
            before = np.sqrt(np.mean(((x[:, 0] - x[:, 1]) / 2) ** 2))
            after = np.sqrt(np.mean(((y[:, 0] - y[:, 1]) / 2) ** 2))
            out[str(hz)] = round(float(20 * np.log10(after / before)), 3)
        return out

    if kind == "loudness":
        out = {}
        for name, path in task["files"].items():
            x = load(path)
            row = {"lufs": round(float(dsp.lufs_integrated(x)), 4),
                   "tp_public": round(float(dsp.true_peak(x)), 4)}
            if hasattr(dsp, "true_peak_annex2"):
                row["tp_annex2"] = round(float(dsp.true_peak_annex2(x)), 4)
                row["tp_poly"] = round(float(dsp.true_peak_poly(x)), 4)
            out[name] = row
        return out

    raise ValueError(kind)


def run_child(root, task):
    r = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child", str(root)],
                       input=json.dumps(task), capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"child failed in {root}:\n{r.stderr[-3000:]}")
    return json.loads(r.stdout)


# --------------------------------------------------------------- parent side

def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True).stdout.strip()


def git_info():
    return {
        "head": git("rev-parse", "--short", "HEAD"),
        "v1": V1,
        "v1_resolved": git("rev-parse", "--short", V1),
        "tracked_changes": git("status", "--porcelain", "--untracked-files=no"),
        "gate_introduced": git("log", "--format=%h %ad %s", "--date=short",
                               "-S", "e.max() - 45.0", "--", "finalizer/measure.py",
                               "finalizer/chain.py"),
    }


def materialise(work):
    dest = work / "v1_tree"
    if not (dest / "run.py").exists():
        dest.mkdir(parents=True, exist_ok=True)
        subprocess.run(f"git -C '{REPO}' archive {V1} | tar -x -C '{dest}'",
                       shell=True, check=True)
    return dest


def load_f32(path):
    import soundfile as sf
    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if sr != SR or x.shape[1] != 2:
        raise SystemExit(f"{path}: need 48 kHz stereo")
    return x


def burst_signal(dur, burst_s, at_s=15.0, seed=2):
    from scipy.signal import butter, sosfilt
    n = int(dur * SR)
    t = np.arange(n) / SR
    low = 0.2 * np.sin(2 * np.pi * 80 * t)
    rng = np.random.default_rng(seed)
    sos = butter(8, [7680 / (SR / 2), 15360 / (SR / 2)], btype="band", output="sos")
    hi = sosfilt(sos, rng.standard_normal(n))
    hi = hi / np.sqrt(np.mean(hi ** 2)) * 10 ** (-30 / 20)
    s = int(at_s * SR)
    hi[s:s + int(burst_s * SR)] *= 10 ** (50 / 20)
    return np.stack([low + hi, low + hi], axis=1).astype(np.float32)


def env_grid(x):
    from finalizer import dsp
    X = dsp.stft(x, 4096, 1024)
    P = dsp.band_power(X)
    f = np.fft.rfftfreq(4096, 1 / SR)
    E = np.empty((P.shape[0], NB))
    for b in range(NB):
        sel = (f >= EDGES[b]) & (f < EDGES[b + 1])
        E[:, b] = 10 * np.log10(P[:, sel].sum(axis=1) + 1e-20)
    allsel = (f >= EDGES[0]) & (f < EDGES[-1])
    e_tot = 10 * np.log10(P[:, allsel].sum(axis=1) + 1e-20)
    return E, e_tot


def population(E, e_tot):
    """The populations each root uses: the chain's base and the report's body."""
    p75_all = np.percentile(E, 75, axis=0)
    mask = (e_tot >= e_tot.max() - 40.0) & (e_tot >= -70.0)
    body_leg = np.full(NB, np.nan)
    body_v2 = np.full(NB, np.nan)
    for b in range(NB):
        e = E[:, b]
        act = e[e > e.max() - 45.0]
        if len(act) > 20:
            body_leg[b] = np.percentile(act, 75)
        if mask.sum() >= 50:
            body_v2[b] = np.percentile(E[mask, b], 75)
    return {"frames": int(len(e_tot)), "mask_frames": int(mask.sum()),
            "p75_all": p75_all, "body_legacy_active": body_leg, "body_v2_mask": body_v2,
            "quiet_v1": p75_all < p75_all.max() - 45.0,
            "quiet_v2": body_v2 < -70.0}


def bc_stats(E):
    seg = int(round(10 * SR / 1024))
    B, C = [], []
    for s in range(0, len(E) - seg + 1, seg):
        e = E[s:s + seg]
        b = np.percentile(e, 75, axis=0)
        B.append(b)
        C.append(np.percentile(e, 99.5, axis=0) - b)
    return np.array(B), np.array(C)


def decision_v1(v, K):
    if v is None:
        return "ok (not assessed)"
    return "over" if v > K + MARGIN else "ok"


def decision_v2(v, status, K):
    if status != "OK" or v is None:
        return "UNKNOWN"
    if v <= K:
        return "PASS"
    return "FAIL" if v > K + MARGIN else "UNKNOWN"


def ideal_tp(x, seg_s=2.0, pad_s=0.25):
    """Band-limited reference: FFT interpolation x4 of overlapping chunks."""
    from scipy.signal import resample
    n = x.shape[0]
    L = int(seg_s * SR)
    P = int(pad_s * SR)
    best = 0.0
    for c in range(x.shape[1]):
        xc = x[:, c].astype(np.float64)
        for s in range(0, n, L):
            a = max(0, s - P)
            b = min(n, s + L + P)
            seg = xc[a:b]
            up = resample(seg, 4 * len(seg))
            i0 = (s - a) * 4
            i1 = (s - a + min(L, n - s)) * 4
            best = max(best, float(np.max(np.abs(up[i0:i1]))))
    return 20 * np.log10(best + 1e-20)


def ffmpeg_meter(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                        "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    txt = r.stderr
    I = re.findall(r"I:\s+(-?\d+\.\d+) LUFS", txt)
    P = re.findall(r"Peak:\s+(-?\d+\.\d+) dBFS", txt)
    return {"I": float(I[-1]) if I else None, "TP": float(P[-1]) if P else None}


def parse_log(path):
    t = Path(path).read_text(errors="replace")
    applied = re.search(r"applied: (.+)", t)
    notches = re.search(r"notches (\d+)", t)
    limiter = re.search(r"limiter: max (-?[\d.]+) dB", t)
    removed = re.search(r"removed: (.+)", t)
    return {"applied": applied.group(1).strip() if applied else None,
            "notches": int(notches.group(1)) if notches else None,
            "limiter_max_db": float(limiter.group(1)) if limiter else None,
            "removed": removed.group(1).strip() if removed else None}


def judge(path, src_sc=None):
    """One meter for everything: the current code (HEAD), applied to any file."""
    from finalizer import dsp, measure, meta
    y = measure.load(str(path))[0]
    edges = np.asarray(EDGES, dtype=float)
    K = [float(v) for v in meta.META["crest_max"]]
    F = [float(v) for v in meta.META["crest_min"]]
    rep = measure.crest_report(y, edges, K, F)
    leg = measure.band_crest_legacy(y, edges)
    bands = []
    for i, r in enumerate(rep["bands"]):
        bands.append({"band": EDGES[i:i + 2], "C_v2": r["C_db"], "status": r["status"],
                      "upper": r["upper"], "lower": r["lower"], "K": K[i], "F": F[i],
                      "C_legacy": None if not np.isfinite(leg[i]) else round(float(leg[i]), 4)})
    over_v2 = [b["band"] for b in bands if b["upper"] == "FAIL"]
    over_legacy = [b["band"] for b in bands if b["C_legacy"] is not None and b["C_legacy"] > b["K"] + MARGIN]
    tpm = dsp.true_peak_meters(y)
    lufs = float(dsp.lufs_integrated(y))
    ff = ffmpeg_meter(path)
    lstat = "PASS" if abs(lufs - meta.META["lufs"]) <= 0.1 else "FAIL"
    tp_code = "PASS" if tpm["max"] <= meta.META["tp"] + 0.1 else "FAIL"      # as coded in run.py
    tp_spec = "PASS" if tpm["max"] + 0.1 <= meta.META["tp"] else "FAIL"    # spec inequality, u = 0.1
    rel_code = "FAIL" if (rep["overall"] == "FAIL" or lstat == "FAIL" or tp_code == "FAIL") else "UNKNOWN"
    rel_spec = "FAIL" if (rep["overall"] == "FAIL" or lstat == "FAIL" or tp_spec == "FAIL") else "UNKNOWN"
    tgt = meta.as_target()
    sc = measure.sustain_contour(y, tgt["centers"], tgt["edges"])
    row = {"bands": bands, "overall_v2": rep["overall"],
           "over_v2": over_v2, "unknown_v2": [b["band"] for b in bands if b["upper"] == "UNKNOWN"],
           "below_floor_v2": [b["band"] for b in bands if b["lower"] == "FAIL"],
           "over_legacy": over_legacy,
           "lufs": round(lufs, 3), "lufs_ffmpeg": ff["I"],
           "tp_annex2": round(tpm["annex2"], 3), "tp_poly": round(tpm["poly"], 3),
           "tp_max": round(tpm["max"], 3), "tp_ffmpeg": ff["TP"],
           "tp_ideal": round(float(ideal_tp(y)), 3),
           "lufs_status": lstat, "tp_status_code": tp_code, "tp_status_spec": tp_spec,
           "release_code": rel_code, "release_spec": rel_spec,
           "side": {k: (round(v, 3) if isinstance(v, float) else v)
                    for k, v in measure.side_metrics(y, f_hi=float(meta.META["mono_below"])).items()},
           "sustain_contour": sc.round(3).tolist()}
    if src_sc is not None:
        d = sc - src_sc
        row["contour_max_db"] = round(float(np.max(np.abs(d))), 3)
        row["contour_rms_db"] = round(float(np.sqrt(np.mean(d ** 2))), 3)
    return row


def run_renders(tracks, roots, rdir, jobs, skip):
    rdir.mkdir(parents=True, exist_ok=True)
    queue = []
    for name, src in tracks.items():
        for vname, (rk, extra) in VARIANTS.items():
            out = rdir / f"{name}_{vname}.wav"
            log = rdir / f"{name}_{vname}.log"
            if skip and out.exists() and log.exists() and out.stat().st_size > 0:
                continue
            cmd = [sys.executable, "run.py", "master", src, "--profile", "low", *extra,
                   "--out", str(out)]
            queue.append((cmd, roots[rk], log))
    running = []
    for cmd, cwd, log in queue:
        while sum(p.poll() is None for p, _ in running) >= jobs:
            time.sleep(2)
        fh = open(log, "w")
        p = subprocess.Popen(cmd, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT)
        running.append((p, fh))
    for p, fh in running:
        rc = p.wait()
        fh.close()
        if rc:
            raise SystemExit(f"render failed (exit {rc}); see the logs in {rdir}")


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return clean(o.tolist())
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 6)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def codec_probe():
    """pre_echo's gap window, and the corrected one, with both averaging domains.

    pre_echo uses frames [i-look, i-1): the last frame before the onset is
    excluded, and that frame carries the largest pre-echo. The corrected window
    is [i-look, i). The old dB-mean also dilutes a concentrated residue, so the
    power-mean is reported next to it.
    """
    sys.path.insert(0, str(REPO))
    from research import pre_echo as pe
    tmp = Path(tempfile.mkdtemp(prefix="pe_"))
    look = int(round(pe.WINDOW_S * SR / pe.FRAME))
    rows = []

    def pmean_db(a):
        return float(10 * np.log10(np.mean(10 ** (np.asarray(a, dtype=float) / 10))))

    def pow_mean(a):
        return float(np.mean(10 ** (np.asarray(a, dtype=float) / 10)))

    def window(env, starts, shift, span, last):
        vals = []
        for s in starts:
            i = int(round(s / pe.FRAME)) + shift
            hi = i if last else i - 1
            vals.append(env[max(0, i - span): max(1, hi)])
        return np.concatenate(vals)

    for bi, (lo, hi) in ((1, (3840, 7680)), (2, (7680, 15360)), (3, (15360, 20000))):
      for crest in (9, 21):
        sigs, starts = pe.build(lo, hi, (crest,), seed=100 + bi)
        for codec in ("aac128", "aac96", "opus96"):
          for bed in (None, 0.0):
            sig = sigs[crest]
            if bed is not None:
                rng = np.random.default_rng(3)
                sig = (sig + pe.band_noise(100, 2000, len(sig), rng) * 10 ** (bed / 20)).astype(np.float32)
            dec = pe.codec_round(sig, pe.CODECS[codec], tmp)
            es = pe.envelope(sig, lo, hi)
            ed = pe.envelope(dec, lo, hi)
            d = pe.align(ed, es, starts)
            body = []
            for s in starts:
                i0 = int((s - int(0.5 * SR)) / pe.FRAME)
                i1 = int((s - int(0.1 * SR)) / pe.FRAME)
                body.append(es[i0:i1])
            body_db = pmean_db(np.concatenate(body))
            src_old, dec_old = window(es, starts, 0, look, False), window(ed, starts, d, look, False)
            src_new, dec_new = window(es, starts, 0, look, True), window(ed, starts, d, look, True)
            src_40, dec_40 = window(es, starts, 0, 2 * look, True), window(ed, starts, d, 2 * look, True)
            m1 = [ed[int(round(s / pe.FRAME)) + d - 1] - es[int(round(s / pe.FRAME)) - 1] for s in starts]
            m2 = [ed[int(round(s / pe.FRAME)) + d - 2] - es[int(round(s / pe.FRAME)) - 2] for s in starts]

            def residue(dec_w, src_w):
                inc = pow_mean(dec_w) - pow_mean(src_w)
                return round(float(10 * np.log10(inc) - body_db), 2) if inc > 0 else None

            m1_each = [round(float(ed[int(round(s / pe.FRAME)) + d - 1] - es[int(round(s / pe.FRAME)) - 1]), 2)
                       for s in starts]
            rows.append({
                "band_hz": [lo, hi], "crest_db": crest, "codec": codec,
                "bed_db": bed, "shift_frames": int(d), "m1_each_burst": m1_each,
                "body_db": round(body_db, 2),
                "pre_onset_frame_m1_added_db": round(float(np.mean(m1)), 2),
                "pre_onset_frame_m2_added_db": round(float(np.mean(m2)), 2),
                "added_dbmean_old_window": round(float(np.mean(dec_old) - np.mean(src_old)), 2),
                "added_dbmean_new_window": round(float(np.mean(dec_new) - np.mean(src_new)), 2),
                "residue_power_old_window_re_body": residue(dec_old, src_old),
                "residue_power_new_window_re_body": residue(dec_new, src_new),
                "residue_power_40ms_re_body": residue(dec_40, src_40),
                "gap_src_power_re_body": round(pmean_db(src_new) - body_db, 2),
            })
    return rows


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--child":
        task = json.loads(sys.stdin.read())
        sys.stdout.write(json.dumps(clean(child(argv[1], task))))
        return 0

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tracks", nargs="+", required=True, metavar="NAME=PATH")
    ap.add_argument("--work", default="/tmp/opencode/fin_compare")
    ap.add_argument("--out", default=str(HERE / "compare_v1_v2.json"))
    ap.add_argument("--render-tracks", nargs="+", default=None,
                    help="tracks to render and judge (default: T2 T4 T5 if present)")
    ap.add_argument("--skip-renders", action="store_true")
    ap.add_argument("--jobs", type=int, default=6)
    a = ap.parse_args(argv)

    import soundfile as sf
    sys.path.insert(0, str(REPO))
    from finalizer import meta as M

    work = Path(a.work).expanduser()
    work.mkdir(parents=True, exist_ok=True)
    tracks = {}
    for item in a.tracks:
        name, path = item.split("=", 1)
        tracks[name] = str(Path(path).expanduser().resolve())
    render_names = a.render_tracks or [n for n in ("T2", "T4", "T5") if n in tracks]
    render_tracks = {n: tracks[n] for n in render_names}
    v1_root = str(materialise(work))
    roots = {"v1": v1_root, "v2": str(REPO)}
    t0 = time.time()

    # synthetic inputs, written once so both trees read the same bytes
    sig_dir = work / "signals"
    sig_dir.mkdir(exist_ok=True)
    files = dict(tracks)
    bursts = {}
    for dur, bs in BURSTS:
        name = f"burst_{dur}s_{int(round(bs * 1000))}ms"
        p = sig_dir / f"{name}.wav"
        sf.write(p, burst_signal(dur, bs), SR, subtype="FLOAT")
        files[name] = str(p)
        bursts[name] = {"dur_s": dur, "burst_s": bs}
    track2 = load_f32(tracks["T2"])
    s0 = int(100 * SR)
    click = track2.copy()
    click[s0:s0 + int(0.05 * SR)] *= 10 ** (30 / 20)
    cp = sig_dir / "T2_click_plus30dB_50ms_at100s.wav"
    sf.write(cp, click, SR, subtype="FLOAT")
    files["T2_click_plus30dB_50ms_at100s"] = str(cp)
    c30 = sig_dir / "T2_first30s.wav"
    sf.write(c30, track2[:30 * SR], SR, subtype="FLOAT")
    ctrl_files = {"T2_first30s": str(c30),
                  "burst_30s_500ms": files["burst_30s_500ms"]}
    del track2, click

    sines_dir = work / "sines"
    sines_dir.mkdir(exist_ok=True)
    sine_files = {}
    t = np.arange(5 * SR) / SR
    for name, (amp, hz, ph) in SINES.items():
        s = amp * np.sin(2 * np.pi * hz * t + ph)
        p = sines_dir / f"{name}.wav"
        sf.write(p, np.stack([s, s], axis=1).astype(np.float32), SR, subtype="FLOAT")
        sine_files[name] = str(p)

    result = {
        "generated_by": "research/audit/compare_v1_v2.py",
        "git": git_info(),
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "ffmpeg": subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.splitlines()[0],
        },
        "trees": {"v1": v1_root, "v2": str(REPO)},
        "commands": {
            "compare": f"python3 research/audit/compare_v1_v2.py --tracks ... --work {a.work}",
            "render": "run.py master SRC --profile low [--no-deharsh] --out OUT (cwd = tree)",
        },
    }

    print("identity ...", flush=True)
    id1 = run_child(roots["v1"], {"kind": "identity"})
    id2 = run_child(roots["v2"], {"kind": "identity"})
    result["identity"] = {"v1": id1, "v2": id2,
                          "same_logic": {
                              "v1.band_crest == v2.band_crest_legacy":
                                  id1["fingerprints"]["measure.band_crest"] == id2["fingerprints"]["measure.band_crest_legacy"],
                              "v1.true_peak == v2.true_peak_poly":
                                  id1["fingerprints"]["dsp.true_peak"] == id2["fingerprints"]["dsp.true_peak_poly"],
                              "constants equal":
                                  id1["constants"] == id2["constants"]}}

    print("estimators ...", flush=True)
    est1 = run_child(roots["v1"], {"kind": "estimator", "files": files})
    est2 = run_child(roots["v2"], {"kind": "estimator", "files": files})

    print("control ...", flush=True)
    ctl1 = run_child(roots["v1"], {"kind": "control", "tag": "v1", "files": ctrl_files,
                                   "out_dir": str(sig_dir)})
    ctl2 = run_child(roots["v2"], {"kind": "control", "tag": "v2", "files": ctrl_files,
                                   "out_dir": str(sig_dir)})

    print("side and loudness ...", flush=True)
    side1 = run_child(roots["v1"], {"kind": "side", "freqs": [30, 40, 60, 80, 100, 120, 160]})
    side2 = run_child(roots["v2"], {"kind": "side", "freqs": [30, 40, 60, 80, 100, 120, 160]})
    loud_files = {**tracks, **sine_files}
    lo1 = run_child(roots["v1"], {"kind": "loudness", "files": loud_files})
    lo2 = run_child(roots["v2"], {"kind": "loudness", "files": loud_files})
    result["side_tone_attenuation_db"] = {"v1": side1, "v2": side2}
    result["loudness_children"] = {"v1": lo1, "v2": lo2}

    # ---- corpus: population and decisions (root-independent definitions)
    print("population and decisions ...", flush=True)
    K = [float(v) for v in M.META["crest_max"]]
    F = [float(v) for v in M.META["crest_min"]]
    corpus, transitions = {}, {}
    bc_by_track = {}
    for name, path in tracks.items():
        x = load_f32(path)
        E, e_tot = env_grid(x)
        pop = population(E, e_tot)
        B, C = bc_stats(E)
        bc_by_track[name] = (B, C)
        a1 = est1[name]
        a2 = est2[name]
        rows = []
        for b in range(NB):
            v1v = a1["band_crest"][b]
            v2v = a2["detail"]["values"][b]
            v2s = a2["detail"]["status"][b]
            d1 = decision_v1(v1v, K[b])
            d2 = decision_v2(v2v, v2s, K[b])
            key = f"{d1} -> {d2}"
            transitions[key] = transitions.get(key, 0) + 1
            rows.append({"band": EDGES[b:b + 2], "K": K[b], "F": F[b],
                         "v1": v1v, "v1_decision": d1,
                         "v1_legacy_equals_v2_legacy": a2["legacy"][b] == v1v,
                         "v2": v2v, "v2_status": v2s,
                         "v2_upper": decision_v2(v2v, v2s, K[b]),
                         "v2_floor": ("UNKNOWN" if v2s != "OK" or v2v is None else
                                      "PASS" if v2v >= F[b] else
                                      "FAIL" if v2v < F[b] - MARGIN else "UNKNOWN"),
                         "n_active_v2": a2["detail"]["n_active"][b],
                         "p75_all_frames": round(float(pop["p75_all"][b]), 3),
                         "body_v1_active": None if np.isnan(pop["body_legacy_active"][b]) else round(float(pop["body_legacy_active"][b]), 3),
                         "body_v2_mask": None if np.isnan(pop["body_v2_mask"][b]) else round(float(pop["body_v2_mask"][b]), 3),
                         "quiet_v1": bool(pop["quiet_v1"][b]), "quiet_v2": bool(pop["quiet_v2"][b])})
        corpus[name] = {"frames": pop["frames"], "mask_frames": pop["mask_frames"], "bands": rows}

    per_track_r = {}
    for name, (B, C) in bc_by_track.items():
        per_track_r[name] = [round(float(np.corrcoef(B[:, b], C[:, b])[0, 1]), 3) for b in range(NB)]
    Ball = np.vstack([bc_by_track[n][0] for n in tracks])
    Call = np.vstack([bc_by_track[n][1] for n in tracks])
    Bd = np.vstack([bc_by_track[n][0] - bc_by_track[n][0].mean(axis=0) for n in tracks])
    Cd = np.vstack([bc_by_track[n][1] - bc_by_track[n][1].mean(axis=0) for n in tracks])
    bc = {"segment_seconds": 10,
          "pooled_r_all_bands": round(float(np.corrcoef(Ball.ravel(), Call.ravel())[0, 1]), 3),
          "pooled_r_within_track_demeaned": round(float(np.corrcoef(Bd.ravel(), Cd.ravel())[0, 1]), 3),
          "per_band_r_pooled": [round(float(np.corrcoef(Ball[:, b], Call[:, b])[0, 1]), 3) for b in range(NB)],
          "per_track_per_band_r": per_track_r,
          "segments": int(len(Ball))}
    result["corpus"] = {"tracks": corpus, "transitions_v1_to_v2": dict(sorted(transitions.items(), key=lambda kv: -kv[1])),
                        "bc_correlation": bc}

    # ---- sensitivity of the v2 gate width (the one parameter the spec did not calibrate)
    print("gate sensitivity ...", flush=True)
    from finalizer import measure as Ms
    gs = {}
    for name, path in tracks.items():
        xg = load_f32(path)
        gs[name] = {}
        for g in (30.0, 40.0, 50.0):
            dd = Ms.band_crest_detail(xg, np.asarray(EDGES, float), gate_db=g)
            gs[name][str(int(g))] = [None if not np.isfinite(v) else round(float(v), 3)
                                     for v in dd["values"]]
    result["gate_sensitivity"] = gs

    # ---- synthetic bursts: raw truth and both meters
    print("bursts and outlier ...", flush=True)
    burst_rows = []
    for name, meta_b in bursts.items():
        x = load_f32(files[name])
        E, e_tot = env_grid(x)
        p75 = np.percentile(E[:, BURST_BAND], 75)
        peak = float(E[:, BURST_BAND].max())
        frac = float(np.mean(E[:, BURST_BAND] > p75 + 20.0))
        a1 = est1[name]
        a2 = est2[name]
        burst_rows.append({
            "file": name, **meta_b,
            "raw_C_tail_db": round(float(np.percentile(E[:, BURST_BAND], 99.5) - p75), 2),
            "raw_C_max_db": round(peak - p75, 2),
            "frames_above_p75_plus_20_percent": round(100 * frac, 3),
            "frames_total": int(len(E)),
            "v1_C_db": a1["band_crest"][BURST_BAND],
            "v2_C_db": a2["detail"]["values"][BURST_BAND],
            "v2_status": a2["detail"]["status"][BURST_BAND],
            "v2_n_active": a2["detail"]["n_active"][BURST_BAND],
            "v2_legacy_C_db": a2["legacy"][BURST_BAND],
        })
    result["bursts"] = burst_rows

    x = load_f32(files["T2_click_plus30dB_50ms_at100s"])
    xs = load_f32(tracks["T2"])
    Eb, eb = env_grid(xs)
    Ec, ec = env_grid(x)
    pb, pc = population(Eb, eb), population(Ec, ec)
    a1b, a1c = est1["T2"], est1["T2_click_plus30dB_50ms_at100s"]
    a2b, a2c = est2["T2"], est2["T2_click_plus30dB_50ms_at100s"]
    result["outlier_click"] = {
        "description": "T2 with +30 dB, 50 ms, all bands, at 100 s",
        "v1_C_before": a1b["band_crest"], "v1_C_after": a1c["band_crest"],
        "v2_C_before": a2b["detail"]["values"], "v2_C_after": a2c["detail"]["values"],
        "v2_n_active_before": a2b["detail"]["n_active"], "v2_n_active_after": a2c["detail"]["n_active"],
        "v2_mask_frames_before": pb["mask_frames"], "v2_mask_frames_after": pc["mask_frames"],
    }

    # ---- control: one crest-stage pass at 6.2 dB on the same material
    print("control ...", flush=True)
    ctl = {}
    for name in ctrl_files:
        x_in = load_f32(ctrl_files[name])
        E_in, e_in = env_grid(x_in)
        p_in = population(E_in, e_in)
        B_in, C_in = bc_stats(E_in)
        row = {}
        for tag, c in (("v1", ctl1), ("v2", ctl2)):
            y = load_f32(c[name]["path"])
            E_o, e_o = env_grid(y)
            B_o, C_o = bc_stats(E_o)
            row[tag] = {
                "body_before": np.percentile(E_in, 75, axis=0).round(3).tolist(),
                "body_after": np.percentile(E_o, 75, axis=0).round(3).tolist(),
                "body_change_db": (np.percentile(E_o, 75, axis=0) - np.percentile(E_in, 75, axis=0)).round(3).tolist(),
                "C_before": np.round(np.percentile(E_in, 99.5, axis=0) - np.percentile(E_in, 75, axis=0), 3).tolist(),
                "C_after": np.round(np.percentile(E_o, 99.5, axis=0) - np.percentile(E_o, 75, axis=0), 3).tolist(),
                "peak_band_before_db": round(float(E_in[:, BURST_BAND].max()), 2),
                "peak_band_after_db": round(float(E_o[:, BURST_BAND].max()), 2),
                "root_meter_on_output": c[name]["estimators"],
            }
        ctl[name] = {"v1_body_base_of_chain": np.round(p_in["p75_all"], 3).tolist(),
                     "v2_body_base_of_chain": np.round(p_in["body_v2_mask"], 3).tolist(),
                     "outputs": row}
    result["control"] = ctl

    # ---- codec probe: the same code path as research/pre_echo.py, residue stated two ways
    print("codec probe ...", flush=True)
    result["codec"] = codec_probe()

    # ---- renders, judged by one meter (HEAD)
    if not a.skip_renders:
        print(f"renders ({len(render_tracks) * len(VARIANTS)}) ...", flush=True)
        rdir = work / "renders"
        run_renders(render_tracks, roots, rdir, a.jobs, skip=False)
    rdir = work / "renders"
    renders = {}
    if rdir.exists() and all((rdir / f"{n}_{v}.wav").exists() for n in render_tracks for v in VARIANTS):
        print("judging renders ...", flush=True)
        for name, path in render_tracks.items():
            x = load_f32(path)
            from finalizer import measure as Mm, meta as Mt
            tgt = Mt.as_target()
            src_sc = Mm.sustain_contour(x, tgt["centers"], tgt["edges"])
            renders.setdefault(name, {})["source"] = judge(path, None)
            for v in VARIANTS:
                out = rdir / f"{name}_{v}.wav"
                row = judge(out, src_sc)
                row["log"] = parse_log(rdir / f"{name}_{v}.log")
                row["sha256"] = hashlib.sha256(out.read_bytes()).hexdigest()
                renders[name][v] = row
    result["renders"] = renders

    # ---- loudness: code vs ffmpeg vs reference, for sources and sines
    print("loudness vs ffmpeg and reference ...", flush=True)
    from finalizer import dsp as D
    table = D._ANNEX2.reshape(12, 4)
    table_norm = (table / table.sum(axis=0, keepdims=True)).reshape(-1)
    from scipy.signal import upfirdn

    def annex_peak(x, h):
        best = 0.0
        for c in range(x.shape[1]):
            y = upfirdn(h, x[:, c].astype(np.float64), up=4, down=1)
            best = max(best, float(np.abs(y).max()))
        return 20 * math.log10(best + 1e-20)

    lr = {}
    for name, path in {**tracks, **sine_files}.items():
        ff = ffmpeg_meter(path)
        x = load_f32(path)
        ref = float(ideal_tp(x))
        lr[name] = {"ffmpeg_I": ff["I"], "ffmpeg_TP": ff["TP"],
                    "ideal_TP": round(ref, 3),
                    "annex2_phase_normalised_TP": round(annex_peak(x, table_norm), 3),
                    "v1_code": lo1[name], "v2_code": lo2[name]}
    for name, (amp, hz, ph) in SINES.items():
        lr[name]["analytic_TP"] = round(20 * math.log10(amp), 3)
    result["loudness"] = lr

    result["wall_seconds"] = round(time.time() - t0, 1)
    out = Path(a.out)
    out.write_text(json.dumps(clean(result), indent=1, ensure_ascii=False))
    print(f"written: {out}  ({result['wall_seconds']} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

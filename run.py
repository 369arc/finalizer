#!/usr/bin/env python3
"""FINALIZER -- reference-state mastering for sustained material.

  meta     [--name meta]     print the admissible region
  analyse  FILE...                     measure contour, width, crest, resonances
  check    FILE...                     how far the balance moves on real devices
  compare  A B                         state difference A -> B
  master   SRC --meta meta --out OUT  bring SRC inside the meta
  master   SRC --target REF --out OUT  ...or onto a measured reference
"""
import argparse
import json
import sys

import os
import numpy as np
import soundfile as sf

from finalizer import dsp, measure, chain, meta as metamod, devices, ingest


def cmd_meta(a):
    m = metamod.get(a.name)
    if m is None:
        raise SystemExit(f"unknown meta: {a.name} "
                         f"(available: {', '.join(sorted(metamod.META_REGISTRY))})")
    print(metamod.table(m))
    print()
    for k, v in metamod.NOTES.items():
        print(f"  {k:>10s}: {v}")
    return 0


def cmd_analyse(a):
    m = metamod.get(a.meta)
    if m is None:
        raise SystemExit(f"unknown meta: {a.meta}")
    for p in a.files:
        x, _ = measure.load(ingest.ingest(p)[0])
        f = measure.features(x)
        print(measure.summary(f, p))
        if a.crest:
            d = measure.band_crest_detail(x, np.array(m["crest_edges"]))
            parts = []
            for i, v in enumerate(d["values"]):
                txt = "--" if not np.isfinite(v) else f"{v:.1f}"
                parts.append(f"{m['crest_edges'][i]:.0f}-"
                             f"{m['crest_edges'][i + 1]:.0f}:{txt}"
                             f"{'' if d['status'][i] == 'OK' else '?'}")
            print("    crest by octave: " + " ".join(parts))
        if a.json_dir:
            import os
            name = os.path.splitext(os.path.basename(p))[0]
            path = os.path.join(a.json_dir, name + ".json")
            with open(path, "w") as fh:
                json.dump(measure.to_json(f), fh, indent=1)
            print(f"    state written: {path}")
    return 0


def _fmt(v, nd=1):
    return "--" if v is None or not np.isfinite(v) else f"{v:.{nd}f}"


def _lufs_status(value, target, tol=0.1):
    return "PASS" if abs(value - target) <= tol else "FAIL"


def _tp_status(value, target, tol=0.1):
    return "PASS" if value <= target + tol else "FAIL"


def cmd_check(a):
    m = metamod.get(a.meta)
    if m is None:
        raise SystemExit(f"unknown meta: {a.meta}")
    for p in a.files:
        x, _ = measure.load(ingest.ingest(p)[0])
        f = measure.features(x)
        edges = np.asarray(m["crest_edges"], dtype=float)
        rep = measure.crest_report(x, edges, m["crest_max"], m["crest_min"])
        side = measure.side_metrics(x, f_hi=m["mono_below"])
        lstat = _lufs_status(f["lufs"], m["lufs"])
        tstat = _tp_status(f["tp"], m["tp"])
        print(f"  {p}")
        print(f"    LUFS {f['lufs']:.2f} (target {m['lufs']:+.1f} +/-0.1): {lstat}")
        print(f"    TP   {f['tp']:.2f} dBTP (limit {m['tp']:+.1f} +0.1 on max meter): {tstat}")
        print(f"    side<{m['mono_below']:.0f} Hz: side/mid "
              f"{_fmt(side['side_mid_db'])} dB, mono loss "
              f"{_fmt(side['mono_loss_db'])} dB, corr "
              f"{side['corr_low']:+.2f}  UNKNOWN (threshold not calibrated)")
        print(f"    {'band':>14s} {'C':>6s} {'K':>5s} {'upper':>7s} "
              f"{'F':>5s} {'lower':>7s}  status")
        for i, r in enumerate(rep["bands"]):
            lo, hi = r["band_hz"]
            print(f"    {lo:6.0f}-{hi:<7.0f} {_fmt(r['C_db']):>6s} "
                  f"{m['crest_max'][i]:5.1f} {r['upper']:>7s} "
                  f"{m['crest_min'][i]:5.1f} {r['lower']:>7s}  {r['status']}")
        print(f"    crest/floor: {rep['overall']} (margin {rep['tol_db']:.2f} dB)")
        if rep["overall"] == "FAIL" or lstat == "FAIL" or tstat == "FAIL":
            release = "FAIL"
        elif rep["overall"] == "UNKNOWN":
            release = "UNKNOWN"
        else:
            release = "UNKNOWN"  # side threshold not calibrated
        print(f"    release: {release}")
        text, _ = devices.report(x, m)
        print("    device model (synthetic, not a measurement):")
        print(text)
        print()
    return 0


def cmd_compare(a):
    xa, _ = measure.load(ingest.ingest(a.a)[0])
    xb, _ = measure.load(ingest.ingest(a.b)[0])
    fa, fb = measure.features(xa), measure.features(xb)
    print(measure.summary(fa, a.a))
    print(measure.summary(fb, a.b))
    return 0


def _write(path, y, sr, bits="24"):
    """Write the master at a declared depth, not at libsndfile's default.

    WAV defaults to PCM_16, so every render used to be quantised to 16 bit
    without anyone asking. 24 bit is transparent (144 dB); 16 bit gets TPDF
    dither, because truncation at that depth is distortion, not noise.
    """
    if bits in ("32", "32f", "float"):
        sf.write(path, y, sr, subtype="FLOAT")
    elif bits in ("16", "16f"):
        lsb = 1.0 / 32768.0
        rng = np.random.default_rng(12345)
        d = (rng.random(y.shape, dtype=np.float32)
             - rng.random(y.shape, dtype=np.float32)) * lsb
        sf.write(path, np.clip(y + d, -1.0, 1.0).astype(np.float32), sr,
                 subtype="PCM_16")
    else:
        sf.write(path, y, sr, subtype="PCM_24")


def cmd_master(a):
    src, _tmp = ingest.ingest(a.src)
    x, sr = measure.load(src)
    if float(np.abs(x).max()) < 1e-6:
        raise SystemExit(f"{a.src}: the file is silent -- nothing to master")

    # The meta is the boundary; a target only supplies the picture.  Resolve
    # it once so the target branch does not silently fall back to a default.
    meta_name = a.meta or metamod.DEFAULT_META
    base_meta = metamod.get(meta_name)
    if base_meta is None:
        raise SystemExit(f"unknown meta: {meta_name} "
                         f"(available: {', '.join(sorted(metamod.META_REGISTRY))})")

    # an explicit target beats a profile's meta: the profile says "meta" by
    # default, but a file on the command line is a decision, not a default
    if a.meta and not (a.target or a.target_json):
        m = base_meta
        tgt = metamod.as_target(m)
        tname = f"meta:{m['name']}"
        lufs_t = a.lufs if a.lufs is not None else m["lufs"]
        deadband = a.deadband if a.deadband is not None else 0.0
        mono_below = a.mono_below if a.mono_below is not None else m["mono_below"]
        crest_max = tgt["crest_max"]
        crest_min = tgt["crest_min"]
        crest_edges = tgt["crest_edges"]
        crest_from_target = False
        fit = a.fit_contour if a.fit_contour is not None else False
    else:
        if not a.target and not a.target_json:
            raise SystemExit("need --meta, --target or --target-json")
        if a.target_json:
            if not os.path.exists(a.target_json):
                raise SystemExit(f"target file not found: {a.target_json}")
            with open(a.target_json) as fh:
                try:
                    tgt = measure.from_json(json.load(fh))
                except json.JSONDecodeError as e:
                    raise SystemExit(
                        f"{a.target_json}: not valid JSON ({e})")
            # the measuring grid is a scale, not a target: fill it from the
            # meta when the file only carries ceilings or a contour
            _base = metamod.as_target()
            for _k in ("centers", "edges"):
                tgt.setdefault(_k, _base[_k])
            tname = a.target_json
        else:
            t, _ = measure.load(a.target)
            tgt = measure.features(t)
            tname = a.target
        # the meta is still the boundary: a target only supplies the picture.
        # absolutes and crest ceilings fall back to the meta when the target
        # file does not carry them
        lufs_t = a.lufs if a.lufs is not None else tgt.get(
            "lufs", base_meta["lufs"])
        deadband = a.deadband or 0.0
        mono_below = (a.mono_below if a.mono_below is not None
                      else tgt.get("mono_below", base_meta["mono_below"]))
        crest_edges = tgt.get("crest_edges", base_meta["crest_edges"])
        crest_max = tgt.get("crest_max", base_meta["crest_max"])
        crest_min = tgt.get("crest_min", base_meta["crest_min"])
        crest_from_target = "crest_max" in tgt
        fit = True if a.fit_contour is None else a.fit_contour

    if a.target_smooth > 0:
        if "rel" not in tgt:
            raise SystemExit("--target-smooth needs --target with a contour")
        tgt = dict(tgt)
        tgt["rel"] = measure.smooth(tgt["rel"], a.target_smooth)

    if a.meta:
        harsh_thr = 99.0 if a.harsh_thr is None else a.harsh_thr
        max_rough = 3.0 if a.max_rough is None else a.max_rough
    else:
        harsh_thr = 2.5 if a.harsh_thr is None else a.harsh_thr
        max_rough = a.max_rough

    meta_only = bool(a.meta) and not (a.target or a.target_json)
    deharsh = (not meta_only) if a.deharsh is None else a.deharsh
    p = dict(hpf=a.hpf, max_eq=a.max_eq, smooth_oct=a.smooth,
             deharsh=deharsh, harsh_thr=harsh_thr,
             harsh_max=a.harsh_max, max_rough=max_rough,
             harsh_total=a.harsh_total, deadband=deadband,
             width=True, width_max=a.width_max,
             mono_below=mono_below,
             mid_guard=a.mid_guard,
             crest_edges=crest_edges,
             # a target's ceilings are already absolute; the profile's
             # multipliers describe taste relative to the META, not to a file
             crest_max=(None if crest_max is None else
                        (np.asarray(crest_max, dtype=float)
                         if crest_from_target else
                         _apply_sub(_apply_bass_scale(np.asarray(crest_max) * a.crest,
                                                      crest_edges, a.bass, a.bass_hz),
                                    crest_edges, a.sub, a.sub_hz))),
             crest_margin=a.margin,
             fit_contour=fit,
             match_width=fit and ("width" in tgt),
             pull=a.pull, one_shot=a.one_shot,
             eq_peak=a.eq_peak,
             ceiling=a.ceiling,
             lookahead=a.lookahead, release=a.release, lufs=lufs_t)

    # Report the ceilings that are actually applied (after crest/bass/sub),
    # not the raw meta before the profile multipliers.
    if p.get("crest_max") is not None:
        crest_max = np.asarray(p["crest_max"], dtype=float)
        crest_edges = np.asarray(p["crest_edges"], dtype=float)

    sc_src = measure.sustain_contour(x, tgt["centers"], tgt["edges"])

    print(f"source : {a.src}")
    print(f"target : {tname}")
    if "lufs" in tgt:
        print(f"         LUFS {tgt['lufs']:.2f}, TP {tgt['tp']:.2f}")
    dbtxt = (f"{deadband:.1f}" if np.ndim(deadband) == 0
             else f"{np.min(deadband):.1f}-{np.max(deadband):.1f}")
    print(f"aim    : LUFS {lufs_t:.2f}, ceiling {a.ceiling:.2f} dBTP, "
          f"contour {'FIT' if fit else 'FREE'}, crest x{a.crest:.2f}, "
          f"bass x{a.bass:.2f} (<{a.bass_hz:.0f} Hz), mono<{mono_below:.0f} Hz")
    print()

    res = chain.master(x, tgt, p, iters=a.iters, verbose=True)
    y = res["audio"][:len(x)]
    _write(a.out, y, sr, a.bits)

    f = res["features"]
    sc_out = f.get("sustain_contour", sc_src)
    if os.environ.get("FIN_DEBUG_EQ"):
        print("  eq_db:", " ".join(f"{c:.0f}:{v:+.1f}" for c, v in
                                   zip(tgt["centers"], res["eq_db"])))

    if fit:
        ds = (measure.smooth(f.get("rel_sustain", f["rel"]))
              - measure.smooth(tgt.get("rel_sustain", tgt["rel"])))
        tol = np.asarray(deadband, dtype=float)
        viol = np.maximum(0.0, np.abs(ds) - tol / 2)
        capped = np.abs(res["eq_db"]) >= a.max_eq - 0.1
        print()
        print(f"  {'Hz':>7s} {'target':>7s} {'result':>7s} {'err':>6s}")
        tsm = measure.smooth(tgt.get("rel_sustain", tgt["rel"]))
        fsm = measure.smooth(f.get("rel_sustain", f["rel"]))
        for i, c in enumerate(tgt["centers"]):
            flags = (" <" if abs(ds[i]) > 1.0 else "") + \
                    (" LIMIT" if capped[i] else "")
            print(f"  {c:7.0f} {tsm[i]:7.1f} {fsm[i]:7.1f} {ds[i]:+6.1f}{flags}")
        print(f"  contour violation: max {viol.max():.2f} dB, rms "
              f"{np.sqrt((viol ** 2).mean()):.2f} dB"
              + (f"   (EQ capped in {int(capped.sum())} bands)" if capped.any() else ""))
    else:
        dc = sc_out - sc_src
        print()
        print(f"  {'Hz':>7s} {'src':>7s} {'result':>7s} {'d':>6s}   {'width':>6s}")
        for i, c in enumerate(tgt["centers"]):
            print(f"  {c:7.0f} {sc_src[i]:7.1f} {sc_out[i]:7.1f} {dc[i]:+6.1f}   "
                  f"{f['width'][i]:6.1f}")
        print(f"  contour change: max |d| {np.abs(dc).max():.2f} dB, "
              f"rms {np.sqrt((dc ** 2).mean()):.2f} dB"
              + ("" if deharsh else "  (deharsh off)"))

    n_over = n_unknown = n_floor = 0
    if crest_max is not None:
        crest_rep = measure.crest_report(y, np.asarray(crest_edges),
                                         np.asarray(crest_max),
                                         None if crest_min is None
                                         else np.asarray(crest_min))
        src = measure.band_crest_detail(x, np.asarray(crest_edges))
        print()
        print(f"  {'band':>14s} {'was':>6s} {'now':>6s} {'max':>6s} "
              f"{'upper':>7s} {'floor':>6s} {'lower':>7s}  status")
        for i, r in enumerate(crest_rep["bands"]):
            was = ("--" if not np.isfinite(src["values"][i])
                   else f"{src['values'][i]:.1f}")
            now = "--" if r["C_db"] is None else f"{r['C_db']:.1f}"
            n_over += r["upper"] == "FAIL"
            n_floor += r["lower"] == "FAIL"
            n_unknown += (r["status"] != "OK"
                          or "UNKNOWN" in (r["upper"], r["lower"]))
            fmin = ("--" if crest_min is None
                    else f"{crest_min[i]:.1f}")
            print(f"  {r['band_hz'][0]:6.0f}-{r['band_hz'][1]:<7.0f} "
                  f"{was:>6s} {now:>6s} {crest_max[i]:6.1f} "
                  f"{r['upper']:>7s} {fmin:>6s} {r['lower']:>7s}  "
                  f"{r['status']}")
        eff = res["info"].get("crest_target_eff")
        if eff:
            print("  applied: " + "  ".join(
                f"{crest_edges[i]:.0f}:{eff[i]:.1f}" for i in range(len(eff))))
        print(f"  crest/floor: {crest_rep['overall']}; {n_over} over, "
              f"{n_unknown} unknown, {n_floor} below floor "
              f"(margin {crest_rep['tol_db']:.2f} dB)")

    lstat = _lufs_status(f["lufs"], lufs_t)
    tstat = _tp_status(f["tp"], a.ceiling)
    side = measure.side_metrics(y, f_hi=mono_below)
    print()
    print(f"  LUFS {f['lufs']:6.2f} (aim {lufs_t:.2f}): {lstat}   "
          f"TP {f['tp']:6.2f} dBTP (limit {a.ceiling:.2f}): {tstat}   "
          f"LRA {f['lra']:5.2f}")
    print(f"  side<{mono_below:.0f} Hz: side/mid {side['side_mid_db']:+.1f} dB, "
          f"mono loss {side['mono_loss_db']:+.1f} dB, corr "
          f"{side['corr_low']:+.2f}  UNKNOWN (threshold not calibrated)")
    if "mid_guard_db" in res["info"]:
        print(f"  mid guard: broad deviation {res['info']['mid_dev_before']:.1f} dB "
              f"-> corrected {res['info']['mid_guard_db']:.1f} dB (240-4000 Hz)")
    print(f"  limiter: max {res['info']['gr_max']:.1f} dB, p99.5 "
          f"{res['info'].get('gr_p99', 0):.1f} dB, mean "
          f"{res['info']['gr_mean']:.2f} dB   notches {len(res['info']['notches'])}")
    if res["info"]["notches"]:
        print("  removed: " + ", ".join(f"{hz:.0f}Hz{g:+.1f}" for hz, (g, q) in
                                        res["info"]["notches"].items()))
    print()
    text, tdev = devices.report(y, base_meta)
    print("  device model (synthetic, not a measurement):")
    print(text)
    yd = y.astype(np.float64)
    rms = float(np.sqrt(np.mean(yd ** 2)))
    var = float(np.mean(yd ** 2))
    a._summary = {
        "crest": (20 * np.log10(float(np.abs(y).max()) / rms)
                  if rms > 0 else float("nan")),
        "kurt": (float(np.mean(yd ** 4) / var ** 2) if var > 0
                 else float("nan")),
        "lra": f["lra"], "tp": f["tp"],
        "lufs": f["lufs"], "lufs_status": lstat, "tp_status": tstat,
        "over": n_over, "unknown": n_unknown, "floor": n_floor,
        "side_mid": side["side_mid_db"],
        "phone": tdev["phone"]["shift_max"],
    }
    print(f"  written: {a.out}")
    return 0


def cmd_master_all(a):
    """Render every profile defined in profiles.toml, one file each.

    They differ only in taste, never in the meta: every variant sits inside the
    same boundary. Which one wins is decided by ear on the track.
    """
    import copy, os, tomllib
    base = os.path.splitext(a.out)[0]
    path = a.profiles or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "profiles.toml")
    if not os.path.exists(path):
        raise SystemExit(f"profile file not found: {path}")
    with open(path, "rb") as fh:
        names = [k for k, v in tomllib.load(fh).items() if isinstance(v, dict)]
    rows = []
    for name in names:
        aa = copy.copy(a)
        aa.profile = name
        aa.out = f"{base}_{name}.wav"
        aa.all_profiles = False
        print(f"\n{'=' * 6} [{name}] {'=' * 6}")
        apply_profile(aa)
        cmd_master(aa)
        rows.append(dict(aa._summary, profile=name, file=aa.out))

    print()
    print(f"  {'profile':>10s} {'crest':>6s} {'kurt':>6s} {'LRA':>6s} {'TP':>6s} "
          f"{'over':>5s} {'unk':>5s} {'side':>6s} {'phone':>6s}")
    for r in rows:
        print(f"  {r['profile']:>10s} {r['crest']:6.2f} {r['kurt']:6.2f} "
              f"{r['lra']:6.2f} {r['tp']:6.2f} {r['over']:5d} "
              f"{r.get('unknown', 0):5d} {r.get('side_mid', float('nan')):6.1f} "
              f"{r['phone']:6.1f}")
    print("  written: " + ", ".join(f"{base}_{n}.wav" for n in names))
    return 0



def _parse_grid(specs):
    import itertools
    keys, vals = [], []
    for spec in specs:
        k, v = spec.split("=", 1)
        keys.append(k.strip())
        vals.append([float(t) for t in v.split(",")])
    return [dict(zip(keys, combo)) for combo in itertools.product(*vals)]


def _apply_sub(cm, edges, sub_crest, sub_hz):
    """Set an absolute crest target for the sub: 1 dB means 'a wall, not a pulse'."""
    if sub_crest is None:
        return cm
    cm = np.array(cm, dtype=float)
    mid = np.sqrt(np.asarray(edges[:-1]) * np.asarray(edges[1:]))
    cm[mid < sub_hz] = sub_crest
    return cm


def _apply_bass_scale(cm, edges, scale, cutoff):
    """Scale only the low bands' ceilings: 0.8 = solid bass, top untouched."""
    if scale == 1.0:
        return cm
    cm = np.array(cm, dtype=float)
    mid = np.sqrt(np.asarray(edges[:-1]) * np.asarray(edges[1:]))
    return np.where(mid < cutoff, cm * scale, cm)


def _variant_params(base, params):
    """Map friendly grid names onto chain parameters."""
    p = dict(base)
    for k, v in params.items():
        if k == "margin":
            p["crest_margin"] = v
        elif k == "crest":
            # multiplier on the meta ceiling: <1 tighter, >1 more open
            p["crest_max"] = np.asarray(base["crest_max"]) * v
        elif k == "bass":
            p["crest_max"] = _apply_bass_scale(p["crest_max"], base["crest_edges"],
                                               v, base.get("bass_hz", 240.0))
        elif k == "sub":
            p["crest_max"] = _apply_sub(p["crest_max"], base["crest_edges"],
                                        v, base.get("sub_hz", 90.0))
        elif k == "rough":
            p["max_rough"] = None if v <= 0 else v
        elif k == "mono":
            p["mono_below"] = v
        elif k == "hpf":
            p["hpf"] = v
        elif k == "deharsh":
            p["deharsh"] = bool(v)
        else:
            raise SystemExit(f"unknown grid parameter: {k}")
    return p


def _variant_name(i, params):
    tag = "_".join(f"{k}{v:g}" for k, v in params.items())
    return f"{i:02d}_{tag}" if tag else f"{i:02d}"


def cmd_variants(a):
    import os
    src, _tmp = ingest.ingest(a.src)
    x, sr = measure.load(src)
    m = metamod.get(a.meta)
    if m is None:
        raise SystemExit(f"unknown meta: {a.meta} "
                         f"(available: {', '.join(sorted(metamod.META_REGISTRY))})")
    tgt = metamod.as_target(m)
    lufs_t = a.lufs if a.lufs is not None else m["lufs"]
    deadband = 0.0

    grid = _parse_grid(a.grid) if a.grid else [dict(crest=0.8), dict(crest=1.0)]
    axes = {k for g in grid for k in g}
    cm_base = np.asarray(tgt["crest_max"]) * (1.0 if "crest" in axes else a.crest)
    if "bass" not in axes:
        cm_base = _apply_bass_scale(cm_base, tgt["crest_edges"], a.bass, a.bass_hz)
    if "sub" not in axes and a.sub is not None:
        cm_base = _apply_sub(cm_base, tgt["crest_edges"], a.sub, a.sub_hz)

    base = dict(hpf=a.hpf, max_eq=a.max_eq, smooth_oct=a.smooth,
                deharsh=True, harsh_thr=99.0, harsh_max=a.harsh_max,
                max_rough=3.0, harsh_total=a.harsh_total, deadband=0.0,
                width=True, width_max=a.width_max, mono_below=m["mono_below"],
                fit_contour=False, match_width=False,
                crest_edges=tgt["crest_edges"], crest_max=cm_base,
                crest_min=tgt["crest_min"],
                crest_margin=0.0, bass_hz=a.bass_hz, sub_hz=a.sub_hz,
                mid_guard=a.mid_guard,
                eq_peak=a.eq_peak, ceiling=a.ceiling,
                lookahead=a.lookahead, release=a.release, lufs=lufs_t)

    os.makedirs(a.out_dir, exist_ok=True)
    src_contour = measure.smooth(measure.sustain_contour(x, tgt["centers"], tgt["edges"]), 1.0)

    rows = []
    for i, params in enumerate(grid):
        p = _variant_params(base, params)
        res = chain.master(x, tgt, p, iters=3, verbose=False)
        y = res["audio"][:len(x)]
        name = _variant_name(i, params)
        rows.append(dict(name=name, params=params, audio=y, res=res))

    # --- everyone must be equally loud before the ear can judge anything
    lufs = [dsp.lufs_integrated(r["audio"]) for r in rows]
    for r, L in zip(rows, lufs):
        r["audio"] = r["audio"] * np.float32(10 ** ((lufs_t - L) / 20))
    tps = [dsp.true_peak(r["audio"]) for r in rows]
    over = max(tps) - a.ceiling
    if over > 0:
        for r in rows:
            r["audio"] = r["audio"] * np.float32(10 ** (-over / 20))

    ce = np.asarray(tgt["crest_edges"]); cmx = np.asarray(tgt["crest_max"])
    for r in rows:
        y = r["audio"]
        f = measure.features(y)
        cre = measure.band_crest(y, ce)
        dfc = measure.smooth(f["rel_sustain"], 1.0) - src_contour
        dtxt, _ = devices.report(y, m)
        r.update(lufs=f["lufs"], tp=f["tp"], lra=f["lra"],
                 crest_over=int(np.nansum(cre > cmx + 0.35)),
                 move=float(np.sqrt(np.nanmean(dfc ** 2))),
                 notches=len(r["res"]["info"]["notches"]),
                 device=dtxt.strip().splitlines()[-1].strip())
        _write(os.path.join(a.out_dir, r["name"] + ".wav"), y, sr, a.bits)

    print(f"\n  {len(rows)} variants -> {a.out_dir}")
    print(f"  {'name':>22s} {'LUFS':>6s} {'TP':>6s} {'LRA':>5s} {'crest>':>6s} "
          f"{'move':>5s} {'notch':>5s}")
    for r in rows:
        print(f"  {r['name']:>22s} {r['lufs']:6.2f} {r['tp']:6.2f} {r['lra']:5.2f} "
              f"{r['crest_over']:6d} {r['move']:5.1f} {r['notches']:5d}")

    _write_variants_index(a.out_dir, rows, str(a.src))
    return 0


def _write_variants_index(outdir, rows, src):
    import os, html
    md = ["# variants", "", f"source: `{src}`", "",
          "| variant | LUFS | TP | LRA | crest over | contour move | notches |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['name']} | {r['lufs']:.2f} | {r['tp']:.2f} | {r['lra']:.2f} | "
                  f"{r['crest_over']} | {r['move']:.1f} dB | {r['notches']} |")
    open(os.path.join(outdir, "variants.md"), "w").write("\n".join(md) + "\n")

    parts = ["<!doctype html><meta charset=utf-8><title>FINALIZER variants</title>",
             "<style>body{font:13px/1.5 system-ui,sans-serif;background:#111;color:#ddd;"
             "margin:24px}table{border-collapse:collapse}td,th{padding:6px 10px;"
             "border-bottom:1px solid #333;text-align:left}th{color:#888;"
             "font-weight:400}audio{height:28px;width:320px;vertical-align:middle}"
             ".n{color:#7ab}</style>",
             f"<h3>{html.escape(os.path.basename(src))}</h3>",
             "<p style='color:#888'>all variants are level-matched to the same LUFS and "
             "true peak, so the comparison is about shape, not loudness.</p>",
             "<table><tr><th>#</th><th>variant</th><th>listen</th><th>LUFS</th>"
             "<th>LRA</th><th>crest over</th><th>move</th></tr>"]
    for r in rows:
        parts.append(
            "<tr><td>%s</td><td class=n>%s</td><td><audio controls preload=none "
            "src='%s.wav'></audio></td><td>%.2f</td><td>%.2f</td><td>%d</td><td>%.1f</td></tr>"
            % (r["name"].split("_")[0], html.escape(r["name"]), html.escape(r["name"]),
               r["lufs"], r["lra"], r["crest_over"], r["move"]))
    parts.append("</table>")
    parts.append("""<script>
document.querySelectorAll('audio').forEach(a=>a.addEventListener('play',()=>{
  document.querySelectorAll('audio').forEach(b=>{if(b!==a)b.pause();});}));
</script>""")
    open(os.path.join(outdir, "index.html"), "w").write("\n".join(parts))



PROFILE_MAP = {"meta": "meta", "crest": "crest", "bass": "bass", "bass_hz": "bass_hz",
               "mid_guard": "mid_guard", "pull": "pull",
               "eq_peak": "eq_peak", "target": "target_json",
               "max_eq": "max_eq",
               "one_shot": "one_shot",
               "sub": "sub", "sub_hz": "sub_hz",
               "margin": "margin", "mono": "mono_below", "rough": "max_rough",
               "deharsh": "deharsh",
               "harsh_total": "harsh_total"}
PROFILE_DEFAULTS = {"meta": None, "mid_guard": None, "sub": None, "sub_hz": 90.0, "crest": 1.0, "bass": 1.0, "bass_hz": 240.0, "margin": 0.0,
                    "pull": 1.0, "eq_peak": None, "target_json": None,
                    "max_eq": 9.0,
                    "one_shot": False,
                    "deharsh": None,
                    "mono_below": None, "max_rough": None, "harsh_total": 3.0}


def apply_profile(a):
    """Taste lives in profiles.toml, never in the meta and never in code."""
    if not hasattr(a, "profile"):
        return
    # no --profile: fall back to [default] if the file defines one, otherwise
    # render neutral. The preference lives in the file, never in the code.
    import os, tomllib
    path = getattr(a, "profiles", None) or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "profiles.toml")
    if not os.path.exists(path):
        raise SystemExit(f"profile file not found: {path}")
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    # the file says which profile a bare `master` should use; the names are a
    # scale (low/mid/high), so "which one by default" is a separate answer
    fallback = data.get("default")
    if not isinstance(fallback, str):
        fallback = "default"
    name = getattr(a, "profile", None) or fallback
    prof = data.get(name)
    if prof is None:
        if getattr(a, "profile", None) is None:
            return                      # no [default]: neutral render
        raise SystemExit(f"no [{name}] in {path}")
    for pk, ak in PROFILE_MAP.items():
        if pk in prof and getattr(a, ak, None) == PROFILE_DEFAULTS.get(ak):
            val = prof[pk]
            if ak == "target_json" and isinstance(val, str) and not os.path.isabs(val):
                val = os.path.join(os.path.dirname(os.path.abspath(path)), val)
            setattr(a, ak, val)
    print(f"  profile: {name} -> "
          + ", ".join(f"{k}={prof[k]}" for k in prof))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("meta")
    q.add_argument("--name", default=metamod.DEFAULT_META)
    q.set_defaults(func=cmd_meta)

    q = sub.add_parser("analyse")
    q.add_argument("files", nargs="+")
    q.add_argument("--json-dir", default=None)
    q.add_argument("--crest", action="store_true")
    q.add_argument("--meta", default=metamod.DEFAULT_META)
    q.set_defaults(func=cmd_analyse)

    q = sub.add_parser("check")
    q.add_argument("files", nargs="+")
    q.add_argument("--meta", default=metamod.DEFAULT_META)
    q.set_defaults(func=cmd_check)

    q = sub.add_parser("compare")
    q.add_argument("a")
    q.add_argument("b")
    q.set_defaults(func=cmd_compare)

    q = sub.add_parser("variants")
    q.add_argument("src")
    q.add_argument("--meta", default=metamod.DEFAULT_META)
    q.add_argument("--grid", nargs="*", default=None,
                   help="e.g. crest=0.8,0.9 bass=0.7,1.0")
    q.add_argument("--out-dir", required=True)
    q.add_argument("--lufs", type=float, default=None)
    q.add_argument("--ceiling", type=float, default=-1.0)
    q.add_argument("--hpf", type=float, default=20.0)
    q.add_argument("--max-eq", type=float, default=9.0)
    q.add_argument("--smooth", type=float, default=1.0)
    q.add_argument("--harsh-max", type=float, default=3.0)
    q.add_argument("--harsh-total", type=float, default=3.0)
    q.add_argument("--width-max", type=float, default=6.0)
    q.add_argument("--bass-hz", type=float, default=240.0)
    q.add_argument("--sub", type=float, default=None)
    q.add_argument("--sub-hz", type=float, default=90.0)
    q.add_argument("--mid-guard", type=float, default=None,
                   help="max broad deviation in 240-4000 Hz, dB (None = off)")
    q.add_argument("--eq-peak", type=float, nargs=3, default=None,
                   metavar=("HZ", "DB", "Q"),
                   help="one broad static bell after the crest stage, e.g. 1000 4.5 0.4")
    q.add_argument("--crest", type=float, default=1.0,
                   help="base crest scale when the grid does not set it")
    q.add_argument("--bass", type=float, default=1.0,
                   help="base bass scale when the grid does not set it")
    q.add_argument("--profile", default=None)
    q.add_argument("--profiles", default=None)
    q.add_argument("--lookahead", type=float, default=20.0)
    q.add_argument("--release", type=float, default=400.0)
    q.add_argument("--bits", default="24", choices=["16", "24", "32f"],
                   help="output depth: 24 (default) | 16 (TPDF dithered) | 32f")
    q.set_defaults(func=cmd_variants)

    q = sub.add_parser("master")
    q.add_argument("src")
    q.add_argument("--meta", default=None, help="meta")
    q.add_argument("--target", default=None)
    q.add_argument("--target-json", default=None)
    q.add_argument("--target-smooth", type=float, default=0.0)
    q.add_argument("--margin", type=float, default=0.0,
                   help="sit this many dB below the crest ceiling")
    q.add_argument("--crest", type=float, default=1.0,
                   help="scale the crest ceiling: 0.85 tighter, 1.0 at the boundary")
    q.add_argument("--bass", type=float, default=1.0,
                   help="scale the crest ceiling only below --bass-hz")
    q.add_argument("--profile", default=None, help="named profile from profiles.toml")
    q.add_argument("--profiles", default=None, help="path to profiles.toml")
    q.add_argument("--bass-hz", type=float, default=240.0)
    q.add_argument("--sub", type=float, default=None,
                   help="absolute crest target below --sub-hz, dB (1.0 = static sub)")
    q.add_argument("--sub-hz", type=float, default=90.0)
    q.add_argument("--mid-guard", type=float, default=None,
                   help="max broad deviation in 240-4000 Hz, dB (None = off)")
    q.add_argument("--eq-peak", type=float, nargs=3, default=None,
                   metavar=("HZ", "DB", "Q"),
                   help="one broad static bell after the crest stage, e.g. 1000 4.5 0.4")
    q.add_argument("--one-shot", action="store_true", dest="one_shot",
                   help="project the target contour once instead of iterating")
    q.add_argument("--pull", type=float, default=1.0,
                   help="how far to move toward a target contour, 0..1")
    q.add_argument("--fit-contour", dest="fit_contour", action="store_const",
                   const=True, default=None,
                   help="also shape the spectral contour (default: free in meta mode)")
    q.add_argument("--free-contour", dest="fit_contour", action="store_const",
                   const=False)
    q.add_argument("--out", required=True)
    q.add_argument("--lufs", type=float, default=None)
    q.add_argument("--ceiling", type=float, default=-1.0)
    q.add_argument("--hpf", type=float, default=20.0)
    q.add_argument("--max-eq", type=float, default=9.0)
    q.add_argument("--smooth", type=float, default=1.0)
    q.add_argument("--deadband", type=float, default=None)
    q.add_argument("--iters", type=int, default=3)
    q.add_argument("--deharsh", action=argparse.BooleanOptionalAction,
                   default=None,
                   help="automatic resonance notches (default: off in meta-only mode)")
    q.add_argument("--harsh-thr", type=float, default=None)
    q.add_argument("--harsh-max", type=float, default=4.0)
    q.add_argument("--harsh-total", type=float, default=8.0)
    q.add_argument("--max-rough", type=float, default=None)
    q.add_argument("--no-width", action="store_true")
    q.add_argument("--width-max", type=float, default=6.0)
    q.add_argument("--mono-below", type=float, default=None)
    q.add_argument("--lookahead", type=float, default=20.0)
    q.add_argument("--release", type=float, default=400.0)
    q.add_argument("--bits", default="24", choices=["16", "24", "32f"],
                   help="output depth: 24 (default) | 16 (TPDF dithered) | 32f")
    q.add_argument("--all-profiles", action=argparse.BooleanOptionalAction,
                   default=True,
                   help="render every profile in profiles.toml (default)")
    q.set_defaults(func=cmd_master)

    a = ap.parse_args(argv)
    if getattr(a, "all_profiles", False) and getattr(a, "profile", None) is None:
        return cmd_master_all(a)
    apply_profile(a)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())

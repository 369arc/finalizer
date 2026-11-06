# Mastering meta: scientific audit

**Repository:** `369arc/finalizer`  
**Commit audited:** `af04531` (`meta: state every ceiling as a model estimate, drop the listening claim`)  
**Date:** 2026-11-06  
**Scope:** the mathematical formulation, the implementation, the stated provenance of every constant, and the evidence available in the repository and in the author's finished masters.  
**No production file was modified for this audit.** All measurements were read-only; generated audio and figures live outside the source material.

> **Post-audit status.** The production fixes that followed this audit are
> recorded in `VALIDATION_REPORT.md` §4. This document remains the audit of
> commit `af04531`; the production metric is now `crest-v1.1-broadband-gate`.

---

## 1. How to read this document

Every claim gets one of six labels:

| label | meaning |
|---|---|
| **VERIFIED** | proved mathematically, or reproduced by a measurement whose method and reference are stated |
| **SUPPORTED** | consistent with the available evidence, but not proved and not exhaustively tested |
| **HYPOTHESIS** | a testable proposition with a stated mechanism; no decisive measurement yet |
| **ASSUMPTION** | accepted for engineering purposes without evidence; must not be presented as measured |
| **UNKNOWN** | the data needed to decide are absent, or the claim cannot be reproduced from the repository |
| **REJECTED** | contradicted by a proof, a measurement, or the implementation itself |

A statement can be **VERIFIED as an implementation** and still be an **ASSUMPTION as a scientific claim**. For example, “the code computes P75 of the band envelope” is verifiable by reading the code; “P75 is the body of the material” is a definition, not a measurement.

The audit separates three things that the source documents often merge:

1. **The mathematical object** — what is written in the formal definition.
2. **The operational estimator** — what the code actually computes, including gates, windows and boundary handling.
3. **The physical/perceptual claim** — what the number is supposed to mean on a device or for a listener.

Most of the problems below live at the boundary between (2) and (3).

### Evidence used

- Static inspection of `finalizer/meta.py`, `measure.py`, `chain.py`, `dsp.py`, `devices.py`, `ingest.py`, `run.py`, `research/pre_echo.py`, `tests/`.
- Five finished masters supplied by the author: `T1`, `T2`, `T3`, `T4`, `T5` (48 kHz, stereo, 110–204 s; see `RESULTS.md` for durations and paths). They are a convenience sample, not a representative corpus.
- Synthetic signals with known crest, known band content, known side content, and deliberately inserted bursts/clicks.
- Cross-checks against `ffmpeg` 8.1.3 `ebur128=peak=true` for integrated loudness and true peak.
- ITU-R BS.1770-4 (10/2015), Annex 2 for true peak; EBU Tech 3342 for LRA; AES75-2023 for the M-Noise/Music-Noise 2 dB compression procedure (used only as a reference, not as a definition of `K_b`).

The five finished masters are not a validation corpus. They are used here to test whether the stated numbers are consistent with the material the tool is supposed to describe, and to expose estimator behaviour that a synthetic sine cannot expose.

---

## 2. Executive summary

> The findings below describe commit `af04531`. The production fixes that
> followed are recorded in `VALIDATION_REPORT.md` §4; read the two together.
> A fix does not erase the finding — it is the reason for the fix.

1. **`K_b` is not measured.** No part of the repository contains a device measurement, an SPL calibration, or a perceptual threshold. The values `6.2 / 7.2 / 8.3 / 8.0 / 10.3` are assumptions or hypotheses. The `75 dB SPL` reference exists only as a comment; the code never converts digital level to SPL.
2. **The low-band 6.2 dB is the most consequential and the least supported value.** It binds on `T3`, `T5` and `T2` and is applied identically to 30–60, 60–120, 120–240, 240–480, 480–960 and 960–1920 Hz, although the physical mechanisms (excursion, port, thermal compression, limiter) are different.
3. **The codec rationale for the top bands was first reported as not reproduced; that negative result is withdrawn (erratum in D2).** The original probe excluded the frame immediately before the onset and averaged the residue in dB. The corrected probe (`V1_VS_V2.md` §6.9) finds pre-echo energy in that frame for AAC 96/128 and Opus 96 at a 21 dB crest. The data are still limited to synthetic mono band noise, one encoder implementation, 50 ms bursts and a few window lengths; audibility is UNKNOWN. The codec neither justifies the top-band numbers nor is ruled out by them.
4. **The crest estimator is not a peak estimator.** `C_b = P99.5 − P75` is a duration-weighted tail statistic. Events shorter than about 0.5 % of the analysed frames are invisible to it. A 50 dB burst lasting 0.5 s in a quiet band was measured as `C_b = 0.38 dB`; bursts of 0.1–0.3 s returned `NaN`, which the tool treats as a pass.
5. **The “no programme” gate silently removes bands.** A band whose P75 is more than 45 dB below the loudest band is assigned `NaN`. On `T1` the top two bands are skipped; on `T5` the top octave is skipped. `NaN` is treated as `ok` in `run.py` and in `chain.master`’s report. A release can therefore be certified while a band was never assessed.
6. **Body and crest are not independent.** They are order statistics of the same sample. Across 10 s segments of the five masters the pooled correlation is `r = −0.36` (per-band `−0.66 … +0.04`). The claim “orthogonal by construction” is false. A crest stage that clamps a long or deep peak can also move P75: measured `−2.09 dB` in 15–20 kHz on a 30 s excerpt, and `< 0.6 dB` on the full tracks.
7. **The floor `F_b` is decorative.** `CREST_MIN` is printed and copied into the target, but no chain stage and no check uses it. Several values in the five finished masters are below the floor. The universal floor has no empirical basis and is not implemented.
8. **`side = 0 below 120 Hz` is false as implemented.** The code applies a 3rd-order Butterworth high-pass to the side channel: `−3.0 dB` at 120 Hz, `−18.1 dB` at 60 Hz, `−36.0 dB` at 30 Hz. On the mastered `T4`, the side/mid ratio in 20–120 Hz is `−15.3 dB`, not `−∞`. The low end is *near*-mono, not mono.
9. **The contour is not free in the default meta path.** `deharsh=True` is the default, and in meta mode it applies absolute roughness notches. On `T4` with the `low` profile it removed four notches, including `−4.0 dB at 1008 Hz`; the reported “contour preserved” then read `max |d| = 3.93 dB`. With `--no-deharsh` it read `3.43 dB` (mostly low bands). The `low` profile’s comment “no colouring” is incorrect.
10. **The meter work is partly good and partly unstated.** Integrated loudness matches `ffmpeg` within `0.05 dB` on the tested tracks, and true peak within `0.03 dB` on real material. But `dsp.true_peak` is a generic `resample_poly` meter, not the 48-tap/4-phase filter of BS.1770-4 Annex 2; on high-frequency sines it differs from `ffmpeg` by up to `0.52 dB`; the Annex 2 filter itself differs from ffmpeg by ~0.6 dB there, so the target needs a specified meter and a tolerance.
11. **The catalogue/ear provenance was not fully removed.** `README.md` still says “Two independent derivations agree”, lists catalogue medians, and says “the meta merely formalises what the ear found on its own”. `finalizer/meta.py` still says “the median of eight finished masters”. The five available masters do not reproduce the listed medians (top bands differ by up to ~3.6 dB; low bands by up to ~3.2 dB). The claim must be removed or documented with the eight tracks and the exact measurement.
12. **The analysis grid is not adequate for the lowest band.** At `N = 4096`, 30–60 Hz contains three FFT bins. The measured crest of `T4` at 30–60 Hz is `1.71 dB` at `N = 4096`, `6.87 dB` at `N = 8192`, and `7.10 dB` at `N = 16384`. The number is a property of the window as much as of the signal.
13. **The two “bodies” are different estimators.** `band_crest` computes P75 on a 4096/1024 STFT; `sustain_contour` computes P75 on a 16384/4096 STFT. Their relative contours differ by up to `5.1 dB` on `T2` and `29 dB` at 30–60 Hz on `T4`. The formal definition’s “same envelope” is not what the code does.
14. **The tests are smoke tests, not metrology.** They prove that commands run and files are written; they do not compare a metric with a reference, test the gate/`NaN` behaviour, the floor, the side criterion, or the crest estimator on a known signal.

The concept — a per-band admissible set rather than a target curve — remains coherent. What the audit rejects is the claim that the current constants and the current estimator constitute a validated scientific boundary.

---

## 3. The formulation as written, as implemented, as measured

The written definition (README, `## Formal definition`):

```
E_b(n)  band power in frame n, dB
B_b   = P75(E_b)
C_b   = P99.5(E_b) − P75(E_b)

C_b(y) ≤ K_b
C_b(y) ≥ F_b
L(y)   = −14 LUFS
TP(y) ≤ −1 dBTP
side(y) = 0 below 120 Hz
```

The implementation:

| object | written | implemented | status |
|---|---|---|---|
| analysis | STFT 4096/1024, Hann | `dsp.stft` 4096/1024 for `band_crest`; 16384/4096 for `sustain_contour`; 16384 non-overlap Welch for `octave_levels` | **inconsistent** |
| `E_b` | band power in frame | hard bin sum `f ∈ [e_b, e_{b+1})`; no crossovers | **implementation of a choice**, not a brick-wall band |
| `B_b` | P75 | P75 of `E_b`, but with a 45 dB “no programme” gate in `band_crest`; no gate in `sustain_contour` | **two different bodies** |
| `C_b` | P99.5 − P75 | P99.5 − P75 over `e > e.max() − 45`; `NaN` if fewer than 21 frames or if P75 is 45 dB below the loudest band | **not the written statistic** |
| `K_b` | constants at 75 dB SPL | constants; no SPL conversion | **assumption/hypothesis** |
| `F_b` | constants | displayed, copied to target, never used by a stage or a check | **not implemented** |
| `L` | BS.1770-4, −14 | `dsp.lufs_integrated`, BS.1770-4 gating; matches ffmpeg | **SUPPORTED**; target is a convention |
| `TP` | 4× true peak | `resample_poly(4)` + `max`; not the Annex 2 filter | **SUPPORTED on real programme; UNKNOWN as a standard meter** |
| `side` | exactly zero below 120 | 3rd-order Butterworth high-pass on the side | **REJECTED as stated** |
| domain | 30–20000 Hz | 30–20000 for crest; 20–20000 for the high-pass; <30 and >20k unregulated | **incomplete** |

The written set and the implemented set are not the same set. The rest of the audit treats this as the central problem: a number can be “inside the meta” according to the code while the written constraint is violated, and vice versa.

---

## 4. Claim-by-claim audit

### 4.1 Definitions and statistics

#### A1. `B_b = P75(E_b)` is the body

**Status: ASSUMPTION (definition), VERIFIED only as code behaviour.**

The 75th percentile is a choice. It is not derived from a physical model, a perceptual model, or a corpus study. It is invariant to a constant gain, which is useful, but it is not a robust “body” for material with long silences: if more than 25 % of the frames are silence or near-silence, P75 falls into the silence. `sustain_contour` has no activity gate at all. On a 30 s excerpt of `T2`, the 30–60 Hz P75 is `51.1 dB`; on the full track it is `59.5 dB` — the same statistic on the same material moves by 8 dB with excerpt length because the percentile samples a different part of a non-stationary distribution.

The label “body” is a definition, not a measurement. It should be stated as “the 75th percentile of the band envelope over the active frames”, and the activity rule must be part of the definition.

#### A2. `C_b = P99.5(E_b) − P75(E_b)` is the crest

**Status: ASSUMPTION (definition); the name is misleading.**

This is a ratio of two order statistics of the same envelope. It measures how far the top 0.5 % of frames rises above the 75th percentile. It is not the peak-to-body ratio: the maximum can be far above P99.5, and a short event can be entirely below the 0.5 % duration threshold.

A 50 dB burst lasting 0.5 s in a 30 s track is 1.7 % of the frames, so it *is* visible to P99.5 if the body is included. But with the current max-based active gate, the body is excluded and the burst is measured against itself (`C_b = 0.38 dB`). A 0.1–0.3 s burst is below the `len(act) > 20` guard and returns `NaN`. The statistic is therefore neither a peak measure nor a stable tail measure in the presence of a dominant short event.

The name “crest” suggests a peak. The operational definition should be called `C_b^tail` (or “sustained crest”), and a separate `C_b^peak`/`C_b^local` should be defined if the intended mechanism is transient-driven.

#### A3. Body and crest are “orthogonal by construction”

**Status: REJECTED.**

`P75` and `P99.5` are order statistics of the same sample. They are dependent random variables. The source’s word “orthogonal” is doing three different jobs; they must be separated:

1. **Gain invariance.** For a constant gain `g`, `B_b(gx) = B_b(x) + 20 log10 g` and `C_b(gx) = C_b(x)`. This is exact and was verified: a `+6.0206 dB` gain shifted B by `+6.0206 dB` and changed C by `0.000000 dB` on all five tracks.
2. **Statistical independence.** False. Across 10 s segments of the five masters, the pooled Pearson correlation between B and C is `−0.36`; per band it ranges from `−0.66` (960–1920) to `+0.04` (7680–15360). The sign is systematic: loud sections have a higher body and a relatively smaller tail, quiet sections have a lower body and a relatively larger tail. A constraint on C therefore carries information about B, and vice versa.
3. **Control independence.** Approximate, not a theorem. A crest stage that modifies only frames above `B_b + K_b` leaves P75 unchanged if those frames are less than 25 % of the sample and the gain is applied only there. In practice the stage uses a time-varying gain with a release; when the cut is deep or the “peak” lasts, P75 moves. Measured on a 30 s `T2` excerpt with a 6.2 dB ceiling: `B` fell by `0.00 … 0.60 dB` up to 3840–7680, by `2.02 dB` at 7680–15360, and by `2.09 dB` at 15360–20000. On the full tracks the body change was `< 0.6 dB` except the low bands of `T4` and `T5` (`−1.3 … −1.8 dB`).

The correct statement is: **C is gain-invariant and approximately control-independent for small cuts; it is not statistically independent of B, and a deep/long crest cut can move the body.** The README and `measure.py` must stop saying “orthogonal by construction”.

#### A4. A cap on `C_b` does not move `B_b`

**Status: REJECTED as a general claim; SUPPORTED only as a small-cut approximation.**

See A3. The chain’s own comment in `chain.py` says the clamp “preserves P75 (the body never moves)”. The measurement above contradicts it for the top bands on a 30 s excerpt. The full-track tests did not expose it because the cuts were smaller; that is a property of the material, not a guarantee.

The consequence is not merely cosmetic: the meta says the contour is free, but the actuator changes it. The change should be measured and reported, or the actuator should be redesigned to preserve the body (e.g., apply gain only to the excess frames with a make-up gain, or use a true peak limiter with a short release). The current report calls the change “contour preserved”, which is false when the notch stage is also active.

#### A5. P75 and P99.5 are stable estimators

**Status: REJECTED for short tracks; SUPPORTED only with a wide uncertainty on long tracks.**

The estimator depends on the number of frames, the overlap, and the position of the loud section. Measurements:

- `T2`, 15–20 kHz: `16.08 dB` on the first 30 s, `11.57` on 60 s, `10.10` on 120 s, `10.95` on the full 204 s.
- `T4`, 15–20 kHz: `11.51 / 10.33 / 8.74 / 8.79` for 30/60/120/150 s.
- `T5`, 7680–15360: `3.93 / 13.00 / 12.66 / 12.66` for 30/60/110/110 s.
- `T1`, 30–60: `0.38 / 0.69 / 3.72 / 2.78`.
- `T3`, 30–60: `11.77 / 9.28 / 9.10` for 30/60/120 s.

A 30 s excerpt is not a short version of the track. The tail statistic is dominated by where the loud section happens to fall. A release decision based on a 30 s excerpt can differ by 8 dB from the full track.

The block bootstrap (10 s blocks, 200 resamples) gives 95 % intervals such as:

| track | band | C_b | 95 % CI | sd |
|---|---|---:|---|---:|
| T2 | 7680–15360 | 10.95 | 8.66–13.39 | 1.20 |
| T2 | 15360–20000 | 10.95 | 8.15–13.50 | 1.44 |
| T5 | 7680–15360 | 12.66 | 10.64–14.29 | 0.84 |
| T4 | 1920–3840 | 5.52 | 3.65–7.78 | 1.16 |
| T1 | 30–60 | 2.78 | 0.64–6.01 | 1.44 |
| T3 | 3840–7680 | 5.43 | 2.73–6.81 | 1.23 |

The band-to-band differences in the current `K_b` are 0.3–2.3 dB. The intervals above are often wider than those differences. The distinction between 8.0 and 8.3 dB, and much of the 6.2 → 7.2 → 8.3 structure, is below the estimator uncertainty on a single 2–3 minute track. This does not prove the values are wrong; it proves they are not resolvable with the current method.

#### A6. The estimator is robust to outliers

**Status: REJECTED.**

Two different failure modes:

- **Max-based active gate.** `act = e[e > e.max() − 45]`. If a band contains a short event more than 45 dB above its body, the body is excluded and the crest is computed inside the event. A synthetic 30 s track with a quiet 7680–15360 body at −30 dB relative to the bass and a 50 dB burst produced `C_b = 0.38 dB` for a 0.5 s burst, and `NaN` for 0.1–0.3 s bursts. The raw `P99.5 − P75` on the same band was `29.8–49.9 dB`.
- **`len(act) > 20` guard.** If the gate leaves fewer than 21 frames, the band returns `NaN`. The tool then treats `NaN` as “no programme” and as a pass. A short, loud event is therefore not merely underestimated; it can be invisible.

A single-sample click is less dangerous because P99.5 ignores less than 0.5 % of the frames; a 1-sample click at 0 dBFS changed the measured C by `< 0.15 dB` on the five tracks. The dangerous case is a *sustained short event* (tens to hundreds of ms) in a quiet band, which is exactly the codec/limiter case the meta is supposed to cover.

#### A7. The statistic is independent of material structure

**Status: UNKNOWN / REJECTED as a universal claim.**

The five masters span a wide range of measured C: `2.77` to `11.34` at 30–60, `2.83` to `8.66` at 960–1920, `10.29` to `12.42` at 7680–15360. The value is a property of the distribution of the band envelope, which is composition-dependent. A single ceiling applied to all material assumes that the same tail ratio means the same thing perceptually and physically; that is a hypothesis, not an established fact.

### 4.2 STFT, bands, and edges

#### B1. A 4096/1024 STFT is adequate for every band

**Status: REJECTED for 30–60 Hz; SUPPORTED for ≥ 120 Hz with caveats.**

At 48 kHz, `N = 4096` gives a bin spacing of 11.72 Hz. The 30–60 Hz band contains three bins (35.2, 46.9, 58.6 Hz). The Hann main lobe is four bins wide. The band is not resolved; the measured power is a windowed projection that includes leakage from adjacent frequencies and misses part of the 30 Hz component. The window sensitivity is large:

| track | 30–60 at N=4096 | N=8192 | N=16384 |
|---|---:|---:|---:|
| T4 | 1.71 | 6.87 | 7.10 |
| T2 | 1.62 | 1.47 | 1.17 |
| T1 | 2.78 | 2.79 | 2.56 |
| T5 | 12.38 | 11.37 | 10.09 |
| T3 | 9.10 | 9.05 | 9.18 |

`T4` moves by 5.4 dB. The first band is the one where the 6.2 dB ceiling is most binding on `T3`/`T5`; it is also the least resolved. A multi-resolution analysis (longer window for the low bands) or a constant-Q filterbank is required before `K_b` at 30–60 can be treated as a number.

For 120–1920 Hz, the window sensitivity is typically < 1 dB; for the top bands, a longer window smears transients and lowers the measured crest by up to ~3 dB. The choice of window is a trade-off, not a neutral measurement.

#### B2. The band edges 30 and 20000 Hz are handled correctly

**Status: REJECTED for the 30 Hz edge; SUPPORTED for the 20 kHz edge.**

- 30 Hz is the lower edge. Content from 20–30 Hz is outside every band; `crest_stage` explicitly zeroes gain below 30 Hz. A sub-30 rumble can be arbitrarily large and never enters `C_b`. The `hpf=20 Hz` default removes only below 20 Hz; 20–30 Hz remains.
- 20 kHz is below Nyquist (24 kHz), so the band exists. But the anti-alias/decimation filters of playback devices and codecs often cut at 20 kHz; the band is at the edge of the reproducible range. The 15–20 kHz ceiling is also the one most often skipped by the “no programme” gate.
- The `sustain_contour` grid is 25 Hz–16.1 kHz (1/3-octave centres), not 30 Hz–20 kHz. The crest grid and the contour grid are different. The formal definition should state the domain and the grid explicitly.

#### B3. Hard bin selection is equivalent to a band filter

**Status: ASSUMPTION.**

`band_crest` sums the power of the FFT bins whose centre lies in `[e_b, e_{b+1})`. This is a windowed projection, not a brick-wall band-pass. The Hann window leaks; the hard edge truncates the leakage; adjacent bands are not orthogonal. The `band_weights` function used for *applying* gain uses 0.4-octave raised-cosine crossovers, so the gain is smooth while the measurement is hard-edged. The number that is controlled and the number that is reported are therefore not measured through the same filter. This is defensible if documented, but the current documents imply a clean octave split.

#### B4. The same envelope is used for B and C

**Status: REJECTED.**

`band_crest` uses a 4096/1024 STFT. `sustain_contour` uses 16384/4096. `octave_levels` uses 16384 non-overlapping Welch frames. These are three different estimators. The relative contours differ:

| track | band | P75 at 4096/1024, rel. 1 kHz | P75 at 16384/4096, rel. 1 kHz | difference |
|---|---|---:|---:|---:|
| T2 | 30–60 | 24.69 | 28.46 | +3.76 |
| T2 | 60–120 | 11.37 | 14.24 | +2.87 |
| T2 | 480–960 | 2.42 | −0.04 | −2.46 |
| T2 | 960–1920 | 0.00 | −2.64 | −2.64 |
| T2 | 15360–20000 | −1.68 | 3.41 | +5.10 |
| T4 | 30–60 | −13.36 | −42.71 | −29.35 |
| T4 | 60–120 | −6.09 | −14.73 | −8.64 |
| T4 | 960–1920 | 0.00 | −7.20 | −7.20 |

The exact cause is material-dependent (the long window resolves a low-frequency modulation that the short window smears; the short window includes a loud section that the long window's P75 suppresses), but the conclusion is not: the “body” used by the contour and the “body” subtracted in the crest are not the same quantity. The formal definition’s “same envelope” is false in the implementation.

A single normative estimator should be chosen. If the low bands need a longer window, the spec must say so and the crest must be computed on the same per-band estimator (with the time resolution stated). The numbers `K_b` are only meaningful relative to that estimator.

#### B5. The first band is extended to DC by the weight matrix

**Status: REJECTED (stale comment).**

The comment in `sustain_contour` says “the weight matrix extends the first band to DC”. There is no weight matrix in that function; it uses hard bins. `band_crest` also uses hard bins. The first band starts at 30 Hz. The comment is a leftover from an earlier implementation and should be removed; it currently misleads the reader about the sub-30 behaviour.

### 4.3 The five constraints

#### C1. `C_b ≤ K_b` is checked

**Status: REJECTED as a reliable check; SUPPORTED that it reports a subset of the constraints.**

`run.py check` computes `band_crest` and prints “over meta crest” when `v > mx + 0.35`. There is no confidence interval; the `+0.35 dB` is an undocumented tolerance; `NaN` is skipped (`not np.isnan(v)`), so a band that was not assessed is treated as passing; the floor, loudness, true peak and side are not part of the check.

`run.py master` prints a per-band table and counts `n_over` only when the measured value is above `max + 0.35`; `NaN` counts as `ok`. It can write a file with `crest: 0 band(s) still over the meta` while a band is `NaN`. The synthetic 50 dB burst is a concrete example: the source's 7680–15360 band was `NaN`/`0.2 dB`, and the report said “ok” before the chain happened to cut the burst.

The check also does not report the *lower* confidence bound or the *upper* bound; it reports a point estimate. A scientific decision needs a rule such as: PASS if the upper 95 % bound ≤ `K_b`; FAIL if the lower bound > `K_b`; otherwise UNKNOWN. The current code has no such rule.

#### C2. `C_b ≥ F_b` is checked / enforced

**Status: REJECTED (not implemented).**

`grep -rn "crest_min"` finds only `meta.py` (definition, `NOTES`, `as_target`, `table`). No chain stage reads it; no check compares against it; no report prints a floor violation. It is a displayed number, not a constraint.

Several values in the five masters are below the floor:

| track | band | C_b | F_b |
|---|---|---:|---:|
| T2 | 30–60 | 1.60 | 2.5 |
| T4 | 30–60 | 1.70 | 2.5 |
| T1 | 30–60 | 2.77 | 2.5 (passes) |
| T5 | 960–1920 | 2.83 | 3.0 |
| T2 | 120–240 | 3.97 | 2.5 (passes) |

The floor is an aesthetic/engineering judgment. It may be useful as a profile guard, but it is not a physical boundary and it is not currently part of the implemented meta.

#### C3. `L = −14 LUFS` is enforced

**Status: SUPPORTED on the tested tracks; the target is a convention.**

`dsp.lufs_integrated` implements the BS.1770-4 K-weighting, 400 ms blocks with 75 % overlap, absolute gate −70 LUFS, relative gate −10 LU. Cross-check against `ffmpeg ebur128`:

| signal | code | ffmpeg | difference |
|---|---:|---:|---:|
| 1 kHz sine, −3 dBFS | −2.993 | −3.0 | +0.007 |
| T2 full | −11.038 | −11.0 | −0.038 |
| T4 full | −17.513 | −17.5 | −0.013 |
| T2 low master | −13.94 | −13.9 | −0.04 |
| T4 low master | −14.00 | −14.0 | 0.00 |

The implementation is conformant within 0.05 dB on these signals. The meta’s equality has no tolerance; the master loop lands within ~0.1 LU. A specification should say `|L − L₀| ≤ 0.1 LU` (or a stated tolerance) and should state that `−14 LUFS` is a **delivery target**, not a physical property. Platform targets differ: Spotify documents −14 LUFS; Apple Music is commonly −16; Deezer −15; SoundCloud does not normalize. The README’s “every streaming service normalises to it” is false as a universal claim.

The function signature `lufs_integrated(x, sr=SR)` accepts `sr` but ignores it; the K-weighting coefficients are 48 kHz only. The pipeline resamples to 48 kHz, so the production path is safe, but the API is a hazard for research code. It should either resample internally or reject non-48 kHz input.

#### C4. `TP ≤ −1 dBTP` is enforced

**Status: SUPPORTED on real programme; REJECTED as BS.1770-4 Annex 2.**

`dsp.true_peak` uses `scipy.signal.resample_poly(..., 4, 1)` and the maximum absolute value. It is a 4× oversampled peak meter, but it is not the 48-tap, 4-phase FIR of ITU-R BS.1770-4 Annex 2. Cross-check:

| signal | code TP | ffmpeg TP | difference |
|---|---:|---:|---:|
| 1 kHz sine, −3 dBFS | −2.994 | −3.000 | +0.006 |
| 19 kHz sine, 0 dBFS | 0.277 | 0.800 | −0.523 |
| 12 kHz sine, 0 dBFS | 0.006 | 0.500 | −0.494 |
| fs/4 sine, 45° | 0.115 | 0.600 | −0.485 |
| T2 full | 0.794 | 0.800 | −0.006 |
| T4 full | −4.172 | −4.200 | +0.028 |
| T2 low master | −1.000 | −1.000 | 0.000 |
| T4 low master | −1.000 | −1.000 | 0.000 |

On real programme the agreement is excellent; on high-frequency sines the code differs from ffmpeg by up to ~0.5 dB. The BS.1770-4 Annex 2 filter itself gives ~0.2 dB on the 19 kHz sine where ffmpeg gives 0.8 dB, so the disagreement is between meters, not proof that the code is wrong. The code is still not the Annex 2 filter, and the “exact rather than approximate” claim in the README is too strong. A master trimmed to −1.00 by this meter can read ~−0.5 dBTP on a different meter. The specification should name the meter/filter and a tolerance, or implement the Annex 2 filter. The `−1 dBTP` value itself is a platform convention (Spotify recommends −1; some platforms recommend −2 for loud masters), not a physical boundary.

#### C5. `side = 0 below 120 Hz`

**Status: REJECTED as stated.**

`chain.stereo_width` applies `dsp.highpass(s, mono_below, order=3)` to the side channel. A 3rd-order Butterworth high-pass at 120 Hz has:

| frequency | attenuation |
|---:|---:|
| 30 Hz | −36.0 dB |
| 40 Hz | −28.6 dB |
| 60 Hz | −18.1 dB |
| 80 Hz | −10.9 dB |
| 100 Hz | −6.0 dB |
| 120 Hz | −3.0 dB |
| 160 Hz | −0.7 dB |

The side is not zero below 120; it is attenuated with a gradual slope. On the mastered tracks:

| track | side/mid, 20–120 Hz, source | side/mid, 20–120 Hz, output | corr<100 source → output |
|---|---:|---:|---:|
| T2 | −17.4 dB | −28.0 dB | 0.98 → 1.00 |
| T4 | −2.7 dB | −15.3 dB | 0.38 → 0.91 |

The output is much more mono-compatible, but it is not mono. The exact-zero claim is a mastering rule, not a physical fact. A measurable criterion is needed, for example `|S(f)| / |M(f)| ≤ −X dB` for `f < f_m`, with `X` and `f_m` derived from a mono-loss/preference experiment. The current `corr_low` is a useful proxy but not the same quantity; `run.py check` does not report the side ratio or a mono-loss pass/fail.

#### C6. `f_m = 120 Hz` is physical

**Status: HYPOTHESIS / ASSUMPTION.**

The physical part is: a mono fold-down computes `L + R`; if `L = −R` below some frequency, the bass cancels. The exact `120 Hz` corner, the filter order, and the requirement of zero are conventions. Many systems use 80–150 Hz; the choice depends on the playback system, the crossover, and the material. The “physics of folding to one speaker” justifies *a* mono-compatibility criterion, not this specific one. The experiment should measure mono loss (or preference) as a function of the side ratio and corner frequency, and choose `f_m`/`X` from data.

### 4.4 Provenance and rationale

#### D1. The device law (≈6 dB headroom) is measured

**Status: ASSUMPTION.**

There is no device measurement in the repository. `devices.py` contains synthetic filters and limiters (`phone`, `laptop`, `bt_speaker`, `earbuds`, `car`, `mono`) with hand-set parameters. They are useful for a *model* of translation, but they are not measurements of any real device. The “roughly 6 dB of headroom in phones and laptops” is a plausible engineering assumption; it is not supported by a measurement, a datasheet, or a cited standard.

The 6.2 dB is applied to six bands with different physics. A phone's 100 Hz behaviour is dominated by the driver/port; a laptop's 1 kHz behaviour by the cabinet; a BT speaker's 60 Hz by the limiter and the port. A single value cannot be a “device law” for all of them.

#### D2. The codec pre-echo limit determines the top bands

**Status: WITHDRAWN (erratum 2026-11-06, `V1_VS_V2.md` §6.9).** The probe excluded the frame before the onset and averaged in dB; the corrected probe shows pre-echo energy in that frame for AAC and Opus at a 21 dB crest. Audibility: UNKNOWN.

**Erratum.** The conclusion below — “the codec does not bind” — is withdrawn. The gap window `[i−look, i−1)` excluded the frame immediately before the onset, where the pre-echo sits, and the dB mean diluted a concentrated residue. The tables are kept as the output of the old probe. The corrected probe is `codec_probe` in `research/audit/compare_v1_v2.py`; results are in `V1_VS_V2.md` §6.9 and `compare_v1_v2.json` (`codec`).

`research/pre_echo.py` builds “body → quiet gap → burst”, encodes it with AAC (128/96/64/48/32 kbps) and Opus (96 kbps), and measures what the codec adds to the 20 ms gap before the burst. The current output:

| band | codec | added residue at crest 3…21 dB | residue at 21 dB re body |
|---|---|---:|---:|
| 1920–3840 | AAC 128 | 0.0 … 0.0 | −30.3 |
| 1920–3840 | AAC 96 | 0.1 … 0.4 | −30.0 |
| 1920–3840 | Opus 96 | 0.3 … 0.5 | −29.8 |
| 3840–7680 | AAC 128 | 0.7 … 2.5 | −28.1 |
| 3840–7680 | AAC 96 | 0.5 … 1.9 | −28.7 |
| 3840–7680 | Opus 96 | −0.2 … 0.1 | −30.5 |
| 7680–15360 | AAC 128 | −0.1 … −0.1 | −30.6 |
| 7680–15360 | AAC 96 | −0.3 … 0.0 | −30.6 |
| 7680–15360 | Opus 96 | 0.0 … 1.1 | −29.4 |
| 15360–20000 | AAC 128 | −3.4 … −2.8 | −32.5 |
| 15360–20000 | AAC 96 | −6.1 … −8.0 | −37.7 |
| 15360–20000 | Opus 96 | 0.1 … 1.0 | −28.7 |

With a competing 0 dBFS bed, the added residue rose to at most `+3.5 dB`, still `27 dB` below the body. At 48 and 32 kbps the band is dropped, not smeared (added residue `−23` to `−135 dB`). **On this window the codec did not appear to bind; that conclusion is withdrawn (erratum above).**

The limitations are substantial: synthetic mono band noise, one encoder implementation (`ffmpeg` native AAC and `libopus`), 50 ms bursts, one gap length, no real music, no confidence intervals, no listening test, no other codecs (HE-AAC, MP3, Vorbis, AC-3), no stereo masking, no bitrate below 32 kbps or above 128 kbps. The old result was **SUPPORTED for the tested conditions**, not a general law; after the window correction it is **WITHDRAWN**. It never removed the codec as a possible constraint on the top-band numbers, and the corrected probe re-opens the question.

The script’s docstring still says “The meta’s top bands are limited by codec pre-echo, not by cone excursion. This script measures that limit.” That is the hypothesis the script was written to test; the old result did not confirm it, and the corrected probe supports it in direction but not in magnitude. The docstring also says “a residue 30 dB below the body is inaudible in any realistic playback” — an unsupported perceptual claim. The audit treats both as documentation errors, not as measurements.

#### D3. The catalogue median of eight masters supports the curve

**Status: UNKNOWN / REJECTED on the available data.**

The repository does not contain the eight tracks, the measurement script, or the table of per-track values. The README lists catalogue medians:

```
6.0 / 5.0 / 7.0 / 6.6 / 6.7 / 6.4 / 7.4 / 8.9 / 11.3 / 9.1 dB
```

The five available finished masters, measured with the current `band_crest`, give medians:

```
2.77 / 4.89 / 5.81 / 5.48 / 5.38 / 5.60 / 6.14 / 5.35 / 8.15 / 8.43 dB
```

The differences are large: `−3.2 dB` at 30–60, `−3.6 dB` at 3840–7680, `−3.2 dB` at 7680–15360, `−0.7 dB` at 15360–20000. Even allowing for the different corpus (five vs eight, different tracks), the README’s claim that the two derivations “agree” and that the catalogue “already lives at the devices’ limit” is not reproducible from the data in hand. The catalogue’s measurement method is not documented either; if it used a different estimator, the comparison is not like-for-like. That is itself a provenance defect. The claim is at best a hypothesis about a different set of tracks.

The `meta.py` docstring says “the median of eight finished masters, which landed on almost the same line.” The README says “catalogue medians per octave.” These are two different provenance stories. Neither is documented with the track list and the measurement method. The claim must be removed or fully documented.

#### D4. Listening calibration is absent from the rationale

**Status: REJECTED as a process claim; SUPPORTED that the `NOTES` text itself is ear-free.**

The `meta.py` `NOTES` no longer mention listening, and the README note says “Nothing here is calibrated by ear”. But:

- `README.md` still says “the meta merely formalises what the ear found on its own” and “Two independent derivations agree” with catalogue medians.
- `finalizer/meta.py` still says “the median of eight finished masters”.
- `profiles.toml` `[mid]` says “the balance chosen by ear”. This is a **profile**, not the meta, and it is legitimate to have a taste profile; the problem is that the README’s “nothing calibrated by ear” can be read as the whole tool.

The user’s instruction was to remove listening from the *rationale of the meta*. The meta’s current code comments and README still contain the catalogue/ear sentence. This is a documentation integrity failure, not a measurement failure. It must be fixed before the meta can claim to be ear-free.

#### D5. The top bands are model estimates

**Status: HYPOTHESIS / UNKNOWN.**

The values are:

| band | K_b | current status | audit status |
|---|---:|---|---|
| 1920–3840 | 7.2 | model estimate | **HYPOTHESIS**; no equation, no measurement |
| 3840–7680 | 8.3 | model estimate | **HYPOTHESIS**; corrected probe shows pre-echo in the frame before onset; audibility UNKNOWN |
| 7680–15360 | 8.0 | model estimate, unverified | **UNKNOWN**; codec residue is codec-dependent in the corrected probe; audibility UNKNOWN; 8.0 is *lower* than 8.3, which the codec mechanism does not explain |
| 15360–20000 | 10.3 | model estimate | **HYPOTHESIS/UNKNOWN**; “plenty of air, no real limit” is an assertion; the corrected probe finds pre-echo here for AAC and Opus, audibility UNKNOWN |

The non-monotonic `8.3 → 8.0 → 10.3` is a red flag. A single physical mechanism (excursion, thermal compression, codec pre-echo) would not normally produce a dip at 7680–15360 followed by a rise at 15360–20000. The shape looks like a composite of different considerations (or a fit to a particular set of tracks), not a model. If there is a mechanism, it must be stated as an equation and tested; if there is not, the numbers are placeholders.

#### D6. The low bands are 6.2 dB

**Status: ASSUMPTION.**

The six low/mid bands all use 6.2 dB. The stated mechanism is “limiter headroom and cone excursion”. The code has no SPL, no device model, and no measurement. The value binds on `T3`, `T5` and `T2`; it is the most consequential number in the meta. A single value across 30–1920 Hz is not a device law; it is a placeholder.

The current `devices.py` models have limiters at −3 dB (BT) and −2 dB (car) and high-pass corners at 480/190/120 Hz; they could be used to generate a *model* prediction of the crest at which the limiter engages, but that would still be a model, not a measurement. The experiment in `EXPERIMENT_DESIGN.md` is the way to replace it.

#### D7. The 75 dB SPL reference

**Status: UNKNOWN / not implemented.**

The number 75 dB SPL appears in `meta.py` comments and the README note. The code never measures SPL, never applies a weighting, and never sets a distance. A digital signal has no SPL until it is reproduced on a device at a volume setting in a room. The reference is a label attached to the numbers, not a condition of the measurement.

If `K_b` is to be a function of SPL, the specification must define:

- the weighting (Z, A, or C) and the time constant (Fast/Slow/Leq);
- the measurement position and distance (1 m on-axis, listening position, etc.);
- the calibration signal and the SPL meter;
- whether 75 dB SPL is the overall programme level or the band body level;
- the body level of the band relative to the overall level.

Without these, “6.2 dB at 75 dB SPL” cannot be reproduced or falsified.

### 4.5 Chain and processing side effects

#### E1. The chain preserves the contour in meta mode

**Status: REJECTED as stated.**

In meta mode `fit_contour=False`, so the contour EQ is not fitted. But `render` still calls `resonance_notches` with `deharsh=True` (the default). With `a.meta` set, `harsh_thr=99`, `max_rough=3.0`; any local roughness peak above 3.0 dB is notched, up to 4 dB. On `T4` with the `low` profile:

```
removed: 126Hz −3.2, 504Hz −3.8, 1008Hz −4.0, 1600Hz −1.5
contour preserved: max |d| 3.93 dB, rms 3.18 dB
```

The `−4.0 dB` notch at 1008 Hz is at the 1 kHz reference band. Because the contour is reported relative to 1 kHz, cutting the reference makes every other band look ~4 dB higher. The reported “max |d| 3.93 dB” is largely the notch, not a crest-stage body drop. With `--no-deharsh` the same master reports `max |d| 3.43 dB, rms 0.86 dB`; the remaining 3.43 dB is mostly the low bands, where the crest stage cut a large peak.

The `low` profile’s comment says “the reference point: no colouring. Full meta boundary + limiter.” It is not neutral: the default notches are colouring. The audit recommends disabling `deharsh` by default in meta mode and making the `low` profile explicitly notch-free, or documenting the notches as part of the profile.

#### E2. The crest stage is a static threshold and P75 does not move

**Status: REJECTED as a general claim.**

`crest_stage` computes a per-band time-varying gain with a 5 ms attack, 120 ms release, lookahead, and a `max_cut` of 18 dB. It is not a static gain; it is a band-wise compressor/limiter. The `base = P75(E)` is fixed, but the gain is applied to the whole band, so frames below the threshold can also be attenuated when the gain is down. The measured body drop is in A3/A4.

The iteration in `render` subtracts `excess + 0.3` from the target and clamps at 0. On a 50 dB burst, the target for the affected band was driven to `0.0`, meaning “flatten the band”, not “cut the excess above P75 + K_b”. The README’s claim that “only the excess above P75 + meta is cut” is not what the current target schedule guarantees. The `max_cut=18 dB` and the 3-iteration loop can over-cut a band whose crest is far above the ceiling; the output can fall below `F_b`, which is not checked.

#### E3. `low` is neutral

**Status: REJECTED.**

See E1. The profile’s `deharsh` is not set, so `render` uses `True`. The `low` output on `T4` has four notches and a 3.93 dB contour move. The profile name “low” means “low pressure”, not “no processing”; the comment should say so.

#### E4. The limiter is a safety net, normally never engages

**Status: SUPPORTED as a design intent; not a guarantee.**

On the full `T2`/`T4`/`T5` low masters, the limiter’s max gain reduction was 1.4 / 0.9 / 0.0 dB; on the 30 s `T2` excerpt it was 3.1 dB. It engages when the loudness target requires it. “Normally never” is material-dependent and should not be a specification.

#### E5. True peak is exact

**Status: SUPPORTED on the tested real masters; UNKNOWN on worst-case signals.**

On the tested real masters it is exact to the displayed 0.01 dB and agrees with ffmpeg to 0.03 dB. On high-frequency sines it differs by ~0.5 dB. The word “exact” is not justified without naming the meter and the filter. See C4.

### 4.6 Tooling, tests, and reproducibility

#### F1. `check` answers “can this be released?”

**Status: REJECTED as a release check.**

`run.py check` prints LUFS, TP, device-model shifts, and crest over. It does not return a pass/fail for `L`, `TP`, `side`, or `F_b`; it does not check the crest floor; it does not handle `NaN` as UNKNOWN; it uses a `+0.35 dB` tolerance. The device-model shifts are a synthetic translation metric, not a measurement of a real device. A release decision cannot be based on this output alone.

#### F2. The tests validate the measurements

**Status: REJECTED.**

`tests/test_engine.py` is a smoke test: it runs `meta`, `analyse`, `check`, `compare`, `variants`, `master` on a 2 s 220 Hz tone, checks that files exist and are 24-bit, and checks error messages. It does not assert a crest value, a loudness value, a true peak, a side ratio, a floor, a `NaN` decision, or a codec result. `tests/test_tui.py` is a UI regression. There is no `pytest` suite for the metrics, no reference signal with a known answer, and no test that the research tool does not modify audio.

#### F3. The research tools measure only

**Status: SUPPORTED for `pre_echo.py`; UNKNOWN for the not-yet-built research tooling.**

`research/pre_echo.py` measures only; it does not modify the input audio (it writes temp files and encodes them). The production `finalizer/chain.py` is a mastering processor; it is not a measurement tool. The new research tooling must be a separate module that imports or reimplements the metrics and never calls the chain’s processing stages. The current `run.py check` uses `devices.py` models and prints a verdict; that is a model, not a measurement, and should be labelled as such.

#### F4. Results are reproducible

**Status: SUPPORTED for deterministic input; UNKNOWN for full reproducibility (no JSON/CI/version).**

`pre_echo.py` uses a fixed seed for the noise (`default_rng(100 + bi)`) and deterministic encoders, but it does not record the ffmpeg version, the encoder implementation, the exact command, or the per-condition values in a machine-readable file. It prints a table. The `--quick` path was removed in the current version; the full run takes minutes. There is no confidence interval and no repeat across seeds.

The audit measurements in `RESULTS.md` are reproducible from the described algorithms and the five source files, but the audit scripts are not yet in the repository. They should be added under `research/audit/` in Phase 5, with a JSON output and the environment recorded.

#### F5. Dependencies are declared

**Status: SUPPORTED for production dependencies; UNKNOWN for research dependencies (not declared).**

`requirements.txt` lists `numpy`, `scipy`, `soundfile`, `textual`. The mandate prefers `librosa`, `pyloudnorm`, `matplotlib`, `pytest`; the audit used `matplotlib` and `ffmpeg` externally. The research extras should be in a separate `requirements-research.txt` or an optional section, with versions. `ffmpeg` is an external dependency (not bundled); the MIT license covers only the Python code.

#### F6. The meta has a single source of truth

**Status: REJECTED.**

`finalizer/meta.py` defines both `CREST_MAX` and `CREST_MAX_CALIBRATED` with identical values. `META` uses `CREST_MAX`; `CREST_MAX_CALIBRATED` is dead code. The name “CALIBRATED” is misleading because nothing is calibrated. Two copies of the same array invite divergence. Remove one.

---

## 5. Quantitative evidence

The full tables are in `RESULTS.md`. The key numbers:

### 5.1 The five masters against the current ceilings

`band_crest` (current code), dB:

| band | K_b | T1 | T2 | T3 | T4 | T5 |
|---|---:|---:|---:|---:|---:|---:|
| 30–60 | 6.2 | 2.77 | 1.60 | **8.86** | 1.70 | **11.34** |
| 60–120 | 6.2 | 3.53 | 4.89 | **8.28** | 4.01 | **11.39** |
| 120–240 | 6.2 | 4.43 | 3.97 | 5.81 | **7.85** | **8.39** |
| 240–480 | 6.2 | 4.15 | **7.96** | 5.48 | 5.87 | 5.34 |
| 480–960 | 6.2 | 4.89 | 5.38 | 5.53 | **6.45** | 5.24 |
| 960–1920 | 6.2 | 5.60 | **8.66** | 5.55 | 5.93 | 2.83 |
| 1920–3840 | 7.2 | 6.18 | **7.75** | 6.14 | 5.30 | 5.12 |
| 3840–7680 | 8.3 | 5.23 | **9.21** | 5.35 | 4.66 | **8.76** |
| 7680–15360 | 8.0 | NaN | **10.29** | 3.62 | 6.00 | **12.42** |
| 15360–20000 | 10.3 | NaN | 9.41 | 2.96 | 8.43 | NaN |

Bold = above the ceiling. `NaN` = the current “no programme” gate did not assess the band.

Fourteen of the 47 assessed band-track pairs are above the ceiling. Three of the 50 are `NaN`; two of those are the top bands of `T1`, one is the top octave of `T5`. The current meta is not a description of this corpus; it is a stricter normative bound. That is allowed — an admissible set need not contain every finished master — but it means the numbers cannot be justified by “the catalogue lives there”. The corpus sits *below* the ceiling in many bands and *above* it in others; the ceiling is not the median.

### 5.2 Estimator sensitivity

- Window length: 30–60 Hz moves by up to **5.4 dB** (`T4`); 60–120 by up to **2.0 dB** (`T4`); the top bands move by up to **3.0 dB** (`T2`).
- Excerpt length: 30 s vs full track moves by up to **8.7 dB** (`T5` 7680–15360, 3.93 vs 12.66; `T2` 15–20k, 16.08 vs 10.95).
- Bootstrap 95 % CI: typically **±1–3 dB**, up to **±2.7 dB** at the top of `T2`.
- Segment-to-segment SD: up to **13.2 dB** (`T4` 15–20k across 10 s segments).

The current band-to-band structure of `K_b` (6.2, 7.2, 8.3, 8.0, 10.3) is at or below this uncertainty. A single number per band may be defensible as a conservative bound; a finely structured curve is not.

### 5.3 The measurement hole

Synthetic test, 30 s, quiet 7680–15360 body at −30 dB relative to the bass, 50 dB burst:

| burst length | raw `P99.5 − P75` | `band_crest` |
|---:|---:|---:|
| 0.10 s | 29.8 dB | NaN |
| 0.25 s | 49.7 dB | NaN |
| 0.30 s | 49.8 dB | NaN |
| 0.50 s | 49.9 dB | **0.38 dB** |

The current code can report a 50 dB event as 0.38 dB (inside the 8.0 dB ceiling) or as `NaN` (treated as pass). This is the most serious correctness defect in the audit.

### 5.4 Body–crest dependence

Pooled correlation across 10 s segments: `r = −0.36`. Per band: `−0.55, −0.53, −0.29, −0.33, −0.52, −0.66, −0.39, −0.13, +0.04, −0.12`. This is not independence. The negative sign means a louder body is associated with a smaller relative tail; a quiet body with a larger relative tail. A fixed `K_b` therefore interacts with the material’s overall level distribution.

### 5.5 Body change under the crest stage

`T2` 30 s excerpt, ceiling 6.2 dB, one `crest_stage` call:

| band | B before | B after | ΔB | C before | C after |
|---|---:|---:|---:|---:|---:|
| 30–60 | 51.08 | 51.08 | 0.00 | 3.64 | 3.64 |
| 60–120 | 37.53 | 37.53 | 0.00 | 6.15 | 5.88 |
| 120–240 | 37.89 | 37.88 | 0.00 | 6.25 | 6.02 |
| 240–480 | 33.35 | 33.32 | −0.03 | 8.34 | 6.31 |
| 480–960 | 25.59 | 25.56 | −0.03 | 7.91 | 6.36 |
| 960–1920 | 23.65 | 23.47 | −0.19 | 11.89 | 7.03 |
| 1920–3840 | 24.43 | 24.10 | −0.33 | 11.50 | 7.49 |
| 3840–7680 | 22.81 | 22.22 | −0.60 | 13.67 | 7.88 |
| 7680–15360 | 22.24 | 20.22 | **−2.02** | 15.39 | 9.67 |
| 15360–20000 | 20.43 | 18.35 | **−2.09** | 16.08 | 9.74 |

The stage did not fully reach the 6.2 dB ceiling in one call; the `render` loop iterates. The body drop is the price of the cut; it is not zero by construction.

### 5.6 The mono filter

See C5. The output side/mid at 20–120 Hz is `−15.3 dB` on `T4` and `−28.0 dB` on `T2`; not zero. The 3rd-order high-pass is `−3 dB` at 120 Hz, so even at the corner it is not zero.

### 5.7 Loudness and true peak

The code’s LUFS agrees with `ffmpeg` within `0.05 dB`; the code’s TP agrees on real tracks within `0.03 dB` but differs by up to `0.52 dB` on high-frequency sines. The `−1 dBTP` target is a platform convention; the `−14 LUFS` target is a Spotify/default convention, not universal.

---

## 6. Required fixes

The fixes are ordered by scientific risk. “P0” means the current tool can give a wrong release decision; “P1” means the documentation claims more than the code does; “P2” means the measurement is not yet standard-conformant; “P3” means tooling/reproducibility.

### P0 — correctness of the measurement

| # | fix | reason |
|---|---|---|
| P0.1 | Replace the max-based active gate in `band_crest` with a broadband activity mask, or no gate, and report the raw `P99.5 − P75`. | The current gate can turn a 50 dB burst into 0.38 dB or NaN. |
| P0.2 | Remove the `len(act) > 20` `NaN` shortcut; define a minimum number of effective frames (e.g., ≥ 1000) and return UNKNOWN otherwise. | 21 frames are not enough for a 99.5th percentile. |
| P0.3 | Treat `NaN` as UNKNOWN, never as PASS, in `check`, `master`, and the report. | A band that was not assessed cannot be certified. |
| P0.4 | Replace the `top − 45 dB` “no programme” gate with a documented activity criterion based on the band’s own noise floor / audibility, not the loudest band. | On `T1`/`T5` the top bands are skipped; these are the bands under question. |
| P0.5 | Define a local/transient crest (`C_b^max` or sliding-window `C_b`) and report it separately; decide whether the meta is a tail or a peak constraint. | The current statistic cannot see short events; the codec/limiter mechanism is transient-driven. |
| P0.6 | Use one normative STFT for B and C, or define two estimators explicitly and calibrate them separately. | The “same envelope” claim is false; the two P75s differ by up to 5 dB (and 29 dB at 30–60 on `T4`). |
| P0.7 | Fix the 30–60 Hz resolution: longer window, multi-resolution, or a constant-Q filterbank; report the low band as unresolved otherwise. | At N=4096 the band has 3 bins; the value is window-dependent. |
| P0.8 | Implement a check for `F_b`, or remove it from the universal meta. | It is currently decorative; several masters are below it. |
| P0.9 | Replace `side = 0` with a measurable side/mid or mono-loss criterion; specify the filter and the threshold. | The implementation is a high-pass; the output is not mono. |
| P0.10 | Add a bootstrap/CI and a three-valued decision rule (PASS/FAIL/UNKNOWN) to every constraint. | The point estimate is not a decision; the current `+0.35 dB` is arbitrary. |
| P0.11 | Disable `deharsh` by default in meta mode; make the `low` profile notch-free or document the notches. | The current “neutral” profile applies up to −4 dB at 1 kHz. |
| P0.12 | Make `check` evaluate all five constraints, not only crest over. | The command currently cannot answer “can this be released?”. |

### P1 — documentation and provenance

| # | fix | reason |
|---|---|---|
| P1.1 | Remove “orthogonal by construction”, “P75 does not move by construction”, and “contour preserved” from README/`measure.py`/`chain.py`; replace with the three-part statement in A3. | The claims are false in general. |
| P1.2 | Remove the catalogue/ear rationale from README and `meta.py` (“two independent derivations agree”, “what the ear found”, “median of eight finished masters”). | The user’s instruction; the data do not reproduce the medians. |
| P1.3 | Remove the codec claim from the top-band table/body; keep the measured result and its limitations. | The original negative result was withdrawn; the corrected probe re-opens the codec question (audibility UNKNOWN). |
| P1.4 | Remove “every streaming service normalises to −14 LUFS”; state the platform convention and examples (Spotify −14, Apple −16, Deezer −15). | False as a universal claim. |
| P1.5 | Remove “side is filtered out / always mono”; say “high-passed; residual side is measured”. | The exact-zero claim is false. |
| P1.6 | Remove `CREST_MAX_CALIBRATED`; keep one source of truth. | Dead duplicate with a misleading name. |
| P1.7 | Fix the `low` profile comment (“no colouring”) and the README chain description to mention the notch stage. | The profile is not neutral. |
| P1.8 | State the status of every constant in one table with the audit labels: 6.2 = ASSUMPTION; 7.2/8.3/10.3 = HYPOTHESIS; 8.0 = UNKNOWN; F_b = ASSUMPTION/not implemented; L/TP/f_m = CONVENTION/HYPOTHESIS. | The current statuses are inconsistent across README, `meta.py`, and the code. |

### P2 — standard meters

| # | fix | reason |
|---|---|---|
| P2.1 | Implement the BS.1770-4 Annex 2 48-tap/4-phase true-peak filter, or validate `resample_poly` against `libebur128` and state the meter. | The current meter under-reads by 0.5 dB on HF sines. |
| P2.2 | Add a tolerance to `TP ≤ −1 dBTP` (e.g., `≤ −1.0 dBTP` on the named meter; internal target −1.2 if the platform is −1.0). | Meter disagreement; the current “exact” claim is too strong. |
| P2.3 | Add a sample-rate guard to `lufs_integrated`/`true_peak`; resample or reject non-48 kHz. | The K-weighting coefficients are 48 kHz only. |
| P2.4 | Cite the exact editions: ITU-R BS.1770-4 (10/2015), Annex 2; EBU Tech 3342 for LRA; AES75-2023 for the 2 dB compression procedure. | The repo currently says “BS.1770-4” in one place and “ITU 1770” in another; the LRA source is not cited. |

### P3 — tooling and reproducibility

| # | fix | reason |
|---|---|---|
| P3.1 | Add `research/metrics.py` with the corrected estimators, units, validation, and a JSON schema; keep it separate from `finalizer/chain.py`. | The mandate: measurement only, no auto-conform. |
| P3.2 | Add `tests/test_metrics.py` with known-answer signals: gain invariance, a known crest, a known side ratio, a known LUFS/TP, a `NaN` case, a short-event case. | The current tests are smoke tests. |
| P3.3 | Record the environment (Python, numpy/scipy/soundfile, ffmpeg/encoder, git commit) in every result file. | Reproducibility. |
| P3.4 | Add a `--json` output to `pre_echo.py`, with per-condition values, repeats, and CIs; remove the audibility claim. | The current table is not machine-readable and has no uncertainty. |
| P3.5 | Add the audit scripts under `research/audit/` (or equivalent) and the figures under `research/figures/`. | The results in this document must be reproducible. |
| P3.6 | Declare research dependencies separately (`matplotlib`, `pytest`, optional `librosa`/`pyloudnorm`). | `requirements.txt` is production-only. |

---

## 7. What the audit does not claim

- It does not claim that the current `K_b` values are wrong. It claims they are **not measured** and **not supported by the evidence in the repository**. A value can be a good guess and still be an assumption.
- It does not claim that the codec is irrelevant. It claims that the tested codecs at 96–128 kbps did not reproduce the pre-echo limit in the tested conditions, and that the result does not generalize to all codecs/bitrates/material.
- It does not claim that `F_b` is meaningless. It claims that no universal `F_b` has been established, that the current values are a craft judgment, and that the implementation does not enforce them. The experiment in `EXPERIMENT_DESIGN.md` is designed to decide whether a universal floor exists.
- It does not claim that `side = 0` is a bad mastering rule. It claims that the code does not implement it, and that the physical justification supports a mono-compatibility criterion, not necessarily an exact zero at 120 Hz.
- It does not claim that the five masters are a representative corpus. They are a convenience sample used to expose estimator behaviour and provenance inconsistencies.

---

## 8. Conclusion

The meta is a coherent engineering idea: a set of per-band constraints on a finished master, with the contour and the stereo width left free. The audit supports the *structure* of that idea. It rejects the *current scientific status* of the implementation:

- the constants are assumptions/hypotheses, not measurements;
- the crest estimator is a tail statistic with a gate that can hide the events it is supposed to catch;
- the floor is not implemented;
- the mono constraint is a high-pass, not a zero;
- the “orthogonal” and “contour preserved” claims are false;
- the catalogue/ear and codec rationales are not reproducible from the repository;
- the true-peak meter is not the standard filter;
- the tests do not validate the metrics.

The next step is not to tune the numbers. It is to run the experiments in `EXPERIMENT_DESIGN.md` with the corrected metrics in `METRIC_SPECIFICATION.md`, and to replace each constant only when a measurement supports it. Until then, every `K_b` should be labelled with its audit status, and every release decision should carry the measurement uncertainty and the `UNKNOWN` bands explicitly.

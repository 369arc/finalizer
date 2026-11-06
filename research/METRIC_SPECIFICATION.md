# Metric specification

**Status:** proposed normative specification for the research programme. It describes the corrected metrics; it is not yet a description of the current code. The deviations of the current implementation are listed in §14.  
**Version:** `metric-spec 0.1-draft`  
**Applies to:** the meta of `369arc/finalizer`, research measurements, and the experiment protocols in `EXPERIMENT_DESIGN.md`.  
**Commit of the audited code:** `af04531`.

The purpose of this document is to remove ambiguity. Every quantity has:

- a symbol and a unit;
- an analysis grid (sample rate, window, hop, band edges);
- an activity rule;
- an estimator and a boundary condition;
- an uncertainty statement;
- a pass/fail/unknown rule.

If any of these changes, the constants `K_b` and `F_b` are not transferable. The metric version must be recorded with every result.

---

## 1. Conventions and units

| quantity | unit | definition |
|---|---|---|
| digital level | dBFS | `20 log10(|x| / 1.0)` for a full-scale square/sine reference; the signal is float, `|x| ≤ 1` is not assumed |
| band level | dB | `10 log10(P / P_ref)` with `P_ref = 1.0`; relative levels are differences of dB |
| acoustic level | dB SPL | `20 log10(p / 20 µPa)`, with a stated weighting and time constant |
| loudness | LUFS | ITU-R BS.1770-4 integrated loudness; 1 LU = 1 dB |
| true peak | dBTP | BS.1770-4 Annex 2 true-peak level |
| frequency | Hz | band edges are exact; bins are selected by their centre frequency |
| time | s | frame index `m` corresponds to the window start `mH / f_s` |
| crest | dB | ratio of two band powers, expressed as a level difference |

The sample rate is **48 000 Hz**. Other rates must be converted before analysis by a documented resampler; the conversion is part of the measurement and must be reported. The current `ingest.py` uses ffmpeg's default resampler; the research tool should use a specified high-quality resampler (e.g., `soxr` via ffmpeg, or `scipy.signal.resample_poly` with a stated filter) and record it.

The signal is stereo. The meta is defined for stereo; mono files are duplicated to two channels for analysis, and this must be reported (it changes the side ratio: a mono file has `S = 0` by construction).

---

## 2. Signal model and preprocessing

`x[n] = (x_L[n], x_R[n])`, `n = 0 … N_s − 1`, float32 or float64.

Preprocessing for the **meta measurement**:

1. Do **not** apply a high-pass, a limiter, a fade, or any other processing. The measurement is of the delivered master.
2. Remove a constant DC offset only if it is an artefact of the file format; report it. A DC offset is otherwise part of the signal and will appear in the lowest band.
3. If the file is shorter than 60 s, the result is `UNKNOWN` for the tail statistics (see §7). A shorter file may still be analysed, but the result must be labelled “short-form” and must not be compared with a 60 s+ `K_b`.
4. Channels: for the band power, sum the power of the two channels (total energy). For the stereo metrics, use the mid/side definitions in §11.

The production chain may apply a 20 Hz high-pass; the research measurement must not. If the delivered master already contains the chain's high-pass, that is part of the master and must be reported.

---

## 3. Analysis grid

### 3.1 STFT

For a band `b` with edges `[e_b, e_{b+1})`, choose a window length `N_b` that resolves the band. The recommended rule:

```
N_b = next_pow2( max(4096, 8 * f_s / (e_{b+1} - e_b)) )
H_b = N_b / 4
```

where `next_pow2(x) = 2^ceil(log2 x)` and `H_b` is an integer (N_b is a power of two).
This gives:

| band, Hz | width, Hz | `N_b` | bin spacing, Hz | bins in band |
|---|---:|---:|---:|---:|
| 30–60 | 30 | 16384 | 2.93 | 10 |
| 60–120 | 60 | 8192 | 5.86 | 10 |
| 120–240 | 120 | 4096 | 11.72 | 10 |
| 240–480 | 240 | 4096 | 11.72 | 20 |
| 480–960 | 480 | 4096 | 11.72 | 41 |
| 960–1920 | 960 | 4096 | 11.72 | 82 |
| 1920–3840 | 1920 | 4096 | 11.72 | 164 |
| 3840–7680 | 3840 | 4096 | 11.72 | 328 |
| 7680–15360 | 7680 | 4096 | 11.72 | 655 |
| 15360–20000 | 4640 | 4096 | 11.72 | 396 |

The window is the periodic Hann:

```
w[n] = 0.5 - 0.5 cos(2π n / N_b),  n = 0 … N_b - 1
```

The signal is padded by `N_b` zeros at both ends. The frame starts at `m H_b`, `m = 0 … M_b − 1`, with `M_b = 1 + floor((N_s + 2N_b − N_b) / H_b)`.

**Why multi-resolution.** At `N = 4096`, 30–60 Hz has three bins and the measured crest of `Y` moves by 5.4 dB between `N = 4096` and `N = 16384`. A single window cannot be both narrow in time for the top octave and narrow in frequency for the bottom octave. The multi-resolution rule is the minimum needed to make the low bands meaningful. The cost is that the low bands have a 341 ms window; the time resolution must be stated.

**Alternative.** A constant-Q filterbank with 1/12-octave resolution and a stated time response is acceptable, but it must be documented and compared with the STFT on a test signal. The current code's 4096/1024 is not acceptable for 30–60.

### 3.2 Band power

For each frame and band:

```
P_b[m] = Σ_{k: e_b ≤ f_k < e_{b+1}} ( |X_L[m,k]|² + |X_R[m,k]|² )
E_b[m] = 10 log10( P_b[m] + ε ),   ε = 1e-20
```

The sum is over the one-sided bins whose centre `f_k = k f_s / N_b` lies in the half-open interval. The Nyquist bin is included only if it lies in the interval. Bands narrower than the bin spacing are not allowed; the rule above prevents them.

**Hard vs smooth bands.** The measurement uses hard bin edges; the gain application may use smooth crossovers. The report must say which is used for the number being quoted. The current code uses hard bins for measurement and 0.4-octave raised-cosine weights for gain; that is a defensible engineering choice, but the two are not the same filter.

### 3.3 Band edges and domain

```
E = {30, 60, 120, 240, 480, 960, 1920, 3840, 7680, 15360, 20000} Hz
```

The meta is defined on `[30, 20000]` Hz. Content below 30 Hz and above 20 kHz is outside the meta and must be reported separately:

- **20–30 Hz**: currently unregulated. Either add a band with an appropriate window (e.g., 20–30, `N = 32768`) or state that the meta requires a high-pass at 30 Hz. The current `hpf=20` does not close the gap.
- **20–24 kHz**: the top band ends at 20 kHz; content from 20–24 kHz is unregulated. This is intentional (the band is at the edge of most playback systems) but must be stated.
- The `sustain_contour` 1/3-octave grid (25 Hz–16.1 kHz) is a *different* grid; it must not be conflated with the crest grid.

---

## 4. Activity, body, and the two crests

### 4.1 Broadband activity mask

The body must not be computed per band with a gate that depends on that band's maximum. A loud short event in a quiet band would otherwise exclude the body and measure the event against itself (the current failure).

Define the broadband frame level:

```
P_tot[m] = Σ_b P_b[m]        (sum over the bands of the analysis grid)
L_tot[m] = 10 log10(P_tot[m] + ε)
```

The activity mask is:

```
A = { m : L_tot[m] ≥ max(L_tot) - G_a  and  L_tot[m] ≥ L_floor }
```

with defaults:

- `G_a = 40 dB` (frames more than 40 dB below the loudest frame are silence/decay);
- `L_floor = −70 dBFS` (absolute noise floor; adjust to the file's measured noise floor + 10 dB and report it).

The mask is **broadband**: a frame is active if the programme is active, even if the band of interest is quiet. A quiet band with a loud burst stays in the body; the burst is a tail event.

**Common time grid.** The multi-resolution bands in §3.1 have different frames (`N_b`, `H_b`). The activity mask needs a common grid. Compute it from a separate 4096/1024 broadband STFT (window 4096, hop 1024), or resample each band envelope to the shortest hop; then expand the mask to each band's native grid by nearest-frame or by overlap. The mask is a programme-activity detector, not a per-band measurement; it must not be recomputed from a band's own maximum. The body and crest for each band use the mask on that band's native grid. The mask's own parameters (`G_a`, `L_floor`) are part of the metric version.

The 40 dB value is a parameter, not a law. It must be sensitivity-tested (30/40/50 dB) and reported. The current 45 dB per-band gate is not equivalent.

### 4.2 Body

```
B_b = P75( E_b[m] for m ∈ A )
```

The percentile uses linear interpolation between order statistics (`numpy.percentile` default), with the number of active frames `N_A` reported. If `N_A < 1000`, `B_b` is `UNKNOWN`; 1000 frames at a 21.3 ms hop is ~21 s, which is the minimum for a stable P75.

If the band has no energy above the noise floor in the active frames, `B_b` is `UNKNOWN` (not a number, not a pass). The current `NaN` conflates “no programme” with “not assessed”.

### 4.3 Tail crest

```
C_b^tail = P99.5( E_b[m] for m ∈ A ) − B_b
```

This is the current meta's statistic, corrected for the gate. It is a **duration-weighted tail ratio**, not a peak. Its resolution is `0.5 %` of `N_A`: for a 60 s track at a 21.3 ms hop, `N_A ≈ 2817`, so the top 0.5 % is ~14 frames (~0.3 s). An event shorter than ~0.3 s is not represented.

### 4.4 Peak and local crest

To describe events shorter than the tail resolution, report:

```
C_b^max = max( E_b[m] for m ∈ A ) − B_b
C_b^local = max over windows W of [ P99(E_b[m], m ∈ W) − P75(E_b[m], m ∈ W) ]
```

with `W` a sliding window of 3 s and a hop of 1 s (or a stated window). `C_b^max` is sensitive to a single click; `C_b^local` is a compromise. The experiment must decide which one is normative for the mechanism:

- **device/codec transient mechanism** → `C_b^local` or `C_b^max` with a measured threshold;
- **sustained programme mechanism** → `C_b^tail`.

The meta may carry two constraints:

```
C_b^tail  ≤ K_b^tail
C_b^local ≤ K_b^local
```

The current `K_b` is a `K_b^tail`; it must not be silently applied to `C_b^max`. A 50 dB, 0.5 s burst has `C_b^tail = 49.9 dB` (raw) and `C_b^max = 50 dB` (approximately), but the current gated estimator reports 0.38 dB; the corrected estimator must report the burst.

### 4.5 The lower bound

If the meta retains a floor:

```
C_b^tail ≥ F_b
```

The floor is a lower bound on the sustained crest. It is not enforced by raising peaks in the audio; it is a **release check**. If the check fails, the master is rejected or the floor is waived by an explicit, documented decision. The research tool must not add transients to meet a floor; that would be auto-conforming and would change the material.

---

## 5. Uncertainty

### 5.1 Block bootstrap

The frames are correlated by the STFT overlap and by the material. A naive binomial CI is too narrow. Use a moving-block bootstrap:

1. Divide the active frames into contiguous blocks of `L_blk` seconds (default 10 s; test 5 and 20 s).
2. Resample blocks with replacement until the resampled series has the original length `N_A`.
3. Recompute `B_b`, `C_b^tail`, `C_b^local` on the resample.
4. Repeat `B = 1000` times (200 is acceptable for a quick look; 1000 for a result).
5. Report the 2.5th and 97.5th percentiles and the standard deviation.

The block length must exceed the correlation time of the envelope. If the result depends strongly on `L_blk`, report that; the uncertainty is then not separable from the non-stationarity.

### 5.2 Decision rule

For an upper bound `C ≤ K`:

| condition | decision |
|---|---|
| `C^{97.5} ≤ K` | **PASS** |
| `C^{2.5} > K` | **FAIL** |
| otherwise | **UNKNOWN** |

For a lower bound `C ≥ F`:

| condition | decision |
|---|---|
| `C^{2.5} ≥ F` | **PASS** |
| `C^{97.5} < F` | **FAIL** |
| otherwise | **UNKNOWN** |

The conservative direction is the one that could reject a good master, not the one that could accept a bad one. `UNKNOWN` is not a pass. The current `+0.35 dB` tolerance is replaced by the CI plus a separate **calibration tolerance** for the meter (e.g., ±0.1 dB for LUFS, ±0.5 dB for TP); the two must not be conflated.

### 5.3 Minimum duration

The tail statistic needs enough frames above the quantile. Require:

- `T ≥ 60 s` and `N_A ≥ 1000` for a `C_b^tail` result;
- for `T < 60 s`, report `UNKNOWN` or a “short-form” value with a warning; do not compare it with a 60 s+ `K_b`;
- for a track with a long silence, `N_A` may be much smaller than the duration suggests; use `N_A`, not `T`.

The five-master audit shows 30 s excerpts can differ from the full track by up to 8.7 dB. A 60 s minimum is necessary, not sufficient; the CI is the real statement.

---

## 6. Per-band constraints and the meta object

A meta is a tuple:

```
M = {
  version,
  bands: [e_0 … e_B],
  K_tail[b], K_local[b] (optional),
  F[b] (optional),
  L0, L_tol,
  TP0, TP_tol, TP_meter,
  mono: { f_m, side_max_db, mono_loss_min_db, filter },
  domain: [30, 20000],
  reference: { SPL, weighting, distance, body_level }
}
```

The constraints are:

```
C_b^tail  ≤ K_tail[b]        for every assessed b
C_b^local ≤ K_local[b]       if the transient constraint is enabled
C_b^tail  ≥ F[b]             if the floor is enabled
|L − L0|  ≤ L_tol
TP        ≤ TP0               on the named meter, with TP_tol
side ratio and mono loss      per §11
```

A band is **assessed** if `N_A ≥ 1000`, the band has programme (P75 above the noise floor + 10 dB), and the band is inside the domain. An unassessed band is `UNKNOWN`, not `PASS`.

The meta is a set of constraints, not a target. The contour `B_b`, the width above `f_m`, and the choice of profile are free. The report must list every constraint with its decision and the evidence. A single `overall: pass` is allowed only if every assessed band passes and no band is `UNKNOWN`; otherwise the overall is `FAIL` or `UNKNOWN`.

---

## 7. Loudness

### 7.1 Algorithm

ITU-R BS.1770-4 (10/2015):

1. K-weighting: the two-stage filter with the 48 kHz coefficients in `dsp.py` (`_B1/_A1`, `_B2/_A2`). The coefficients are valid at 48 kHz only.
2. Mean square per channel over 400 ms blocks with 75 % overlap (100 ms hop).
3. Channel weights: 1.0 for L/R (stereo).
4. Block loudness: `l_i = −0.691 + 10 log10(Σ_c G_c z_{c,i})`.
5. Absolute gate: keep blocks with `l_i > −70 LUFS`.
6. Relative gate: `Γ = −0.691 + 10 log10(mean(z_i over absolute-gated blocks)) − 10`; keep blocks with `l_i > Γ`.
7. Integrated loudness: `L = −0.691 + 10 log10(mean(z_i over both gates))`.

The current implementation matches this and agrees with `ffmpeg` within 0.05 dB on the tested signals. It must reject or resample non-48 kHz input; the `sr` argument is currently ignored.

### 7.2 Target and tolerance

`L0 = −14.0 LUFS` is a **delivery convention**, not a physical boundary. The specification requires:

```
|L − L0| ≤ 0.1 LU
```

for a file of at least 10 s. For shorter files, report `UNKNOWN`. The report must state the platform and the date of the convention; platform targets differ (Spotify documents −14 LUFS; Apple Music is commonly −16; Deezer −15; SoundCloud does not normalize). A master at −16 LUFS is not “outside physics”; it is outside a chosen delivery target.

The target must not be used to justify limiting. Loudness normalization at playback does not undo limiting; a hotter master that is turned down keeps the limiting that was applied to make it hot. The rationale “louder buys nothing” is incomplete: it buys nothing in playback level, but it may have cost dynamics.

---

## 8. True peak

### 8.1 Algorithm

ITU-R BS.1770-4 Annex 2:

1. Attenuate by 12.04 dB if integer arithmetic is used (not needed in float).
2. Oversample by 4× with the 48-tap, 4-phase FIR interpolating filter specified in the Annex (or a filter that meets the same passband/stopband accuracy).
3. Take the absolute value; convert to dBTP; compensate the attenuation.

The current `dsp.true_peak` uses `scipy.signal.resample_poly(..., 4, 1)`. It is a 4× oversampled peak meter, but not the Annex 2 filter. On real programme it agrees with `ffmpeg` within 0.03 dB; on high-frequency sines it under-reads by up to 0.52 dB. It must be replaced or validated against a reference meter.

### 8.2 Target and tolerance

`TP0 = −1.0 dBTP` is a **platform convention** (Spotify recommends −1; some platforms recommend −2 for loud masters). Let `TP_meas` be the reading of the named meter and `u` the half-width of its uncertainty. The conservative requirement is:

```
TP_meas + u ≤ TP0
```

so the true peak is below `TP0` even if the meter under-reads. For a meter validated against BS.1770-4 Annex 2 on real programme, `u = 0.1 dB`; for a generic meter or worst-case high-frequency content, `u = 0.5 dB`. If the internal meter is not the platform meter, use an internal target of `TP0 − u` (e.g., `−1.2 dBTP` for `TP0 = −1.0` with `u = 0.2`). The report must name the meter and the filter. The current code's `resample_poly` meter is in the `u = 0.5 dB` class until it is validated.

---

## 9. Stereo and mono

### 9.1 Definitions

```
M[n] = (L[n] + R[n]) / 2
S[n] = (L[n] - R[n]) / 2
```

The 1/2 scaling is a convention; it cancels in the ratios below.

For a band `[f_lo, f_hi]`, compute the band-limited RMS of `M` and `S` with a stated filter (e.g., a 4th-order Linkwitz-Riley or a linear-phase FIR). Then:

```
R_S = 20 log10( RMS(S) / RMS(M) )          side-to-mid ratio, dB
mono_loss = 20 log10( RMS(M) / sqrt( (RMS(L)² + RMS(R)²) / 2 ) )
```

`mono_loss = 0 dB` for `L = R`; `−∞` for `L = −R`; a negative value is the loss of level in the mono fold-down relative to the uncorrelated power sum.

The current `corr_low` is the correlation of the low-passed L/R; it is a diagnostic, not `R_S` or `mono_loss`. Report all three if desired, but the constraint must use a stated one.

### 9.2 Criterion

The exact-zero rule is a special case:

```
R_S(f) = −∞ dB for all f < f_m
```

It is not achievable with a causal IIR high-pass, and it is stronger than the physical requirement. A measurable criterion is:

```
R_S(f) ≤ −X dB for f < f_m
mono_loss(f) ≥ −Y dB for f < f_m
```

with `f_m`, `X`, `Y` determined by a mono-compatibility/preference experiment. The current implementation is a 3rd-order Butterworth at 120 Hz; it gives `−3 dB` at 120 and `−18 dB` at 60, not `−∞`. The report must state the filter and the measured residual.

If exact zero is required, use a linear-phase FIR or an STFT mask on the side channel and report the pre-ringing; a minimum-phase filter cannot be exactly zero on a band without also changing the phase above it.

### 9.3 Domain

The mono criterion applies below `f_m` (currently 120 Hz). The choice of `f_m` is a hypothesis; it depends on the playback system and the material. The experiment should test 80/100/120/150 Hz.

---

## 10. Reference SPL and the definition of `K_b`

### 10.1 The problem

`K_b` is not a property of a digital file. It is a property of a **device + SPL + programme + room** combination. A number such as “6.2 dB at 75 dB SPL” is incomplete unless the following are defined:

- **Weighting and time constant** for the SPL: Z (flat), A, or C; Slow (1 s), Fast (125 ms), or Leq over the stimulus.
- **Position and distance**: 1 m on-axis, the listening position, or a defined grid.
- **Calibration**: IEC 60942 class 1/2 calibrator; IEC 61672-1 class 1/2 sound level meter; microphone calibration file.
- **Body level**: is 75 dB SPL the overall programme level, or the level of the band under test? A band at 75 dB SPL in 30–60 Hz is a very different stress from a 75 dB SPL overall programme with a bass band at 85 dB.
- **Stimulus**: the crest is defined on the electrical input; the acoustic output has a different crest. State which is measured.
- **Duration and duty cycle**: thermal compression depends on time; a 3 s burst and a 3 min programme are different tests.

The current code has none of these. The values are digital constants with a label.

### 10.2 The operational definition

For a device class `D`, a reference SPL `S`, and a body level `L_body`:

```
K_b(D, S, L_body) = sup { c : PC_b(c; D, S, L_body) ≤ δ }
```

where:

- `c` is the input `C_b^tail` (or `C_b^local`, if the transient constraint is used), measured on the electrical stimulus with the normative estimator;
- `PC_b(c)` is the power compression of the band:

```
PC_b(c) = [ L_b^out(c) − L_b^out(0) ] − [ L_b^in(c) − L_b^in(0) ]
```

with `L_b` the band body (P75) measured on the acoustic output (or the electrical input, for the input term); `c = 0` is a low-level linear reference, not a sine;
- `δ` is the degradation criterion. A starting value is 2 dB, following the AES75-2023 maximum-linear-SPL procedure; it is an engineering criterion, not an audibility threshold. The final `δ` should be the smaller of the engineering `δ` and the perceptual threshold from Experiment C.

The set `{c : PC_b(c) ≤ δ}` must be checked for monotonicity. If `PC_b` is not monotonic, define `K_b` as the upper end of the connected interval containing `c = 0`, and report the non-monotonicity. A simple `max` over a non-monotonic set is not meaningful.

### 10.3 The 2 dB criterion

AES75-2023 (formerly M-Noise) uses a 2 dB compression target over at least two octaves, or 3 dB anywhere, plus a coherence reduction target, to find the maximum linear SPL of a loudspeaker with a broadband Music-Noise stimulus. It is a **loudspeaker maximum-SPL** procedure, not a per-band crest experiment. Transferring the 2 dB number to `K_b` is an **assumption**. The experiment must:

- measure the compression curve, not just the stop condition;
- measure the perceptual threshold for the same compression;
- report both `K_b(δ=2 dB)` and `K_b(δ=perceptual)`;
- not call the 2 dB value “the” threshold without a citation and a justification.

### 10.4 Device class and unit variance

`K_b` is a property of a class, not a single unit. The experiment must sample at least 3 units per class and report the between-unit standard deviation. A conservative meta uses a lower quantile (e.g., the 5th percentile) of the unit distribution, not the mean. The class definition (phone, laptop, BT speaker, earbuds, car, monitor) is a convenience; the report must list the make/model/firmware.

---

## 11. Reporting format

Every measurement writes a JSON object (and optionally a CSV row) with at least:

```json
{
  "metric_version": "metric-spec 0.1-draft",
  "git_commit": "af04531",
  "file": "path/to/master.wav",
  "sha256": "…",
  "sample_rate": 48000,
  "channels": 2,
  "duration_s": 204.0,
  "analysis": {
    "window": "hann-periodic",
    "n_per_band": {"30-60": 16384, "60-120": 8192, "default": 4096},
    "hop_ratio": 0.25,
    "activity_gate_db": 40.0,
    "activity_floor_dbfs": -70.0,
    "percentile_method": "linear"
  },
  "bands": [
    {
      "band_hz": [30, 60],
      "B_db": 59.46,
      "C_tail_db": 1.60,
      "C_local_db": 3.2,
      "C_max_db": 6.8,
      "ci95": [1.22, 2.26],
      "n_active": 8123,
      "status": "PASS",
      "K_tail_db": 6.2,
      "F_db": 2.5
    }
  ],
  "loudness": {"L_lufs": -13.94, "target": -14.0, "tol": 0.1, "status": "PASS"},
  "true_peak": {"tp_dbtp": -1.00, "meter": "bs1770-4-annex2", "status": "PASS"},
  "stereo": {"side_mid_20_120_db": -15.3, "mono_loss_db": -0.8, "status": "UNKNOWN"},
  "overall": "UNKNOWN",
  "notes": ["…"]
}
```

Rules:

- `status` is one of `PASS`, `FAIL`, `UNKNOWN`.
- `overall` is `PASS` only if every assessed constraint passes and no constraint is `UNKNOWN`; otherwise `FAIL` or `UNKNOWN`.
- `NaN` is not a JSON number; use `null` and `status: "UNKNOWN"`.
- The JSON must include the analysis parameters; a result without them is not reproducible.
- The research tool writes JSON/CSV/figures, never audio. The production chain is a separate program.

---

## 12. Versioning

The metric version changes if any of the following changes:

- window length, hop, window function, padding;
- band edges or band selection;
- activity gate or floor;
- percentile or interpolation method;
- bootstrap block length or number of resamples;
- loudness/TP algorithm or filter;
- side/mono filter or criterion.

A change invalidates the constants `K_b` and `F_b` unless the old and new estimators are compared on a common corpus and the mapping is reported. The meta object must carry `metric_version`; a result measured with one version must not be compared with a `K_b` calibrated with another.

---

## 13. Test vectors (normative examples)

These are the minimum tests for an implementation of this specification. They are intentionally simple so that an independent researcher can reproduce them.

| test | signal | expected |
|---|---|---|
| gain invariance | any signal `x`, `2x` | `B` shifts by `+6.0206 dB`; `C` unchanged within `1e-6 dB` |
| known crest | body noise + a burst of known gain; measure `C_tail` | within `0.5 dB` of the design value after the body fraction is > 75 % |
| short event | quiet band + 0.5 s burst 50 dB above body | `C_tail` ≈ 50 dB, `C_max` ≈ 50 dB; not 0.38 dB, not `null` |
| short event, below tail | quiet band + 0.1 s burst 50 dB above body | `C_max` ≈ 50 dB; `C_tail` may be lower; status must be `FAIL` or `UNKNOWN`, not `PASS` |
| `NaN`/unassessed | a band with no programme | `status: "UNKNOWN"`, not `PASS` |
| floor | a signal with `C` below `F` | `status: "FAIL"` for the floor, not silence |
| LUFS | 1 kHz sine at −20 dBFS, 10 s | `−20.0 LUFS ± 0.1` (BS.1770-4) |
| LUFS reference | any file | `|code − ffmpeg| ≤ 0.1 LU` |
| TP | 1 kHz sine at −1 dBFS | `−1.0 dBTP ± 0.1` on the named meter |
| TP worst case | 19 kHz sine at 0 dBFS | compare with the reference meter; state the difference; do not claim “exact” |
| side | `L = sin(2π60t)`, `R = −L` | before: `R_S ≈ 0 dB`; after the mono filter: `R_S` equals the filter's measured attenuation, not `−∞` |
| mono loss | `L = R` | `mono_loss = 0 dB`; `L = −R` | `mono_loss → −∞` |
| duration | 30 s excerpt vs full track | report both; do not use the 30 s value as a `K_b` result |

---

## 14. Deviations of the current implementation

This table is the bridge between the specification and the code at `af04531`. It is not a criticism of the code's authors; it is a list of the exact places where the code and the written definition diverge.

| spec | current code | consequence |
|---|---|---|
| multi-resolution `N_b` | one `N=4096`, `H=1024` for all bands | 30–60 has 3 bins; window-dependent |
| broadband activity mask | per-band `e > e.max() − 45` | hides short/loud events; body can be excluded |
| `C_tail` on active frames | gated `P99.5 − P75` | not the written statistic; 50 dB burst → 0.38 dB |
| `N_A ≥ 1000` | `len(act) > 20` | 21 frames accepted; short events → `NaN` |
| `UNKNOWN` | `NaN` treated as `ok` in `check`/`master` | unassessed band can pass |
| one body for B and C | 4096/1024 vs 16384/4096 | contours differ by up to 5 dB (29 dB at 30–60 on `Y`) |
| `F_b` check | `crest_min` never used | floor is decorative |
| `side` criterion | 3rd-order high-pass | not zero; −3 dB at 120, −18 dB at 60 |
| `TP` Annex 2 | `resample_poly` | 0.5 dB under-read on HF sines |
| `L` 48 kHz guard | `sr` ignored | wrong if called on non-48 kHz |
| `deharsh` off in meta | `deharsh=True` default | notches the contour, incl. the 1 kHz reference |
| `check` all constraints | crest + device model only | no L/TP/side/floor pass/fail |
| CI / decision | point estimate + `+0.35 dB` | no uncertainty; arbitrary tolerance |
| `CREST_MAX` single source | `CREST_MAX` + `CREST_MAX_CALIBRATED` | dead duplicate |

---

## 15. What the specification deliberately does not decide

- The numerical values of `K_b`, `F_b`, `f_m`, `X`, `Y`, `L0`, `TP0`. They are outputs of the experiments, not inputs to the specification.
- The device class list. It is a sampling frame, not a law.
- The perceptual criterion `ε`. It is measured in Experiment C; the specification only says how to combine it with the engineering criterion.
- Whether the meta should have a transient constraint in addition to the tail constraint. The experiment must decide; the specification provides both statistics so the decision can be made without changing the estimator again.

# Experiment design

**Status:** protocol for the research programme. It is written to be executed, not to confirm the current constants. The current `K_b` and `F_b` are treated as inputs to the null hypothesis, not as expected results.  
**Companion documents:** `MASTERING_META_AUDIT.md` (what is wrong and why), `METRIC_SPECIFICATION.md` (how to measure), `RESULTS.md` (what has been measured so far), `VALIDATION_REPORT.md` (what the tooling has been tested against).  
**Metric version:** `metric-spec 0.1-draft`.

---

## 1. Research questions

The programme has four independent questions and one integration question.

**Q1 — device dynamics.** For a given class of playback device, at a stated SPL and body level, what is the largest per-band crest `K_b` at which the device's power compression and nonlinear distortion stay below a defined degradation criterion?

**Q2 — coding.** For a given codec, bitrate, encoder and material type, at what input crest does the codec produce an audible pre-echo, band dropout or other artefact? Does this constraint bind before the device constraint?

**Q3 — perception.** At what degradation magnitude does a listener detect the degradation, and at what magnitude does preference change? These are two different thresholds and must not be conflated.

**Q4 — the floor.** Is there a lower bound on the per-band crest below which sustained material loses a perceptually meaningful property (expressiveness, movement, life)? Is it universal, band-dependent, or material-dependent? If there is no robust effect, the universal `F_b` should be removed.

**Q5 — integration.** Can the constraints be combined into one admissible set with a clear meaning, without adding up incommensurable quantities? The answer is yes only if each constraint is expressed in the same decision framework (a band-specific statistic, a criterion, an uncertainty, and a pass/fail/unknown rule).

The current meta answers none of Q1–Q4 with a measurement. The purpose of the experiments is to replace each constant with a measured value or to mark it as `UNKNOWN` and remove it from the universal set.

---

## 2. Hypotheses and falsification

### 2.1 Device

- **H1.0 (null).** For every band, device class and SPL in the sample, `PC_b(c) ≤ 2 dB` for all `c ≤ 21 dB`. If accepted, the device mechanism does not justify a finite `K_b` in the tested range.
- **H1.1.** `PC_b(c)` is monotone non-decreasing in `c` for the tested range. If rejected, the `sup {c : PC_b ≤ δ}` definition is not valid without a monotonicity qualification.
- **H1.2.** `K_b` depends on SPL; the 75 dB and 85 dB curves differ by more than the measurement uncertainty. If rejected, a single SPL reference is sufficient for the tested class.
- **H1.3.** `K_b` differs between bands by more than the uncertainty. If rejected, the per-band structure should be collapsed to fewer bands.
- **H1.4.** `K_b` differs between units of the same class by less than the between-class difference. If rejected, the class is not homogeneous; the meta needs a lower quantile or a per-unit calibration.

Falsification: a flat `PC_b(c)` curve, a non-monotone curve, CIs that overlap across bands/SPL/units, or a compression that is entirely explained by the measurement chain (mic/room) rather than the device.

### 2.2 Codec

- **H2.0 (null).** At the tested bitrates (≥ 96 kbps) and codecs, the codec artefact is below the detection threshold for input crest up to 21 dB. If accepted, the codec is not the binding constraint in these conditions.
- **H2.1.** The artefact increases with input crest and with lower bitrate. If rejected, the mechanism is not a simple crest effect.
- **H2.2.** The artefact is material-dependent; synthetic band noise is not a substitute for real programme. If rejected, the synthetic test generalizes (unlikely).

Falsification: a detectable artefact at a crest below the device `K_b`, or a residue that grows with crest in a way that contradicts the block-switching model. The current evidence supports H2.0 for AAC 96/128 and Opus 96 on synthetic noise; it does not test H2.2.

### 2.3 Perception

- **H3.0 (null).** The detection threshold for the device/codec degradation is above the degradation produced at the current `K_b`. If accepted, the current values are conservative with respect to audibility (not necessarily correct).
- **H3.1.** Detection and preference have different thresholds; a degradation can be detected without changing preference, and vice versa.
- **H3.2.** The threshold depends on SPL, band, duration and material.

Falsification: detection at a degradation below the measurement noise, or a preference effect without detection (possible, but then the mechanism is not the one being modelled).

### 2.4 Floor

- **H4.0 (null).** There is no universal lower bound on `C_b` that is preferred across materials, bands and listeners. If accepted, remove `F_b` from the universal meta.
- **H4.1.** A lower bound exists but is material- or band-specific. If accepted, `F_b` becomes a profile parameter, not a universal constant.
- **H4.2.** A universal lower bound exists. This is the only case in which the current `F_b` structure is justified; the values still have to be measured.

Falsification: no reliable preference/rating difference down to `C_b = 0` (a static band), or a difference that is entirely explained by loudness/spectrum rather than crest.

---

## 3. Common protocol

These rules apply to all experiments.

### 3.1 Pre-registration

Before collecting data, write and date:

- the hypotheses and the primary outcome;
- the sample size and the stopping rule;
- the randomization and blinding;
- the exclusion criteria;
- the statistical model and the multiple-comparison correction;
- the planned figures and tables.

The pre-registration is stored in the repository (e.g., `research/preregistration/`) and is not edited after the data are seen. Exploratory analyses are labelled as such.

### 3.2 Calibration and level matching

- SPL: IEC 61672-1 class 1 sound level meter, IEC 60942 class 1 calibrator; calibration before and after each session; report the weighting (Z/A/C) and the time constant (Fast/Slow/Leq).
- Microphone: class 1 measurement microphone with a calibration file; report the model/serial.
- Playback level: measured at the listening position or at 1 m on-axis; the distance and the room are part of the result.
- Loudness matching: for listening tests, match the integrated loudness (BS.1770-4) within 0.1 LU and the true peak within 0.1 dB; do not match only the RMS.
- Background noise: ≤ 25 dBA for loudspeaker tests; measure with the device off; report.
- Temperature/humidity: report; thermal compression depends on them.

### 3.3 Blinding and randomization

- The listener does not know the condition, the expected result, or the other listeners' responses.
- The operator who prepares the stimuli does not run the analysis; the analyst receives coded files and a separate key.
- The order of conditions is randomized per listener/session; the order is balanced across listeners (Latin square or full randomization).
- The device/unit order is randomized; the warm-up is identical for each unit.
- The analysis code is fixed before unblinding; the key is opened after the primary analysis is frozen.

### 3.4 Level matching and anchoring

- All stimuli in a comparison are matched in integrated loudness and true peak. If the experimental variable changes the loudness (e.g., crest), apply a gain to match; report the gain.
- Include a hidden reference and, for preference tests, an anchor (e.g., a clearly over-compressed version) to check scale use.
- Do not use the same file as both “reference” and “test” without a hidden duplicate; include a catch trial.

### 3.5 Data

- Keep the raw audio, the measurement JSON, the analysis scripts, the environment, and the calibration files.
- Check sums (SHA-256) for every source and stimulus.
- Never overwrite a result; write a new version with a timestamp and a commit hash.
- The research tools write JSON/CSV/figures, never audio. The production chain is a separate program; it is not used to create the research stimuli unless the experiment is explicitly about the chain.

---

## 4. Experiment A — device power compression and `K_b`

### 4.1 Design overview

A repeated-measures design with factors:

- **device class**: phone, laptop, BT speaker, earbuds, car, monitor/subwoofer (at least 3 units per class);
- **SPL**: 75 and 85 dB SPL (plus 65 dB as a low-level control);
- **band**: the ten meta bands (or a subset for the pilot);
- **crest**: 3, 6, 9, 12, 15, 18, 21 dB (finer steps around the expected transition);
- **repeat**: 3 runs per condition, randomized.

The primary outcome is `PC_b(c; SPL, unit)`, the power compression of the band. The secondary outcomes are THD/IMD, coherence, and the acoustic `C_b` of the output.

### 4.2 Device sample

For each class, record:

- make, model, firmware, serial number;
- amplifier/source, volume setting, any DSP/limiter mode;
- manufacturer's frequency range and maximum SPL;
- unit age/condition (a worn driver is not a new one).

At least 3 units per class is the minimum for a variance estimate; 5 is better. The units should be a convenience sample of the class, not selected to be good or bad. Report how they were obtained. If a class is represented by one unit, the result is a case study, not a class estimate.

### 4.3 Room and instrumentation

- Low-reverberation room (RT60 ≤ 0.3 s at mid frequencies) or a hemi-anechoic chamber. If neither is available, use a treated room and measure the room's transfer function; report the deviation from free field.
- Microphone at 1 m on-axis at the height of the intended listener; for a phone/laptop, the manufacturer's reference distance (often 0.5–1 m) and the typical listening position.
- Measure at 3–5 positions on a 1 m grid around the reference; report the mean and the spatial SD. A single position can sit in a room mode.
- Measurement chain: microphone → preamp → audio interface → 48 kHz/24-bit recorder. Measure the chain's noise floor and frequency response; calibrate with a pistonphone.
- Background noise: ≤ 25 dBA; the probe band's output should be ≥ 15 dB above the noise at the lowest level.

### 4.4 SPL reference

Define **two** levels for every condition:

1. **Overall programme SPL**: the Z-weighted (or A-weighted, stated) slow/Leq level of the whole stimulus at the reference position. This is the “75/85 dB SPL” of the meta.
2. **Band body SPL**: the level of the probe band's body alone, measured at the same position, with the bed off (or estimated from the transfer function). This is the level that determines the device's operating point in that band.

Do not report only one. A 75 dB SPL overall with a 95 dB SPL bass band is not the same as a 75 dB SPL bass band. The meta's `K_b` must state which level it refers to. The recommended primary reference is: **overall Z-weighted Leq = 75 or 85 dB SPL, with the probe band's body at the level it would have in a reference mix**. The reference mix must be defined (e.g., the band's share of the total power in the five-master corpus, or a flat 1/octave distribution). Report the band body SPL for every condition.

Calibration signal: pink noise or a 1 kHz sine at the reference position; measure with the SLM; set the gain; verify with a second signal. The SLM and the microphone should agree within 0.5 dB.

### 4.5 Stimulus

The stimulus must satisfy three requirements:

1. **The input `C_b` is known and equals the nominal crest.** Use the normative estimator (`METRIC_SPECIFICATION.md` §4) on the electrical stimulus; verify offline. A burst-to-body gain is not enough.
2. **The body is the body.** The body must occupy more than 75 % of the active frames, so P75 falls on the body, and the burst must occupy more than 0.5 % of the frames, so P99.5 sees it. A period of 10 s with 8 s body, 1 s burst, 1 s gap satisfies both (80 % body, 10 % burst).
3. **Only the crest changes.** The body level, the spectrum, the bed, the duration and the SPL reference are identical across crest conditions. The burst gain is the only variable.

Recommended construction:

- **Probe band**: band-limited noise with a flat spectrum within `[e_b, e_{b+1}]`, shaped by a raised-cosine at the edges (10 % of the band) to avoid clicks. The noise is frozen across crest conditions (same seed).
- **Body**: the probe noise at the body level, gated with 10 ms raised-cosine transitions; 8 s per 10 s period.
- **Burst**: the same noise at `body + c` dB, 1 s per period, with 10 ms raised-cosine edges.
- **Gap**: 1 s at −60 dB relative to the body (not digital silence, so the device/codec does not switch off).
- **Bed**: a low-level broadband programme-like noise (pink or a multiband sum) at a fixed level, present in all conditions. The bed keeps the device in a realistic operating point and masks the probe's edges. The bed's level is part of the reference; report it. For a pure band-isolation test, run a second condition without the bed and compare; the difference is the bed's effect.
- **Duration**: at least 30 s per condition (3 periods); 60 s is better. The first period is discarded (warm-up/limiter attack).
- **Level**: set the overall SPL to 75/85 dB with the body at the reference share; the burst raises the peak. Report the peak SPL and the overall Leq for each crest. If the peak exceeds the device's protection limit, stop; that is a result, not a reason to lower the body.

Why not a single-band sine? A sine has no crest distribution; the P75/P99.5 statistic is undefined in the same way, and the device's protection may respond to the sine's steady power rather than a musical crest. Band-limited noise with a controlled envelope is closer to the meta's statistic and to programme. A sine can be used as a secondary probe for THD and for the transfer function, not as the primary crest stimulus.

### 4.6 Procedure

1. **Warm-up**: 30 min at a low level (e.g., 65 dB SPL), then 5 min at the reference level. Measure the transfer function before and after; if it drifts by > 0.5 dB, extend the warm-up.
2. **Linear reference**: at each SPL, measure the probe band at a low crest (e.g., 3 dB) and at a low level; this is the `c = 0` reference for `PC_b`. The reference must be in the linear range; verify with a level sweep that the output/input ratio is constant within 0.2 dB.
3. **Crest sweep**: for each crest, randomize the order; play 3 periods; record the last 2. Wait at least 30 s between conditions for thermal/limiter recovery; if the device has a slow limiter, wait longer and verify the reference.
4. **Repeat**: 3 runs per condition; randomize the run order; measure the reference after each run.
5. **Distortion**: for each band/SPL, run a multitone or a stepped sine at the body level and at the burst level; measure THD/IMD and the harmonics. This is a separate measurement, not a by-product of the noise.
6. **Adjacent bands**: measure the bands on both sides of the probe with the same stimulus; a limiter or a port may redistribute energy.
7. **Coherence**: record the electrical input and the microphone output; compute the magnitude-squared coherence in the probe band. A drop below 0.9 (or the AES75 15 dB SNR criterion) indicates nonlinearity/noise; report.

### 4.7 Measurement and analysis

For each condition:

```
B_b^in(c)  = P75 of the input band envelope over the active frames
B_b^out(c) = P75 of the output band envelope over the active frames
PC_b(c)    = [B_b^out(c) − B_b^out(0)] − [B_b^in(c) − B_b^in(0)]
```

The output is the acoustic signal at the microphone; the input is the electrical stimulus. The microphone/room transfer function cancels in the difference if it is linear and stable; verify with the reference.

Distortion:

```
THD_b = 10 log10( Σ_{h≥2} P_h / P_1 )
IMD_b = 10 log10( Σ P_{intermod} / P_{carrier} )
```

Report the harmonics/intermodulation products; a single number can hide a narrow resonance. A device can compress without audible distortion (thermal) or distort without much compression (excursion); the criterion must include both.

`K_b`:

```
K_b(δ) = sup { c : PC_b(c) ≤ δ and D_b(c) ≤ δ_D }
```

where `D_b` is the distortion/coherence degradation and `δ_D` is a stated threshold. Start with `δ = 2 dB` (the AES75-2023 compression target) and `δ_D` = the coherence/THD limit; report `K_b(1)`, `K_b(2)`, `K_b(3)` and the perceptual `K_b` from Experiment C. If the set is not an interval, report the non-monotonicity and use the largest interval containing `c = 0`.

Uncertainty:

- repeatability: SD across the 3 runs per condition;
- spatial: SD across the 3–5 mic positions;
- between-unit: SD across the units of the class;
- calibration: the SLM/mic uncertainty (typically 0.3–0.5 dB);
- bootstrap or mixed-effects CI for `K_b`.

Class value: the 5th percentile of the unit-specific `K_b` (conservative), or the mean with the between-unit SD. Report both. A class with 3 units has a very uncertain 5th percentile; state that.

### 4.8 Controls and confounds

| confound | control |
|---|---|
| room modes | 3–5 mic positions; report spatial SD; low-reverberation room |
| thermal compression | 30 min warm-up; reference before/after; duty cycle; report time history |
| device limiter | long inter-stimulus interval; test 1/3/10 s periods; report attack/release |
| crossover/port | measure the transfer function; choose bands within a driver's passband; measure adjacent bands |
| nonlinear distortion | THD/IMD; coherence; report separately from compression |
| frequency-response change | measure the transfer function at each level; `PC_b` is a level change, not a shape change; report the shape change separately |
| microphone/room | calibration file; reference measurement; repeat with a second mic if possible |
| unit variance | ≥ 3 units; report between-unit SD |
| SPL calibration | class 1 SLM/calibrator; before/after; report weighting/time |
| background noise | ≤ 25 dBA; probe ≥ 15 dB above noise |
| stimulus order | randomized; balanced; reference after each run |
| experimenter bias | blind analysis; pre-registration |

### 4.9 Sample size

A pilot on one unit per class, 2 SPLs, 7 crests, 3 repeats (42 measurements per class) estimates the SD of `PC_b`. For the main experiment, the primary contrast is the difference between adjacent crests near `K_b`; to detect 1 dB with SD 1 dB, alpha 0.05, power 0.8, a paired design needs ~16 pairs. With 5 units × 3 repeats = 15 pairs, the design is marginal; 5 units × 5 repeats = 25 is safer. The total for 6 classes × 3 SPLs × 7 crests × 25 = 3150 measurements; at 1 min each plus waits, this is a multi-week experiment. A staged design is recommended: pilot (1 class), then 2 classes, then the rest; stop if the effect is clearly below the noise.

### 4.10 What would falsify the device story

- `PC_b(c)` is flat up to 21 dB for all units/bands: the device does not justify a finite `K_b` in the tested range.
- The compression is the same at 75 and 85 dB SPL: `K_b` is SPL-independent; the meta can use one reference.
- The CIs across bands overlap: the per-band structure is not supported; collapse the bands.
- The compression is explained by the measurement chain (mic/room) or by the stimulus's own spectrum: the experiment is invalid; fix the chain.
- The distortion threshold binds long before the compression threshold: `K_b` is distortion-limited, not compression-limited; the meta must use the distortion criterion.

---

## 5. Experiment B — codecs

### 5.1 Design

The current `pre_echo.py` is a probe, not a full experiment. Extend it:

- **Codecs**: AAC-LC, HE-AAC (if available), Opus, MP3, Vorbis; at least two encoder implementations where possible (ffmpeg native, FDK-AAC, Apple AAC).
- **Bitrates**: 32, 48, 64, 96, 128, 192, 256 kbps; mono and stereo; CBR/VBR as stated.
- **Material**: the five masters (excerpts, with permission), synthetic transients (click, burst, cymbal-like noise), band-limited noise, and a quiet-gap signal. At least 3 excerpts per material type.
- **Transient types**: 1 ms click, 10 ms burst, 50 ms burst, 200 ms burst; repeated and isolated; at different phases relative to the codec frame.
- **Measurements**: pre-echo residue in the quiet gap (power-averaged, 20 ms window), band dropout (output band energy vs input), spectral flux, envelope correlation, and a perceptual metric (PEAQ/ViSQOL) as secondary. A listening test (Experiment C) for the detection threshold.

### 5.2 Procedure

1. Generate the stimulus; measure its `C_b` with the normative estimator.
2. Encode/decode with each codec/bitrate/encoder; record the command and version.
3. Align the decoded signal to the input by cross-correlation of the envelope (not by the gap; matching the gap would cancel the residue).
4. Measure the residue in the 20 ms before the transient, in dB relative to the body and relative to the original gap.
5. Repeat across seeds (noise stimuli) and excerpts (real material); report the mean, SD and 95 % CI.
6. For the real material, use a quiet passage before a transient; if the material has no such passage, construct one by editing (with the edit documented) or use a synthetic probe.

### 5.3 Analysis

- `C_b^codec` = the largest input `C_b` at which the residue is below the detection threshold from Experiment C, for a given codec/bitrate/material.
- Do not use a fixed “30 dB below body” as the threshold; it is not an audibility threshold.
- Report the residue as a function of crest, bitrate, codec, encoder and material; use a mixed-effects model with material as a random effect.
- If the codec artefact is below the detection threshold at all tested crests, the codec does not bind; `K_b^codec = ∞` for that condition.
- If the codec drops the band (48/32 kbps), report it as a band-loss constraint, not a pre-echo constraint.

### 5.4 Limitations to state

The result is conditional on the codecs, bitrates, encoders and material tested. It must not be generalized to “all codecs” or “all streaming”. The encoder version matters; record it. The stereo masking and the bit reservoir of real music differ from synthetic noise; the real-material part is essential.

---

## 6. Experiment C — psychoacoustics

### 6.1 Two questions, two methods

**Detection**: can the listener hear that the test signal is degraded relative to the reference? This is a sensory threshold. Use a two-interval forced choice (2IFC) or ABX with an adaptive staircase; the threshold is the degradation at which the proportion correct is 75 % (or the adaptive convergence point).

**Preference**: which of two versions does the listener prefer? This is a judgment, not a threshold. Use a paired comparison or MUSHRA with a hidden reference and anchors. A preference result does not establish a physical boundary; it establishes a preference.

Do not use a preference test to set `K_b` and call it an audibility threshold. Do not use a detection test to set a profile and call it a preference.

### 6.2 Listeners

- 20–30 listeners for a general population; 8–12 experienced listeners for a pilot.
- Screening: audiometry (thresholds ≤ 20 dB HL at 0.25–8 kHz), no recent noise exposure, no hearing aids; report age range and experience.
- Sample size: power analysis for the primary outcome. For a 2IFC with 75 % threshold, 100 trials per listener gives a binomial SE of ~5 %; 20 listeners give a CI of ~2 %. For a paired preference with a 60/40 split, 20 listeners × 10 pairs = 200 judgments; the 95 % CI is ~±7 %. Pre-register the target.
- Compensation: follow the institution's policy; do not pressure.

### 6.3 Stimuli

- Device/codec outputs at the crest values around `K_b` and around the detection threshold; include the linear reference and a hidden duplicate.
- Level-match within 0.1 LU and 0.1 dBTP; the level matching must not undo the degradation (a compressor may change the loudness; use a gain, not a re-compression).
- Duration: 3–10 s per trial; longer for the device (the thermal/limiter effect needs time). Use a fade-in/out to avoid clicks.
- Playback: headphones (calibrated coupling) or loudspeakers (calibrated SPL at the listening position); report the model and the SPL. For a device experiment, the device itself is the playback; for a codec experiment, a neutral monitor/headphone is the playback.
- SPL: 75 dB SPL (the meta reference) and 85 dB SPL (the louder condition); measure at the ear/distance; do not exceed 85 dB SPL for long sessions; provide breaks.

### 6.4 Procedure

1. Training: 5–10 trials with feedback; the listener learns the task, not the conditions.
2. Detection: adaptive 2IFC/ABX; 3-down/1-up or 2-down/1-up; 50–100 trials; randomized order; no feedback after training.
3. Preference: paired comparison or MUSHRA; randomized; hidden reference; anchor; 3 repetitions per pair; no feedback.
4. Breaks every 15–20 min; total session ≤ 60 min; no listening when tired.
5. Catch trials: a hidden duplicate (should be judged “same”) and a clearly degraded anchor (should be judged “different”); exclude a listener whose catch-trial performance is at chance.

### 6.5 Analysis

- Detection: mixed-effects logistic regression with condition, SPL, band and material as fixed effects and listener as a random intercept; or the adaptive threshold per listener, then a mixed-effects model on the thresholds. Report the 75 % threshold and the 95 % CI.
- Preference: mixed-effects ordinal regression or a sign test; report the proportion of preference, the effect size, and the CI. Correct for multiple comparisons (Holm or FDR).
- Equivalence: for the floor, use an equivalence test, not a non-significant difference. Define the equivalence margin before the experiment (e.g., 55/45 preference, or 0.5 on a 7-point scale).
- Do not pool listeners with different hearing/experience without reporting; do not remove outliers without a pre-registered rule.

### 6.6 Controls

- Order/carryover: randomized, balanced; a washout between conditions.
- Fatigue: breaks; session length; time of day.
- Level: matched; measured; not adjusted by the listener.
- Room: quiet; report the noise floor; for loudspeakers, the room is part of the stimulus.
- Headphone coupling: the same model, the same fit; report.
- Expectation: blind; the listener is not told the hypothesis; the operator is blind to the condition code.
- Analysis: fixed before unblinding; the key is opened after the primary analysis is frozen.

---

## 7. Experiment D — is there a floor `F_b`?

### 7.1 What the floor would mean

The floor is a lower bound on the per-band crest. It is not a physical limit like excursion; it is a claim that below some crest the material loses a perceptual property (expressiveness, movement, life) or becomes indistinguishable from a static band. The current values `2.5 → 5.0 dB` are a craft judgment; the audit did not find an empirical basis, and the implementation does not enforce them.

The experiment must answer:

1. Is there a crest below which listeners reliably prefer the higher-crest version?
2. Is the effect band-dependent?
3. Is it material-dependent (tonal, noisy, dynamic)?
4. Is it explained by loudness/spectrum rather than crest?
5. Is the effect large enough to justify a universal constraint?

### 7.2 Stimuli

- Source: 3–5 sustained excerpts (the five masters or specially recorded material), 10–20 s, with a clear body in the band under test.
- Bands: low (60–120), mid (480–960), high (3840–7680); one band per stimulus, the others unchanged.
- Crest reduction: clamp the band's peaks with a smooth gain envelope to `C_b = 1, 2, 3, 4, 5, 6 dB`, measured with the normative estimator. Do not use a pump compressor; the body and the spectrum must stay constant. Verify: the body change ≤ 0.2 dB, the spectrum change ≤ 0.5 dB, the loudness matched within 0.1 LU.
- Include the original (unprocessed) as a hidden reference; include a clearly over-compressed anchor (e.g., `C_b = 0.5 dB`).
- Level-match all versions; the crest change may change the peak, so use a gain, not a limiter.

### 7.3 Task

- **Preference**: 2AFC between the original and each reduced version; randomized; 3 repetitions per pair.
- **Rating**: a 7-point scale for “movement/life” and “naturalness”, with operational definitions; the scale is anchored with examples; the listener is trained.
- **Detection**: optionally, can the listener hear that the band's crest was reduced? This separates “audible” from “preferred”.

### 7.4 Analysis

- For each band/material/crest, estimate the preference proportion and the mean rating with a 95 % CI.
- Fit a mixed-effects model with crest, band, material and their interactions; listener as a random effect.
- The candidate floor is the largest crest below which the preference/rating drops by more than the equivalence margin. Use equivalence testing: if the difference between `C_b = 2` and `C_b = 6` is within the margin, there is no evidence for a floor at 2; if it is outside, the floor is at or above 2.
- If the effect is material-specific, the universal `F_b` is rejected; the floor becomes a profile parameter with a range, or is removed.
- If no effect is found down to `C_b = 1`, remove `F_b` from the universal meta.

### 7.5 What not to do

- Do not set the stimuli to the current `F_b` values and ask “is this better?”; that would test the current values, not the existence of a floor.
- Do not use a preference test with a loudness difference; that would measure loudness, not crest.
- Do not average over materials if the interaction is significant; report the interaction.
- Do not call a non-significant result “no effect” without an equivalence test; the absence of evidence is not evidence of absence.

---

## 8. Experiment E — the mono/side criterion (recommended)

The `side = 0` rule is not implemented and is stronger than the physics. A short experiment can replace it:

- **Stimuli**: a sustained track with a controllable side signal below 150 Hz; vary `R_S` from 0 to −20 dB at 60/80/100/120/150 Hz; keep the mid and the overall spectrum/loudness constant.
- **Playback**: a single speaker (mono fold-down) and a stereo pair; the listener compares the full mix and the mono sum at matched loudness.
- **Task**: preference and “bass loss/phase” rating; detection of the mono fold-down.
- **Analysis**: the largest `R_S` that is not preferred less and not detected as a loss; report the band and the CI.
- **Outcome**: `f_m`, `X` (side attenuation) and `Y` (mono loss) for the meta, or a decision that exact zero is unnecessary.

This experiment is optional for the first phase but is needed before the side constraint can be called scientific.

---

## 9. Data management and reproducibility

- **Repository layout**: `research/experiments/<experiment>/` with `preregistration.md`, `stimuli/` (or a manifest with hashes), `raw/`, `analysis/`, `results/`, `README.md`.
- **Raw data**: keep the original recordings; do not overwrite; use read-only mounts for source material.
- **Metadata**: device serial, firmware, room, temperature/humidity, mic/calibrator, SPL meter, sample rate, bit depth, software versions, git commit.
- **Scripts**: one command reproduces each table/figure; the scripts are versioned; the random seeds are recorded.
- **Blinding key**: stored separately; opened only after the primary analysis is frozen.
- **Independent reproduction**: a second analyst re-runs the analysis from the raw data and the scripts; the results must match within the reported tolerance. If they do not, the difference is investigated before publication.

---

## 10. Validity criteria

| type | question | evidence |
|---|---|---|
| construct | does `PC_b` measure power compression, not a spectrum change? | transfer function at each level; `PC_b` vs shape change reported separately |
| construct | does `C_b^tail` capture the mechanism? | compare `C_b^tail`, `C_b^local`, `C_b^max`; if the mechanism is transient, the tail statistic is the wrong one |
| internal | are the conditions randomized and blinded? | pre-registration; randomization log; blind key |
| internal | is the level calibrated? | SLM/calibrator; before/after; report |
| internal | are the confounds controlled? | thermal, limiter, room, unit, mic; see A8 |
| external | can the result be generalized? | device sample, material sample, room; report the limits; no “all devices” claim |
| statistical | is the effect larger than the uncertainty? | CIs, mixed models, power analysis, multiple-comparison correction |
| reproducibility | can an independent researcher repeat it? | raw data, scripts, environment, hashes |

---

## 11. Success criteria

The programme succeeds if it produces:

1. a measured `K_b` for at least one device class, with a stated SPL, body level, criterion and uncertainty;
2. a measured SPL dependence (or a demonstration that it is below the uncertainty);
3. a separate codec contribution, with the codecs/bitrates/material stated;
4. a separate perceptual threshold (detection) and a preference result, not conflated;
5. a verdict on `F_b`: measured, material-specific, or removed from the universal meta;
6. an uncertainty for every number and a reproducible pipeline;
7. an independent reproduction of at least one result.

The programme fails if it produces a new set of numbers without a measurement, or if the numbers are tuned to the current values. The current values are the null hypothesis, not the target.

---

## 12. Where the current 2 dB criterion comes from, and why it is not enough

AES75-2023 (the standard behind M-Noise/Music-Noise) uses:

- a 2 dB compression target over at least two octaves, or 3 dB anywhere, plus
- a coherence reduction target (10 dB SNR, γ² ≤ 91 %),

to find the maximum linear SPL of a loudspeaker with a broadband Music-Noise stimulus. It is a **loudspeaker maximum-SPL** procedure, not a per-band crest experiment. The 2 dB is a stop condition chosen by the industry (Pat Brown proposed 3 dB; Meyer Sound uses 2 dB); it is not an audibility threshold.

For `K_b`, the 2 dB is a **starting engineering criterion**, not a standard. The experiment must:

- measure the compression curve, not just the stop condition;
- measure the perceptual threshold for the same compression;
- report `K_b(δ=2 dB)` and `K_b(δ=perceptual)`;
- state that the transfer from AES75 to `K_b` is an assumption until validated.

If the perceptual threshold is 1 dB in a band, the 2 dB criterion is too loose; if it is 3 dB, it is conservative. The meta should use the smaller of the two, with the uncertainty.

---

## 13. Timeline (indicative)

| phase | duration | output |
|---|---|---|
| pilot: 1 device class, 1 band, 3 crests, 3 repeats | 2–3 weeks | SD estimate, power analysis, protocol corrections |
| main device experiment: 3 classes × 3 units × 2 SPLs × 7 crests × 3 repeats | 6–10 weeks | `K_b` per class/SPL, CIs, between-unit SD |
| codec experiment: 5 codecs × 5 bitrates × 3 materials × 3 seeds | 3–4 weeks | codec residue curves, codec `K_b` or “does not bind” |
| perceptual experiment: detection + preference, 20–30 listeners | 4–6 weeks | detection threshold, preference, `ε` |
| floor experiment: 3 bands × 3 materials × 6 crests × 20 listeners | 3–5 weeks | `F_b` verdict |
| integration and independent reproduction | 3–4 weeks | meta object, validation report |

The timeline is indicative; the pilot may change it. The important rule is: no main experiment before the pilot has estimated the variance and the measurement chain is validated.

---

## 14. What the experiments must not do

- Do not use the current `K_b` as the expected answer.
- Do not stop the crest sweep when the expected value is reached; sweep beyond it.
- Do not average over bands/SPL/units before checking the interactions.
- Do not use a preference test as an audibility threshold.
- Do not use a synthetic signal as a substitute for real material without reporting it.
- Do not call a model a measurement; the device models in `devices.py` are not measurements.
- Do not call a measurement “inaudible” without a listening test.
- Do not delete or overwrite the source material or the raw data.
- Do not let the production chain “fix” the research stimuli; the research tools measure only.

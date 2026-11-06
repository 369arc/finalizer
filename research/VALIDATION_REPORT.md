# Validation report

**Repository:** `369arc/finalizer`  
**Commit:** `af04531`  
**Date:** 2026-11-06  
**Scope:** the existing regression suites, the new validation measurements performed for the audit, the defects they exposed, and the tests that must exist before the meta can be called a measurement system.

This report is not a certificate. It states what was tested, what passed, what failed, and what remains untested.

---

## 1. Test inventory

### 1.1 Existing suites

| suite | checks | what it covers | what it does not cover |
|---|---:|---|---|
| `tests/test_engine.py` | 10 | CLI commands run; `meta`, `analyse`, `check`, `compare`, `variants`, `master`; three profiles; 24-bit output; silence refused; broken JSON/missing file/unknown profile reported | any numerical correctness of a metric; crest values; LUFS/TP values; floor; side; `NaN`; codec |
| `tests/test_tui.py` | 14 | picker, profile stage, progress, delete/rename, state path, theme, key bindings | any DSP or meta measurement |

Result at `af04531`:

```
1..10   all engine tests passed
1..14   TUI checks passed
python3 -m py_compile finalizer/*.py run.py research/pre_echo.py   ok
```

The suites are smoke tests. They prove that the program does not crash on a 2 s 220 Hz sine, not that the numbers it prints are correct.

### 1.2 New validation measurements

These were performed read-only on the five finished masters and on synthetic signals. The methods are in `RESULTS.md` and `METRIC_SPECIFICATION.md`.

| # | check | result | status |
|---|---|---|---|
| V1 | gain invariance: `x` vs `2x` | B shifts `+6.0206 dB`, C changes `0.000000 dB` | **PASS** |
| V2 | integrated loudness vs `ffmpeg ebur128` | within `0.05 dB` on 1 kHz sine, T2, T4, two masters | **PASS** |
| V3 | true peak vs `ffmpeg` on real programme | within `0.03 dB` on T2/T4 and the masters | **PASS** |
| V4 | true peak vs `ffmpeg` on HF sines | code differs by `0.49–0.52 dB`; Annex 2 filter gives ~0.2 dB at 19 kHz, so the difference is meter-dependent | **METER DIFFERENCE** |
| V5 | crest gate on a 50 dB, 0.5 s burst | `band_crest = 0.38 dB`; 0.1–0.3 s bursts → `NaN` | **FAIL (critical)** |
| V6 | `NaN` decision | `check`/`master` treat `NaN` as `ok` | **FAIL (critical)** |
| V7 | floor `F_b` | `crest_min` is never read by a stage or a check | **FAIL (not implemented)** |
| V8 | side `= 0` below 120 Hz | 3rd-order high-pass: `−3.0 dB` at 120, `−18.1 dB` at 60 | **FAIL as stated** |
| V9 | body preservation under crest stage | `−2.09 dB` at 15–20 kHz on a 30 s excerpt; `< 0.6 dB` on full tracks | **PARTIAL** |
| V10 | B–C independence | pooled `r = −0.36`; per-band `−0.66 … +0.04` | **FAIL (“orthogonal”)** |
| V11 | window stability | 30–60 moves by `5.39 dB` (`T4`) between N=4096 and 16384; top band `3.38 dB` (`T2`) | **FAIL** |
| V12 | duration stability | 30 s vs full track moves by up to `8.73 dB` (`T5` 7680–15360); 30 vs 60 s is `9.07 dB` | **FAIL** |
| V13 | `check` completeness | no pass/fail for L, TP, side or floor; crest only | **FAIL** |
| V14 | `low` profile neutrality | default `deharsh` applies four notches on `T4`, incl. `−4.0 dB` at 1 kHz | **FAIL** |
| V15 | codec pre-echo | 27–38 dB below body up to 21 dB crest; codec does not bind in tested conditions | **PASS (limited)** |
| V16 | end-to-end master, T2/T4/T5 | crest 0 over, LUFS within 0.1, TP −1.00; contour changes 1.38/3.43/2.00 dB max | **PARTIAL** |

---

## 2. Detailed validation

### 2.1 Gain invariance (V1)

`B_b` and `C_b` are invariant to a constant gain in the precise sense:

```
B_b(2x) = B_b(x) + 20 log10(2) = B_b(x) + 6.0206 dB
C_b(2x) = C_b(x)
```

Measured on all five tracks: `max |ΔB − 6.0206| = 0.0206 dB` (the 0.0206 is the exact gain, not an error; `20 log10(2) = 6.0206`), `max |ΔC| = 0.000000 dB`.

This is the only “orthogonality” that survives. It is **gain invariance**, not statistical independence.

### 2.2 Loudness (V2)

The code’s `lufs_integrated` was compared with `ffmpeg 8.1.3 ebur128=peak=true` on:

- a 1 kHz sine at −3 dBFS (5 s);
- `T2` full (204 s);
- `T4` full (150 s);
- `T2` low master;
- `T4` low master.

Differences: `+0.007`, `−0.038`, `−0.013`, `−0.04`, `0.00 dB`. The BS.1770-4 gating is implemented correctly for 48 kHz stereo. The `sr` argument is ignored; the function is 48 kHz only. This is a latent API hazard, not a failure of the production path (which resamples to 48 kHz).

### 2.3 True peak (V3/V4)

On real programme:

| signal | code | ffmpeg | difference |
|---|---:|---:|---:|
| T2 full | 0.794 | 0.800 | −0.006 |
| T4 full | −4.172 | −4.200 | +0.028 |
| T2 low master | −1.000 | −1.000 | 0.000 |
| T4 low master | −1.000 | −1.000 | 0.000 |

On worst-case high-frequency signals:

| signal | code | ffmpeg | difference |
|---|---:|---:|---:|
| 19 kHz, 0 dBFS | 0.277 | 0.800 | −0.523 |
| 12 kHz, 0 dBFS | 0.006 | 0.500 | −0.494 |
| fs/4, 45° | 0.115 | 0.600 | −0.485 |

The code uses `resample_poly`, not the BS.1770-4 Annex 2 48-tap/4-phase FIR. On real music the difference is small; on synthetic HF content it is ~0.5 dB. The Annex 2 filter itself gives `0.20 dB` on the 19 kHz sine where ffmpeg gives `0.80 dB`, so the disagreement is between meters, not a simple error in the code. A master trimmed with the code’s meter can still read ~0.5 dB higher on a different meter, so the meter must be named and a tolerance used. The `−1 dBTP` target must name the meter and include a tolerance, or the code must implement the Annex 2 filter.

### 2.4 Crest gate (V5)

The most serious defect. Synthetic 30 s track:

- quiet 7680–15360 body at −30 dB relative to the bass;
- a burst at +50 dB relative to the body;
- body fraction 80 %, burst duration varied.

| burst | raw `P99.5 − P75` | `band_crest` |
|---:|---:|---:|
| 0.10 s | 29.8 | NaN |
| 0.25 s | 49.7 | NaN |
| 0.30 s | 49.8 | NaN |
| 0.50 s | 49.9 | 0.38 |

The max-based gate `e > e.max() − 45` excludes the body when the burst is more than 45 dB above it. `act` then contains only the burst, and `P99.5 − P75` inside the burst is ~0.4 dB. The `len(act) > 20` guard turns shorter bursts into `NaN`.

This is not an edge case of a single click; it is a sustained short event, which is exactly the codec/limiter case. The current estimator cannot certify that a band is inside the ceiling when such an event is present.

### 2.5 `NaN` decision (V6)

`run.py check`:

```python
bad = [(e, v, mx) for e, v, mx in zip(...)
       if not np.isnan(v) and v > mx + 0.35]
```

A `NaN` is skipped. `cmd_master`:

```python
ok = "ok" if (np.isnan(cre[i]) or cre[i] <= crest_max[i] + 0.35) else "OVER"
```

A `NaN` is `ok`. On `T1`, the top two bands are `NaN` and are reported as “no programme in source”; on `T5`, the top octave is `NaN`. A band that was not assessed is not a passing band. The decision must be three-valued: `PASS`, `FAIL`, `UNKNOWN`.

### 2.6 Floor (V7)

`grep -rn "crest_min"` returns only `meta.py` (definition, `NOTES`, `as_target`, `table`). No chain stage, no check, no report. The floor is displayed, not enforced. On the five masters, several values are below the floor (`T2` 30–60 1.60 < 2.5; `T4` 30–60 1.70 < 2.5; `T5` 960–1920 2.83 < 3.0). If the floor were a real constraint, these masters would fail; the tool does not tell the user.

### 2.7 Side/mono (V8)

`chain.stereo_width` applies `dsp.highpass(s, 120, order=3)`. Measured attenuation of a pure side tone:

```
30 Hz −36.0 dB
40 Hz −28.6 dB
60 Hz −18.1 dB
80 Hz −10.9 dB
100 Hz −6.0 dB
120 Hz −3.0 dB
160 Hz −0.7 dB
```

On the masters:

| track | side/mid 20–120 source | output | corr<100 |
|---|---:|---:|---:|
| T2 | −17.4 | −28.0 | 0.98 → 1.00 |
| T4 | −2.7 | −15.3 | 0.38 → 0.91 |

The output is more mono-compatible, but the claim “side = 0” is false. The 1 kHz `corr_low` is a proxy, not the side ratio; `check` does not report a side pass/fail.

### 2.8 Body preservation (V9)

The 30 s `T2` excerpt, one `crest_stage` call with a 6.2 dB ceiling:

```
B: 30–60 0.00, 60–120 0.00, 120–240 0.00, 240–480 −0.03,
   480–960 −0.03, 960–1920 −0.19, 1920–3840 −0.33,
   3840–7680 −0.60, 7680–15360 −2.02, 15360–20000 −2.09 dB
```

The body moves when the cut is deep. On full tracks the high-band body change was `< 0.6 dB`, but the low bands of `T4` and `T5` moved by `−1.3 … −1.8 dB`. The claim “P75 does not move by construction” is false; the correct claim is “P75 moves little for small cuts on stationary material”.

### 2.9 B–C dependence (V10)

Across 10 s segments of the five masters, the pooled Pearson correlation is `−0.36`; per band it ranges from `−0.66` (960–1920) to `+0.04` (7680–15360). This is a direct refutation of “orthogonal”. The negative sign is systematic; it is not a small-sample artefact of five tracks (the segments provide hundreds of pairs per band). A permutation test would be appropriate for a formal claim; the sign and magnitude are already enough to reject independence.

### 2.10 Window and duration (V11/V12)

Window: `T4` 30–60 moves `1.71 → 6.87 → 7.10` for N=4096/8192/16384; `T2` 15–20k moves `10.95 → 9.31 → 7.57`. The lowest band is not resolved at 4096; the top band is smeared at 16384.

Duration: `T2` 15–20k `16.08` at 30 s vs `10.95` full; `T5` 7680–15360 `3.93` at 30 s vs `12.66` full; `T4` 120–240 `4.96` at 30 s vs `7.98` full. A 30 s excerpt is not a short version of the track. The current tests use a 2 s file, where the tail statistic is even less meaningful.

### 2.11 `check` completeness (V13)

`check` prints:

```
LUFS ... TP ... corr<100Hz ...
device model shifts
over meta crest: ...
```

It does not print a pass/fail for `L`, `TP`, `side`, or `F_b`; it does not verify the meta’s `mono_below`; it uses the synthetic `devices.py` models as the translation verdict; it does not handle `NaN` as `UNKNOWN`. A user can read “worst balance shift: phone 3.1 dB (pass)” and “no over crest” and believe the master is inside the meta, while the floor/side/loudness/TP are unchecked.

### 2.12 `low` neutrality (V14)

`T4` with `--profile low` (default `deharsh=True`):

```
removed: 126Hz −3.2, 504Hz −3.8, 1008Hz −4.0, 1600Hz −1.5
contour preserved: max |d| 3.93 dB, rms 3.18 dB
```

With `--no-deharsh`:

```
contour preserved: max |d| 3.43 dB, rms 0.86 dB
```

The `low` profile is not neutral. The notch at the 1 kHz reference makes the relative contour report look like a 4 dB boost of everything else. The user’s profile comment “no colouring” is false.

### 2.13 Codec (V15)

The current `pre_echo.py` result is reproducible in the tested conditions: AAC 128/96 and Opus 96 add at most `+2.5 dB` to the quiet gap, and the residue remains `28–38 dB` below the body up to 21 dB crest; with a 0 dBFS bed, `+3.5 dB`, still `27 dB` below. At 48/32 kbps the band is dropped. The test is limited: synthetic mono noise, one encoder implementation, 50 ms bursts, no CIs, no real music, no listening test. The docstring’s “inaudible in any realistic playback” is not validated.

### 2.14 End-to-end (V16)

On `T2`, `T4`, `T5` full tracks, the `low` meta master reached `0` crest-over bands, LUFS within `0.1 LU` of `−14`, and `TP −1.00` (T5 `−3.58`, still inside). The contour changed by `1.38 / 3.43 / 2.00 dB` max (rms `0.46 / 0.86 / 0.64`) with `--no-deharsh`; with the default `deharsh`, `T4` changed by `3.93 dB` max. The outputs are inside the *current* crest ceilings on the *current* meter. This is a successful engineering result, not a validation of the ceilings: the ceilings were the target, and the meter has the gate defect.

---

## 3. Defect register

| id | severity | defect | evidence | fix |
|---|---|---|---|---|
| D1 | **critical** | `band_crest` max-based gate hides short/loud events; `len(act)>20` turns them into `NaN` | 50 dB burst → 0.38 dB / NaN | broadband activity mask; no max gate; minimum frames |
| D2 | **critical** | `NaN` treated as `PASS` in `check`/`master` | code inspection; T1/T5 top bands | three-valued decision |
| D3 | **critical** | `F_b` not implemented or checked | `crest_min` unused | implement a check or remove |
| D4 | **high** | `side = 0` is a 3rd-order high-pass | −3 dB at 120, −18 dB at 60; T4 −15.3 dB | replace with a measurable criterion |
| D5 | **high** | “orthogonal by construction” / “P75 does not move” | r = −0.36; ΔB up to −2.09 dB | correct the claims; redesign or document the actuator |
| D6 | **high** | `deharsh=True` default in meta mode; `low` not neutral | T4 4 notches incl. −4 dB at 1 kHz | disable in meta mode; fix the profile |
| D7 | **high** | `check` does not evaluate L/TP/side/floor | code inspection | evaluate all constraints |
| D8 | **high** | TP meter is not BS.1770-4 Annex 2 | 0.52 dB vs ffmpeg on HF sines | implement the Annex 2 filter or validate |
| D9 | **medium** | 30–60 Hz has 3 bins at N=4096; window sensitivity 5.4 dB | window table | multi-resolution or exclude |
| D10 | **medium** | B and C use different STFTs (4096/1024 vs 16384/4096) | contour difference up to 5.1 dB | one normative estimator |
| D11 | **medium** | duration dependence up to 9 dB; no minimum | duration table | ≥60 s; CI; UNKNOWN for short |
| D12 | **medium** | `CREST_MAX_CALIBRATED` dead duplicate | code inspection | remove |
| D13 | **medium** | `lufs_integrated` ignores `sr` | code inspection | resample/reject |
| D14 | **medium** | `pre_echo.py` docstring asserts the codec hypothesis and audibility; no JSON/CI | docstring; output | rewrite; add JSON/CI |
| D15 | **low** | stale comment “weight matrix extends the first band to DC” | `measure.py` | remove |
| D16 | **low** | README catalogue/ear/codec claims; “every streaming service −14” | README lines 124–169 | remove/replace |
| D17 | **low** | `profiles.toml` `low` comment “no colouring” | file | correct |
| D18 | **low** | research dependencies not declared | `requirements.txt` | add `requirements-research.txt` |

Severity: **critical** = a release decision can be wrong; **high** = a stated constraint is not implemented or a claim is false; **medium** = the number is estimator-dependent or the tooling is incomplete; **low** = documentation/hygiene.

---

## 4. Post-fix production validation

The audit above describes commit `af04531`. The production fixes were applied
after the research layer; the production metric version is now
`crest-v1.1-broadband-gate`. This section records what changed and what was
re-run. The audit documents remain the record of why the changes were needed.

| defect | change | evidence |
|---|---|---|
| D1 max-based gate | `band_crest` now uses a broadband 40 dB activity mask; `band_crest_legacy` keeps the old estimator for comparison | the 50 dB burst is `> 40 dB` in `tests/test_crest_gate.py`; the legacy estimator still gives 0.22/NaN |
| D2 `NaN` as pass | `band_crest_detail` returns `status`; `crest_report` is three-valued; `check`/`master` print `UNKNOWN` | `tests/test_floor.py`; `check` output on T2 |
| D3 floor | `crest_report` checks `F_b`; the chain clamps its target at the floor but does not add transients; a floor failure is `UNKNOWN` overall, not a PASS | `tests/test_floor.py`; T2 30–60 1.6 < 2.5 is shown as `FAIL`/`UNKNOWN` |
| D4 side | `measure.side_metrics` reports side/mid, mono loss and corr; `check`/`master` say `UNKNOWN` until the threshold is calibrated | `tests/test_side.py`; T2 output −27.9 dB, T4 −15.3 dB |
| D5 orthogonality | README/measure/chain comments corrected; the report says `contour change`, not “preserved” | audit text; T4 `max |d| 3.43 dB` with deharsh off |
| D6 `deharsh` | meta-only default is off; `low` sets `deharsh=false`; `mid`/`high` set true | profiles.toml; T4/T2/T5 `notches 0` with `low` |
| D7 `check` | evaluates L, TP, side, crest and floor; prints `release: PASS/FAIL/UNKNOWN` | `run.py check` output |
| D8 true peak | dual meter: BS.1770-4 Annex 2 and polyphase, conservatively maxed; report names both | `tests/test_lufs_tp.py`; 19 kHz: Annex2 0.20, poly 0.28 |
| D9 30–60 resolution | production still uses 4096/1024; the research metric uses multi-resolution; the README states the difference | `research/metrics.py`; v2 table |
| D12 duplicate | `CREST_MAX_CALIBRATED` removed | `meta.py` |
| D13 LUFS rate | `lufs_integrated` rejects non-48 kHz | `tests/test_lufs_tp.py` |
| D14 pre-echo claim | script docstring still needs the Phase 5 cleanup; the audit result is unchanged | — |

End-to-end `low` profile on the full tracks with the new gate (`deharsh` off):

| track | bands over | unknown | below floor | LUFS | TP | release |
|---|---:|---:|---:|---:|---:|---|
| T2 | 0 | 0 | 1 (30–60) | −13.94 (PASS) | −1.00 (PASS) | UNKNOWN |
| T4 | 0 | 0 | 0 | −14.00 (PASS) | −1.00 (PASS) | UNKNOWN (side) |
| T5 | 0 | 2 | 0 | −14.00 (PASS) | −3.58 (PASS) | UNKNOWN |

`T4` is crest/floor PASS; T2 is UNKNOWN because the provisional floor is not
met in 30–60 and the side threshold is not calibrated; T5 is UNKNOWN because
30–60 is 6.3 vs 6.2 (inside the 0.35 margin) and 960–1920 is 2.8 vs 3.0 (inside
the margin). None of the three is reported as a release PASS, which is the
correct result while the side threshold and the floor are uncalibrated.

The new broadband mask reduced the crest-stage body drop on the 30 s T2
excerpt from −2.09 to −1.85 dB at 15–20 kHz; it did not eliminate it. The
`P75` claim is now “approximately preserved for small cuts”, not “by
construction”.

The tests run after the fixes:

```
tests/test_metrics.py       10 passed
tests/test_experiments.py    5 passed
tests/test_crest_gate.py     3 passed
tests/test_floor.py          3 passed
tests/test_side.py           2 passed
tests/test_lufs_tp.py        3 passed
tests/test_engine.py        10 checks passed
tests/test_tui.py           14 checks passed
```

What is still open: the production 30–60 band is 4096/1024 (D9); the side
threshold is uncalibrated (D4); the floor is provisional (D3); the pre-echo
docstring and the codec/JSON/CI work are still due (D14); and the constants
`K_b`/`F_b` have not been recalibrated — they remain the hypothesis under test.
The production tool now reports this instead of hiding it.

---

## 5. Reproducibility

### 4.1 Existing tests

```
python3 tests/test_engine.py   -> 10/10 passed
python3 tests/test_tui.py      -> 14/14 passed
python3 -m py_compile finalizer/*.py run.py research/pre_echo.py -> ok
```

The tests use `tempfile.mkdtemp` and `XDG_STATE_HOME`; they do not touch the user's folders. They do not validate the metrics.

### 4.2 Audit measurements

- Source files: read-only; no writes to the author's source archive.
- Intermediate audio: `/tmp/opencode`; removed by the OS eventually.
- Environment: Python 3.14.10, numpy 2.4.2, scipy 1.18.0, soundfile 0.14.0, matplotlib 3.11.2, ffmpeg 8.1.3.
- Random seeds: `numpy.random.default_rng(100 + band_index)` for the codec noise; the bootstrap seeds are fixed per track; the synthetic burst uses `default_rng(2)`.
- The audit scripts are not yet in the repository. They will be moved to `research/audit/` with a JSON schema and a `README` in Phase 5. The tables in `RESULTS.md` can be regenerated from those scripts and the five source files.
- The five source files are not redistributed; a reader without them can reproduce the synthetic and codec tests, not the corpus tables.

### 4.3 Independent reproduction

Not yet performed. A second analyst should:

1. run `tests/test_engine.py` and the new `tests/test_metrics.py`;
2. re-measure the five tracks with the current `band_crest` and compare with `RESULTS.md` §3.1;
3. re-run the 50 dB burst test and confirm the 0.38/NaN behaviour;
4. compare LUFS/TP with `ffmpeg` on two files;
5. confirm the `side` attenuation at 60/120 Hz;
6. confirm `crest_min` is unused.

If any of these do not match, the difference must be explained before the audit is accepted.

---

## 6. Regression tests to add

| test file | assertions |
|---|---|
| `tests/test_metrics.py` | gain invariance; known crest; known side ratio; known LUFS/TP; `NaN` ≠ pass; short-event case; duration warning |
| `tests/test_crest_gate.py` | 50 dB burst → C ≈ 50, not 0.38; 0.1 s burst → status FAIL/UNKNOWN, not PASS |
| `tests/test_floor.py` | a signal below `F_b` → FAIL for the floor; a signal above → PASS |
| `tests/test_side.py` | `L=sin(60)`, `R=−L` → `R_S` equals the filter attenuation, not −∞; `L=R` → 0 dB mono loss |
| `tests/test_lufs_tp.py` | code vs ffmpeg within 0.1 LU / 0.1 dB on a real file; skip if ffmpeg absent |
| `tests/test_check_decisions.py` | `check` returns PASS/FAIL/UNKNOWN for all five constraints; no `NaN` pass |
| `tests/test_pre_echo.py` | tiny synthetic file; JSON schema; no input modification; ffmpeg version recorded |
| `tests/test_json_schema.py` | the reporting schema in `METRIC_SPECIFICATION.md` §11 is valid; no `NaN` in JSON |

The tests must use temp dirs and must not read the user's folders. They should be fast (< 60 s total), with an optional slow marker for the codec/ffmpeg tests.

---

## 7. Sign-off

**Validated:**

- the CLI and TUI run and write files;
- LUFS is BS.1770-4 conformant on the tested signals;
- true peak is close to `ffmpeg` on real programme;
- gain invariance of B and C;
- the codec probe is reproducible in its tested conditions;
- the end-to-end master reaches the current crest ceilings, LUFS and TP on `T2`/`T4`/`T5` with the current meter.

**Not validated:**

- the meta as a scientific admissible set;
- any `K_b` or `F_b` as a measured value;
- the crest estimator in the presence of short/loud events;
- the side/mono constraint as stated;
- the floor;
- the true-peak meter on worst-case signals;
- the perceptual audibility of the codec/device degradation;
- the claim that the corpus supports the current constants.

**Recommendation:** do not use `run.py check` as a release certificate until D1, D2, D3, D4, D7 and D8 are fixed. Do not present `K_b` as measured; present it with the audit status and the experiment that would replace it. The next step is the Phase 5 implementation of the corrected metrics and tests, followed by the experiments in `EXPERIMENT_DESIGN.md`.

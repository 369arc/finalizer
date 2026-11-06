# Preregistration template

Copy this file to `research/experiments/<experiment>/preregistration.md` and
fill it in **before** collecting data. Do not edit it after the data are seen;
add dated amendments instead.

## 1. Title and date

- title:
- date:
- experiment (A/B/C/D/E):
- responsible researcher(s):
- git commit of the analysis code:

## 2. Question and hypotheses

- primary question:
- H0:
- H1:
- direction (one- or two-sided):
- what would falsify H1:

## 3. Design

- factors and levels:
- within/between subjects or units:
- number of units/listeners:
- number of repetitions:
- randomization:
- blinding (who is blind to what):
- level matching (LUFS/dBTP/SPL):
- calibration (SLM, microphone, calibrator):
- room and playback:

## 4. Stimuli

- source material:
- bands:
- crest values:
- body level and SPL reference:
- duration and duty cycle:
- how the crest was measured (metric version):
- how the body/spectrum/loudness were held constant:
- hidden reference/anchor:

## 5. Primary and secondary outcomes

- primary:
- secondary:
- how each is measured (units, instrument, algorithm):
- minimum meaningful effect / equivalence margin:

## 6. Sample size and stopping

- pilot variance estimate:
- power analysis (alpha, power, effect size):
- planned n:
- stopping rule:
- what happens if the pilot variance is larger than expected:

## 7. Analysis

- model (e.g., mixed-effects `pc ~ crest * C(spl) + (1|unit)`):
- fixed/random effects:
- multiple-comparison correction:
- confidence intervals:
- missing data / exclusions:
- software and version:
- code path:

## 8. Exclusion criteria

- units:
- listeners:
- trials:
- pre-registered, not post hoc:

## 9. Data and reproducibility

- raw data location and hash:
- calibration files:
- scripts:
- who will reproduce the analysis:
- what will be published:

## 10. Deviations

Record every deviation from this plan with a date and a reason. A deviation is
not a failure; an unrecorded deviation is.

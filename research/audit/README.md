# Audit scripts

These scripts reproduce the measurements in `research/RESULTS.md` and the
figures in `research/figures/`. They are measurement-only: they read audio and
write JSON/PNG, never audio.

## Files

| file | purpose |
|---|---|
| `audit_crest.py` | v1 `measure.band_crest` vs the v2 reference (`research/metrics.py`); bootstrap, window/duration sensitivity; the 50 dB synthetic burst |
| `audit_relations.py` | B–C correlation over 10 s segments; crest-stage body change; side high-pass response |
| `make_figures.py` | plot the audit JSON, or fall back to `expected.json` |
| `expected.json` | the published v1 values, intervals, window/duration arrays and side response; used when the source audio is not available |

## Manifest

The audio is not redistributed. Create a manifest with the five finished
masters (or any files):

```json
{
  "T1": "/path/to/T1.wav",
  "T2": "/path/to/T2.wav",
  "T3": "/path/to/T3.wav",
  "T4": "/path/to/T4.wav",
  "T5": "/path/to/T5.wav"
}
```

The labels are anonymised; they are not the source file names. Keep the
manifest outside the repository.

All files must be 48 kHz stereo. The scripts do not modify them.

## Run

```bash
python3 research/audit/audit_crest.py --manifest tracks.json \
    --out research/audit/audit_crest.json

python3 research/audit/audit_relations.py --manifest tracks.json \
    --out research/audit/audit_relations.json

python3 research/audit/make_figures.py
```

`audit_crest.py --no-bootstrap` skips the 200-resample bootstrap (faster).
`audit_crest.py` also runs the synthetic burst test without a manifest, so it
can be used on a machine without the source masters:

```bash
python3 research/audit/audit_crest.py --no-bootstrap
```

## What the two estimators are

- **v1** is `finalizer.measure.band_crest_legacy`, the estimator at commit
  `af04531`: 4096/1024, a per-band `e > e.max() − 45` gate, and a
  `top − 45 dB` no-programme gate. It is the estimator behind the tables in
  `RESULTS.md` §3.1–3.8. The audit JSON also carries `v1_new`, the corrected
  broadband-gate estimator now used by the production tool.
- **v2** is `research/metrics.py`: multi-resolution bands (16384 for 30–60,
  8192 for 60–120, 4096 above), a broadband activity mask, and separate
  `C_tail`, `C_local`, `C_max` statistics. It is the proposed estimator; the
  current `K_b` was not calibrated on it.

The difference is not a bug fix that can be applied silently: the v2 low band
can move by several dB. The current constants are historical until a new
calibration is done.

## `expected.json`

`expected.json` is a fallback for the figures, not a substitute for the audio.
It contains the v1 table, the bootstrap intervals, the window and duration
arrays, and the side response published in `RESULTS.md`. The per-track
correlations in the fallback are the pooled per-band values, not the per-track
values; the note in the file says so. Regenerate the JSON from the manifest
for the real per-track data.

## What these scripts do not do

- They do not measure a device, a codec or a listener.
- They do not modify the source audio.
- They do not "fix" a master to the meta.
- They do not replace the experiments in `research/EXPERIMENT_DESIGN.md`.

## v1 against v2 (`compare_v1_v2.py`)

Runs the pre-audit tree (`af04531`, via `git archive`) and the current tree on
the same signals and files, judges all masters with one meter, runs the codec
probe with the corrected window, and writes `compare_v1_v2.json`. The report is
`research/V1_VS_V2.md`; every measured table there is backed by a key of the JSON.

```bash
python3 research/audit/compare_v1_v2.py --tracks T2=... T4=... T5=... \
  --render-tracks T2 T4 T5 --work /tmp/opencode/fin_compare \
  --out research/audit/compare_v1_v2.json
```

# Experiments: what is here and what is not

This directory contains the **measurement harness** for the protocols in
`research/EXPERIMENT_DESIGN.md`. It does not contain device or listener data;
those require a lab and participants.

## Files

| file | purpose |
|---|---|
| `stimuli.py` | generate a crest-controlled band stimulus (body/gap/burst) and verify its measured `C_tail`/`C_max` |
| `device_measure.py` | analyse aligned electrical input / acoustic output recordings, compute `PC_b(c)` and `K_b` |
| `analysis.py` | `K_b` from a compression curve, unit bootstrap, optional mixed-effects template |
| `preregistration_template.md` | fill this in before collecting data |

## 1. Generate a stimulus

```bash
python3 research/experiments/stimuli.py \
    --lo 3840 --hi 7680 --crest 9 --dur 60 \
    --out /tmp/probe_3840_7680_09.wav
```

The script prints the measured `C_tail` and `C_max` of the generated signal.
Check that `C_tail` is within ~1 dB of the nominal crest before using the
stimulus. The body is 80 % of the period, the burst 10 %, the gap 10 %; this
keeps P75 on the body and P99.5 on the burst.

## 2. Record the device

Follow `EXPERIMENT_DESIGN.md` §4: calibrate the SPL, warm up the device, play
the stimulus at the reference level, record the acoustic output at the
microphone, and keep the electrical input as the reference channel. Repeat for
each crest value and each unit.

## 3. Analyse one band

```bash
python3 research/experiments/device_measure.py --manifest run.json --out result.json
```

`run.json`:

```json
{
  "band_hz": [3840, 7680],
  "reference_crest": 3,
  "conditions": [
    {"crest": 3, "input": "in_03.wav", "output": "out_03.wav"},
    {"crest": 6, "input": "in_06.wav", "output": "out_06.wav"},
    {"crest": 9, "input": "in_09.wav", "output": "out_09.wav"}
  ]
}
```

The harness estimates a single delay between input and output, computes the
band body in both, and reports `PC_b` and `K_b` at the chosen `--delta`
(default 2 dB). It trims the longer file to the shorter one; record both with
the same duration.

The 2 dB is a **starting engineering criterion** (see `EXPERIMENT_DESIGN.md`
§12), not an audibility threshold. Report `K_b` for 1, 2 and 3 dB and compare
with the perceptual threshold from Experiment C.

## 4. What is not implemented

- The acoustic measurement itself: microphone calibration, room, SPL meter,
  device warm-up and the recording procedure. These are in the protocol, not
  in software.
- The listening experiments (Experiment C/D): presentation, blinding,
  loudness matching and statistics need a listener panel; the protocol is in
  `EXPERIMENT_DESIGN.md`.
- The codec experiment: `research/pre_echo.py` is the current probe; it needs
  the extensions described in `EXPERIMENT_DESIGN.md` §5 (real material,
  encoders, JSON/CI). This directory does not duplicate it.

## 5. Rules

- The harness measures; it never modifies the recordings or the source audio.
- Do not tune the stimulus or the analysis to a desired `K_b`.
- Record the environment, device serial, calibration file and git commit with
  every result.
- Pre-register before collecting data.

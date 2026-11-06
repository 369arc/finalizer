# FINALIZER

A final layer for sustained material: not matching someone else's record, but
fitting an **admissible region** — a meta.

The meta is a design of perception, not a measurement of taste. The current
values are **provisional model estimates**; the audit and the experiments that
would replace them are in `research/`. Nothing here is calibrated by ear, and
the old catalogue check is gone.

![Choosing a file](docs/picker.png)

The tree is always on screen and the button changes in place: `Master` →
`low / mid / high / all` → render → `Master` again, with the new file already
in the list.

![Choosing a profile](docs/profiles.png)

## Installation

The quick way:

```bash
curl -fsSL https://raw.githubusercontent.com/369arc/finalizer/main/install.sh | sh
```

It checks python3 (3.11+) and ffmpeg, creates a private environment in
`~/.local/share/finalizer`, downloads the application and puts the `finalizer`
command into `~/.local/bin`. Nothing is installed system-wide: everything lives
in one directory, and `install.sh --uninstall` removes it.

```bash
finalizer            # the interface
finalizer run ...    # the CLI, e.g. finalizer run master SRC.wav --out OUT.wav
finalizer update     # fetch the latest main
finalizer path       # where it is installed
```

The script is plain POSIX shell — read it before piping if you prefer
(`curl -fsSL ... | less`), then run `sh install.sh` from the checkout.

### By hand

Python 3.11+ and **ffmpeg**. ffmpeg is not used for processing, only for input:
anything that is not 48 kHz / stereo / float is converted once
(`finalizer/ingest.py`). Without ffmpeg the program still runs, but opens only
48 kHz stereo PCM — the status line says so at startup.

```bash
# Arch
sudo pacman -S ffmpeg python-numpy python-scipy python-soundfile
pip install --user textual

# Debian / Ubuntu
sudo apt install ffmpeg python3-numpy python3-scipy python3-soundfile
pip install --user textual

# Fedora
sudo dnf install ffmpeg python3-numpy python3-scipy python3-soundfile
pip install --user textual

# macOS
brew install ffmpeg
pip install --user -r requirements.txt textual

# Windows (PowerShell)
winget install --id Gyan.FFmpeg
py -m pip install -r requirements.txt textual
```

`soundfile` ships a binary wheel on every platform; on Windows it needs the
common Visual C++ runtime, which is usually already installed.

Check that everything is in place:

```bash
python3 -c "import numpy, scipy, soundfile, textual; print('ok')"
ffmpeg -version | head -1
```

## Running

```bash
python3 tui.py                      # minimal interface
python3 run.py master SRC --out OUT # or straight through the CLI
```

Checks after installation:

```bash
python3 tests/test_engine.py   # every command, every profile, edge cases
python3 tests/test_tui.py      # 14 interface steps, no terminal needed
```

Both tests work only in temporary directories and never touch your files.

## The working point

```bash
python3 run.py master SRC.wav --out OUT.wav
```

All three profiles sit on the crest boundary: `crest 1.0`, `bass 1.0`
(< 240 Hz). `mid` and `high` add `mid_guard 4.0` (240–4000 Hz); `low` is
neutral and has no automatic notches. They differ in density: `low` / `mid` /
`high` (see "Profiles"). The older, tighter `crest 0.8 / bass 0.7` can still be
requested on the command line. Without a profiles file the render is neutral.

```
run.py meta                      # what the meta is and where the numbers come from
run.py check  FILE...            # LUFS, TP, side, crest/floor and the synthetic device model
run.py analyse FILE...           # contour, width, resonances, crest
run.py variants SRC --out-dir D  # a grid of parameters for close calls
```

## What the meta is

The meta is not a point, not a reference and not a target curve. It is a
**boundary**: a set of admissible numbers, inside which the sound is yours. It
answers one question — can this be released — and says nothing about anything
else.

Four groups, and only these.

**1. Crest ceiling per octave.** The current values are **provisional model
estimates, not measurements**:

| band, Hz | ceiling | status |
|---|---|---|
| 30–1920 | 6.2 | **assumption** — no device or SPL measurement |
| 1920–3840 | 7.2 | **hypothesis** — no equation, no measurement |
| 3840–7680 | 8.3 | **hypothesis** — codec pre-echo present in a corrected probe (`research/V1_VS_V2.md` §6.9); audibility unknown |
| 7680–15360 | 8.0 | **unknown** — codec residue is codec-dependent in the corrected probe (AAC mostly with a bed, Opus without); audibility unknown |
| 15360–20000 | 10.3 | **hypothesis/unknown** — no measured limit |

The audit (`research/MASTERING_META_AUDIT.md`) found no device measurement and
no SPL calibration. The codec pre-echo rationale for the top bands was first
tested with a probe that had a window error and dB averaging; the first
negative result is **withdrawn**, and the corrected probe re-opens the question
(`research/V1_VS_V2.md` §6.9). The five finished masters used in
the audit (anonymised as `T1`–`T5`) do not reproduce the old catalogue medians
either. Treat the table as a starting point for the experiments, not as a norm.

**2. Crest floor.** 2.5 → 5.0 dB, a provisional craft judgment. The floor is
reported by `check` and by `master`; a floor failure is shown as `UNKNOWN`
overall, because the value is not calibrated and the chain does not add
transients to meet it. The experiment that would establish or reject a
universal floor is in `research/EXPERIMENT_DESIGN.md`.

**3. Delivery conventions.** `−14 LUFS` is a platform convention, not a
physical boundary — Spotify documents −14, Apple Music is commonly −16, Deezer
−15, and SoundCloud does not normalize. `−1 dBTP` is a headroom convention;
the meter is the larger of the BS.1770-4 Annex 2 filter and a polyphase 4×
meter, and the report names both. Tolerances: ±0.1 LU and +0.1 dB on the named
meter.

**4. Mono below 120 Hz.** The side channel is **high-passed**, not set to zero:
−3 dB at 120 Hz, −18 dB at 60 Hz. The report gives side/mid, mono loss and the
low-band correlation. The threshold for “good enough” is not calibrated yet;
`check` says `UNKNOWN` rather than inventing one. See
`research/METRIC_SPECIFICATION.md` §9.

**What the meta does not contain: a contour or a width profile.** Matching a
shape is a separate task and a separate flag (`--target`). One catalogue's
median as a norm would turn its habits into a law for everyone else, so those
fields simply do not exist here.

**Crest is a boundary, not a taste.** How close to sit to it is decided per
track: `--crest 0.85` sits 15% below the ceiling, `1.0` sits on it. A hard-coded
value would mean one track's taste became law for all; that is why it lives in
`profiles.toml`, not here.

**No catalogue and no ear in the rationale.** Earlier versions justified the
curve with a catalogue median and with listening. That is gone. The audit
measured five finished masters and did not reproduce the old medians; the
numbers above are assumptions until the experiments replace them. Listening is
still how a *profile* is chosen; it is not evidence for a boundary.

## Formal definition

Let `x(t)` be a stereo signal at 48 kHz, analysed by STFT (window 4096, hop
1024). Split it into octave bands with edges

```
E = {30, 60, 120, 240, 480, 960, 1920, 3840, 7680, 15360, 20000} Hz
```

For band `b`, let `E_b(n)` be the band power in frame `n`, in dB.

**Body** — the stable part of the envelope, over the broadband active frames:

```
B_b = P75(E_b),   E_b over frames where the programme is active
```

**Crest** — the tail above the body:

```
C_b = P99.5(E_b) − P75(E_b)
```

`B_b` and `C_b` are **gain-invariant**: a constant gain shifts `B_b` and leaves
`C_b` unchanged. They are **not statistically independent** — they are order
statistics of the same sample — and a deep or long crest cut can move `B_b`.
The audit measured both effects (`research/RESULTS.md`). The production
estimator uses a 4096/1024 STFT; the research reference uses a multi-resolution
band plan (`research/METRIC_SPECIFICATION.md`). The two are not interchangeable.

The production crest estimator uses a broadband activity mask. A band is
`UNKNOWN`, not a pass, when the file has too few active frames or the band is
below the noise floor. `NaN` is never reported as `ok`.

The contour report uses `sustain_contour` (16384/4096, P75, no activity mask).
It is a separate estimator and is not the body subtracted in the crest. The two
are reported separately; do not compare them as if they were the same number.

**The meta is an admissible set**, not a target curve. A master `y` is inside
it when

```
C_b(y) ≤ K_b                  for every assessed band b   crest ceiling
C_b(y) ≥ F_b                  for every assessed band b   provisional floor
|L(y) − L₀| ≤ 0.1 LU          L₀ = −14 LUFS               integrated loudness
TP_meas + u ≤ T₀              T₀ = −1 dBTP, u = meter uncertainty
R_S(f) ≤ X below f_m          f_m = 120 Hz                side/mid criterion
```

`L₀` and `T₀` are delivery conventions, not physical boundaries. `F_b` and
`X`/`f_m` are provisional; a failure/unknown is reported, not hidden. Nothing
else is regulated — in particular the contour `B_b` and the stereo width are
free.

### What each number is, and how solid it is

| quantity | value | status |
|---|---|---|
| `K_b`, 30–1920 Hz | 6.2 dB | **assumption** — no device/SPL measurement |
| `K_b`, 1920–3840 | 7.2 | **hypothesis** — no equation, no measurement |
| `K_b`, 3840–7680 | 8.3 | **hypothesis** — codec pre-echo present in the corrected probe; audibility unknown |
| `K_b`, 7680–15360 | 8.0 | **unknown** — codec residue is codec-dependent; audibility unknown |
| `K_b`, 15360–20000 | 10.3 | **hypothesis/unknown** |
| `F_b` | 2.5 → 5.0 | **assumption**; reported, not auto-enforced |
| `L₀` | −14 LUFS | delivery convention; platform targets differ |
| `T₀` | −1 dBTP | delivery convention; meter-dependent |
| `f_m` | 120 Hz | hypothesis; the side is high-passed, not zero |

### The open problem: `K_b`

The ceiling is the largest crest at which degradation on a device stays below
the audibility threshold:

```
K_b = sup { c : D_b(c) < ε }
```

Everything in the meta reduces to what `D_b` is taken to be:

- **dynamics** — power compression at a reference SPL;
- **codec** — pre-echo spread across the MDCT window;
- **perception** — preference in a blind comparison.

Each mechanism gives its own `K_b`; the meta should take the minimum.

The current constants are not a measured `D_b`: they are assumptions and
hypotheses. The codec probe does not settle the codec question; the device
experiment is the one that can.

### What measurement says so far

**Erratum.** The first probe (`research/pre_echo.py`) concluded that the codec
does not bind, with residues 27–38 dB below the body. That conclusion is
**withdrawn**: its gap window excluded the frame immediately before the onset,
where the pre-echo sits, and its dB averaging diluted a concentrated residue.

The corrected probe (`research/V1_VS_V2.md` §6.9; data in
`research/audit/compare_v1_v2.json`, key `codec`) runs AAC 128/96 and Opus 96
at a 21 dB crest. In the frame before the onset the decoded signal exceeds the
source gap by +3 to +37 dB in every configuration; for AAC 128 at 3.8–7.7 kHz it
reaches about +4 to +11 dB above the body level for ~2.7 ms. Audibility is not
measured. The codec question for the top bands is therefore open.

### The experiment that would close it

A reference SPL (75 and 85 dB), a signal with per-band controllable crest, and
per-band power compression measured on the device. AES75-2023 uses a 2 dB
compression target for a **broadband loudspeaker maximum-SPL** procedure; using
that number for a per-band crest is an assumption, not a standard. The
experiment measures the compression curve and the perceptual threshold and
reports both.

```
K_b(SPL) = sup { c : PC_b(c) ≤ δ }
```

with `δ` chosen from the engineering criterion and the listening experiment, not
borrowed. Then `K_b` becomes a measurement on a device class, and codec
behaviour and taste enter as separate terms instead of standing in for physics.

## Free contour — the main mode

Every track has its own frequency response; that is the artistic picture and it
must not be touched. So by default (`--meta meta`) the contour is **not fitted
at all**. Only what governs translation is regulated:

```
HPF → resonance suppression → width (mono low only)
    → per-band crest control → presence bell → loudness → limiter → trim
```

The key is that contour and crest are two statistics of the same envelope:

- band contour = `P75(E_b)` — the body, "where the band lives";
- band crest = `P99.5(E_b) − P75(E_b)` — the tail above the body.

They are **gain-invariant**, not statistically independent. Crest control cuts
the upper tail, which leaves `P75` almost unchanged for a small cut; a deep or
long cut can move it. The report says `contour change`, with the maximum and
RMS, not “preserved”. On the full tracks tested in the audit the change was
≤ 1.5 dB RMS with the notches off; the maximum was up to 3.4 dB in the low
bands. See `research/RESULTS.md`.

Shape fitting is switched on explicitly: `--fit-contour` (or `--target REF`,
where the reference is by definition the picture you asked for).

The order is chosen for cleanliness, not for effect:

- **contour EQ** (only with `--fit-contour`) — minimum-phase FIR. Linear phase
  gives pre-ringing: a click *before* the hit. For sustained material that is
poison.
- **resonances** are cut only in profiles that enable `deharsh`; `low` has it
  off. These are narrow peaks, not "brightness". The low end below 100 Hz is
  excluded — the edge of the spectrum is not a resonance.
- **width** is applied to the side channel with a minimum-phase FIR; below
  120 Hz the side is **high-passed** (−3 dB at 120, −18 dB at 60), not zero.
  The report gives side/mid and mono loss; the threshold is not calibrated.
- **crest control** is a band-wise gain with lookahead and release, not a
  static threshold: in a quiet section it does not invent a peak, in a loud one
  it does not pump. A deep cut can move `P75`; the report shows it.
- **the limiter** is a safety net, not a sound: 20 ms lookahead, 400 ms release.
  It engages when the loudness target requires it; "normally never" is not a
  guarantee.
- **true peak** is measured on both the BS.1770-4 Annex 2 filter and a
  polyphase 4× meter and trimmed to the larger. The two can differ by ~0.5 dB
  on high-frequency content; the report names them.

## The residual is the result

The tool does not pretend to converge. If a band hits `max_eq`, the report says
`LIMIT`; if the loudness is unreachable at the given ceiling, the difference is
shown. `feasible-band rms` is the contour error without the bands that are
physically unreachable.

The same with crest: cutting a peak "down to the sustain" (crest → 0) is a
square wave. The stage cuts the excess above `P75 + target`, but a deep cut can
move `P75`; the report shows the change.

The `OVER` line is not a report but an assignment. The tool measures crest after
processing, subtracts the excess from that band's threshold and runs again. It
is **not** guaranteed to preserve `P75`, and the target is clamped at the
provisional floor: if the floor and ceiling conflict, the band may remain over
the ceiling and the report says so. The stopping criterion is 0.1 dB for the
contour, 0.35 dB for the crest report.

## Profiles

The meta is the boundary, the profile is the pressure inside it. Taste lives in
`profiles.toml`, not in code and not in the meta:

```toml
default = "mid"

[low]        # no colouring, no automatic notches: crest stage and limiter only
[mid]        # a 1 kHz bell, +4.5 dB, Q 0.4 -- a fixed shape; notches on
[high]       # a one-pass projection toward a speech curve; notches on
```

```bash
python3 run.py master SRC --out OUT.wav
#   -> OUT_low.wav  OUT_mid.wav  OUT_high.wav  (every profile in the file)

python3 run.py master SRC --profile mid --out OUT.wav      # just one
python3 run.py master SRC --no-all-profiles --out OUT.wav  # only default
python3 run.py variants SRC --grid bass=0.5,0.7 --out-dir DIR
```

**`master` without `--profile` renders every profile in the file.** There are
three — `low`, `mid`, `high`. These are not three masterings but three pressures
inside one boundary. The ear decides on a given track; the tool ends with a
summary:

```
   profile  crest   kurt    LRA     TP  over  phone
       low  14.81   4.30   8.87  -3.11     0    5.2
       mid  15.17   4.37   8.78  -2.82     0    5.2
      high  15.98   4.49   9.76  -2.60     0    5.2
```

On dark material `high` lifts the air: on one dark piece +5.7 dB at 1 kHz
and **+13.2 dB at 10 kHz**. That is not a defect but a direct consequence of the track sitting
far below the speech curve up top. If the top is not wanted, take `mid`.

**`mid` versus `high`.** `mid` is a fixed bell: the same correction on any
material. `high` computes the correction **from the track itself**: it measures
the contour, subtracts the speech curve (LTASS) and applies the difference in one
pass (`--one-shot`), with a `max_eq` ceiling.

Single-pass is not an optimisation here but a condition: with iterations the loop
oscillates, and at full pull the result annihilates itself (on a bright, dense
piece +0.8 dB remained instead of +5.8).

Strength is governed by **`max_eq`, not `pull`**: the difference hits the ceiling
at both edges, the constant part is removed by normalisation, and what comes out
is the part that did not reach the ceiling. `max_eq 12` gives a +5.8 dB bell,
`max_eq 9` gives +3.3.

The numbers for `mid` came from `high`: the track was pulled, its response
measured, and the result reduced to a single filter — 0.44 dB rms across bands.

`crest` is peak/RMS of the whole wave, `kurt` is excess kurtosis, `over` is bands
above the meta, `phone` is the balance shift on a phone.

`--crest` scales the ceiling everywhere (control), `--bass` only below `bass_hz`
(the body). The profiles sit on the boundary itself (`1.0 / 1.0`): the three
pressures differ by colouring, not by how far below the ceiling they sit.
The default profiles now sit at the boundary. Any CLI flag overrides the
profile; an axis named in a `variants` grid replaces the profile value for that
axis only.

Important: this is a preference, not a law. The file is text and is edited for
the material — that is exactly how it should be used.

## Presence instead of saturation

For a long time it seemed that a track lacked density and that saturation was
the way to get it. What was audible turned out to be not distortion but a
**lift of the midrange**: harmonics of 300–600 Hz land exactly in 1–3 kHz, where
the ear reads body and presence. Saturation delivered that lift nonlinearly, so
it crackled, depended on the material and demanded a separate decision per track.

A bell does the same thing directly:

```toml
[mid]
eq_peak = [1000.0, 4.5, 0.4]   # +4.5 dB at 1 kHz, Q 0.4
```

One filter, linear, static. It generates no harmonics and does not touch the
meta boundary: a static equaliser changes a band's level, not its crest.

Important: the bell sits **after** the crest stage. Placed before it, it distorts
the crest measurement — in one run the 7.7–15 kHz band slipped out of control
because of it (12.4 against the current 8.0 ceiling).

Everything that was saturation — `--sat*`, `--wave-drive`, `--peak-drive`,
`--crest-until`, the `mid`/`high`/`push` profiles — is gone. The numbers for the
bell were obtained by pulling a track 35% toward the speech curve (LTASS),
measuring the resulting response and reducing it to one filter — 0.42 dB rms
across bands from the original result.

## Translation check

`check` runs the material through device models (phone, laptop, BT speaker,
earbuds, car cabin, mono) and reports two things:

- **shift** — how far the balance moved where the device still reproduces;
- **lost** — how many bands that carried energy disappeared.

A phone always loses the sub — that is physics. If a phone also *changes* the
midrange, that is a mastering defect.

## Research

The meta is under calibration, and the current numbers are labelled
**provisional**. The full audit and the experiment protocols are in `research/`:

- `MASTERING_META_AUDIT.md` — claim-by-claim status, the estimator gates, the
  side/floor gaps, and the required fixes;
- `METRIC_SPECIFICATION.md` — corrected definitions, units, activity mask,
  uncertainty and decision rules;
- `EXPERIMENT_DESIGN.md` — device power-compression, codec, blind listening and
  `F_b` protocols;
- `RESULTS.md` — what was actually measured on five finished masters and
  synthetic signals;
- `VALIDATION_REPORT.md` — reference comparisons, defects and regression tests.
- `V1_VS_V2.md` — technical comparison of the pre-audit and current sensor and chain, with the corrections found while doing it.

The research tools (`research/metrics.py`, `research/audit/`,
`research/experiments/`) measure only: they read audio and write JSON/CSV/PNG,
never a “corrected” master. The production chain is a separate program.

## Limitations

- **the meta is provisional.** The crest ceilings and the floor are assumptions
  or hypotheses; the audit found no device/SPL measurement and did not
  reproduce the codec rationale for the top bands. See `research/`;
- **the crest estimator is 4096/1024 and does not resolve 30–60 Hz well.** The
  research reference uses a multi-resolution band plan; the two estimators are
  not interchangeable;
- **the side constraint is a high-pass, not an exact zero.** The side/mid and
  mono-loss numbers are reported, but the threshold is not calibrated;
- **input is converted to 48 kHz / 2 channels / float32**. 16 and 24 bit are
  represented exactly in float32, so for them the conversion changes nothing;
  but 44.1 kHz with 48 kHz coefficients puts every crossover and every
  measurement 9% off. So anything that is not 48 kHz stereo is converted once
  by ffmpeg to `pcm_f32le` before it enters the chain (`finalizer/ingest.py`);
- **output depth is 24 bit** (`--bits 24|16|32f`). `sf.write` used to write
  PCM_16 silently — the WAV default in libsndfile. Noise floor: 16 bit −93 dBFS,
  24 bit −144 dBFS, so 24 bit is transparent while 16 bit leaves audible noise in
  quiet passages. 16 bit is written with TPDF dither: at that depth truncation is
  distortion, not noise;
- the contour is measured over the whole file: for compilations of dissimilar
  pieces the meta must be set per piece, not per album;
- device models are approximations (LR4 filters and shelves), not measurements of
  specific models;
- `master` holds the whole file in memory; hour-long pieces need ~2 GB.

## License

MIT — see `LICENSE`. It covers our code entirely.

**ffmpeg is neither shipped nor bundled.** It is called as an external program
(`ffmpeg` in `PATH`) and is needed only for input: anything that is not 48 kHz
stereo float is converted once. ffmpeg's own license (LGPL or GPL depending on
the build) belongs to your system, not to this repository — so MIT here mixes
with nothing.

`numpy`, `scipy`, `soundfile` and `textual` are likewise not shipped or bundled;
they are dependencies from `requirements.txt`, each under its own license.

### What the repository does not contain

- audio files or render results (`*.wav`, `out/`, `logs/`, `listen/`);
- test recordings or references taken from someone else's material;
- compiled binaries.

## Files

```
finalizer/meta.py      the meta numbers and their reasoning
finalizer/measure.py   contour, width, roughness, per-band crest
finalizer/devices.py   playback models and the translation metric
finalizer/chain.py     the chain and the outer iteration
finalizer/dsp.py       STFT, BS.1770, minimum-phase FIR, limiter
finalizer/ingest.py    input: any format -> 48 kHz / 2 ch / float32
run.py                 CLI
tui.py                 minimal interface (textual)
profiles.toml          taste: low / mid / high
references/            targets for --target-json
```

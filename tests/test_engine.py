"""Smoke tests for the engine: every command, every profile, the ugly inputs.

Run:  python3 tests/test_engine.py
Nothing here touches the user's folders: all files live in a temp directory.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
RUN = [sys.executable, str(ROOT / "run.py")]
D = Path(tempfile.mkdtemp(prefix="fin_engine_"))
T = np.arange(48000 * 2) / 48000
X = np.stack([0.2 * np.sin(2 * np.pi * 220 * T)] * 2, axis=1)
SRC = D / "a.wav"


def run(*args):
    return subprocess.run(RUN + [str(a) for a in args],
                          capture_output=True, text=True)


def main():
    sf.write(SRC, X, 48000, subtype="FLOAT")
    sf.write(D / "b.wav", X * 0.9, 48000)
    sf.write(D / "silence.wav", np.zeros((48000, 2), np.float32), 48000)

    r = run("meta")
    assert r.returncode == 0 and "ceiling" in r.stdout
    print("1. meta ok")

    for cmd in ("analyse", "check"):
        r = run(cmd, SRC)
        assert r.returncode == 0, r.stderr[-300:]
    print("2. analyse / check ok")

    r = run("compare", SRC, D / "b.wav")
    assert r.returncode == 0, r.stderr[-300:]
    print("3. compare ok")

    r = run("variants", SRC, "--grid", "crest=0.9", "--out-dir", D / "v")
    assert r.returncode == 0 and list((D / "v").glob("*.wav"))
    print("4. variants ok")

    for profile in ("low", "mid", "high"):
        out = D / f"{profile}.wav"
        r = run("master", SRC, "--profile", profile, "--out", out)
        assert r.returncode == 0, r.stderr[-400:]
        assert out.exists()
        info = sf.info(str(out))
        assert info.subtype == "PCM_24", info.subtype
        y, _ = sf.read(str(out), always_2d=True)
        lufs = float(np.mean(y ** 2))
        assert lufs > 0, "silent output"
    print("5. master low / mid / high ok, 24 bit")

    r = run("master", SRC, "--out", D / "all.wav")
    assert r.returncode == 0
    for name in ("all_low.wav", "all_mid.wav", "all_high.wav"):
        assert (D / name).exists(), name
    print("6. all profiles in one run ok")

    r = run("master", D / "silence.wav", "--out", D / "s.wav")
    assert r.returncode != 0 and "silent" in (r.stderr + r.stdout)
    print("7. silence is refused with a message")

    (D / "bad.json").write_text("{ not json")
    r = run("master", SRC, "--target-json", D / "bad.json", "--out", D / "x.wav")
    assert r.returncode != 0 and "not valid JSON" in (r.stderr + r.stdout)
    print("8. broken target json is reported, not traced")

    r = run("master", D / "nope.wav", "--out", D / "x.wav")
    assert r.returncode != 0 and "no such file" in (r.stderr + r.stdout)
    print("9. missing input is reported")

    r = run("master", SRC, "--profile", "nope", "--out", D / "x.wav")
    assert r.returncode != 0 and "no [nope]" in (r.stderr + r.stdout)
    print("10. unknown profile is reported")


if __name__ == "__main__":
    main()
    import shutil
    shutil.rmtree(D, ignore_errors=True)
    print("\nall engine tests passed")

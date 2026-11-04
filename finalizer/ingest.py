"""Bring any source to the chain's own format before it is touched.

The chain runs at 48 kHz stereo in float32. Two different things are at stake:

  * depth.  16 and 24 bit are exactly representable in float32 (the mantissa
            holds 2**24 steps), so reading them as float32 loses nothing --
            that conversion already happens and needs no external tool.
  * rate and channels.  These are not cosmetic. A 44.1 kHz file filtered with
            48 kHz coefficients gets every crossover, every notch and every
            measurement at the wrong frequency -- not by a little, by 9%.
            The same goes for a mono file whose side channel is assumed to
            exist.

So anything that is not already 48 kHz stereo float32 (or exactly-widened
16/24 bit) is converted once, by ffmpeg, into a temporary 32f WAV. The rest
of the program sees one format and stops guessing.
"""
import atexit
import os
import subprocess
import tempfile

import soundfile as sf

SR = 48000
# depths that float32 represents exactly: no conversion needed
EXACT = {"FLOAT", "PCM_16", "PCM_24"}


def _describe(info):
    return f"{info.samplerate} Hz, {info.channels} ch, {info.subtype}"


def ingest(path, tmpdir=None):
    """Return (path_to_use, temp_path_or_None).

    The temporary file is removed when the process exits, so a caller that
    fails halfway does not leave debris behind.
    """
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        raise SystemExit(f"no such file: {path}")
    info = sf.info(path)
    if (info.samplerate == SR and info.channels == 2
            and info.subtype in EXACT):
        return path, None

    tmpdir = tmpdir or None            # the system temp directory
    fd, out = tempfile.mkstemp(suffix=".wav", dir=tmpdir)
    os.close(fd)
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", path,
           "-c:a", "pcm_f32le", "-ar", str(SR), "-ac", "2", "-f", "wav", out]
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        os.unlink(out)
        raise SystemExit("ffmpeg not found: needed to convert "
                         f"{_describe(info)} to 48 kHz stereo float32")
    except subprocess.CalledProcessError:
        os.unlink(out)
        raise SystemExit(f"ffmpeg could not convert {path} ({_describe(info)})")
    atexit.register(lambda: os.path.exists(out) and os.unlink(out))
    print(f"  ingest: {_describe(info)} -> 48 kHz, 2 ch, FLOAT  ({os.path.basename(out)})")
    return out, out

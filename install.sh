#!/bin/sh
# FINALIZER installer.
#
#   curl -fsSL https://raw.githubusercontent.com/369arc/finalizer/main/install.sh | sh
#
# What it does:
#   1. checks python3 (>= 3.11) and ffmpeg
#   2. creates a venv and installs numpy, scipy, soundfile, textual into it
#   3. downloads the application into $PREFIX/app
#   4. writes a `finalizer` launcher into $BIN
#
# Nothing is installed system-wide. Everything lives in one directory:
#   $PREFIX          default ~/.local/share/finalizer
#   $PREFIX/venv     python environment
#   $PREFIX/app      the application
#   $BIN/finalizer   the command, default ~/.local/bin
#
# Options:
#   --prefix DIR     where to install          (default ~/.local/share/finalizer)
#   --bin DIR        where to put the command  (default ~/.local/bin)
#   --branch NAME    which branch to fetch     (default main)
#   --source PATH    install from a local directory, tarball or URL
#   --no-deps        skip the venv; use the system python3 as is
#   --no-ffmpeg      do not look for or install ffmpeg
#   --uninstall      remove $PREFIX and the launcher, then exit
#   -h, --help       this text
#
# Requires: python3. ffmpeg is optional: without it only 48 kHz stereo PCM
# opens (the interface says so at startup).

set -eu

REPO="369arc/finalizer"
BRANCH="main"
PREFIX="${FINALIZER_PREFIX:-$HOME/.local/share/finalizer}"
BIN="${FINALIZER_BIN:-$HOME/.local/bin}"
SOURCE=""
NO_DEPS=0
NO_FFMPEG=0
UNINSTALL=0

say()  { printf '  %s\n' "$*"; }
warn() { printf '  ! %s\n' "$*" >&2; }
die()  { printf '  x %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --prefix)   PREFIX="$2"; shift 2 ;;
        --bin)      BIN="$2"; shift 2 ;;
        --branch)   BRANCH="$2"; shift 2 ;;
        --source)   SOURCE="$2"; shift 2 ;;
        --no-deps)  NO_DEPS=1; shift ;;
        --no-ffmpeg) NO_FFMPEG=1; shift ;;
        --uninstall) UNINSTALL=1; shift ;;
        -h|--help)  sed -n '3,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)          die "unknown option: $1 (see --help)" ;;
    esac
done

# ---------------------------------------------------------------- uninstall
if [ "$UNINSTALL" = 1 ]; then
    rm -rf "$PREFIX"
    rm -f "$BIN/finalizer"
    say "removed $PREFIX and $BIN/finalizer"
    exit 0
fi

say "FINALIZER installer"

# ---------------------------------------------------------------- python
PY=""
FALLBACK=""
for cand in python3.13 python3.12 python3.11 python3; do
    command -v "$cand" >/dev/null 2>&1 || continue
    "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null || continue
    [ -n "$FALLBACK" ] || FALLBACK="$cand"
    # with --no-deps the interpreter must already have the libraries
    if [ "$NO_DEPS" = 1 ]; then
        "$cand" -c 'import numpy, scipy, soundfile' 2>/dev/null && { PY="$cand"; break; }
    else
        PY="$cand"; break
    fi
done
[ -n "$PY" ] || PY="$FALLBACK"
[ -n "$PY" ] || die "python 3.11+ not found. Install it first, then run this again."
say "python: $("$PY" --version 2>&1) ($PY)"

# ---------------------------------------------------------------- ffmpeg
if [ "$NO_FFMPEG" = 0 ]; then
    if command -v ffmpeg >/dev/null 2>&1; then
        say "ffmpeg: $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f1-3)"
    else
        warn "ffmpeg not found — only 48 kHz stereo PCM will open"
        if [ "$(uname -s)" = "Darwin" ]; then
            say "install it with:  brew install ffmpeg"
        elif command -v pacman >/dev/null 2>&1; then
            say "install it with:  sudo pacman -S ffmpeg"
        elif command -v apt-get >/dev/null 2>&1; then
            say "install it with:  sudo apt install ffmpeg"
        elif command -v dnf >/dev/null 2>&1; then
            say "install it with:  sudo dnf install ffmpeg"
        elif command -v zypper >/dev/null 2>&1; then
            say "install it with:  sudo zypper install ffmpeg"
        elif command -v apk >/dev/null 2>&1; then
            say "install it with:  sudo apk add ffmpeg"
        fi
    fi
fi

# ---------------------------------------------------------------- layout
mkdir -p "$PREFIX" "$BIN"
APP="$PREFIX/app"

fetch() {
    # $1 destination directory
    mkdir -p "$1"
    if [ -n "$SOURCE" ] && [ -d "$SOURCE" ]; then
        say "source: local directory $SOURCE"
        cp -R "$SOURCE"/. "$1"/
        rm -rf "$1/.git" "$1/__pycache__" "$1/finalizer/__pycache__"
    elif [ -n "$SOURCE" ] && [ -f "$SOURCE" ]; then
        say "source: local archive $SOURCE"
        tar -xzf "$SOURCE" -C "$1" --strip-components=1
    else
        URL="${SOURCE:-https://codeload.github.com/$REPO/tar.gz/refs/heads/$BRANCH}"
        say "source: $URL"
        command -v curl >/dev/null 2>&1 || die "curl not found"
        curl -fsSL "$URL" | tar -xz -C "$1" --strip-components=1
    fi
}

# remove the old code, keep the venv: an update must not re-download numpy
rm -rf "$APP"
fetch "$APP"
[ -f "$APP/run.py" ] || die "download looks broken: no run.py in $APP"

# ---------------------------------------------------------------- deps
if [ "$NO_DEPS" = 1 ]; then
    say "deps: skipped (--no-deps), the launcher will use $PY"
    RUNTIME="$PY"
else
    VENV="$PREFIX/venv"
    if [ ! -x "$VENV/bin/python" ]; then
        say "creating venv in $VENV"
        "$PY" -m venv "$VENV" || die \
            "could not create a venv. On Debian/Ubuntu install python3-venv first."
    fi
    say "installing dependencies"
    "$VENV/bin/python" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
    "$VENV/bin/python" -m pip install --quiet -r "$APP/requirements.txt" || \
        die "pip could not install the dependencies (no network?)"
    RUNTIME="$VENV/bin/python"
fi

"$RUNTIME" -c 'import numpy, scipy, soundfile' 2>/dev/null || \
    die "dependencies are not importable with $RUNTIME"

# ---------------------------------------------------------------- launcher
cat > "$BIN/finalizer" <<LAUNCH
#!/bin/sh
# generated by FINALIZER install.sh
APP="$APP"
PY="$RUNTIME"
case "\${1:-}" in
    run) shift; exec "\$PY" "\$APP/run.py" "\$@" ;;
    update) shift; exec sh -c "\$(command -v curl) -fsSL https://raw.githubusercontent.com/$REPO/main/install.sh | sh -s -- --prefix '$PREFIX' --bin '$BIN'" ;;
    path) echo "\$APP" ;;
    *) exec "\$PY" "\$APP/tui.py" "\$@" ;;
esac
LAUNCH
chmod +x "$BIN/finalizer"
say "command: $BIN/finalizer"

case ":$PATH:" in
    *":$BIN:"*) ;;
    *) warn "$BIN is not in PATH. Add it:  export PATH=\"$BIN:\$PATH\"" ;;
esac

# ---------------------------------------------------------------- self check
"$RUNTIME" -c "import sys; sys.path.insert(0, '$APP'); import finalizer.meta; print('  ready: meta', finalizer.meta.LUFS, 'LUFS')" \
    || die "the application did not start"

say ""
say "done.  run:  finalizer"
say "       cli:  finalizer run master SRC.wav --out OUT.wav"

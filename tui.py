"""Minimal TUI for FINALIZER: one window, one button that changes shape.

    tree is always on screen
    ┌──────────────────────────────────────────────┐
    │  ▾ FILES                                     │
    │    ▾ ALBUM                                   │
    │      ● track.wav                             │
    │                                              │
    │              [ Master ]                      │
    └──────────────────────────────────────────────┘

Press Master (or Enter on a file): the same button becomes
    [ low ]  [ mid ]  [ high ]
in the same place. Pick one -- it becomes a spinner -- and when the render is
finished the row is [ Master ] again and the new file is already in the tree.

No second screen, no second menu, no Open/Back buttons: `o` opens whatever is
selected in the tree in the system player, `esc` goes back to picking.

The TUI does no audio work itself: it calls `run.py master --profile`, so the
chain, the profiles and the format handling stay in one place.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from rich.style import Style
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import (Button, DirectoryTree, Footer, Input,
                             LoadingIndicator, OptionList, Static)
from textual.widgets.option_list import Option

# Colour is rank, not decoration. The scale runs from the absolute that must
# recede to the surface that must come forward:
#
#   0  black    #000000  the meta. Background only -- never text, never a mark
#   1  surface  #0d0d0d  lifted black: panels that must be seen as panels
#   2  purple   #b89ae8  interactive surfaces: buttons, anything you press
#   3  berry    #d6336c  attention: focus, error, the one active thing
#   4  gold     #f0c674  structure: folders, the map of where you are
#   5  white    #d0d0d0  text. Maximum contrast, therefore reserved for words
#
# Two rules follow. First: structure (gold) never competes with attention
# (berry) -- a folder is not an action. Second: black is the background and, by
# inversion, the text on a filled control; both are the same rank seen from
# opposite sides, and on a light purple chip black is what stays legible.
PALETTE = {
    "black": "#000000",
    "surface": "#0d0d0d",
    "panel": "#1a1a1a",
    "purple": "#b89ae8",
    "blue": "#3fa9ff",
    "berry": "#d6336c",
    "berry_light": "#ff5c8a",
    "gold": "#f0c674",
    "white": "#d0d0d0",
    "teal": "#b8e3ea",
}

DIR_COLOR = PALETTE["gold"]

PROFILES = ("low", "mid", "high")
CHOICES = PROFILES + ("all",)      # "all" renders every profile at once

# The terminal's own palette (Ghostty "369arc"): berry on pure black.
THEME_369ARC = Theme(
    name="369arc",
    primary=PALETTE["berry"],        # attention
    secondary=PALETTE["purple"],     # interactive
    accent=PALETTE["gold"],          # structure
    foreground=PALETTE["white"],     # text
    background=PALETTE["black"],     # the meta
    surface=PALETTE["surface"],
    panel=PALETTE["panel"],
    success=PALETTE["teal"],
    warning=PALETTE["gold"],
    error=PALETTE["berry_light"],
    dark=True,
    variables={"icon-folder": PALETTE["gold"]},
)


def _state_dir() -> Path:
    """Where a desktop puts an app's state on this platform."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA")
                    or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_STATE_HOME")
                    or Path.home() / ".local" / "state")
    return base / "finalizer"


def _state_file() -> Path:
    return _state_dir() / "tui.json"


def load_state() -> dict:
    try:
        return json.loads(_state_file().read_text())
    except Exception:                      # no file, no permission, bad json
        return {}


def save_state(state: dict) -> None:
    try:
        p = _state_file()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, indent=1))
    except Exception:
        pass                               # never fail a render over this


# everything libsndfile/ffmpeg will take as audio; the tree shows nothing else
AUDIO_EXT = {
    ".wav", ".wave", ".w64", ".rf64", ".flac", ".mp3", ".mp2", ".m4a", ".aac",
    ".alac", ".ogg", ".oga", ".opus", ".aif", ".aiff", ".aifc", ".wma", ".ape",
    ".wv", ".dsf", ".dff", ".caf", ".au", ".snd", ".ac3", ".mka",
}
# The TUI never reads text, so the keyboard layout must not matter: every
# printable key is translated back to its US position before it is matched.
# The mapping below covers the Cyrillic keyboard layout; other layouts leave
# ASCII alone, and special keys (arrows, enter, space) are layout-independent
# by definition. The Cyrillic keys are written as Unicode escapes so the
# source stays ASCII.
_LAYOUT = {
    "\u0439": "q", "\u0446": "w", "\u0443": "e", "\u043a": "r", "\u0435": "t", "\u043d": "y", "\u0433": "u",
    "\u0448": "i", "\u0449": "o", "\u0437": "p", "\u0445": "[", "\u044a": "]",
    "\u0444": "a", "\u044b": "s", "\u0432": "d", "\u0430": "f", "\u043f": "g", "\u0440": "h", "\u043e": "j",
    "\u043b": "k", "\u0434": "l", "\u0436": ";", "\u044d": "'",
    "\u044f": "z", "\u0447": "x", "\u0441": "c", "\u043c": "v", "\u0438": "b", "\u0442": "n", "\u044c": "m",
    "\u0431": ",", "\u044e": ".", "\u0451": "`",
}

RUNPY = Path(__file__).resolve().parent / "run.py"
HAS_FFMPEG = shutil.which("ffmpeg") is not None
# first run (no saved dir yet): the home folder -- nothing to assume about
# someone else's layout. After the first master the state remembers where.
START_DIR = Path.home()


def out_path(src: Path, profile: str) -> Path:
    return src.with_name(f"{src.stem}_{profile}.wav")


def expected(src: Path, choice: str) -> list[Path]:
    if choice == "all":
        return [out_path(src, p) for p in PROFILES]
    return [out_path(src, choice)]


_SUBTYPE = {
    "PCM_S8": "8 int", "PCM_16": "16 int", "PCM_24": "24 int",
    "PCM_32": "32 int", "FLOAT": "32 float", "DOUBLE": "64 float",
    "ALAC_16": "16 alac", "ALAC_24": "24 alac",
    "MPEG_LAYER_III": "lossy", "MPEG_LAYER_II": "lossy",
    "VORBIS": "lossy", "OPUS": "lossy", "MP3": "lossy",
}


def file_info(path: Path) -> str:
    """format · bit depth · sample rate · hh:mm:ss, or an honest failure."""
    try:
        import soundfile as sf
        i = sf.info(str(path))
        bits = _SUBTYPE.get(i.subtype, i.subtype.lower())
        secs = i.frames / i.samplerate if i.samplerate else 0.0
        h, m, s = int(secs // 3600), int(secs % 3600 // 60), int(secs % 60)
        return (f"{i.format} · {bits} · {i.samplerate} Hz · "
                f"{h:02d}:{m:02d}:{s:02d}")
    except Exception:
        pass
    try:                                   # formats libsndfile will not open
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "format=format_name,duration:"
                              "stream=sample_rate,sample_fmt,bits_per_raw_sample",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=10)
        d = json.loads(r.stdout or "{}")
        st = (d.get("streams") or [{}])[0]
        fmt = (d.get("format") or {}).get("format_name", "?")
        secs = float((d.get("format") or {}).get("duration") or 0)
        h, m, s = int(secs // 3600), int(secs % 3600 // 60), int(secs % 60)
        bits = st.get("bits_per_raw_sample") or st.get("sample_fmt") or "?"
        return (f"{fmt} · {bits} · {st.get('sample_rate', '?')} Hz · "
                f"{h:02d}:{m:02d}:{s:02d}")
    except Exception as e:  # noqa: BLE001
        return f"{path.name}: {e}"


def build_cmd(src: Path, choice: str, out: Path) -> list[str]:
    if choice == "all":
        # no --profile: run.py renders every profile in profiles.toml and
        # derives its names from --out, so pass the stem without extension
        return [sys.executable, str(RUNPY), "master", str(src),
                "--out", str(src.with_suffix(""))]
    return [sys.executable, str(RUNPY), "master", str(src),
            "--profile", choice, "--out", str(out)]


class Picker(DirectoryTree):
    """DirectoryTree with space-marking, like a file manager."""

    # glyphs that exist in ordinary monospace fonts (Geist Mono, DejaVu):
    # "▸" is missing from Geist and would show as a box in the terminal
    ICON_FOLDER = "› "
    ICON_FILE = "· "

    BINDINGS = [
        Binding("space", "mark", "mark", show=True),
        Binding("left", "up_level", "back", show=False),
        Binding("right", "enter_node", "forward", show=False),
    ]

    def __init__(self, path: str, **kw):
        super().__init__(path, **kw)
        self.marked: list[Path] = []

    def action_up_level(self) -> None:
        """left: collapse the open folder, otherwise go one level up."""
        node = self.cursor_node
        if (node is not None and node is not self.root
                and getattr(node, "allow_expand", False) and node.is_expanded):
            node.collapse()
            return
        here = Path(self.path)
        parent = here.parent
        if parent != here and parent.is_dir():
            self.path = str(parent)
            self.reload()

    def _populate_node(self, node, content):
        """One level only: a directory is a door, not a branch.

        Without this the tree grows in place as you descend; with it the list
        always shows exactly the current folder, and right/enter walk into a
        folder by re-rooting instead of unfolding it.
        """
        content = list(content)
        super()._populate_node(node, content)
        for child in node.children:
            child.allow_expand = False

    def _is_dir_node(self, node) -> bool:
        if node is self.root:
            return True
        path = getattr(getattr(node, "data", None), "path", None)
        return path is not None and Path(path).is_dir()

    def render_label(self, node, base_style, style) -> Text:
        """Own icons: the folder glyph is gold, the file glyph is quiet.

        The stock renderer picks the icon from `allow_expand`, and every node
        here is non-expandable (one level only), so it would draw folders with
        a file icon.
        """
        label = node._label.copy()
        label.stylize(style)
        if not self.is_mounted:
            return label
        # assemble, not `head + label`: concatenation carries the head's style
        # as the base style of the whole line, and the folder name came out
        # gold with it
        if self._is_dir_node(node):
            icon = (self.ICON_FOLDER, Style(color=DIR_COLOR, bold=True))
        else:
            icon = (self.ICON_FILE, Style(dim=True))
        return Text.assemble(icon, label)

    def _enter(self, path: Path) -> None:
        self.marked.clear()
        self.path = str(path)
        self.reload()

    def action_enter_node(self) -> None:
        """right: walk into the folder under the cursor."""
        node = self.cursor_node
        path = getattr(getattr(node, "data", None), "path", None)
        if path is not None and Path(path).is_dir():
            self._enter(Path(path))

    def action_select_cursor(self) -> None:
        """enter on a folder walks in; enter on a file selects it."""
        node = self.cursor_node
        path = getattr(getattr(node, "data", None), "path", None)
        if path is not None and Path(path).is_dir():
            self._enter(Path(path))
            return
        super().action_select_cursor()

    def filter_paths(self, paths):
        """Directories stay, files only if they are audio."""
        return [p for p in paths
                if p.is_dir() or p.suffix.lower() in AUDIO_EXT]

    def action_mark(self) -> None:
        node = self.cursor_node
        data = getattr(node, "data", None) if node else None
        path = getattr(data, "path", None)
        if path is None or Path(path).is_dir():
            return
        p = Path(path)
        if p in self.marked:
            self.marked.remove(p)
            node.label = p.name
        else:
            self.marked.append(p)
            node.label = f"● {p.name}"


class ThemeScreen(ModalScreen[str | None]):
    """Theme list with a live preview: the app changes as you move."""

    CSS = """
    /* the app stays visible: no dim layer, the panel floats to the right,
       away from the tree, so the choice is made against the real picture */
    ThemeScreen { align: right middle; background: transparent; }
    #themes { width: 40; height: 80%; margin-right: 2;
              border: tall $primary; background: $surface; padding: 0 1; }
    """

    BINDINGS = [Binding("escape", "cancel", "cancel", show=False)]

    def compose(self) -> ComposeResult:
        # no wrapper container: the screen aligns the list itself, and a
        # full-size wrapper would eat the alignment
        self._list = OptionList(
            *[Option(name, id=name)
              for name in sorted(self.app.available_themes)],
            id="themes",
        )
        yield self._list

    def on_mount(self) -> None:
        names = [o.id for o in self._list.options]
        if self.app.theme in names:
            self._list.highlighted = names.index(self.app.theme)
        self._list.focus()

    def on_option_list_option_highlighted(
            self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id:
            self.app.theme = event.option.id          # preview, not commit

    def on_option_list_option_selected(
            self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def action_cancel(self) -> None:
        self.dismiss(None)


KEYS_TEXT = """\
  ↑ ↓        navigate
  ← →        out / into a folder, between buttons
  space      mark a file
  enter      proceed
  m          master (marked or cursor file)
  1 2 3 4    low  mid  high  all
  o          open the selected file
  d          delete the selected file (y / n)
  r          rename the selected file
  i          info: format · bit depth · rate · length
  t          theme
  k          this list
  q          quit
"""


class RenameScreen(ModalScreen[str | None]):
    """One text field. The only place in the TUI that reads typing."""

    CSS = """
    RenameScreen { align: center middle; background: $background 50%; }
    #box { width: 60; height: auto; padding: 1 2;
           border: tall #f0c674; background: $surface; }
    #name { width: 100%; }
    #note { color: $text-muted; padding-top: 1; }
    """

    BINDINGS = [Binding("escape", "cancel", "cancel", show=False)]

    def __init__(self, current: str):
        super().__init__()
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="box"):
            yield Input(value=self._current, id="name")
            yield Static("enter — rename    esc — cancel", id="note")

    def on_mount(self) -> None:
        inp = self.query_one("#name", Input)
        inp.focus()
        # select the whole name: typing replaces it, arrows allow editing
        inp.action_select_all()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        name = event.value.strip()
        self.dismiss(name or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class KeysScreen(ModalScreen[None]):
    """The whole key map, in one place, since there is no command palette."""

    CSS = """
    KeysScreen { align: center middle; background: $background 60%; }
    #keys { width: 62; height: auto; padding: 1 2;
            border: tall $primary; background: $surface; color: $text; }
    """

    BINDINGS = [Binding("escape,k,q", "close", "close", show=False)]

    def compose(self) -> ComposeResult:
        yield Static(KEYS_TEXT, id="keys")

    def action_close(self) -> None:
        self.dismiss(None)


class FinalizerTUI(App):
    TITLE = "FINALIZER"
    SUB_TITLE = "algorithmic mastering"

    CSS = """
    Screen { background: $surface; }
    #hint { padding: 1 2 0 2; color: $text-muted; text-align: center; }
    #hint.title { color: $text; text-style: bold; }
    #tree { height: 1fr; margin: 0 2; }
    #row { height: auto; padding: 1 2; align: center middle; }
    #row Button { margin: 0 1; min-width: 10; height: 1; padding: 0 1;
                  border: none;
                  background: $secondary; color: $background; }
    #row Button:hover { background: $secondary-lighten-2; }
    #row Button:focus { background: $secondary-lighten-1; }
    #status { height: 1; padding: 0 2; color: $text; text-align: center; }
    /* blue = work in progress. Literal hex, not $busy: custom theme
       variables are not resolved when the app CSS is parsed */
    #status.busy { color: #3fa9ff; }
    #status.ask { color: #d6336c; }
    #spin { color: #3fa9ff; }
    """
    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        Binding("m", "master", "master", show=True),
        Binding("1", "profile('low')", "low", show=True),
        Binding("2", "profile('mid')", "mid", show=True),
        Binding("3", "profile('high')", "high", show=True),
        Binding("4", "profile('all')", "all", show=True),
        Binding("o", "open_current", "open", show=True),
        Binding("d", "delete", "delete", show=True),
        Binding("r", "rename", "rename", show=True),
        Binding("i", "info", "info", show=True),
        Binding("t", "theme", "theme", show=True),
        Binding("k", "keys", "keys", show=True),
        Binding("q", "quit", "quit", show=True),
        # not in the footer: obvious, or only meaningful in context
        Binding("left", "move(-1)", "prev", show=False),
        Binding("right", "move(1)", "next", show=False),
        Binding("escape", "pick", "back", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.register_theme(THEME_369ARC)
        self.state = load_state()
        self.selected: list[Path] = []
        self.stage = "pick"
        self.outputs: list[Path] = []
        self.started = 0.0
        self.current = ""
        self._pending_delete: list[Path] | None = None

    # ---------------------------------------------------------------- layout
    def compose(self) -> ComposeResult:
        yield Static("FINALIZER", id="hint", classes="title")
        yield Static("", id="status")
        start = Path(self.state.get("dir") or START_DIR)
        yield Picker(str(start if start.is_dir() else START_DIR), id="tree")
        yield Horizontal(
            Button("Master", id="go"),
            Button("low", id="p_low"),
            Button("mid", id="p_mid"),
            Button("high", id="p_high"),
            Button("all", id="p_all"),
            LoadingIndicator(id="spin"),
            id="row",
        )
        yield Footer()

    def on_mount(self) -> None:
        name = self.state.get("theme")
        if name not in self.available_themes:
            name = "369arc"
        self.theme = name
        self._stage_pick()
        self.set_interval(0.5, self._tick)

    def _watch_theme(self, theme_name: str) -> None:
        super()._watch_theme(theme_name)
        if getattr(self, "_preview", False):
            return                      # a preview is not a decision
        if self.state.get("theme") != theme_name:
            self.state["theme"] = theme_name
            save_state(self.state)

    def action_change_theme(self) -> None:
        """ctrl+p -> Change theme also goes through the previewing list."""
        self.action_theme()

    def action_keys(self) -> None:
        self.push_screen(KeysScreen())

    def action_theme(self) -> None:
        if isinstance(self.screen, ThemeScreen):
            return
        self._theme_before = self.theme
        self._preview = True
        self.push_screen(ThemeScreen(), self._theme_chosen)

    def _theme_chosen(self, name: str | None) -> None:
        self._preview = False
        if name is None:
            self.theme = self._theme_before      # escape -> back as it was
            return
        self.theme = name
        self.state["theme"] = name
        save_state(self.state)

    # ---------------------------------------------------------------- keys
    def check_action(self, action: str, parameters) -> bool | None:
        # while a delete is waiting for an answer every binding is suspended:
        # the next key decides, and nothing else can happen by accident
        if self._pending_delete is not None:
            return False
        return True

    def on_key(self, event) -> None:
        """Any layout behaves as US: Cyrillic 'o' is 'o', Cyrillic 'q' is 'q'."""
        key = event.key
        if self._pending_delete is not None:
            event.stop()
            if len(key) == 1:
                latin = _LAYOUT.get(key.lower(), key.lower())
                if latin == "y":
                    self._do_delete()
                    return
            self._cancel_delete()
            return
        if len(key) != 1:
            return
        latin = _LAYOUT.get(key.lower())
        if latin is None:
            return
        event.stop()
        # re-dispatch through the same bindings, so a new key never has to be
        # added here as well; run_action is a coroutine in textual 8.x
        for binding in self.BINDINGS:
            if binding.key == latin and binding.action:
                self.call_later(self.run_action, binding.action)
                return

    # ---------------------------------------------------------------- events
    def on_directory_tree_file_selected(self, event) -> None:
        # "done" is not a dead end: enter on a file starts the next master
        if self.stage not in ("pick", "done"):
            return
        tree = self.query_one("#tree", Picker)
        self.selected = list(tree.marked) or [Path(event.path)]
        self._stage_profiles()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "go":
            self.action_master()
        elif event.button.id and event.button.id.startswith("p_"):
            self.action_profile(event.button.id[2:])

    def action_move(self, delta: int) -> None:
        """Arrow keys walk the buttons that are visible right now."""
        if self.stage == "pick":
            return                      # the tree owns left/right there
        ids = [b.id for b in self.query("Button") if b.display]
        if not ids:
            return
        cur = self.focused.id if self.focused is not None else None
        i = ids.index(cur) if cur in ids else (-1 if delta > 0 else 0)
        self.query_one(f"#{ids[(i + delta) % len(ids)]}").focus()

    def action_delete(self) -> None:
        """d: ask in the status line; the next key answers."""
        if self._pending_delete is not None:
            return
        tree = self.query_one("#tree", Picker)
        files = list(tree.marked)
        if not files:
            path = getattr(getattr(tree.cursor_node, "data", None), "path", None)
            if path is not None and not Path(path).is_dir():
                files = [Path(path)]
        if not files:
            return
        self._pending_delete = files
        what = (files[0].name if len(files) == 1
                else f"{len(files)} files")
        st = self.query_one("#status", Static)
        st.add_class("ask")
        st.update(f"delete {what}?  y / n")

    def _cancel_delete(self) -> None:
        self._pending_delete = None
        st = self.query_one("#status", Static)
        st.remove_class("ask")
        st.update("cancelled")

    def _do_delete(self) -> None:
        files = self._pending_delete or []
        self._pending_delete = None
        done, failed = [], []
        for p in files:
            try:
                p.unlink()
                done.append(p.name)
            except OSError as e:
                failed.append(f"{p.name}: {e.strerror}")
        tree = self.query_one("#tree", Picker)
        tree.marked.clear()
        tree.reload()
        st = self.query_one("#status", Static)
        st.remove_class("ask")
        if failed:
            st.update("could not delete: " + "; ".join(failed))
        else:
            st.update("deleted: " + ", ".join(done))

    def action_info(self) -> None:
        """i: what this file is, in the status line."""
        tree = self.query_one("#tree", Picker)
        path = getattr(getattr(tree.cursor_node, "data", None), "path", None)
        if path is None or Path(path).is_dir():
            return
        self.query_one("#status", Static).update("reading…")
        self._info_worker(Path(path))

    @work(thread=True, exclusive=True)
    def _info_worker(self, path: Path) -> None:
        # ffprobe can take a second or two on exotic containers; never on the
        # UI thread
        self.call_from_thread(
            lambda: self.query_one("#status", Static).update(file_info(path)))

    def action_master(self) -> None:
        """m, the Master button, or enter on a file: all the same door."""
        if self.stage not in ("pick", "done"):
            return
        tree = self.query_one("#tree", Picker)
        files = list(tree.marked)
        if not files:
            path = getattr(getattr(tree.cursor_node, "data", None), "path", None)
            if path is not None and not Path(path).is_dir():
                files = [Path(path)]
        if files:
            self.selected = files
            self._stage_profiles()

    def action_rename(self) -> None:
        """r: rename the file under the cursor."""
        tree = self.query_one("#tree", Picker)
        if len(tree.marked) > 1:
            self.query_one("#status", Static).update(
                "rename works on one file — clear the marks first")
            return
        src = tree.marked[0] if tree.marked else None
        if src is None:
            path = getattr(getattr(tree.cursor_node, "data", None), "path", None)
            if path is not None and not Path(path).is_dir():
                src = Path(path)
        if src is None:
            return
        self.push_screen(RenameScreen(src.name),
                         lambda name: self._do_rename(src, name))

    def _do_rename(self, src: Path, name: str | None) -> None:
        st = self.query_one("#status", Static)
        if not name or name == src.name:
            st.update("")
            return
        try:
            dst = src.with_name(name)
        except ValueError:
            st.update(f"[red]invalid name: {name}[/red]")
            return
        if dst.exists():
            st.update(f"[red]exists: {name}[/red]")
            return
        try:
            src.rename(dst)
        except OSError as e:
            st.update(f"[red]rename failed: {e.strerror}[/red]")
            return
        tree = self.query_one("#tree", Picker)
        tree.marked.clear()
        tree.reload()
        self.call_after_refresh(self._reveal, dst)
        st.update(f"renamed: {src.name} → {name}")

    def action_open_current(self) -> None:
        """o: open what is selected in the tree, in the system player."""
        tree = self.query_one("#tree", Picker)
        files = list(tree.marked)
        if not files:
            node = tree.cursor_node
            path = getattr(getattr(node, "data", None), "path", None)
            if path is not None and not Path(path).is_dir():
                files = [Path(path)]
        for p in files:
            if p.exists():
                self._open_with_system(p)

    def _open_with_system(self, path: Path) -> None:
        """xdg-open on Linux, open on macOS, the shell association on Windows."""
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))          # noqa: S606  (Windows only)
                return
            cmd = ["open", str(path)] if sys.platform == "darwin" \
                else ["xdg-open", str(path)]
            subprocess.Popen(
                cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=True)
        except Exception as e:  # noqa: BLE001
            self.query_one("#status", Static).update(
                f"could not open: {e}")

    def action_pick(self) -> None:
        if self.stage in ("profile", "done", "error"):
            self._stage_pick()

    # ---------------------------------------------------------------- stages
    def _hint(self, text: str, title: bool = False) -> None:
        h = self.query_one("#hint", Static)
        h.update(text)
        h.set_class(title, "title")

    def _show(self, **which: bool) -> None:
        for wid, on in which.items():
            self.query_one(f"#{wid}").display = on

    def _stage_pick(self) -> None:
        self.stage = "pick"
        self._show(go=True, p_low=False, p_mid=False, p_high=False,
                   p_all=False, spin=False)
        tree = self.query_one("#tree", Picker)
        tree.marked.clear()
        tree.reload()
        tree.focus()
        self._hint("FINALIZER", title=True)
        # a missing converter is not fatal, but it limits the input to
        # 48 kHz stereo PCM -- say so before the first file is picked
        self.query_one("#status", Static).update(
            "" if HAS_FFMPEG else
            "ffmpeg not found — only 48 kHz stereo PCM will open (see README)")

    def _stage_profiles(self) -> None:
        self.stage = "profile"
        names = ", ".join(p.name for p in self.selected[:3])
        more = f" (+{len(self.selected) - 3})" if len(self.selected) > 3 else ""
        self._hint(f"{names}{more}")
        self._show(go=False, p_low=True, p_mid=True, p_high=True,
                   p_all=True, spin=False)
        last = self.state.get("profile")
        self.query_one(f"#p_{last}" if last in CHOICES else "#p_mid",
                       Button).focus()
        self.query_one("#status", Static).update(
            "← → choose   enter apply   1 2 3 4 direct   esc back")

    def action_profile(self, profile: str) -> None:
        if self.stage != "profile" or profile not in CHOICES:
            return
        self.stage = "render"
        self.state["profile"] = profile
        self.state["dir"] = str(self.selected[0].parent)
        save_state(self.state)
        self.started = time.time()
        self.outputs = [o for s in self.selected for o in expected(s, profile)]
        self._hint(f"{profile} — rendering")
        self._show(p_low=False, p_mid=False, p_high=False, p_all=False,
                   spin=True)
        self.query_one("#status", Static).add_class("busy")
        self.query_one("#status", Static).update("starting…")
        self._render(profile)

    def _tick(self) -> None:
        if self.stage != "render":
            return
        el = time.time() - self.started
        self.query_one("#status", Static).update(
            f"{self.current}   {int(el // 60)}:{int(el % 60):02d}")

    @work(thread=True, exclusive=True)
    def _render(self, profile: str) -> None:
        total = len(self.selected)
        for i, src in enumerate(self.selected, 1):
            outs = expected(src, profile)
            out = outs[0] if len(outs) == 1 else src.with_suffix("")
            self.current = f"{i}/{total}  {src.name}"
            self.call_from_thread(self._status, self.current)
            try:
                r = subprocess.run(build_cmd(src, profile, out),
                                   capture_output=True, text=True)
            except Exception as e:  # noqa: BLE001
                self.call_from_thread(self._fail, f"{src.name}: {e}")
                return
            if r.returncode != 0 or not all(o.exists() for o in outs):
                tail = (r.stderr or r.stdout or "").strip().splitlines()[-3:]
                self.call_from_thread(self._fail,
                                      f"{src.name}: " + " / ".join(tail))
                return
        self.call_from_thread(self._done)

    def _status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)

    def _fail(self, text: str) -> None:
        self.stage = "error"
        self.query_one("#status", Static).remove_class("busy")
        self._show(spin=False, go=True)
        self.query_one("#go", Button).focus()
        self.query_one("#status", Static).update(f"[red]{text}[/red]")

    def _done(self) -> None:
        self.stage = "done"
        self.query_one("#status", Static).remove_class("busy")
        self._show(spin=False, go=True)
        tree = self.query_one("#tree", Picker)
        tree.marked.clear()
        tree.reload()
        # put the cursor back on the SOURCE, not on the file we just wrote:
        # the next Enter should master the track again, not master the master
        self.call_after_refresh(self._reveal,
                                self.selected[-1] if self.selected else None)
        tree.focus()
        self._hint("done — o opens · m or enter masters another file")
        self.query_one("#status", Static).update(
            "  ".join(p.name for p in self.outputs))

    def _reveal(self, path: Path | None, tries: int = 6) -> None:
        """Put the cursor on a file, retrying while the tree rebuilds."""
        if path is None:
            return
        tree = self.query_one("#tree", Picker)
        if not self._reveal_now(tree, path) and tries > 0:
            self.set_timer(0.05, lambda: self._reveal(path, tries - 1))

    def _reveal_now(self, tree: "Picker", path: Path) -> bool:
        """Move the cursor to path; False if it is not in the tree yet."""
        try:
            rel = path.relative_to(Path(tree.path))
        except ValueError:
            return False
        node = tree.root
        for part in rel.parts[:-1]:
            nxt = None
            for ch in node.children:
                d = getattr(getattr(ch, "data", None), "path", None)
                if d is not None and Path(d).name == part:
                    nxt = ch
                    break
            if nxt is None:
                return False
            nxt.expand()
            node = nxt
        for ch in node.children:
            d = getattr(getattr(ch, "data", None), "path", None)
            if d is not None and Path(d) == path:
                tree.move_cursor(ch)
                return True
        return False


def main() -> None:
    FinalizerTUI().run()


if __name__ == "__main__":
    main()

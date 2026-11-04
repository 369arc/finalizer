"""Headless regression for tui.py. Never touches the user's folders.

Run:  python3 tests/test_tui.py
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

# never read or write the user's state file
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp(prefix="fin_state_")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import tui  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="fin_tui_test_"))
SRC = _TMP / "T2.wav"
_t = np.arange(48000) / 48000
sf.write(SRC, np.stack([0.2 * np.sin(2 * np.pi * 220 * _t)] * 2, axis=1), 48000)

opened: list[str] = []


def fake_run(cmd, **kw):
    class R:
        returncode = 0
        stdout = stderr = ""
    Path(cmd[cmd.index("--out") + 1]).write_bytes(b"RIFF")
    return R()


async def main():
    assert tui.out_path(SRC, "mid").name == "CHIRO_mid.wav"
    print("1. naming ok")

    tui.subprocess.run = fake_run
    tui.subprocess.Popen = lambda *a, **k: opened.append(a[0][1])

    app = tui.FinalizerTUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one("#tree", tui.Picker)
        shown = [b.id for b in app.query("Button") if b.display]
        assert shown == ["go"], shown
        assert tree.display
        print("2. start: only Master, tree visible")

        tree._enter(SRC.parent)
        await pilot.pause()

        # 'm' is the same door as the Master button and enter-on-a-file
        for ch in tree.root.children:
            if getattr(getattr(ch, "data", None), "path", None) == SRC:
                tree.move_cursor(ch)
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        assert app.stage == "profile", app.stage
        assert app.selected == [SRC], app.selected
        await pilot.press("escape")
        await pilot.pause()
        print("3. 'm' opens profiles for the cursor file")

        app.selected = [SRC]
        app._stage_profiles()
        await pilot.pause()
        shown = [b.id for b in app.query("Button") if b.display]
        assert shown == ["p_low", "p_mid", "p_high", "p_all"], shown
        assert tree.display, "tree must stay visible"
        print("4. profiles: four buttons, tree still visible")

        await pilot.press("enter")
        for _ in range(60):
            await pilot.pause()
            if app.stage == "done":
                break
        shown = [b.id for b in app.query("Button") if b.display]
        assert shown == ["go"], shown
        # the tree rebuilds after the render; wait for it instead of racing it
        names = []
        for _ in range(40):
            await pilot.pause()
            names = [str(ch.label) for ch in tree.root.children]
            if "CHIRO_mid.wav" in names:
                break
        assert "CHIRO_mid.wav" in names, names
        print("5. done: Master is back, output is in the tree")

        cur = getattr(getattr(tree.cursor_node, "data", None), "path", None)
        assert cur == SRC, cur
        print("6. cursor is back on the source")

        await pilot.press("enter")
        await pilot.pause()
        assert app.stage == "profile", app.stage
        print("7. enter after done -> profiles again")

        opened.clear()
        await pilot.press("\u0449")          # 'o' on a Cyrillic layout
        await pilot.pause()
        assert opened == [str(SRC)], opened
        print("8. cyrillic '\u0449' opens like 'o'")

        await pilot.press("escape")
        await pilot.pause()
        assert app.stage == "pick", app.stage
        print("9. esc -> pick")

        await pilot.press("k")
        await pilot.pause()
        assert type(app.screen).__name__ == "KeysScreen"
        await pilot.press("escape")
        await pilot.pause()
        print("10. k -> keys, esc closes")

        await pilot.press("ctrl+p")
        await pilot.pause()
        assert type(app.screen).__name__ == "Screen"
        print("11. ctrl+p does nothing (no command palette)")

        # info: i prints format / depth / rate / length
        for ch in tree.root.children:
            if getattr(getattr(ch, "data", None), "path", None) == SRC:
                tree.move_cursor(ch)
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()
        info = str(app.query_one("#status").render())
        assert "WAV" in info and "48" in info and info.count(":") >= 2, info
        print("12. info:", info)

        # delete: d asks, n cancels, y deletes
        scratch = SRC.parent / "scratch.wav"
        scratch.write_bytes(b"x")
        tree.reload()
        await pilot.pause()
        for ch in tree.root.children:
            if getattr(getattr(ch, "data", None), "path", None) == scratch:
                tree.move_cursor(ch)
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert scratch.exists(), "n must cancel"
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert not scratch.exists(), "y must delete"
        print("13. delete: n keeps, y removes")

        # rename: r, type, enter
        old = SRC.parent / "old.wav"
        old.write_bytes(b"x")
        tree.reload()
        await pilot.pause()
        for ch in tree.root.children:
            if getattr(getattr(ch, "data", None), "path", None) == old:
                tree.move_cursor(ch)
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        app.screen.query_one("#name", tui.Input).value = "new.wav"
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        assert (SRC.parent / "new.wav").exists() and not old.exists()
        print("14. rename: old.wav -> new.wav")


asyncio.run(main())
import shutil  # noqa: E402
shutil.rmtree(_TMP, ignore_errors=True)

#!/usr/bin/env python3
"""Fails a game that has no visual QA entry.

    scripts/check-visual-qa.py <project-dir>

A game (a `game.sh` at the root next to a `project.godot`) must track `tools/visual_qa.gd`: the
script dot-game's `dot_game_visual_qa.sh` runs to capture contact sheets and a clip verdict of the
game's moving things. The harness lives in dot-game; the game's file only lists items and stages
them. A tracked `tools/visual_qa_shot.sh` must be executable in git (mode 100755), or a box that
runs it as a command fails with "Permission denied".

Not a game (no `game.sh`): skipped. Escape: a line `*` (with a `#` comment saying why and what
will replace it) in `ci/visual-qa.allow` in the checked repository exempts the missing entry.
"""
import os
import subprocess
import sys

ENTRY = "tools/visual_qa.gd"
SHOT = "tools/visual_qa_shot.sh"


def problems(files, modes, allowed=False):
    """files: set of tracked paths; modes: path -> git mode string."""
    if "game.sh" not in files or "project.godot" not in files:
        return []
    out = []
    if ENTRY not in files and not allowed:
        out.append(f"{ENTRY} is missing: add a visual QA entry that extends DotGameVisualQaCapture "
                   "(addons/dot_game/docs/visual-qa.md), or list `*` in ci/visual-qa.allow with the reason")
    if SHOT in files and modes.get(SHOT) != "100755":
        out.append(f"{SHOT} is not executable in git: git update-index --chmod=+x {SHOT}")
    return out


def main(argv):
    d = argv[1] if len(argv) > 1 else "."
    r = subprocess.run(["git", "-C", d, "ls-files", "-s", "-z"], capture_output=True)
    if r.returncode:
        print(f"git ls-files failed in {d}", file=sys.stderr)
        return 2
    modes = {}
    for rec in r.stdout.decode("utf-8", "surrogateescape").split("\0"):
        if rec:
            meta, path = rec.split("\t", 1)
            modes[path] = meta.split()[0]
    allowed = False
    allow = os.path.join(d, "ci", "visual-qa.allow")
    if os.path.exists(allow):
        with open(allow, encoding="utf-8") as f:
            allowed = any(l.strip() == "*" for l in f)
    bad = problems(set(modes), modes, allowed)
    if bad:
        print("FAIL visual QA entry:", file=sys.stderr)
        print("\n".join(bad), file=sys.stderr)
        return 1
    print("visual qa ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

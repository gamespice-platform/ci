#!/usr/bin/env python3
"""Fails a repository that tracks a file split into numbered or meaningless parts.

    scripts/check-split-names.py <project-dir>      # paths from git ls-files
    scripts/check-split-names.py --stdin            # one path per line

A file that outgrew its size is split by responsibility and each piece is named for what
it holds (`fc_game_combat.gd`, `fc_game_loadouts.gd`), never `fc_game_part1.gd`,
`fc_game_part2.gd`. Flags a file or directory whose name, without extension, is or ends
in `_part<N>` / `_pt<N>` (an optional single letter after the number: `part2a`), or is
`part<N>`; or is exactly `misc`, `miscellaneous`, `stuff`, `junk` or `untitled`; or is
`helpers<N>` / `utils<N>` / `util<N>` / `helper<N>`.

A script (`.gd .rs .py .ts .tsx .js .sh .gdshader`) whose name ends in a lone letter (`tests_a`), a
number (`tests_2`), or a letter plus number and an optional letter (`tests_b1`, `tests_a2`,
`dedicated_b2a`) is the same thing: a piece numbered or lettered instead of named. Not flagged:
`_2d`/`_3d`, and the protocol or product names in `SUFFIX_OK` (`a2s`, `e2e`, `x86`, `v2`).
Scenes and assets are not checked here (`avatar_a.tscn` can be a real variant).

Escape: a path listed (one per line, `#` comments) in `ci/split-names.allow` in the checked
repository, for vendored third-party names that cannot be changed.
"""
import os
import re
import subprocess
import sys

SPLIT = re.compile(r"(^|[_.-])(part|pt)[0-9]+[a-z]?$", re.I)
VAGUE = re.compile(r"^(misc|miscellaneous|stuff|junk|untitled|(helpers?|utils?)[0-9]+)$", re.I)


SCRIPT_EXT = (".gd", ".rs", ".py", ".ts", ".tsx", ".js", ".sh", ".gdshader")
SUFFIX = re.compile(r"_([a-z]|[0-9]+|[a-z][0-9]+[a-z]?)$", re.I)
SUFFIX_OK = {"a2s", "e2e", "x86", "x64", "i18n", "l10n", "h264", "h265", "sha256", "v1", "v2", "v3", "v4", "v5"}


def lettered(name):
    """True for a script whose stem ends `_a`, `_2`, `_b1`, `_b2a` (a piece numbered, not named)."""
    base = name.split("/")[-1]
    s = stem(base)
    if base.startswith(".") or "." + base[len(s):].lstrip(".").split(".")[0] not in SCRIPT_EXT:
        return False
    m = SUFFIX.search(s)
    return bool(m) and m.group(1).lower() not in SUFFIX_OK


def stem(part):
    """The component without its extensions (`a_part1.gd.uid` -> `a_part1`)."""
    return part.split(".", 1)[0] if not part.startswith(".") else part


def problems(paths, allowed=()):
    out = []
    for p in paths:
        if p in allowed:
            continue
        for part in p.split("/"):
            s = stem(part)
            if SPLIT.search(s):
                out.append(f"{p}: '{part}' is a numbered split; name each piece for what it holds")
                break
            if VAGUE.match(s):
                out.append(f"{p}: '{part}' says nothing about what it holds")
                break
        else:
            if lettered(p):
                out.append(f"{p}: ends in a letter or number; name the piece for what it holds")
    return out


def main(argv):
    allowed = set()
    if argv[1:] == ["--stdin"]:
        paths = [l.rstrip("\n") for l in sys.stdin if l.strip()]
    else:
        d = argv[1] if len(argv) > 1 else "."
        r = subprocess.run(["git", "-C", d, "ls-files", "-z"], capture_output=True)
        if r.returncode:
            print(f"git ls-files failed in {d}", file=sys.stderr)
            return 2
        paths = [x for x in r.stdout.decode("utf-8", "surrogateescape").split("\0") if x]
        allow = os.path.join(d, "ci", "split-names.allow")
        if os.path.exists(allow):
            with open(allow, encoding="utf-8") as f:
                allowed = {l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")}
    bad = problems(paths, allowed)
    if bad:
        print("FAIL file names that are numbered splits or say nothing:", file=sys.stderr)
        print("\n".join(bad), file=sys.stderr)
        return 1
    print(f"split names ok ({len(paths)} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""Fails a repository whose scripts load a resource by uid:// instead of by res:// path.

    scripts/check-no-uid-loads.py <project-dir>      # files from git ls-files
    scripts/check-no-uid-loads.py --stdin            # one path per line

A box or a pack whose uid cache does not know the uid fails `load("uid://...")` with
"Unrecognized UID": the script then runs without what it loads (weapons, props) and a suite can
still pass. Flags, in tracked .gd files, a load or preload of a uid:// string, and outside
examples/ and tests/ any whole uid literal ("uid://b0h67pyeqben"), which is how a const ends up in a
load. A bare "uid://" prefix (a begins_with check) is fine; .tscn/.tres ext_resource uids are not
read. Comment text is ignored. A line that must keep one says `uid-load: allow <reason>` in a comment.
"""
import re
import subprocess
import sys

LOAD = re.compile(r"""\b(?:pre)?load\(\s*["']uid://""")
LITERAL = re.compile(r"""["']uid://[0-9a-z]{4,}["']""")
ALLOW = "uid-load: allow"


def code_part(line):
    # A '#' inside a string is rare enough here that cutting at the first one is the honest approximation.
    i = line.find("#")
    return line if i < 0 else line[:i]


def problems(path, text):
    if not path.endswith(".gd"):
        return []
    fixture = path.startswith(("examples/", "tests/")) or "/examples/" in path or "/tests/" in path
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if ALLOW in line:
            continue
        code = code_part(line)
        if LOAD.search(code) or (not fixture and LITERAL.search(code)):
            out.append(f"{path}:{n}: loads by uid://; a box without the uid cache fails it ({line.strip()[:80]})")
    return out


def main(argv):
    if argv[1:] == ["--stdin"]:
        root = "."
        paths = [l.rstrip("\n") for l in sys.stdin if l.strip()]
    else:
        root = argv[1] if len(argv) > 1 else "."
        paths = subprocess.run(["git", "-C", root, "ls-files", "*.gd"], capture_output=True, text=True,
                               check=True).stdout.splitlines()
    bad = []
    for p in paths:
        if "/.godot/" in "/" + p or p.startswith("build/"):
            continue
        try:
            with open(f"{root}/{p}", encoding="utf-8") as f:
                bad += problems(p, f.read())
        except (OSError, UnicodeDecodeError):
            continue
    for b in bad:
        print(b)
    if bad:
        print(f"{len(bad)} uid:// load(s). Load by the res:// path the file's .uid sidecar belongs to.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

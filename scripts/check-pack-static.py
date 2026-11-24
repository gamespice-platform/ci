#!/usr/bin/env python3
"""Static gate on a built pack zip (the *-pack.zip release.yml attaches), judged as the artifact, not as source.

  check-pack-static.py [--deny REGEX]... PACK.zip [PACK.zip...]

FAILS (exit 1) on, inside one pack:
  - an addons/dot_* directory or a dot_*.gd script (a pre-rename addon, which collides with its gs_* successor in the host)
  - a Dot* class_name
  - one uid:// claimed by two different resources (the shell that mounts the pack then refuses to load one of them)
  - with --deny, a text file matching REGEX (a dev-only origin or panel address that must not ship to players)
Exit 2 when a zip is unreadable or holds nothing. Tests: tests/test_check_pack_static.py.
"""
import re, sys, zipfile
from collections import defaultdict

HDR = re.compile(r'^\[gd_(?:scene|resource)[^\]]*\buid="(uid://[a-z0-9]+)"', re.M)
UID = re.compile(r'uid://[a-z0-9]+')
TEXT = (".gd", ".tscn", ".tres", ".cfg", ".json", ".yml", ".yaml", ".txt", ".md", ".html", ".js", ".uid", ".import", ".remap")


def owner_of(rel):
    for suf in (".uid", ".remap", ".import"):
        if rel.endswith(suf):
            return rel[: -len(suf)]
    return rel


def judge(zf, deny):
    owners = defaultdict(set)
    bad, dirs, n = [], {}, 0
    for name in zf.namelist():
        if name.endswith("/"):
            continue
        n += 1
        m = re.match(r'(addons/dot_[^/]+)(/|$)', name)
        if m:
            dirs[m.group(1)] = dirs.get(m.group(1), 0) + 1
        elif re.search(r'(^|/)dot_[^/]*\.(gd|gdc)$', name):
            bad.append(f"stale dot_* script in the pack: {name}")
        if not name.endswith(TEXT):
            continue
        text = zf.read(name).decode("utf-8", errors="replace")
        if name.endswith(".uid"):
            for u in UID.findall(text):
                owners[u].add(owner_of(name))
        elif name.endswith((".remap", ".import")):
            m = re.search(r'^uid="(uid://[a-z0-9]+)"', text, re.M)
            if m:
                owners[m.group(1)].add(owner_of(name))
        elif name.endswith((".tscn", ".tres")):
            m = HDR.search(text)
            if m:
                owners[m.group(1)].add(name)
        elif name.endswith(".gd"):
            for m in re.finditer(r'^class_name\s+(Dot\w*)', text, re.M):
                bad.append(f"Dot* class {m.group(1)} in {name}")
        for rx in deny:
            m = rx.search(text)
            if m:
                bad.append(f"{name}: matches the deny pattern {rx.pattern!r} ({m.group(0)[:60]!r})")
    for d, c in dirs.items():
        bad.append(f"stale addon directory {d} ({c} files)")
    for u, who in sorted(owners.items()):
        if len(who) > 1:
            bad.append(f"duplicate uid {u} claimed by: {', '.join(sorted(who))}")
    return n, bad


def main(argv):
    deny, zips, i = [], [], 1
    while i < len(argv):
        if argv[i] == "--deny" and i + 1 < len(argv):
            deny.append(re.compile(argv[i + 1]))
            i += 2
        else:
            zips.append(argv[i])
            i += 1
    if not zips:
        print(__doc__)
        return 2
    rc = 0
    for z in zips:
        try:
            with zipfile.ZipFile(z) as zf:
                n, bad = judge(zf, deny)
        except (OSError, zipfile.BadZipFile) as e:
            print(f"check-pack-static: cannot read {z}: {e}")
            return 2
        if n == 0:
            print(f"check-pack-static: {z} holds nothing to judge")
            return 2
        for b in bad:
            print(f"ERROR: {z}: {b}")
        if bad:
            print(f"check-pack-static: FAIL {z} ({len(bad)} problem(s), {n} files)")
            rc = 1
        else:
            print(f"check-pack-static: ok {z} ({n} files)")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""Stale vendored art: which games hold an old copy of an addon repository's art?

    check-vendored-art.py [--addon DIR] [--games-root DIR] [--ref REF] [--game NAME ...]

A game cannot load art that lives outside its own tree, so it vendors a copy of the
files the addon's art table names (zee-dot-weapons/tools/sync-art.sh). Nothing re-copies
when the addon adds or changes a model, so the game goes red in CI later. 2026-11-20:
zee-dot-weapons a5b7b0e added frag.glb and sticky.glb and five games were stale.

This is the fast, Godot-free form of `sync-art.sh <game> --check`. It reads git objects only:
  * SOURCE: the addon repository's files under assets/ at --ref (default HEAD).
  * GAME: the game's committed tree on its local main branch.
For every assets/<dir> the game vendors (same dir name as in the source):
  * a vendored file that differs from the source is STALE (a .import compares without its uid= line);
  * a source .glb whose name the art table (addons/*/art/zee_weapon_art_table*.gd, not the attachments) writes as a quoted string, and the
    game lacks, is MISSING (only in low-poly-guns and melee: the optional arms, ammo and blaster-kit parts a game may skip are checked for staleness only).
It approximates ZeeWeaponArtTable.model_paths(): it can miss a model the table builds from
pieces, so sync-art.sh --check stays the authority. Exit 1 when any game is stale, listing each
game and the fix command; exit 0 when all are current. Runs in seconds.
Consumers are the games under --games-root (default: the parent of the addon repository) that
have an addons/zee_weapons entry and an assets/ directory shared with the source.
"""
import argparse
import hashlib
import os
import re
import subprocess
import sys


WEAPON_DIRS = ("low-poly-guns", "melee")  # where whole weapons live; a game may skip optional kit parts


def git(repo, *args, raw=False):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True)
    if r.returncode != 0:
        return None
    return r.stdout if raw else r.stdout.decode("utf-8", "replace")


def tree(repo, ref, prefix):
    """{path: blob} of files under prefix at ref; None when the ref is missing."""
    out = git(repo, "ls-tree", "-r", ref, "--", prefix)
    if out is None:
        return None
    files = {}
    for line in out.splitlines():
        meta, _, path = line.partition("\t")
        files[path] = meta.split()[2]
    return files


def content(repo, blob, path):
    data = git(repo, "cat-file", "blob", blob, raw=True) or b""
    if path.endswith(".import"):
        data = b"\n".join(x for x in data.split(b"\n") if not x.startswith(b"uid="))
    return hashlib.md5(data).hexdigest()


def named_models(addon, ref):
    """Basenames (x.glb) the art table spells out, as "x.glb" or a bare "x" passed to _gun/_blaster."""
    names = set()
    listing = git(addon, "ls-tree", "-r", "--name-only", ref, "--", "addons")
    for path in (listing or "").splitlines():
        if "/art/zee_weapon_art_table" not in path or not path.endswith(".gd"):
            continue
        src = git(addon, "show", "%s:%s" % (ref, path)) or ""
        for stem, _ in re.findall(r'"([A-Za-z0-9_\-]+)(\.glb)?"', src):
            names.add(stem + ".glb")
    return names


def check_game(addon, game, src, dirs, named):
    branch = "main" if git(game, "rev-parse", "--verify", "-q", "main") else "HEAD"
    mine = tree(game, branch, "assets")
    if mine is None:
        return None
    lines = []
    for d in sorted(dirs):
        prefix = "assets/%s/" % d
        if not any(p.startswith(prefix) for p in mine):
            continue
        for p, b in sorted(src.items()):
            if not p.startswith(prefix):
                continue
            if p in mine:
                if mine[p] != b and content(game, mine[p], p) != content(addon, b, p):
                    lines.append("stale:   " + p)
            elif p.endswith(".glb") and os.path.basename(p) in named and d in WEAPON_DIRS:
                lines.append("missing: " + p)
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--addon", default=".")
    ap.add_argument("--games-root")
    ap.add_argument("--ref", default="HEAD")
    ap.add_argument("--game", action="append", default=[])
    a = ap.parse_args()
    addon = os.path.abspath(a.addon)
    root = a.games_root or os.path.dirname(addon)
    src = tree(addon, a.ref, "assets")
    if not src:
        print("check-vendored-art: %s has no assets/ at %s" % (addon, a.ref), file=sys.stderr)
        return 2
    named = named_models(addon, a.ref)
    dirs = {p.split("/")[1] for p in src}
    bad = {}
    seen = 0
    for name in sorted(os.listdir(root)):
        game = os.path.join(root, name)
        if not name.startswith("game-") or not os.path.exists(os.path.join(game, "addons", "zee_weapons")):
            continue
        if a.game and name not in a.game and name.replace("game-", "") not in a.game:
            continue
        lines = check_game(addon, game, src, dirs, named)
        if lines is None:
            continue
        seen += 1
        if lines:
            bad[name] = lines
    for name, lines in bad.items():
        print("STALE %s (%d file(s))" % (name, len(lines)))
        for line in lines[:12]:
            print("  " + line)
        if len(lines) > 12:
            print("  ... %d more" % (len(lines) - 12))
    if bad:
        print("\nResync each, commit, push (checked against %s at %s):" % (os.path.basename(addon), a.ref))
        for name in bad:
            print("  %s/tools/sync-art.sh %s/%s   # via hv, needs Godot" % (os.path.basename(addon), root, name))
        return 1
    print("check-vendored-art: %d game(s) vendor current art from %s" % (seen, os.path.basename(addon)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

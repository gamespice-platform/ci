#!/usr/bin/env python3
"""Fails a repository that tracks a symlink pointing at itself or at an absolute path.

    scripts/check-self-symlinks.py <project-dir>

A tracked link (git mode 120000) whose target resolves back to its own path is a loop: every tool
that follows addon links (hv pre-flight, gpu.sh copy) stops on it. An absolute target is a path from
one machine, so it breaks everywhere else. No escape: untrack the link and ignore the path.
"""
import os
import subprocess
import sys


def tracked_links(root):
    out = subprocess.run(["git", "-C", root, "ls-files", "-s", "-z"], capture_output=True, text=True, check=True).stdout
    for rec in out.split("\0"):
        if rec.startswith("120000"):
            yield rec.split("\t", 1)[1]


def problems(root):
    for rel in tracked_links(root):
        path = os.path.join(root, rel)
        own = os.path.join(os.path.realpath(os.path.dirname(path)), os.path.basename(path))
        target = os.readlink(path)
        if os.path.isabs(target):
            if os.path.realpath(target) == own:
                yield f"{rel}: symlink points at itself ({target})"
            else:
                yield f"{rel}: symlink has an absolute target ({target})"
        elif os.path.realpath(os.path.join(os.path.dirname(path), target)) == own:
            yield f"{rel}: symlink loops ({target})"


def main():
    bad = list(problems(sys.argv[1] if len(sys.argv) > 1 else "."))
    for b in bad:
        print(b, file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Web build size report: raw and gzip bytes per build file, and what the pck holds.

    scripts/web-build-report.py [--top N] [--json] <web-build-dir | file.pck>

The numbers a load-time change needs before and after: the wasm and pck a browser downloads
(raw, and gzip as a CDN serves them), then the pck by top-level folder and by extension, and
its largest files. It reads Godot 4 pcks (format 2 and 3), unencrypted. Nothing is written.
"""
import argparse
import gzip
import json
import os
import struct
import sys
import zlib
from collections import defaultdict


def read_pck(path):
    """Returns [(path, size)] for each file in an unencrypted Godot 4 pck."""
    with open(path, "rb") as f:
        if f.read(4) != b"GDPC":
            raise SystemExit("%s: not a pck" % path)
        fmt, _maj, _min, _pat, flags = struct.unpack("<5I", f.read(20))
        if flags & 1:
            raise SystemExit("%s: encrypted directory" % path)
        base = struct.unpack("<Q", f.read(8))[0]
        if fmt >= 3:
            diroff = struct.unpack("<Q", f.read(8))[0]
            f.seek(diroff)
        else:
            f.read(16 * 4)  # reserved
        count = struct.unpack("<I", f.read(4))[0]
        out = []
        for _ in range(count):
            n = struct.unpack("<I", f.read(4))[0]
            name = f.read(n).rstrip(b"\0").decode("utf-8", "replace")
            _off, size = struct.unpack("<QQ", f.read(16))
            f.read(16)  # md5
            f.read(4)  # flags
            out.append((name, size))
        del base
        return out


def gz_size(path):
    total = 0
    c = zlib.compressobj(6, zlib.DEFLATED, 31)
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            total += len(c.compress(b))
    return total + len(c.flush())


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("target")
    p.add_argument("--top", type=int, default=15)
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    files = {}
    pck = None
    if os.path.isdir(a.target):
        for n in sorted(os.listdir(a.target)):
            fp = os.path.join(a.target, n)
            if os.path.isfile(fp) and n.endswith((".wasm", ".pck", ".js", ".html")):
                files[n] = {"raw": os.path.getsize(fp), "gzip": gz_size(fp)}
                if n.endswith(".pck"):
                    pck = fp
    else:
        pck = a.target
    entries = read_pck(pck) if pck else []
    top = defaultdict(int)
    ext = defaultdict(int)
    for name, size in entries:
        parts = name.replace("res://", "").split("/")
        top["/".join(parts[:3]) if parts[0] == "addons" else parts[0]] += size
        ext[os.path.splitext(name)[1] or "(none)"] += size
    rep = {
        "files": files,
        "pck_files": len(entries),
        "pck_bytes": sum(s for _, s in entries),
        "by_folder": dict(sorted(top.items(), key=lambda kv: -kv[1])[: a.top]),
        "by_ext": dict(sorted(ext.items(), key=lambda kv: -kv[1])[: a.top]),
        "largest": sorted(entries, key=lambda e: -e[1])[: a.top],
    }
    if a.json:
        json.dump(rep, sys.stdout, indent=1)
        return
    for n, v in files.items():
        print("%-28s raw %11d  gzip %11d" % (n, v["raw"], v["gzip"]))
    print("pck: %d files, %d bytes" % (rep["pck_files"], rep["pck_bytes"]))
    for title, key in (("by folder", "by_folder"), ("by extension", "by_ext")):
        print(title)
        for k, v in rep[key].items():
            print("  %-44s %11d" % (k, v))
    print("largest")
    for n, s in rep["largest"]:
        print("  %11d  %s" % (s, n))


if __name__ == "__main__":
    main()

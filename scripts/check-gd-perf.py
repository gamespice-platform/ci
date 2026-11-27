#!/usr/bin/env python3
"""GDScript performance practices in the scripts a repository marks as hot.

    scripts/check-gd-perf.py [--update|--init] [--baseline F] [--hot F] [--by-file] [--top N] <project-dir>

The hot set is ci/efficiency/gd-perf-hot.txt: one fnmatch glob per line over the tracked
paths (`game/fc_bots*.gd`, `addons/gs_bot/*.gd`), `#` comments. A `cold: REGEX` line names
the functions that run once (setup, build, signal handlers); without one, DEFAULT_COLD is
used, and a `cold+: REGEX` line adds names to whichever applies. With no hot file the gate has nothing to scan and passes, so a repository opts in.

Kinds, counted per function (key `path::func::kind`, count = sites, as check-frame-hazards):

  typing, every function and the member block (`<members>`):
    untyped_var      `var x = ...` / `var x` with no type (`:=` is typed by inference, allowed)
    untyped_param    a parameter with no `: Type` (and no `:=` default)
    no_return_type   a named func with no `-> Type`
    untyped_array    `Array` / `Dictionary` with no element type in a declaration or signature
  per tick, hot functions only (every function not matched by `cold:`):
    node_lookup      $Path, get_node*, find_child(ren), get_nodes_in_group, get_first_node_in_group
    alloc            [..] / {..} literals, Array()/Dictionary()/StringName(), .duplicate(),
                     Physics*QueryParameters3D.create/new
    string_build     print*, str(), .format(), "..." % x, + "..." unless an enclosing `if`
                     names a debug/verbose/log/trace flag
    dynamic_call     call/callv/call_deferred, has_method, get/set by string, Callable(), .bind(),
                     emit_signal
    singleton_lookup Engine.get_singleton, get_world_3d(), .direct_space_state, get_tree(),
                     ProjectSettings.get_setting
    emit_in_loop     a signal .emit( inside a for/while body (batch it)
    empty_process    a _process/_physics_process whose body is only `pass`

A justified exception is a trailing `# perf-lint: allow <kind> <reason>` on the line (any
kind when <kind> is `all`). Everything else is the ratchet in ci/efficiency/gd-perf.tsv: a
new key or a higher count fails, --update only lowers. It is a text scan without types, so
it is a guard for new code, not a proof.
"""
import fnmatch
import os
import re
import sys
import effgate

DEFAULT_COLD = (r"^(_init|_ready|_enter_tree|_exit_tree|_notification|_to_string|_get_property_list"
                r"|_validate_property|_on_.*|on_.*|setup.*|_setup.*|build.*|_build.*|configure.*|_configure.*"
                r"|load.*|_load.*|make_.*|_make_.*|create.*|_create.*|reset.*|_reset.*|register.*|_register.*"
                r"|bind.*|_bind.*|unbind.*|rebind.*|_rebind.*|teardown.*|clear.*|_clear.*|describe.*|dump.*"
                r"|debug.*|_debug.*|report.*|_report.*|install.*|_install.*|attach.*|_attach.*)$")

TYPING = ("untyped_var", "untyped_param", "no_return_type", "untyped_array")

HOT_PATTERNS = [
    ("node_lookup", re.compile(r"(?<![\w\"'])\$[\w\"'/%]|\bget_node(?:_or_null)?\s*\(|\bfind_childre?n?\s*\("
                               r"|\bget_(?:first_)?nodes?_in_group\s*\(")),
    ("alloc", re.compile(r"(?:[=(,:]|\breturn)\s*[\[{]|^\s*[\[{]|\b(?:Array|Dictionary|StringName)\s*\("
                         r"|\.duplicate\s*\(|\bPhysics(?:Ray|Shape|Point)QueryParameters3D\.(?:create|new)\s*\(")),
    ("string_build", re.compile(r"\b(?:print|prints|printt|printerr|printraw|print_debug|print_rich)\s*\("
                                r"|\bstr\s*\(|\.format\s*\(|[\"']\s*%\s*[\w\[(]|\+=?\s*[\"']|[\"']\s*\+")),
    ("dynamic_call", re.compile(r"(?:\.|(?<![\w.]))(?:call|callv|call_deferred|emit_signal)\s*\(|\bhas_method\s*\("
                                r"|\.(?:get|set)\s*\(\s*&?[\"']|\bCallable\s*\(|\.bind\s*\(")),
    ("singleton_lookup", re.compile(r"\bEngine\.get_singleton\s*\(|\bget_world_3d\s*\(\s*\)|\.direct_space_state\b"
                                    r"|(?<![\w.])get_tree\s*\(|\bProjectSettings\.get_setting\s*\(")),
]
EMIT = re.compile(r"\.emit\s*\(")
LOOP = re.compile(r"^\s*(?:for|while)\b")
GUARD = re.compile(r"^\s*(?:el)?if\b.*(?:debug|verbose|log|trace|dbg|print|probe)", re.I)
ALLOW = re.compile(r"#\s*perf-lint:\s*allow\s+(\w+)")
VAR = re.compile(r"^\s*(?:@\w+(?:\([^)]*\))?\s+)*(?:static\s+)?var\s+\w+\s*(.*)$")
FUNC_HEAD = re.compile(r"^\s*(?:static\s+)?func\s+(\w+)\s*\(")
BARE_ARRAY = re.compile(r"(?::|->)\s*(?:Array|Dictionary)\b(?!\s*\[)")


def read_hot(path):
    globs, cold, extra = [], DEFAULT_COLD, []
    if not os.path.isfile(path):
        return globs, re.compile(cold)
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.split("#", 1)[0].strip()
            if not ln:
                continue
            if ln.startswith("cold+:"):
                extra.append(ln[6:].strip())
            elif ln.startswith("cold:"):
                cold = ln[5:].strip()
            else:
                globs.append(ln)
    return globs, re.compile("|".join(["(?:%s)" % cold] + ["^(?:%s)$" % e for e in extra]))


def allowed(raw, kind):
    m = ALLOW.search(raw)
    return bool(m) and m.group(1) in (kind, "all")


def signature(lines, i):
    """(text between the parens, text after them, last line index) of the func at line i."""
    text, depth, j = "", 0, i
    started = False
    while j < len(lines):
        c = effgate.code_of(lines[j])
        for ch in c:
            if ch == "(":
                depth += 1
                started = True
            elif ch == ")":
                depth -= 1
        text += c + " "
        if started and depth <= 0:
            break
        j += 1
    a = text.find("(")
    depth, b = 0, a
    for k in range(a, len(text)):
        if text[k] == "(":
            depth += 1
        elif text[k] == ")":
            depth -= 1
            if depth == 0:
                b = k
                break
    return text[a + 1:b], text[b + 1:], j


def split_params(s):
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return [p.strip() for p in out if p.strip()]


def guarded(lines, a, i):
    """Whether an enclosing block header of line i (inside the function starting at a) is a debug if."""
    ind = effgate.indent_of(lines[i])
    for j in range(i - 1, a, -1):
        t = lines[j]
        if not t.strip() or t.lstrip().startswith("#"):
            continue
        ti = effgate.indent_of(t)
        if ti < ind:
            if GUARD.match(effgate.code_of(t)):
                return True
            ind = ti
    return False


def in_loop(lines, a, i):
    ind = effgate.indent_of(lines[i])
    for j in range(i - 1, a, -1):
        t = lines[j]
        if not t.strip() or t.lstrip().startswith("#"):
            continue
        ti = effgate.indent_of(t)
        if ti < ind:
            if LOOP.match(t):
                return True
            ind = ti
    return False


def scan_file(rel, lines, cold):
    cur = {}

    def add(func, kind, raw):
        if allowed(raw, kind):
            return
        k = "%s::%s::%s" % (rel, func, kind)
        cur[k] = cur.get(k, 0) + 1

    funcs = effgate.functions(lines)
    owner = {}
    for name, a, b in funcs:
        for i in range(a, b + 1):
            owner.setdefault(i, (name, a, b))  # outermost function owns a nested class's lines
    sig_end = {}
    for name, a, b in funcs:
        params, after, j = signature(lines, a)
        sig_end[a] = j
        raw = lines[a]
        for p in split_params(params):
            if ":" not in p:
                add(name, "untyped_param", raw)
        if "->" not in after:
            add(name, "no_return_type", raw)
        if BARE_ARRAY.search(params + " " + after.split(":")[0] if "->" in after else params):
            add(name, "untyped_array", raw)
    for i, raw in enumerate(lines):
        code = effgate.code_of(raw)
        if not code.strip():
            continue
        fn = owner.get(i)
        fname = fn[0] if fn else "<members>"
        if fn and fn[1] <= i <= sig_end.get(fn[1], fn[1]):
            continue  # the signature, counted above
        m = VAR.match(code)
        if m:
            rest = m.group(1).strip()
            if not rest.startswith(":"):
                add(fname, "untyped_var", raw)
            elif BARE_ARRAY.search(rest.split("=")[0] if not rest.startswith(":=") else ""):
                add(fname, "untyped_array", raw)
        if not fn or cold.match(fn[0]):
            continue
        name, a, b = fn
        for kind, rx in HOT_PATTERNS:
            if rx.search(code):
                if kind == "alloc" and VAR.match(code) is None and re.search(r"\b(?:const|enum)\b", code):
                    continue
                if kind == "string_build" and guarded(lines, a, i):
                    continue
                add(name, kind, raw)
        if EMIT.search(code) and in_loop(lines, a, i):
            add(name, "emit_in_loop", raw)
    for name, a, b in funcs:
        if name in ("_process", "_physics_process"):
            body = [effgate.code_of(l).strip() for l in lines[sig_end[a] + 1:b + 1]]
            body = [l for l in body if l]
            if body == ["pass"] or not body:
                add(name, "empty_process", lines[a])
    return cur


def measure(root, hot_path):
    globs, cold = read_hot(hot_path)
    cur = {}
    if not globs:
        return cur
    for rel in effgate.gd_files(root):
        if not any(fnmatch.fnmatch(rel, g) for g in globs):
            continue
        cur.update(scan_file(rel, effgate.read_lines(root, rel), cold))
    return cur


def by_file(cur):
    files = {}
    for k, v in cur.items():
        path, _, kind = k.split("::")
        row = files.setdefault(path, {})
        row[kind] = row.get(kind, 0) + v
    kinds = sorted({k for r in files.values() for k in r})
    print("%-44s %6s  %s" % ("file", "total", "  ".join(kinds)))
    for path, row in sorted(files.items(), key=lambda kv: -sum(kv[1].values())):
        print("%-44s %6d  %s" % (path, sum(row.values()), "  ".join("%s=%d" % (k, row[k]) for k in kinds if k in row)))


def main():
    p = effgate.make_parser(__doc__.split("\n")[0], "ci/efficiency/gd-perf.tsv")
    p.add_argument("--hot", default=None, help="hot list (default: <dir>/ci/efficiency/gd-perf-hot.txt)")
    p.add_argument("--by-file", action="store_true", help="print totals per file and kind, then gate")
    a = p.parse_args()
    cur = measure(a.dir, a.hot or os.path.join(a.dir, "ci/efficiency/gd-perf-hot.txt"))
    if a.by_file:
        by_file(cur)
    return effgate.run_gate(a, cur, "gd-perf", "sites")


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Compare one perf-smoke result with its budget file. Used by perf-smoke.sh.

    perf-budget.py check|init|update <budget.json> <tolerance-pct> '<result json>'

Lower is better for every metric. Timed metrics get 2.5x the tolerance (run-to-run noise). `check` fails when a metric exceeds budget by more than the
tolerance; `update` lowers budgets and never raises one, the same ratchet as the other gates.

Node count and memory are the same on every machine, so they are checked everywhere. Load and
frame time depend on the machine, so they are checked only on the kind of host the budget was
timed on (the budget's "host", "local" when absent: rollout-caller.sh records budgets under
`heavy`). Elsewhere, such as a GitHub-hosted runner timing a budget from a dev box, they are
printed and not compared. PERF_HOST names this run's host; the default is "github-runner" under
GitHub Actions and "local" otherwise.
"""
import json
import os
import sys

METRICS = ("load_ms", "frame_ms", "nodes", "mem_mb")
# Timings move 30% between identical runs on a loaded box; counts and memory do not.
TIMED = ("load_ms", "frame_ms")
TIMED_FACTOR = 2.5


def this_host():
    if os.environ.get("PERF_HOST"):
        return os.environ["PERF_HOST"]
    return "github-runner" if os.environ.get("GITHUB_ACTIONS") == "true" else "local"


def main():
    mode, path, tol, raw = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
    cur = json.loads(raw)
    host = this_host()
    new = {k: cur[k] for k in ("scene",) + METRICS}
    new["host"] = host
    if mode == "init":
        if os.path.exists(path):
            print("perf-smoke: %s exists; use --update" % path)
            return 1
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(new, open(path, "w"), indent=2)
        print("wrote %s: %s" % (path, json.dumps(new)))
        return 0
    try:
        bud = json.load(open(path))
    except OSError:
        print("perf-smoke: no budget at %s (run --init); this run: %s" % (path, raw))
        return 1
    timed_here = bud.get("host", "local") == host
    bad = []
    for k in METRICS:
        limit = bud[k] * (1 + tol * (TIMED_FACTOR if k in TIMED else 1) / 100.0)
        if k in TIMED and not timed_here:
            print("%-9s %9s  budget %9s  not compared: timed on %s, this run on %s"
                  % (k, cur[k], bud[k], bud.get("host", "local"), host))
            continue
        print("%-9s %9s  budget %9s  limit %9.3f" % (k, cur[k], bud[k], limit))
        if cur[k] > limit:
            bad.append(k)
    if mode == "update":
        for k in METRICS:
            if timed_here or k not in TIMED:
                bud[k] = min(bud[k], cur[k])
        json.dump(bud, open(path, "w"), indent=2)
        print("updated %s" % path)
    if bad:
        print("perf-smoke: REGRESSED %s (> %g%% over budget)" % (", ".join(bad), tol))
        return 1
    print("perf-smoke: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())

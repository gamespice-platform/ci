#!/usr/bin/env bash
# Headless perf smoke for a project: load time, frame time, node count and memory after N
# seconds, compared with a budget recorded in the project (ci/perf/smoke.json).
# Usage: perf-smoke.sh [--init|--update] [--scene res://x.tscn] [--seconds N] [--tolerance PCT] <project-dir>
#   (no flag)  fail when a metric is more than PCT (default 20) over the budget
#   --init     write the budget from this run (refuses to overwrite)
#   --update   lower the budget where this run is better; never raises one
# Scene: --scene, else the budget's "scene", else the project's main scene. The budget's "env"
# (a JSON object, written by --env KEY=VALUE, repeatable, on --init) is exported to the run, so a
# game pins what its scene picks at random (a map) and CI and local runs load the same thing.
# Budgets without "scene"/"env" work as before. GODOT picks the runtime (default: godot).
# Frame time is the engine's process time with rendering off, so it is a CPU-side ratchet
# for scripts and node count, not a measure of what a GPU does. Run it through `heavy`.
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mode=check scene="" seconds=5 tol=20 envs=()
while [ $# -gt 1 ]; do
    case "$1" in
        --init) mode=init; shift ;;
        --update) mode=update; shift ;;
        --scene) scene="$2"; shift 2 ;;
        --seconds) seconds="$2"; shift 2 ;;
        --env) envs+=("$2"); shift 2 ;;
        --tolerance) tol="$2"; shift 2 ;;
        *) break ;;
    esac
done
dir="${1:?usage: perf-smoke.sh [options] <project-dir>}"
[ -f "$dir/project.godot" ] || { echo "perf-smoke: $dir has no project.godot" >&2; exit 2; }
budget="$dir/ci/perf/smoke.json"
if [ -z "$scene" ] && [ -f "$budget" ]; then
    scene="$(python3 "$here/perf-budget.py" read "$budget" scene)" || exit 2
fi
if [ -z "$scene" ]; then
    scene="$(sed -n 's/^run\/main_scene="\(.*\)"/\1/p' "$dir/project.godot" | head -1)"
fi
case "$scene" in res://uid://*|uid://*) echo "perf-smoke: pass --scene (main scene is a uid)" >&2; exit 2 ;; esac
[ -n "$scene" ] || { echo "perf-smoke: no main scene; pass --scene" >&2; exit 2; }

log="$(mktemp)"
trap 'rm -f "$log"' EXIT
pinned=()
if [ -f "$budget" ]; then
    mapfile -t pinned < <(python3 "$here/perf-budget.py" read "$budget" env) || exit 2
fi
(cd "$dir" && env "${pinned[@]}" "${envs[@]}" timeout $((seconds + 120)) "${GODOT:-godot}" --headless --path . --script "$here/perf_smoke.gd" -- "$scene" "$seconds") >"$log" 2>&1
line="$(grep '^PERF_SMOKE ' "$log" | tail -1 | cut -d' ' -f2-)"
if [ -z "$line" ]; then
    echo "perf-smoke: no result"; tail -5 "$log"; exit 1
fi
if grep -q 'SCRIPT ERROR\|Parse Error' "$log"; then
    echo "perf-smoke: script errors while running"; grep 'SCRIPT ERROR\|Parse Error' "$log" | head -5; exit 1
fi
PERF_ENV="$(printf '%s\n' "${envs[@]}")" exec python3 "$here/perf-budget.py" "$mode" "$budget" "$tol" "$line"

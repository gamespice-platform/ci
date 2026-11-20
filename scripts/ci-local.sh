#!/usr/bin/env bash
#
# Run the check exactly as GitHub CI will, before pushing.
#
#   scripts/ci-local.sh <project-dir> [--parse]
#
# WHY THIS EXISTS. `game.sh test` and a plain check.sh run in the working checkout, whose
# addons/ are symlinks to sibling working trees: whatever commit, branch, dirty edit or
# stale pull each happens to hold. CI runs the COMMITTED tree with every addon freshly
# cloned from the tip of its default branch (resolve-deps.sh), the suite timeout from the
# caller's ci.yml, and the suites it names. Those differ, and the difference is where
# "green here, red in CI" lives. 2026-11-20: zee-dot-weapons main named two new weapon
# models; each game that vendors a copy of that art went red in CI while its last local
# run, made before the addon moved, was green.
#
# So this clones HEAD of the project into a scratch directory (uncommitted edits are
# NOT tested: commit first, as the push would), resolves the addons the way CI does,
# takes suite-timeout and suites from .github/workflows/ci.yml, and calls check.sh.
#
# Environment: GODOT (default godot), KEEP=1 keeps the scratch directory.
# Under hv: sudo -u gamedev hv <worktree> local scripts/ci-local.sh <dir>
set -uo pipefail

SELF="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
PROJECT="${1:-.}"
[ -d "$PROJECT" ] || { printf 'no such directory: %s\n' "$PROJECT" >&2; exit 2; }
PROJECT="$(cd "$PROJECT" && pwd)"
git -C "$PROJECT" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
    || { printf '%s is not a git checkout\n' "$PROJECT" >&2; exit 2; }

if [ -n "$(git -C "$PROJECT" status --porcelain --untracked-files=no)" ]; then
    printf 'note: uncommitted edits are not part of this run (CI sees commits only)\n' >&2
fi

WORK="$(mktemp -d)"
[ -n "${KEEP:-}" ] || trap 'rm -rf "$WORK"' EXIT
git clone -q --no-hardlinks "$PROJECT" "$WORK/project" || exit 2
git -C "$WORK/project" checkout -q "$(git -C "$PROJECT" rev-parse HEAD)" || exit 2
printf 'ci-local: %s at %s\n' "$(basename "$PROJECT")" "$(git -C "$PROJECT" rev-parse --short HEAD)"

# The inputs the caller passes to validate.yml. Absent means the workflow's default.
WF="$WORK/project/.github/workflows/ci.yml"
input() {
    [ -f "$WF" ] || return 0
    sed -nE "s/^[[:space:]]+$1:[[:space:]]*['\"]?([^'\"#]*[^'\"# ])['\"]?[[:space:]]*(#.*)?$/\1/p" "$WF" | head -1
}
st="$(input suite-timeout)"; su="$(input suites)"
export SUITE_TIMEOUT="${st:-300}"
export SUITES="${su:-}"
printf 'ci-local: suite-timeout %s, suites: %s\n' "$SUITE_TIMEOUT" "${SUITES:-auto-detect}"

"$SELF/resolve-deps.sh" "$WORK/project" \
    || { printf 'ci-local: dependency resolution failed, as it would in CI\n' >&2; exit 1; }
"$SELF/check.sh" "$WORK/project" ${2:+"$2"}

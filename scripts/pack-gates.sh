#!/usr/bin/env bash
#
# Build the pack release.yml would build and run its two artifact gates on it, before a tag.
#
#   scripts/pack-gates.sh <project-dir> [options]
#
#   --compat strict|advisory|off   server-compat.sh: strict fails (default), advisory warns
#                                  (a ::warning:: annotation and a step-summary line, exit 0),
#                                  off skips it
#   --deny REGEX                   release.yml's `pack-deny`
#   --exclude-dirs "A B"           release.yml's `pack-exclude-dirs`
#   --owned-addons                 release.yml's `pack-owned-addons`
#   --host-lock PATH               release.yml's `host-lock` (relative to the project)
#   --from-release-yml             read the inputs above from the project's
#                                  .github/workflows/release.yml (the job that calls release.yml)
#   --no-import                    the project is already imported (validate.yml's check.sh did it)
#
# WHY. release.yml refuses a pack that fails check-pack-static.py or server-compat.sh, and
# runs only after the tag is pushed, so a red release was found an hour after tagging.
# validate.yml calls this on every push: the static gate is a real defect that always fails
# the release (hard); server-compat is `advisory` there because an addon that is not yet
# tagged is the normal state of main and only blocks at tag time. scripts/pre-tag.sh runs
# it strict. The pack is built by the same package.sh with the same flags release.yml
# passes; release.yml itself is unchanged and stays the final authority.
#
# Environment: GODOT (the runtime, default `godot`), DEPS_TOKEN (server-compat, private repos).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="${1:-}"
[ -n "$PROJECT" ] && [ -d "$PROJECT" ] || { echo "usage: $0 <project-dir> [options]" >&2; exit 2; }
shift
PROJECT="$(cd "$PROJECT" && pwd)"

COMPAT=strict DENY="" EXCLUDE="" OWNED=0 HOST_LOCK_IN="" IMPORT=1 FROM_YML=0
while [ $# -gt 0 ]; do
    case "$1" in
        --compat) COMPAT="${2:-}"; shift 2 ;;
        --deny) DENY="${2:-}"; shift 2 ;;
        --exclude-dirs) EXCLUDE="${2:-}"; shift 2 ;;
        --owned-addons) OWNED=1; shift ;;
        --host-lock) HOST_LOCK_IN="${2:-}"; shift 2 ;;
        --from-release-yml) FROM_YML=1; shift ;;
        --no-import) IMPORT=0; shift ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done
case "$COMPAT" in strict|advisory|off) ;; *) echo "--compat: strict|advisory|off" >&2; exit 2 ;; esac

if [ "$FROM_YML" = 1 ]; then
    yml="$PROJECT/.github/workflows/release.yml"
    [ -f "$yml" ] || { echo "no $yml" >&2; exit 2; }
    # One line per input: pack, deny, exclude, owned, host-lock, server-compat.
    mapfile -t got < <(python3 - "$yml" <<'PY'
import sys, yaml
doc = yaml.safe_load(open(sys.argv[1]))
w = {}
for job in (doc.get("jobs") or {}).values():
    if "release.yml" in str(job.get("uses", "")):
        w = job.get("with") or {}
for k, d in (("pack", False), ("pack-deny", ""), ("pack-exclude-dirs", ""),
             ("pack-owned-addons", False), ("host-lock", ""), ("server-compat", True)):
    v = w.get(k, d)
    print(str(v).lower() if isinstance(v, bool) else v)
PY
)
    [ "${got[0]:-}" = true ] || { echo "release.yml does not set pack: true: no pack, nothing to check"; exit 0; }
    DENY="${got[1]}"; EXCLUDE="${got[2]}"
    [ "${got[3]}" = true ] && OWNED=1
    HOST_LOCK_IN="${got[4]}"
    [ "${got[5]}" = false ] && COMPAT=off
fi

GODOT="${GODOT:-godot}"
if [ "$IMPORT" = 1 ]; then
    echo "importing $PROJECT" >&2
    timeout 600 "$GODOT" --headless --path "$PROJECT" --import >/dev/null 2>&1 || true
fi

OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT
args=(--pack)
for d in $EXCLUDE; do args+=(--exclude-dir "$d"); done
[ "$OWNED" = 1 ] && args+=(--pack-owned-addons)
[ -n "$HOST_LOCK_IN" ] && args+=(--host-lock "$PROJECT/$HOST_LOCK_IN")
"$HERE/package.sh" "$PROJECT" 0.0.0-pregate --out "$OUT/dist" --name "$(basename "$PROJECT")" "${args[@]}" >/dev/null \
    || { echo "::error::the pack did not build (package.sh --pack failed)"; exit 1; }

shopt -s nullglob
zips=("$OUT"/dist/*-pack.zip)
[ "${#zips[@]}" -gt 0 ] || { echo "::error::package.sh --pack made no pack zip"; exit 1; }

rc=0
sargs=()
[ -n "$DENY" ] && sargs+=(--deny "$DENY")
python3 "$HERE/check-pack-static.py" "${sargs[@]}" "${zips[@]}" || { echo "::error::pack-static gate failed: release.yml would refuse this pack"; rc=1; }

note() { [ -n "${GITHUB_STEP_SUMMARY:-}" ] && printf '%s\n' "$1" >> "$GITHUB_STEP_SUMMARY"; return 0; }
if [ "$COMPAT" != off ]; then
    log="$OUT/compat.log"
    crc=0
    for z in "${zips[@]}"; do "$HERE/server-compat.sh" "$z" >>"$log" 2>&1 || crc=1; done
    cat "$log"
    if [ "$crc" = 1 ]; then
        reason="$(grep -v '^\s*$' "$log" | tail -1 | sed 's/^ *//')"
        if [ "$COMPAT" = strict ]; then
            echo "::error::server-compat gate failed: the newest released server cannot run this pack"
            rc=1
        else
            echo "::warning::server-compat: no released server can run this pack yet ($reason). Normal on main; it blocks at tag time (scripts/pre-tag.sh, release.yml)."
            note "**server-compat (advisory):** not satisfied: $reason. Tag the addon, bump and release the server first."
        fi
    else
        note "server-compat: ok"
    fi
fi
exit $rc

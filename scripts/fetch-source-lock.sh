#!/usr/bin/env bash
#
# Restore the binaries a repository does not track in git, from its source.lock.json.
#
#   scripts/fetch-source-lock.sh <dir> <gs-cloud-dir>
#
# <dir> holds source.lock.json (gs-cloud tools/publish_pack.sh --source-lock). Each file the lock
# names is downloaded by hash from the CDN into <dir> and verified, via gs-cloud's
# tools/lock_verify.sh --fetch (docs/source-lock.md in gs-cloud). A directory without the lock needs
# nothing and exits 0; a lock with no fetcher, or a download that does not verify, fails.
set -uo pipefail

DIR="${1:?usage: fetch-source-lock.sh <dir> <gs-cloud-dir>}"
CLOUD="${2:?usage: fetch-source-lock.sh <dir> <gs-cloud-dir>}"

[ -f "$DIR/source.lock.json" ] || { printf 'no source.lock.json in %s, nothing to restore\n' "$DIR"; exit 0; }
tool="$CLOUD/tools/lock_verify.sh"
[ -x "$tool" ] || [ -f "$tool" ] || { printf 'FAIL  %s has a source.lock.json and %s is missing\n' "$DIR" "$tool" >&2; exit 2; }
bash "$tool" --lock "$DIR/source.lock.json" --fetch "$DIR"

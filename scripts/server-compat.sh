#!/usr/bin/env bash
#
# Refuse a game pack that no released server could run.
#
#   scripts/server-compat.sh <requires.json | pack.zip>
#   scripts/server-compat.sh <requires.json | pack.zip> --server-ref v0.1.8
#
# WHY A RELEASE HAS TO ASK THIS
#
# A game pack says which gs-* addon API levels it was built against (requires.json, see
# GameSpice Core's GSAddonApi). A server checks that list before mounting the pack and refuses
# one it cannot satisfy -- correctly, and too late: by then the pack is published, the
# site offers it, and a server that restarts onto it boots into "This game needs
# GameSpice Platform API level 3 or newer; this server has level 2". That happened on
# 2026-10-04 with game-airdrift v0.1.5, because the addon release it needed existed only
# as untagged commits when the game was tagged.
#
# So the same rule is asked here, of the newest RELEASED server: the addons.lock of
# gamespice-platform/server-deploy's highest v* tag names the ref of every addon a box
# installs, and each addon's level is the `const LEVEL` / `const OLDEST` in its
# addons/<addon>/<addon>_api.gd at that ref (absent means 1, as GSAddonApi reads it).
# A game passes when, for every addon it names: the lock has it, need <= LEVEL, and
# need >= OLDEST.
#
# The newest released server is the newest tag whose PINNED CLIENT BUILD was exported
# from its own lock. A game pack carries no addons and runs on the ones compiled into
# the client build its server names (web/shell-build); a tag whose lock moved past that
# build is refused at Play however new its lock is. The server repository records
# sha256 of the lock its pinned build came from in web/shell-build.inputs, and a tag
# whose record disagrees is skipped (a tag with no record predates it and counts). The fix for a failure is never here -- it is to tag the addon, bump the
# lock, and release GameSpice Server Deploy, then re-tag the game.
#
# Environment:
#   SERVER_REPO   default gamespice-platform/server-deploy
#   DEPS_TOKEN    optional; read access for private repositories (never printed)
#   GS_OWNER     default gamespice-platform (the addons; repositories drop the dot- prefix)
#   GAME_OWNER    default zees-games     (zee-dot-weapons and zed-dot-weapons, the addons that are not)
set -uo pipefail

INPUT="${1:-}"
[ -n "$INPUT" ] && [ -f "$INPUT" ] || { printf 'usage: %s <requires.json|pack.zip> [--server-ref TAG]\n' "$0" >&2; exit 2; }
shift

SERVER_REF=""
while [ $# -gt 0 ]; do
    case "$1" in
        --server-ref) SERVER_REF="${2:-}"; shift 2 ;;
        *) printf 'unknown argument: %s\n' "$1" >&2; exit 2 ;;
    esac
done

export INPUT SERVER_REF
export SERVER_REPO="${SERVER_REPO:-gamespice-platform/server-deploy}"
export GS_OWNER="${GS_OWNER:-${DOT_OWNER:-gamespice-platform}}"
export GAME_OWNER="${GAME_OWNER:-zees-games}"

exec python3 - <<'PY'
import hashlib, json, os, re, subprocess, sys, urllib.error, urllib.request, zipfile

inp = os.environ["INPUT"]
if inp.endswith(".zip"):
    with zipfile.ZipFile(inp) as z:
        if "requires.json" not in z.namelist():
            print(f"  --   {os.path.basename(inp)} carries no requires.json; nothing to check")
            sys.exit(0)
        requires = json.loads(z.read("requires.json"))
else:
    requires = json.load(open(inp))

needs = {str(k): int(v) for k, v in (requires.get("addons") or {}).items()}
token = os.environ.get("DEPS_TOKEN", "")
repo = os.environ["SERVER_REPO"]


def fetch(owner_repo, ref, path):
    url = f"https://raw.githubusercontent.com/{owner_repo}/{ref}/{path}"
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"token {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


ref = os.environ.get("SERVER_REF", "")
if not ref:
    # The highest v<major>.<minor>.<patch> tag: what a box installed today gets. A tag
    # rather than main, because main can be ahead of anything a box has.
    url = f"https://{'x-access-token:' + token + '@' if token else ''}github.com/{repo}.git"
    out = subprocess.run(["git", "ls-remote", "--tags", url], capture_output=True, text=True)
    if out.returncode != 0:
        print(f"  FAIL  could not list {repo}'s tags", file=sys.stderr)
        sys.exit(1)
    tags = set(re.findall(r"refs/tags/(v\d+\.\d+\.\d+)$", out.stdout, re.M))
    if not tags:
        print(f"  FAIL  {repo} has no release tags", file=sys.stderr)
        sys.exit(1)
    ordered = sorted(tags, key=lambda t: tuple(int(x) for x in t[1:].split(".")), reverse=True)
else:
    ordered = [ref]


def shell_matches(ref, lock_text):
    """Whether the client build the server at `ref` pins was exported from its lock.

    A game pack carries no addons: it runs on the addon code compiled into the client
    build the server names, so a release whose lock moved past its pinned build is one
    no game built on the new lock can be played on, whatever the lock says. The server
    repository records sha256 of the lock its pinned build was exported from in
    web/shell-build.inputs (a `lock<TAB><sha256>` line). No record means a release from
    before the record existed, which is taken as it always was.
    """
    record = fetch(repo, ref, "web/shell-build.inputs")
    if record is None:
        return True
    want = hashlib.sha256(lock_text.encode()).hexdigest()
    return f"lock\t{want}" in record.splitlines()


lock_text = None
explicit = bool(os.environ.get("SERVER_REF", ""))
for candidate in ordered:
    text = fetch(repo, candidate, "addons.lock")
    if text is None:
        print(f"  FAIL  {repo}@{candidate} has no addons.lock", file=sys.stderr)
        sys.exit(1)
    if shell_matches(candidate, text):
        ref, lock_text = candidate, text
        break
    if explicit:
        print(f"  FAIL  {repo}@{candidate}: its pinned client build was not exported from its addons.lock", file=sys.stderr)
        sys.exit(1)
    print(f"  --    {repo}@{candidate}: its pinned client build was not exported from its lock; not a release players can use, skipped")

if lock_text is None:
    print(f"  FAIL  no {repo} release pins a client build exported from its own lock", file=sys.stderr)
    sys.exit(1)

lock = {}
for line in lock_text.splitlines():
    if not line.strip() or line.startswith("#"):
        continue
    parts = line.split("\t")
    if len(parts) >= 2:
        lock[parts[0]] = parts[1]


# A renamed addon directory: current -> legacy. fc-weapons (Fatal Contact's weapons) holds
# addons/fc_weapons; its tags up to v1.4.51 hold the legacy addons/arena_weapons. Which one a
# server has is decided by what its locked ref holds, never assumed.
LEGACY_DIRS = {"fc_weapons": "arena_weapons"}
CURRENT_DIRS = {old: new for new, old in LEGACY_DIRS.items()}


def repo_of(addon):
    if addon in ("fc_weapons", "arena_weapons"):
        return "fc-weapons"
    if addon in ("zee_weapons", "zed_weapons"):
        return addon.replace("_weapons", "-dot-weapons")
    return addon.replace("_", "-")


def remote_name(r):
    return r[len("dot-"):] if r.startswith("dot-") else r


def owner_of(r):
    return (os.environ.get("GS_OWNER") or os.environ["DOT_OWNER"]) if r.startswith("dot-") else os.environ["GAME_OWNER"]


def const(text, name):
    m = re.search(rf"^const\s+{name}\s*(?::\s*int)?\s*:?=\s*(\d+)", text or "", re.M)
    return max(1, int(m.group(1))) if m else None


print(f"checking {len(needs)} addon requirement(s) against {repo}@{ref}")
problems = []
for addon in sorted(needs):
    need = needs[addon]
    r = repo_of(addon)
    if r not in lock:
        problems.append(f"needs {addon}, and the server at {ref} does not install it")
        continue
    source = f"{owner_of(r)}/{remote_name(r) if owner_of(r) == (os.environ.get('GS_OWNER') or os.environ['DOT_OWNER']) else r}"
    if addon in LEGACY_DIRS or addon in CURRENT_DIRS:
        # The pack names the directory its game references; the server installs the one its
        # ref holds. Both must agree, or the game's res:// paths miss on that server.
        other = LEGACY_DIRS.get(addon) or CURRENT_DIRS.get(addon)
        if fetch(source, lock[r], f"addons/{addon}/plugin.cfg") is None:
            if fetch(source, lock[r], f"addons/{other}/plugin.cfg") is not None:
                problems.append(f"needs addons/{addon}; the server at {ref} locks {r} {lock[r]}, which holds addons/{other}")
            else:
                problems.append(f"needs addons/{addon}; {r} {lock[r]} holds neither addons/{addon} nor addons/{other}")
            continue
        if addon in CURRENT_DIRS:
            print(f"  WRN   {addon} is the legacy directory name ({r} {lock[r]}); the current one is {CURRENT_DIRS[addon]}")
    api = fetch(source, lock[r], f"addons/{addon}/{addon}_api.gd")
    have = const(api, "LEVEL") or 1
    oldest = min(const(api, "OLDEST") or 1, have)
    if need > have:
        problems.append(f"needs {addon} API level {need}; the server at {ref} locks {r} {lock[r]}, which has level {have}")
    elif need < oldest:
        problems.append(f"was built for {addon} API level {need}; {r} {lock[r]} supports {oldest} to {have}")
    else:
        print(f"  ok    {addon} {need} (server has {have}, {r} {lock[r]})")

if problems:
    for p in problems:
        print(f"  FAIL  {p}")
    print(
        "\nNo released server can run this pack. Tag the addon it needs, bump "
        f"{repo}'s addons.lock to that tag and release it, then tag this game again."
    )
    sys.exit(1)

print(f"every requirement is met by {repo}@{ref}")
PY

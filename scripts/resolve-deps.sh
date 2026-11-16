#!/usr/bin/env bash
#
# Put the addons a project needs into its addons/, on a machine that has nothing.
#
#   scripts/resolve-deps.sh <project-dir>
#   scripts/resolve-deps.sh <project-dir> --print   name the repositories, clone nothing
#
# WHY A RUNNER NEEDS THIS AT ALL
#
# The links in addons/ are gitignored in every project here, on purpose: a consumer
# copies the addon folder into its own tree rather than depending on a checkout of
# ours. So a fresh `git clone` of any project except dot-core opens with no addons,
# and in GDScript that is not a missing-feature situation -- a script that MENTIONS a
# class_name the project does not have fails to parse, and takes every script that
# references it down with it. One unresolved addon is a hundred parse errors that name
# identifiers rather than the missing directory, which reads exactly like a broken
# repository. The whole parse pass is worthless until this has run.
#
# THE LIST IS NOT HERE, AND THAT IS THE POINT
#
# The addons a project needs come from that project's OWN .gitignore, from its
# /addons/<name> lines -- the same derivation bootstrap.sh does, for the same reason:
# the repository that gains a dependency is the repository that has to ignore the
# link, so the list maintains itself and cannot drift. A manifest in this repository
# would be a second copy of fifty-odd lists, which is the exact bug projects.tsv was
# written to stop and which this family has already shipped three times.
#
# A project with no /addons/<name> lines needs nothing (dot-core). dot-server-deploy's
# .gitignore is a bare `/addons/` -- "ignore the lot", which names nothing to link and
# must not be read as "link everything" -- and its list is its `addons.lock` instead,
# resolved at the locked refs (see below).
#
# THE OWNER SPLIT IS ENCODED HERE, AND THAT IS A THIRD COPY ON PURPOSE
#
# The addons are the organisation's and the games are their author's. projects.tsv is
# the one list that records which is which, and dot-server-deploy's setup.sh already
# carries a second copy of the RULE for the one case that cannot read that file: a
# fresh box cloning what it needs before dot-bootstrap is on it. A CI runner is the
# same case -- it has an empty disk and a token, and reaching projects.tsv would mean
# cloning dot-bootstrap first to find out where to clone dot-core from. So the rule is
# repeated, in two lines, and not the list.
#
# CREDENTIALS come from the environment and never from an argument: an argument is in
# the runner log, in the process list, and in `ps`.
#
#   DEPS_TOKEN   a token that can read the private addon repositories
#   GIT_HOST     default github.com
#   GS_OWNER    default gamespice-platform (the addons; their repositories drop the dot- prefix)
#   GAME_OWNER   default zees-games     (the games, and the weapons packs)
#
set -uo pipefail

PROJECT="${1:-.}"
MODE="${2:-clone}"

[ -d "$PROJECT" ] || { printf 'no such directory: %s\n' "$PROJECT" >&2; exit 2; }
PROJECT="$(cd "$PROJECT" && pwd -P)"

GIT_HOST="${GIT_HOST:-github.com}"
GS_OWNER="${GS_OWNER:-${DOT_OWNER:-gamespice-platform}}"
GAME_OWNER="${GAME_OWNER:-zees-games}"
DEPS_DIR="$PROJECT/.deps"

## The repository an addon directory lives in.
##
## dot_user_avatar -> dot-user-avatar, true for every link in the family except the
## weapons packs: each took a prefix (`zee_`, `zed_`) so it could sit on top of the family
## without colliding with it, and its repository is named for what it IS rather than for
## its prefix (zee-dot-weapons, zed-dot-weapons). Same exception setup.sh's addon_repo()
## carries. fc-weapons (Fatal Contact's weapons) holds addons/fc_weapons; its tags up to
## v1.4.51 hold the legacy addons/arena_weapons, which still maps here (see legacy_dir).
addon_repo() {
    case "$1" in
        zee_weapons) printf 'zee-dot-weapons\n' ;;
        zed_weapons) printf 'zed-dot-weapons\n' ;;
        fc_weapons|arena_weapons) printf 'fc-weapons\n' ;;
        *)           printf '%s\n' "${1//_/-}" ;;
    esac
}

## The legacy directory a renamed addon had, or nothing. Used only when the ref a clone is
## at actually holds that directory, and every use prints a WRN naming the ref.
legacy_dir() {
    case "$1" in
        fc_weapons) printf 'arena_weapons\n' ;;
    esac
}

## The current directory for a legacy one, or nothing.
current_dir() {
    case "$1" in
        arena_weapons) printf 'fc_weapons\n' ;;
    esac
}

## Who owns it. See the note above about why this rule is here and the list is not.
addon_owner() {
    case "$1" in
        dot-radio|dot-trail) printf '%s\n' "$GAME_OWNER" ;;
        dot-*) printf '%s\n' "$GS_OWNER" ;;
        *)     printf '%s\n' "$GAME_OWNER" ;;
    esac
}

## The name a repository has on the host. The addons live in the GS_OWNER organisation without the
## `dot-` prefix (dot-audio -> audio); the directory a clone lands in keeps the local name.
remote_name() {
    if [ "$1" = "$GS_OWNER" ]; then printf '%s\n' "${2#dot-}"; else printf '%s\n' "$2"; fi
}

# /addons/ on its own names nothing. The anchored, single-segment pattern is what
# makes that true: `/addons/` does not match `^/addons/[a-z0-9_]+$`, and a project
# that vendors its addons therefore resolves zero of them rather than all of them.
mapfile -t ADDONS < <(grep -oE '^/addons/[a-z0-9_]+$' "$PROJECT/.gitignore" 2>/dev/null \
    | sed 's|^/addons/||' | sort -u)

# [b]A project with an `addons.lock` is checked at the refs it ships, not at main.[/b]
#
# dot-server-deploy's .gitignore is a bare `/addons/` and names nothing, so until this
# existed its CI could not resolve a single addon and ran with the Godot check switched
# off -- shell syntax only. Its lock names the release tag of every addon a server
# installs, and a box clones exactly those (setup.sh). So the lock is the list, and each
# addon is cloned at its locked ref rather than at the tip of main: a check against main
# passes for a host script that calls an addon API no tag has yet, and that is precisely
# how a server came to boot with no host on 2026-10-04 while every check was green.
#
# The lock is repo<TAB>ref; the addon directory is the repository's own, by the inverse
# of addon_repo.
declare -A REF=()
LOCK="$PROJECT/addons.lock"

if [ -f "$LOCK" ]; then
    ADDONS=()
    while IFS=$'\t' read -r repo ref _; do
        [ -z "$repo" ] && continue
        case "$repo" in \#*) continue ;; esac
        case "$repo" in
            zee-dot-weapons) addon=zee_weapons ;;
            zed-dot-weapons) addon=zed_weapons ;;
            fc-weapons)      addon=fc_weapons ;;  # refs up to v1.4.51 hold the legacy arena_weapons: decided after the clone
            *)               addon="${repo//-/_}" ;;
        esac
        ADDONS+=("$addon")
        REF[$addon]="$ref"
    done < "$LOCK"
    printf 'addons from %s (%d, at their locked refs)\n' "$(basename "$LOCK")" "${#ADDONS[@]}"
fi

# [b]Content a project links from another repository, when it asks for it here.[/b]
#
# A game's maps can live in a repository of their own (playlot-maps, the mg-*
# -maps), linked in by bootstrap.sh from a comment directly above the ignored path:
#
#     # bootstrap-link: game-playground-maps/maps ci
#     /maps/custom
#
# Without the link a runner checks a game with none of its maps, and every suite that
# loads one fails -- game-playlot's CI was red for two days over twelve documents it
# could not see. The trailing `ci` is an OPT-IN, and the default is no on purpose:
# airdrift-maps is 1.8 GB, and two games link it. A link without `ci` is left to the
# suite, which is expected to cope with the directory being absent. bootstrap.sh reads
# only the third field, so the extra word costs it nothing.
#
# Each line is: path<TAB>repo<TAB>path inside the repo.
mapfile -t CONTENT < <(awk '/^# bootstrap-link: /{src=$3; ci=($4=="ci"); next}
    src!="" && ci && /^\//{p=$0; sub(/^\//,"",p); sub(/\/$/,"",p);
        r=src; sub(/\/.*/,"",r); sub_=src; sub(/^[^\/]*\/?/,"",sub_);
        print p "\t" r "\t" sub_}
    {src=""; ci=0}' "$PROJECT/.gitignore" 2>/dev/null)

if [ "${#ADDONS[@]}" -eq 0 ] && [ "${#CONTENT[@]}" -eq 0 ]; then
    printf 'no addon dependencies declared in %s/.gitignore\n' "$(basename "$PROJECT")" >&2
    exit 0
fi

if [ "$MODE" = "--print" ]; then
    for a in "${ADDONS[@]}"; do printf '%s\t%s\t%s\n' "$a" "$(addon_repo "$a")" "${REF[$a]:-default branch}"; done
    for c in "${CONTENT[@]}"; do printf 'content\t%s\n' "$c"; done
    exit 0
fi

# The token is OPTIONAL, and which way it goes is not this script's to decide. Every
# repository in the family is public as this is written, and a public clone needs no
# credential at all -- so demanding one would fail every check in the family over a
# secret nothing needs. One going private later must not need a change here either,
# which is the whole reason the caller passes a secret that is usually empty.
CREDENTIAL=""
[ -n "${DEPS_TOKEN:-}" ] && CREDENTIAL="x-access-token:${DEPS_TOKEN}@"

## Keep the token out of anything printed.
##
## A no-op when there is no token, and that case is not hypothetical -- `sed s||***|g`
## with an empty pattern replaces at EVERY position, so an unauthenticated clone
## failure would print a wall of asterisks instead of the reason it failed.
_redact() {
    if [ -n "${DEPS_TOKEN:-}" ]; then
        sed "s|${DEPS_TOKEN}|***|g"
    else
        cat
    fi
}

mkdir -p "$DEPS_DIR" "$PROJECT/addons"

# .gdignore, and it is not belt and braces. The clones land INSIDE the project, so
# Godot's import pass walks them -- and a second copy of dot-core's scripts under a
# different path does not fail as "there are two", it fails as `Class "DotResult"
# hides a global script class`, once per class, naming files that are all correct.
# A dot-prefixed directory being skipped is the editor's behaviour and not a promise;
# this file is the documented way to say it, and it costs nothing.
printf '' > "$DEPS_DIR/.gdignore"

fails=0

for addon in "${ADDONS[@]}"; do
    repo="$(addon_repo "$addon")"
    owner="$(addon_owner "$repo")"
    ref="${REF[$addon]:-}"
    # A locked clone is kept under its ref, so a cache from another lock (or from a
    # main-branch run) is never mistaken for it.
    clone="$repo${ref:+@$ref}"

    if [ ! -d "$DEPS_DIR/$clone/.git" ]; then
        # --depth 1: CI wants the files, never the history, and dot-core's history is
        # larger than every addon it ships. The token is interpolated into the URL
        # rather than passed as an argument so it is never a separate word anything
        # logs; git itself keeps it out of the error text.
        if ! err="$(git clone --quiet --depth 1 ${ref:+--branch "$ref"} \
            "https://${CREDENTIAL}${GIT_HOST}/${owner}/$(remote_name "$owner" "$repo").git" \
            "$DEPS_DIR/$clone" 2>&1)"; then
            # git echoes the URL it was given, and the URL carries the token. Redacted
            # here rather than discarded: a clone failure with no reason printed is
            # half an hour of guessing between "the token cannot see it", "the
            # repository is not created yet" and "the name is wrong", and those want
            # three different fixes.
            printf '  FAIL  could not clone %s/%s%s (for addons/%s)\n        %s\n' \
                "$owner" "$repo" "${ref:+ at $ref}" "$addon" \
                "$(printf '%s' "$err" | _redact | tr '\n' ' ')" >&2
            fails=$((fails + 1))
            continue
        fi
    fi

    # A renamed addon is linked under the directory its ref HOLDS, because its own res://
    # paths name that directory. fc-weapons tags up to v1.4.51 hold addons/arena_weapons,
    # later ones addons/fc_weapons. Never an alias: a game naming one directory and a ref
    # holding the other is a FAIL (the game or the pin has to move), and the legacy name
    # is always reported.
    if [ ! -d "$DEPS_DIR/$clone/addons/$addon" ]; then
        old="$(legacy_dir "$addon")"; new="$(current_dir "$addon")"
        if [ -n "$old" ] && [ -n "${REF[$addon]:-}" ] && [ -d "$DEPS_DIR/$clone/addons/$old" ]; then
            printf '  WRN   %s at %s holds the legacy addons/%s, not addons/%s; linked as addons/%s (deprecated: pin a ref that holds addons/%s)\n' \
                "$repo" "$ref" "$old" "$addon" "$old" "$addon" >&2
            addon="$old"
        elif [ -n "$old" ] && [ -d "$DEPS_DIR/$clone/addons/$old" ]; then
            printf '  FAIL  %s names addons/%s, but %s%s still holds the legacy addons/%s\n' \
                "$(basename "$PROJECT")" "$addon" "$repo" "${ref:+ at $ref}" "$old" >&2
            fails=$((fails + 1))
            continue
        elif [ -n "$new" ] && [ -d "$DEPS_DIR/$clone/addons/$new" ]; then
            printf '  FAIL  %s names the legacy addons/%s, but %s%s holds addons/%s: rename it in the project\n' \
                "$(basename "$PROJECT")" "$addon" "$repo" "${ref:+ at $ref}" "$new" >&2
            fails=$((fails + 1))
            continue
        else
            printf '  FAIL  %s has no addons/%s\n' "$clone" "$addon" >&2
            fails=$((fails + 1))
            continue
        fi
    elif [ -n "$(current_dir "$addon")" ]; then
        printf '  WRN   addons/%s is the legacy name (%s%s); the current one is addons/%s\n' \
            "$addon" "$repo" "${ref:+ at $ref}" "$(current_dir "$addon")" >&2
    fi

    # Replaced unconditionally. A stale link, or a regular file a checkout on a machine
    # without symlink support left behind, both have to go -- and the second is not
    # hypothetical: Git writes the link's TARGET PATH into a text file when it cannot
    # make one, and Godot then reads a one-line text file where a directory should be
    # and registers not one class_name.
    rm -rf "${PROJECT:?}/addons/$addon"
    ln -s "../.deps/$clone/addons/$addon" "$PROJECT/addons/$addon"
    printf '  linked addons/%s -> %s\n' "$addon" "$clone"
done

printf '%d addon(s) declared, %d failed\n' "${#ADDONS[@]}" "$fails"

for line in "${CONTENT[@]}"; do
    IFS=$'\t' read -r path repo inner <<< "$line"
    owner="$(addon_owner "$repo")"
    if [ ! -d "$DEPS_DIR/$repo/.git" ]; then
        if ! err="$(git clone --quiet --depth 1 \
            "https://${CREDENTIAL}${GIT_HOST}/${owner}/$(remote_name "$owner" "$repo").git" \
            "$DEPS_DIR/$repo" 2>&1)"; then
            printf '  FAIL  could not clone %s/%s (for %s)\n        %s\n' \
                "$owner" "$repo" "$path" "$(printf '%s' "$err" | _redact | tr '\n' ' ')" >&2
            fails=$((fails + 1))
            continue
        fi
    fi
    target="$DEPS_DIR/$repo${inner:+/$inner}"
    if [ ! -d "$target" ]; then
        printf '  FAIL  %s has no %s\n' "$repo" "${inner:-root}" >&2
        fails=$((fails + 1))
        continue
    fi
    # A relative link, like the addons', climbing out of the directory the link sits
    # in: maps/custom sits in maps/, so ../.deps/...; a top-level courses, ./.deps/...
    parent="$(dirname "$path")"
    up="."
    [ "$parent" != "." ] && up="$(printf '%s' "$parent" | sed 's|[^/][^/]*|..|g')"
    mkdir -p "$(dirname "$PROJECT/$path")"
    rm -rf "${PROJECT:?}/$path"
    ln -s "$up/.deps/$repo${inner:+/$inner}" "$PROJECT/$path"
    printf '  linked %s -> %s%s\n' "$path" "$repo" "${inner:+/$inner}"
done

[ "${#CONTENT[@]}" -gt 0 ] && printf '%d content link(s)\n' "${#CONTENT[@]}"
exit $((fails > 0))

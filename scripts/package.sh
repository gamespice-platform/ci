#!/usr/bin/env bash
#
# Build the artifact a release attaches, out of a checkout.
#
#   scripts/package.sh <project-dir> <version> [--out DIR]
#
# Prints one artifact path per line on stdout. Everything said to a person goes to
# stderr, so a caller can read the paths with $(...).
#
# TWO SHAPES, because two different people are downloading.
#
#   An ADDON repository ships addons/<name>/ and nothing else. That folder IS the
#   distributable -- project.godot and examples/ exist only so the addon can be opened
#   and validated standalone, and shipping them would put a second project.godot into
#   the tree of whoever unzipped it. The zip's entries start at addons/, which is the
#   convention every Godot addon follows: unzip at the project root and it is
#   installed.
#
#   Everything ELSE -- the games, the launcher, the deployment tool -- ships the
#   tracked tree as a tarball. A game is not installed into a project; it is a SOURCE
#   that the central publisher turns into a signed pack. That is why no release here
#   builds one: signing is what makes a mounted pack safe, a mounted pack can contain
#   scripts, and the private half of that key exists in one place on purpose. Sixty
#   repositories each holding a copy of it would be sixty ways to lose it.
#
#   With --pack, a game (or an addon repository that is also a Workshop pack: provides.json
#   at its root; its own addons/ stays out of the pack) ALSO ships <name>-<version>-pack.zip: the tree the publisher
#   turns into that signed pack. The tarball cannot be it, and not for want of a
#   format -- it has no addons (they are gitignored links) and no .godot/imported, and
#   a mounted pack is never re-imported, so every texture and model in it would fail
#   to load and say nothing. The pack zip is the tracked tree minus what the host
#   already has or no player needs (addons, examples, tools, screenshots, images, and any
#   --exclude-dir), plus exactly the imported outputs the remaining .import files
#   name. It is UNSIGNED: website-city publishes a release file ending in -pack.zip in
#   place of everything else on the release, and signs it there.
#
#   --pack needs the checkout IMPORTED first (`godot --headless --import`), with its
#   addons resolved so the import can see them. release.yml does both when the caller
#   passes `pack: true`.
#
#   --host-lock FILE (or HOST_LOCK=FILE) names the addons.lock of the shell the pack will
#   run on. Its pinned addon levels (read by the project's dot-core, DotAddonApi
#   pinned_levels, from the repositories in GS_REPOS_ROOT, <project>/.deps, beside the
#   project, TMC_REPOS_DIR, ~/godot) go to dot_requires.gd as --pin, so a
#   requires.floor.json floor above what that shell ships fails the pack instead of being
#   judged against the linked head. A lock that reads to no level fails. Without it,
#   nothing changes.
#
# WHAT IS IN THE ARTIFACT IS WHAT GIT TRACKS, via git archive. Not `cp -r`, and the
# difference is the point: addons/ is a directory of gitignored SYMLINKS into sibling
# checkouts on a developer box and into .deps/ on a runner, and a copy would either
# follow them -- shipping a second, stale copy of every dot-* addon at the same res://
# paths the host already defines -- or preserve them, shipping links that dangle the
# moment the tree moves. git archive resolves it by never seeing them: an ignored file
# is not tracked, so it is not in the archive, and the list maintains itself.
#
set -uo pipefail

USAGE="usage: package.sh <project-dir> <version> [--out DIR] [--name NAME] [--pack [--exclude-dir DIR]... [--pack-owned-addons] [--host-lock FILE]]"
PROJECT="${1:?$USAGE}"
VERSION="${2:?$USAGE}"
shift 2
OUT=""
NAME=""
PACK=0
PACK_OWNED=0
HOST_LOCK="${HOST_LOCK:-}"
# What a game pack never carries, at any depth. addons/ above all: every dot-* addon
# is already in the host build, and packing a game with its addons produced an 11 MiB
# pack of which the game was a fraction. images/ is a README's pictures: every game's
# preview GIFs went in on 2026-10-03 and the next pack was 71 MiB of a 4 MiB game, every
# byte of it downloaded by every player on connect and loaded by nothing. The same list
# dot-server-deploy's content/<id>/pack.json files give, which is what a pack published
# from there holds.
# docs/ and every *.md are the repository's documentation: read by people and agents,
# loaded by nothing at runtime (no game opens a .md), and since 2026-10-10 most of a
# game's text lives in docs/. DotCloudPublisher drops *.md and the content/<id>/pack.json
# files list docs/ for the same reason.
EXCLUDE_DIRS=(addons examples tools screenshots images docs .github)
# Top-level only; DotCloudPublisher.exclude_roots (addons/dot_cloud/publish) is this list.
EXCLUDE_ROOTS=(examples tests tools docs ci .github screenshots reports art-src)
while [ $# -gt 0 ]; do
    case "$1" in
        --out)  OUT="${2:?--out needs a directory}"; shift 2 ;;
        --name) NAME="${2:?--name needs a name}"; shift 2 ;;
        --pack) PACK=1; shift ;;
        --pack-owned-addons) PACK_OWNED=1; shift ;;
        --host-lock) HOST_LOCK="${2:?--host-lock needs an addons.lock}"; shift 2 ;;
        --exclude-dir) EXCLUDE_DIRS+=("${2:?--exclude-dir needs a name}"); shift 2 ;;
        *) printf 'unknown option: %s\n' "$1" >&2; exit 2 ;;
    esac
done

[ -d "$PROJECT" ] || { printf 'no such directory: %s\n' "$PROJECT" >&2; exit 2; }
PROJECT="$(cd "$PROJECT" && pwd -P)"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
if [ -n "$HOST_LOCK" ]; then
    [ -f "$HOST_LOCK" ] || { printf 'no such host lock: %s\n' "$HOST_LOCK" >&2; exit 2; }
    HOST_LOCK="$(cd "$(dirname "$HOST_LOCK")" && pwd -P)/$(basename "$HOST_LOCK")"
fi

# --name, and it is not a convenience. A runner checks the repository out into a
# directory it chose -- `project` here -- so the basename is the CHECKOUT's name and
# not the repository's, and every game in the family would have released a tarball
# called project-1.2.3.tar.gz. Found by packaging a runner-shaped checkout rather than
# a developer one, which is the only place the two names differ.
NAME="${NAME:-$(basename "$PROJECT")}"
OUT="${OUT:-$PROJECT/dist}"
mkdir -p "$OUT" || exit 1
OUT="$(cd "$OUT" && pwd -P)"

# A leading v is how the tags are written and is not part of the version. plugin.cfg
# and the Asset Library both want the bare number.
VERSION="${VERSION#v}"

cd "$PROJECT" || exit 2
git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
    || { printf '%s is not a git checkout, and the artifact is defined by what git tracks\n' "$NAME" >&2; exit 2; }

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

## The addons this repository OWNS, as opposed to the ones it links in to open.
##
## Ownership is decided by git, not by the filesystem: every linked dependency is
## gitignored in every project here, so a tracked addons/<name>/ is ours and an
## untracked one is somebody else's. Reading the directory instead would need a
## symlink test, which is right on Linux and wrong on Windows -- where the family
## COPIES addons rather than linking them, and a copied dependency is indistinguishable
## from owned source by any test except this one.
##
## Only a directory with a plugin.cfg is an addon. A game may track folders of its own
## under addons/ (hook folders it finds at boot, with no plugin.cfg): counted as addons,
## they made the game an "addon repository", --pack was ignored, and the release then
## failed for want of a pack zip.
mapfile -t OWNED < <(git ls-files 'addons/*/plugin.cfg' | cut -d/ -f2 | sort -u)

artifacts=()

if [ "${#OWNED[@]}" -gt 0 ]; then
    git archive --format=tar HEAD | tar -x -C "$STAGE" || exit 1

    for addon in "${OWNED[@]}"; do
        [ -d "$STAGE/addons/$addon" ] || continue

        cfg="$STAGE/addons/$addon/plugin.cfg"
        if [ -f "$cfg" ]; then
            # Stamped in the ARTIFACT, not in the repository. The version of a release
            # is the tag -- that is the thing that is unique, signed by the push, and
            # impossible to forget to bump -- and a committed 0.1.0 that has to be
            # edited in lockstep across fifty-six repositories is a number that goes
            # wrong silently and is then shipped. Editing it here cannot drift because
            # nothing reads it between this line and the upload.
            sed -i -E "s|^version=\".*\"$|version=\"$VERSION\"|" "$cfg"
            grep -q "version=\"$VERSION\"" "$cfg" \
                || printf 'warning: %s/plugin.cfg has no version line to stamp\n' "$addon" >&2
        fi

        zip_path="$OUT/${addon}-${VERSION}.zip"
        rm -f "$zip_path"
        # Entries begin at addons/, so the zip installs by being unpacked at a project
        # root. README and LICENSE ride along INSIDE the addon folder rather than at
        # the top, where they would land in the consumer's project root and overwrite
        # theirs -- which is a thing addon zips do and is never what anyone wanted.
        for extra in README.md LICENSE; do
            [ -f "$STAGE/$extra" ] && [ ! -f "$STAGE/addons/$addon/$extra" ] \
                && cp "$STAGE/$extra" "$STAGE/addons/$addon/$extra"
        done
        ( cd "$STAGE" && zip -q -r "$zip_path" "addons/$addon" ) || exit 1
        artifacts+=("$zip_path")
        printf 'packed addons/%s -> %s\n' "$addon" "$(basename "$zip_path")" >&2
    done
fi

if [ "${#artifacts[@]}" -eq 0 ]; then
    # No owned addon: a game, the launcher, the deployment tool. The tracked tree,
    # under one top-level directory so it cannot explode into the cwd of whoever
    # unpacks it without looking.
    tar_path="$OUT/${NAME}-${VERSION}.tar.gz"
    rm -f "$tar_path"
    git archive --format=tar.gz --prefix="${NAME}-${VERSION}/" -o "$tar_path" HEAD || exit 1
    artifacts+=("$tar_path")
    printf 'packed the tracked tree -> %s\n' "$(basename "$tar_path")" >&2
fi

# An addon repository takes --pack too: its zip is the install, the pack is the data it
# publishes to the Workshop (provides.json, weapons/, cfg/). addons/ is left out of the pack
# by default: the host owns the dot-* addons and the Workshop pack is data only.
# --pack-owned-addons puts this repository's OWN addons (the tracked addons/<name>/plugin.cfg
# folders above) back in, version-stamped, for a pack that carries its code as well as its
# data: one a host mounts as an add-on overlay instead of building it in. Linked addons stay
# out; the other exclusions still apply inside the owned folders.
if [ "$PACK" -eq 1 ]; then
    [ -d "$PROJECT/.godot/imported" ] || {
        printf '%s has not been imported: --pack needs `godot --headless --import` first\n' "$NAME" >&2
        exit 2
    }

    PACK_DIR="$STAGE/pack"
    mkdir -p "$PACK_DIR" || exit 1
    git archive --format=tar HEAD | tar -x -C "$PACK_DIR" || exit 1

    for d in "${EXCLUDE_DIRS[@]}"; do
        find "$PACK_DIR" -depth -type d -name "$d" -exec rm -rf {} + || exit 1
    done
    if [ "$PACK_OWNED" -eq 1 ]; then
        [ "${#OWNED[@]}" -gt 0 ] || { printf '%s owns no addons/<name>/plugin.cfg for --pack-owned-addons\n' "$NAME" >&2; exit 2; }
        mkdir -p "$PACK_DIR/addons" || exit 1
        for addon in "${OWNED[@]}"; do
            # From the stage, where plugin.cfg already carries this release's version.
            cp -a "$STAGE/addons/$addon" "$PACK_DIR/addons/$addon" || exit 1
            for d in "${EXCLUDE_DIRS[@]}"; do
                [ "$d" = addons ] && continue
                find "$PACK_DIR/addons/$addon" -mindepth 1 -depth -type d -name "$d" -exec rm -rf {} + || exit 1
            done
            printf 'pack keeps owned addons/%s\n' "$addon" >&2
        done
    fi
    # A script's .uid sidecar is editor bookkeeping; DotCloudPublisher leaves it out
    # too, and the two publishers should produce the same pack from the same tree.
    find "$PACK_DIR" -name '*.gd.uid' -type f -delete || exit 1
    find "$PACK_DIR" -name '*.md' -type f -delete || exit 1
    find "$PACK_DIR" \( -name '*.tmp' -o -name .DS_Store -o -name Thumbs.db -o -name .gitignore -o -name .gitattributes \) -type f -delete || exit 1
    # Top-level folders nothing loads at runtime (tests, CI, review reports, editable art
    # sources): the same list DotCloudPublisher.exclude_roots gives, so the pack this
    # builds and the one dot-cloud's publish_pack.sh builds hold the same files. Roots
    # only, unlike EXCLUDE_DIRS: a `ci` or `reports` folder inside content stays.
    for d in "${EXCLUDE_ROOTS[@]}"; do
        rm -rf "${PACK_DIR:?}/$d" || exit 1
    done

    # The imported outputs, chosen by the .import files that SURVIVED the
    # exclusions rather than by copying .godot/imported whole. That directory holds
    # the output of every asset in the checkout, examples and screenshots included,
    # and one game's excluded map folder is most of its bytes.
    # Under _imported/, NOT at .godot/imported/ where they live in the project,
    # with every marker rewritten to match. A web export cannot read the engine's
    # own reserved directory back out of a mounted pack -- "A required file is not
    # readable after mounting" -- while Linux reads it fine, so a headless check
    # passes on the platform that does not matter. DotCloudPublisher.IMPORTED_DIR
    # is the same name for the same reason; a marker names its output by absolute
    # path, so the directory can be anything the marker agrees with.
    IMPORTED_DIR="_imported"
    imported=0
    missing=0
    dropped=0
    while IFS= read -r -d '' marker; do
        found=0
        while IFS= read -r res; do
            rel="${res#res://}"
            if [ -f "$PROJECT/$rel" ]; then
                mkdir -p "$PACK_DIR/$IMPORTED_DIR" || exit 1
                cp "$PROJECT/$rel" "$PACK_DIR/$IMPORTED_DIR/${rel#.godot/imported/}" || exit 1
                imported=$((imported + 1))
                found=$((found + 1))
            else
                # A marker naming an output the import did not write is an asset
                # that will not load from the pack. Said here, where it can be
                # fixed, instead of on a player's machine where it cannot.
                printf 'missing imported output: %s (from %s)\n' "$rel" "${marker#"$PACK_DIR"/}" >&2
                missing=$((missing + 1))
            fi
        done < <(grep -o 'res://\.godot/imported/[^"]*' "$marker" | sort -u)
        sed -i 's|res://\.godot/imported/|res://'"$IMPORTED_DIR"'/|g' "$marker" || exit 1
        # The source an imported output stands in for (.glb, .jpg, .png, .wav...) is dead
        # weight: nothing imports at runtime and every load of its path goes through the
        # marker to the output. DotCloudPublisher drops it too (ship_import_sources off);
        # shipping both made a pack 5x the size of the one publish_pack.sh builds. Only
        # when the marker had an output to stand on.
        src="${marker%.import}"
        if [ "$found" -gt 0 ] && [ -f "$src" ]; then
            rm -f "$src" || exit 1
            dropped=$((dropped + 1))
        fi
    done < <(find "$PACK_DIR" -name '*.import' -type f -print0)

    [ "$missing" -eq 0 ] || { printf '%d imported outputs are missing; re-import and try again\n' "$missing" >&2; exit 1; }

    # What the pack needs of the host's addons, as requires.json at its root. A pack's
    # scripts compile against the addons of whatever mounts it, so one built against a
    # newer dot-net than a player's client has fails to PARSE there, mid-load, with
    # nothing a person can read; dot-cloud reads this file before mounting and says it
    # in a sentence instead (see dot-core's DotAddonApi). Derived from the game's own
    # files at the levels THIS checkout's addons have -- "built against" -- so nobody
    # keeps the list. A game that commits its own keeps control of it, and it is
    # audited here instead: an addon used and not declared, or declared above what
    # this build has, fails the release rather than a player's join.
    REQ_TOOL="res://addons/dot_core/tools/dot_requires.gd"
    REQ_PINS=()
    if [ -n "$HOST_LOCK" ]; then
        # The shell's levels, so a floor is judged against what players run. A dot-core
        # that cannot take them would ignore --pin and judge against the linked head:
        # failed, not passed, since the caller asked for the check.
        grep -q '"--pin"' "$PROJECT/addons/dot_core/tools/dot_requires.gd" 2>/dev/null \
            && grep -q 'func pinned_levels' "$PROJECT/addons/dot_core/core/dot_addon_api.gd" 2>/dev/null \
            || { printf 'the linked dot-core cannot judge floors against a lock (no --pin / pinned_levels); --host-lock needs a newer one\n' >&2; exit 1; }
        pins_out="$("${GODOT:-godot}" --headless --path "$PROJECT" --script "$HERE/lock_pins.gd" -- "$HOST_LOCK" \
            "${GS_REPOS_ROOT:-${DOT_REPOS_ROOT:-}}" "$PROJECT/.deps" "$(dirname "$PROJECT")" "${TMC_REPOS_DIR:-}" "$HOME/godot")" \
            || { printf 'could not read the addon levels %s pins\n' "$HOST_LOCK" >&2; exit 1; }
        while IFS=$'\t' read -r tag pin; do
            [ "$tag" = pin ] && REQ_PINS+=(--pin "$pin")
        done <<< "$pins_out"
        [ "${#REQ_PINS[@]}" -gt 0 ] \
            || { printf '%s reads to no addon level (are its repositories in GS_REPOS_ROOT?)\n' "$HOST_LOCK" >&2; exit 1; }
        printf 'floors judged against %d addon levels pinned by %s\n' "$(( ${#REQ_PINS[@]} / 2 ))" "$HOST_LOCK" >&2
    fi
    if [ -f "$PROJECT/addons/dot_core/tools/dot_requires.gd" ]; then
        if [ -f "$PACK_DIR/requires.json" ]; then
            "${GODOT:-godot}" --headless --path "$PROJECT" --script "$REQ_TOOL" -- --check requires.json >&2 \
                || { printf '%s/requires.json does not cover what the game uses\n' "$NAME" >&2; exit 1; }
        else
            "${GODOT:-godot}" --headless --path "$PROJECT" --script "$REQ_TOOL" -- --out "$PACK_DIR/requires.json" "${REQ_PINS[@]}" >&2 \
                || { printf 'could not derive requires.json for %s\n' "$NAME" >&2; exit 1; }
            [ -s "$PACK_DIR/requires.json" ] \
                || { printf 'requires.json for %s came out empty\n' "$NAME" >&2; exit 1; }
        fi
    else
        # A dot-core pinned from before the tool existed. Said, not failed: the pack is
        # exactly what it was the day before, and a host checks nothing it is not given.
        printf 'note: dot-core has no dot_requires.gd; %s ships without requires.json\n' "$NAME" >&2
    fi

    pack_path="$OUT/${NAME}-${VERSION}-pack.zip"
    rm -f "$pack_path"
    # Entries at the top level, not under a wrapper directory: the publisher strips
    # a common root anyway, and a pack whose files sit one level down mounts where
    # no reference resolves.
    ( cd "$PACK_DIR" && zip -q -r -y "$pack_path" . ) || exit 1
    artifacts+=("$pack_path")
    printf 'packed the game with %d imported outputs (%d import sources left out) -> %s\n' "$imported" "$dropped" "$(basename "$pack_path")" >&2
fi

# A digest beside each artifact. The release page is not the only thing that consumes
# these -- whatever syncs them onward has to be able to say the bytes it got are the
# bytes that were built, and asking it to trust a redirect is not that.
( cd "$OUT" && sha256sum "${artifacts[@]##*/}" > SHA256SUMS ) || exit 1
artifacts+=("$OUT/SHA256SUMS")

printf '%s\n' "${artifacts[@]}"

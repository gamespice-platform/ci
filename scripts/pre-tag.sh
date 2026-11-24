#!/usr/bin/env bash
#
# Run before `git tag` on a game: the two gates release.yml applies after the tag is pushed,
# strictly, against the pack that tag would build.
#
#   GODOT=godot scripts/pre-tag.sh ../game-x
#
# Reads pack, pack-deny, pack-exclude-dirs, pack-owned-addons, host-lock and server-compat
# from the job of the game's .github/workflows/release.yml that calls release.yml, imports
# the project, builds the pack from HEAD (what the tag will point at), and runs
# check-pack-static.py and server-compat.sh. Exit 0: tag away. Nonzero: the release would
# be red. server-compat needs network and DEPS_TOKEN for private repositories.
exec "$(dirname "${BASH_SOURCE[0]}")/pack-gates.sh" "${1:?usage: pre-tag.sh <game-repo-dir>}" --from-release-yml --compat strict

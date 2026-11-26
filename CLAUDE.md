# gs-ci

The family's shared CI: three reusable GitHub Actions workflows (`validate.yml`, `release.yml`, `release-maps.yml`) and the shell scripts they run, called by every other repository. Read [README.md](README.md) first: it is the interface, and it explains the choices rather than just listing them.

This is not a Godot project. It has no `project.godot`, no `addons/`, and nothing here is ever linked into one. **This repository is public**: write nothing here about another repository beyond what the README already says.

## Read before

| Read | Before |
| --- | --- |
| [docs/design.md](docs/design.md) | changing a workflow or script: one copy of the knowledge, the two deliberate copies (Godot pin, owner rule), dependency resolution, the traps, `requires.json`, the two publishers agreeing |
| [docs/history.md](docs/history.md) | the untagged addon API that passed CI, the engine error that failed a suite, the `project-<version>` artifact name |

## Layout

| Path | What |
| --- | --- |
| `.github/workflows/validate.yml` | reusable: resolve addons, import, parse every tracked script, run every suite |
| `.github/workflows/release.yml` | reusable: artifact + `SHA256SUMS` on a `v*` tag; `pack: true` adds `-pack.zip`; server-compat gate; optional `host-lock` input -> `package.sh --host-lock` |
| `.github/workflows/release-maps.yml` | reusable: one pack per map for a map repository |
| `.github/workflows/ci.yml` | this repository's own check: `bash -n` and shellcheck on `scripts/`, workflows load as YAML, the pin fetches and verifies |
| `godot.pin` | the runtime version and SHA512 (the second copy; it says which is authoritative) |
| `scripts/fetch-godot.sh` | fetch and verify the pinned runtime |
| `scripts/resolve-deps.sh` | addons from `.gitignore` or `addons.lock`, cloned into `.deps/` and linked |
| `scripts/ci-local.sh <dir>` | the pre-push replica of CI: clones HEAD of a checkout to scratch, resolves addons from their default-branch tips like `validate.yml`, takes `suite-timeout`/`suites` from its `ci.yml`, runs `check.sh`. Differs from `game.sh test`, which uses the sibling working trees |
| `scripts/fetch-source-lock.sh <dir> <gs-cloud>` | restores a repo's untracked binaries from its `source.lock.json` by hash (gs-cloud `lock_verify.sh --fetch`); `validate.yml` runs it on the project, `resolve-deps.sh` on every addon clone that has a lock (`GS_CLOUD` = the gs-cloud checkout) |
| `scripts/check.sh` | import, parse pass, suites, the exit-0 stderr check |
| `scripts/check-export-filter.sh` | fails a repository whose `export_presets.cfg` or `.example.cfg` has a preset `include_filter` without `cfg/*` |
| `scripts/check-cfg-names.sh` | fails a repository with a `*` or `?` in any path under a `cfg/` directory (spell per-map globs `surf_%.yml`) |
| `scripts/check-floor-uses.py` | fails a game whose `requires.floor.json` is below the API level of an addon class its scripts name with no `build_level`/`level_of` guard in the file (introducing levels read from each `gs_<x>_api.gd`; file-level, cannot see string loads) |
| `scripts/check-pack-static.py` | the artifact gate on a built `-pack.zip`: stale `dot_*` addons, `Dot*` classes, duplicate uids, optional `--deny` regex; run by `release.yml` before the release exists (tests in `tests/test_check_pack_static.py`) |
| `scripts/check-no-js-eval.py` | fails a repository that evaluates a JavaScript string (`JavaScriptBridge.eval`, `GSWeb.eval`, `eval(`/`new Function(` in page scripts): the web origin's CSP has no `unsafe-eval`. Escape: a `js-eval: allow <reason>` comment. Always on in `validate.yml`; tests in `tests/test_no_js_eval.py` |
| `scripts/check-no-uid-loads.py` | fails a repository whose tracked `.gd` files `load`/`preload` a `uid://` string, or (outside `examples/` and `tests/`) hold a whole uid literal: a box or pack without the uid cache fails it with "Unrecognized UID" and runs on without the resource. Load by `res://` path. Escape: a `uid-load: allow <reason>` comment. Always on in `validate.yml`; tests in `tests/test_no_uid_loads.py` |
| `scripts/check-split-names.py` | fails a repository that tracks a file or directory named `*_part<N>` (`_pt<N>`, `part2a`), a script ending `_a`/`_2`/`_b1`/`_b2a` (`.gd .rs .py .ts .sh`; `_2d`/`_3d` and `a2s`/`e2e`/`v2` are fine, scenes and assets are not checked), `misc`, `stuff`, `helpers<N>` and the like: a split file is divided by responsibility and every piece is named for what it holds. Escape: `ci/split-names.allow` (one path per line). Always on in `validate.yml`; tests in `tests/test_split_names.py` |
| `scripts/check-visual-qa.py` | fails a game (`game.sh` + `project.godot` at the root) that does not track `tools/visual_qa.gd` (gs-game's visual QA harness entry), or whose tracked `tools/visual_qa_shot.sh` is not mode 100755. Escape: a `*` line in `ci/visual-qa.allow`, with the reason. Always on in `validate.yml`; tests in `tests/test_visual_qa.py` |
| `scripts/check-windows-names.py` | fails a repository whose `git ls-files` has a name Windows cannot check out: `* ? : " < > | \`, a component ending in a dot or space, a reserved device name (CON, NUL, COM1...), or two paths differing only by case. Always on in `validate.yml`; tests in `tests/test_windows_names.py` |
| `scripts/check-size.py`, `check-frame-hazards.py`, `check-duplication.py` | the efficiency gates (opt-in `efficiency: true`): file/function size, per-frame hazards, duplicated 30-line windows. Each has a baseline at `ci/efficiency/*.tsv` in the checked repository that only shrinks (`--init` once, `--update` lowers and refuses to add); `check-duplication.py --cross <dirs>` is the report-only nightly mode. Shared code in `effgate.py`; tests in `tests/` |
| `scripts/owner-identity-hook` | the system-wide git hook (`core.hooksPath` in /etc/gitconfig, installed at `/usr/local/lib/git-owner-hooks/`): every pushed commit authored and committed as the owner; on pushes to main the efficiency gates above plus `check-duplication.py --siblings` on the files the push touched. Refuses only what a push adds: no-op and no-`.gd` pushes skip, failures the remote's commit already has are reported, a crashing gate warns. Edit here, then `sudo -u gamedev sudo install -m 755 scripts/owner-identity-hook /usr/local/lib/git-owner-hooks/owner-identity-hook`; tests in `tests/test_owner_hook.py` |
| `scripts/check-vendored-art.py` | stale vendored art, no Godot, about a second: for an addon repository that owns art (`tools/sync-art.sh`, today zee-gs-weapons) it compares the art a game vendors (the game's `origin/main`, same `assets/<dir>` names) with the addon's files at `--ref` (default HEAD): a differing file is stale, a weapon model the art table names and the game lacks is missing. Run in the addon repo: `python3 ../gs-ci/scripts/check-vendored-art.py`; exit 1 lists the games and the `sync-art.sh <game>` fix. It approximates the table, so `sync-art.sh <game> --check` stays the authority. Wired into `owner-identity-hook` (pre-push of the addon's main lists stale games loudly; `OWNER_HOOK_VENDORED_ART=strict` refuses, `=off` skips) and into `efficiency-nightly.sh` (exit 1 when any game is stale). Tests in `tests/test_vendored_art.py` |
| `scripts/efficiency-report.sh [dirs]` | one summary table for the nightly panel (repo, size violations, frame hazards, lines, comment-line share, then cross-repository duplicate clusters) over the given repositories, default every `~/godot/*/` with a `.git`. Report only, never fails; ignores baselines |
| `scripts/efficiency-nightly.sh`, `perf-smoke.sh`, `perf_smoke.gd`, `perf-budget.py` | the nightly report plus trend in one command; the headless perf smoke (load, frame time, nodes, memory vs `ci/perf/smoke.json`, 20% ratchet). [README](README.md#running-the-scripts-yourself) |
| `scripts/check-comments.py`, `check-generated.py`, `check-web-size.py`, `check-logging.py`, `check-markdown-wrap.py`, `check-suite-checks.py`, `duplication-cross.sh` | the opt-in `hygiene: true` gates (report-only unless `hygiene-blocking`) with the same shrink-only baselines, and the nightly cross-repository duplication wrapper. [README](README.md#hygiene-gates-and-the-nightly-scan) |
| `scripts/check-profiles.sh` | opt-in `profiles: true`: runs GameSpice Profile's `profile_check.gd` over a project's `cfg/` profile yml; fails on any schema, `extends` or duplicate-id problem |
| `scripts/rollout-caller.sh <repo-dir>` | one caller's efficiency rollout: runs the missing `--init` baselines, adds `efficiency`/`perf`/`hygiene: true` under `with:` in its `ci.yml`, one plain commit, never pushes (skips a dirty tree, exit 3). Idempotent; tests in `tests/test_rollout_caller.py` |
| `scripts/affected.sh [REPO] [--since REV] [--cmds\|--json]` | which sibling repositories link the changed repository and which of their suites (reached by class name or file name through three hops) to run; `parse` when none names the change. Tests in `tests/test_affected.py` |
| `scripts/package.sh` | the release artifact; `--pack` builds the pack zip and `requires.json`; `--host-lock FILE` passes that lock's addon levels (`lock_pins.gd`) to `gs_requires.gd` as `--pin`. With a `source.lock.json` it restores the untracked files (`fetch-source-lock.sh`, `GS_CLOUD` or a sibling gs-cloud) and lays them over every `git archive` tree (tarball, addon zip, pack); `release.yml` also fetches before the import. Real run (zz-medieval-weapons, 2026-11-25): the locked sources reach the import (30 imported outputs from the 30 restored glb/jpg), but the `--pack` zip is imported outputs only, so its files do not hash to `source_files`; compare the tarball or a non-pack zip against the lock instead. Tests in `tests/test_package_lock_pins.py`, `tests/test_package_source_lock.py` |
| `scripts/package-subpacks.sh` | one pack per map directory |
| `scripts/pack-gates.sh <dir>`, `pre-tag.sh <game-dir>` | build the pack `release.yml` would and run `check-pack-static.py` plus `server-compat.sh`: `validate.yml` (input `pack: true`) runs it with server-compat advisory, `pre-tag.sh` strict from the game's `release.yml` inputs. Tests in `tests/test_pack_gates.py` |
| `scripts/server-compat.sh` | refuses a pack the newest released server cannot run |

## Running and testing

There is no way to test a reusable workflow except by calling it. Tag this repository (`v1` moves; `v1.2.3` does not), point one caller at the new tag, watch it, then move `v1`. The `v1` tag is stale and must not be used (it clones the old zees-games/gs-* repos); callers pin an exact immutable tag, currently `@v1.4.0`. Callers pin a tag on purpose: a floating `@main` across sixty repositories means a typo here is sixty red repositories at once.

The scripts run on a laptop and should be exercised there first; they take a directory ([README](README.md#running-the-scripts-yourself) has the full list):

```bash
GODOT=godot scripts/check.sh ../gs-cloud
scripts/package.sh ../gs-cloud 0.2.0 --out /tmp/out
scripts/package.sh ../game-fatal-contact 0.2.0 --out /tmp/out --pack   # imported first
```

## Rules that bite

- Never write a step into a caller; add an input here. `suites` is the one per-repository fact. [design](docs/design.md#one-copy-of-the-knowledge)
- Moving the Godot version means editing `godot.pin` and gs-server-deploy's `tools/fetch-godot.sh` in one change; take the digest from the release's own `SHA512-SUMS.txt`. [design](docs/design.md#two-things-here-are-copies-and-both-are-deliberate)
- The owner rule is repeated in `resolve-deps.sh` (`GS_OWNER`, `GAME_OWNER`, `addon_repo()`); the project list is never copied here. [design](docs/design.md#two-things-here-are-copies-and-both-are-deliberate)
- Dependencies come from the project's `.gitignore` (`^/addons/[a-z0-9_]+$`, so a bare `/addons/` names nothing) or its `addons.lock` at the locked refs. [design](docs/design.md#what-is-not-copied-and-must-not-be)
- Workflows check out their own scripts at `github.job_workflow_sha`; `release.yml` never calls `validate.yml`. [design](docs/design.md#traps-worth-not-re-finding)
- The deps token stays optional; `_redact` must stay a no-op on an empty token; never gate a step on `secrets.` in an `if:`. [design](docs/design.md#traps-worth-not-re-finding)
- An exit-0 suite fails on `SCRIPT ERROR` or `Parse Error` only, never on the engine's `ERROR: Condition`. Noise filters match both wordings (`( were )?`). [design](docs/design.md#traps-worth-not-re-finding)
- Headless Godot still needs `libfontconfig1` and the X11 libraries; `unzip` runs with `< /dev/null`. [design](docs/design.md#traps-worth-not-re-finding)
- Artifacts are named with `--name` (the repository name), never the checkout's basename; test new packaging on a runner-shaped checkout. [design](docs/design.md#traps-worth-not-re-finding)
- Parse lists and artifacts come from `git ls-files`, never `find` or a path rule. [design](docs/design.md#traps-worth-not-re-finding)
- After changing what `--pack` includes, diff its paths against the pack GameSpice Server Deploy publishes from the same tree. [design](docs/design.md#the-two-publishers-must-agree)
- A release signs nothing and publishes nothing; it ends at an artifact and a digest. [README](README.md#what-a-release-does-not-do)

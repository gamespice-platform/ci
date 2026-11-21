# Custom web export template

`scripts/build-web-template.sh` builds a Godot 4.7.2-stable web template (dlink / GDExtension, single-threaded)
from source with pinned versions (godot tag + commit, emsdk 4.0.20, scons 4.9.1) and unused modules disabled,
`optimize=size lto=full`. Run it through heavy on the build VM (the side-module link peaks above 4 GB, so
`HEAVY_JOB_MAX_GB` must allow 8; a 4.7 GB ceiling OOM-killed the first attempt):

    sudo -u gamedev /home/gamedev/bin/hv <worktree> local scripts/build-web-template.sh

It never installs or publishes the zip; the output is an artifact under `$WORK/out` (default
`~/web-template-build/out`). Full build from cold: about 14 minutes on the build VM.

## Measurements (2026-11-21, adv text server, 14 modules off)

| file | official 4.7.2 raw | custom raw | official gzip-9 | custom gzip-9 |
|---|---|---|---|---|
| godot.side.wasm (engine) | 44,078,870 | 40,390,643 (-8.4%) | 10,486,172 | 9,903,284 (-5.6%) |
| godot.wasm (main) | 1,508,095 | 1,497,255 | 582,004 | 580,811 |

Artifact zip sha256 `7cd171a28714012c3fef707f9dc3dba5758aabb9e8bf115532b08e9c92e293d3`
(`/home/gamedev/web-template-build/out/web_dlink_nothreads_release.zip`, 10,901,879 bytes).

The saving is modest: the official template is already size-optimised, and the biggest remaining parts are the
renderer, 3D and text servers. `--text-server fb` (drops ICU/HarfBuzz; loses complex-script shaping, which the
games do not use) is the next lever and is not measured yet.

## Boot test

The custom engine was dropped into the stamped shell build (index.js, index.wasm, index.side.wasm from the
custom zip; fileSizes updated) and run with tools/web_load_timing.mjs --runs 3 (dot-server-deploy) through
gpu.sh cdp-run on staging02, renderer ANGLE NVIDIA GeForce RTX 2070: canvas 156 / 218 / 214 ms, index.side.wasm
(40,390,643 B) and dot_sim.wasm both load, 0 console errors in runs 2 and 3; run 1 had one 404 that is not a shell
file (browser favicon request, first load only). Not done: the official-template run on the same box for
the same session, the fc/playlot web smoke, the fb text-server variant, and a debug template.

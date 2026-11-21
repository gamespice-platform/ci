#!/usr/bin/env bash
# Build a size-optimised Godot web export template (dlink / GDExtension, single-threaded) from source.
#   scripts/build-web-template.sh [--debug-too] [--text-server fb|adv] [--jobs N] [--out DIR]
# Run it on the build VM through heavy (a wasm LTO link wants about 8 GB):
#   sudo -u gamedev /home/gamedev/bin/hv <worktree> local scripts/build-web-template.sh
# Everything is pinned below; nothing needs root: emsdk, scons (pip, into a venv) and the engine source
# are fetched into WORK (default ~/web-template-build). Output in OUT (default $WORK/out):
#   web_dlink_nothreads_release.zip (+ _debug.zip with --debug-too), SIZES.txt, SHA256SUMS
# SIZES.txt compares the engine's side module and main module, raw and gzip -9, against the official 4.7.2
# template when OFFICIAL_ZIP points at it. The result is an artifact: this script never installs or
# publishes it. docs/web-template.md has the measurements and the boot test.
set -euo pipefail
GODOT_TAG=4.7.2-stable
GODOT_COMMIT_PREFIX=ed1daf0bf
EMSDK_VERSION=4.0.20      # the emscripten the official 4.7.2 web templates report; the tag's CI names 4.0.11
SCONS_VERSION=4.9.1
WORK="${WORK:-$HOME/web-template-build}"
OUT="$WORK/out"
JOBS="$(nproc)"
DEBUG_TOO=0
TEXT_SERVER=adv
OFFICIAL_ZIP="${OFFICIAL_ZIP:-$HOME/.local/share/godot/export_templates/4.7.2.stable/web_dlink_nothreads_release.zip}"
while [ $# -gt 0 ]; do
    case $1 in
        --debug-too) DEBUG_TOO=1; shift ;;
        --text-server) TEXT_SERVER=${2:?fb|adv}; shift 2 ;;
        --jobs) JOBS=${2:?N}; shift 2 ;;
        --out) OUT=${2:?DIR}; shift 2 ;;
        *) echo "build-web-template: unknown argument '$1'" >&2; exit 2 ;;
    esac
done
mkdir -p "$WORK" "$OUT"
cd "$WORK"

# Modules the shell and the games never reach (grep over the games, addons and the shell, 2026-11-21; the
# boot test in docs/web-template.md is the real gate). 3D stays on: the games are 3D.
DISABLED_MODULES="mono openxr webxr mobile_vr camera theora upnp webrtc jsonrpc xatlas_unwrap lightmapper_rd visual_shader objectdb_profiler fbx interactive_music"
MODFLAGS=()
for m in $DISABLED_MODULES; do MODFLAGS+=("module_${m}_enabled=no"); done
if [ "$TEXT_SERVER" = fb ]; then MODFLAGS+=(module_text_server_adv_enabled=no module_msdfgen_enabled=no); fi

[ -d emsdk ] || git clone -q --branch "$EMSDK_VERSION" --depth 1 https://github.com/emscripten-core/emsdk.git emsdk
./emsdk/emsdk install "$EMSDK_VERSION" >/dev/null
./emsdk/emsdk activate "$EMSDK_VERSION" >/dev/null
# shellcheck disable=SC1091
EMSDK_QUIET=1 source ./emsdk/emsdk_env.sh
emcc --version | head -1

[ -d venv ] || python3 -m venv venv
venv/bin/pip install -q "scons==$SCONS_VERSION"
export PATH="$WORK/venv/bin:$PATH"

[ -d godot ] || git clone -q --branch "$GODOT_TAG" --depth 1 https://github.com/godotengine/godot.git godot
head=$(git -C godot rev-parse HEAD)
case $head in "$GODOT_COMMIT_PREFIX"*) ;; *) echo "build-web-template: godot is at $head, expected $GODOT_COMMIT_PREFIX*" >&2; exit 3 ;; esac

targets=(template_release); [ "$DEBUG_TOO" = 1 ] && targets+=(template_debug)
for t in "${targets[@]}"; do
    (cd godot && scons platform=web target="$t" dlink_enabled=yes threads=no arch=wasm32 \
        optimize=size lto=full debug_symbols=no \
        "${MODFLAGS[@]}" -j"$JOBS")
    kind=${t#template_}
    cp "godot/bin/godot.web.template_${kind}.wasm32.nothreads.dlink.zip" "$OUT/web_dlink_nothreads_${kind}.zip"
done

{
    echo "godot $GODOT_TAG ($head) emsdk $EMSDK_VERSION scons $SCONS_VERSION text_server=$TEXT_SERVER"
    echo "disabled: $DISABLED_MODULES"
    for z in "$OUT"/web_dlink_nothreads_release.zip ${OFFICIAL_ZIP:+"$OFFICIAL_ZIP"}; do
        [ -f "$z" ] || continue
        d=$(mktemp -d); (cd "$d" && python3 -m zipfile -e "$z" .)
        echo "== $z"
        for f in "$d"/*.side.wasm "$d"/godot.dlink.wasm "$d"/*.wasm; do
            [ -f "$f" ] && printf '%-36s raw %10d  gzip-9 %10d\n' "$(basename "$f")" "$(stat -c %s "$f")" "$(gzip -9 -c "$f" | wc -c)"
        done | sort -u
        rm -rf "$d"
    done
} | tee "$OUT/SIZES.txt"
(cd "$OUT" && sha256sum ./*.zip > SHA256SUMS && cat SHA256SUMS)

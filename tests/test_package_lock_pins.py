"""package.sh --host-lock: the shell's addons.lock levels reach gs_requires.gd as --pin; none without it."""
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(ROOT, "scripts", "package.sh")

# Stands in for godot: logs each call's arguments, answers lock_pins.gd with FAKE_PINS
# (`pin<TAB>NAME=LEVEL` lines) and gs_requires.gd --out with an empty requirement set.
FAKE_GODOT = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_LOG"
case "$*" in
    *lock_pins.gd*) printf 'Godot Engine banner\n'; printf '%b' "${FAKE_PINS:-}"; exit 0 ;;
esac
prev=""
for a in "$@"; do
    [ "$prev" = "--out" ] && printf '{"addons": {}}\n' > "$a"
    prev="$a"
done
exit 0
"""


def write(path, text):
    with open(path, "w") as f:
        f.write(text)


def git(cwd, *args):
    # CI runners have no git identity; the fixture commit needs one.
    env = dict(os.environ, GIT_AUTHOR_NAME="fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
               GIT_COMMITTER_NAME="fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid")
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=env)


class PackageHostLock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gsci-lockpins-")
        self.project = os.path.join(self.tmp, "game")
        os.makedirs(self.project)
        os.makedirs(os.path.join(self.project, ".godot", "imported"))
        write(os.path.join(self.project, "project.godot"), "config_version=5\n")
        write(os.path.join(self.project, "main.gd"), "extends Node\n")
        write(os.path.join(self.project, ".gitignore"), "/addons/gs_core\n/dist/\n/.godot/\n")
        git(self.project, "init", "-q")
        git(self.project, "add", ".")
        git(self.project, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture")
        self.gs_core(pins=True)
        self.lock = os.path.join(self.tmp, "addons.lock")
        write(self.lock, "gs-net\tv1.2.0\n")
        self.godot = os.path.join(self.tmp, "godot")
        write(self.godot, FAKE_GODOT)
        os.chmod(self.godot, 0o755)
        self.log = os.path.join(self.tmp, "calls.log")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def gs_core(self, pins):
        core = os.path.join(self.project, "addons", "gs_core")
        os.makedirs(os.path.join(core, "tools"), exist_ok=True)
        os.makedirs(os.path.join(core, "core"), exist_ok=True)
        write(os.path.join(core, "tools", "gs_requires.gd"), 
            'if args[i] != "--pin":\n' if pins else "extends SceneTree\n")
        write(os.path.join(core, "core", "gs_addon_api.gd"), 
            "static func pinned_levels(lock_path, repos_root):\n" if pins else "extends RefCounted\n")

    def run_package(self, *extra, pins="pin\tgs_net=3\npin\tgs_core=7\n", env=None):
        e = {k: v for k, v in os.environ.items() if k != "HOST_LOCK"}
        e.update(GODOT=self.godot, FAKE_LOG=self.log, FAKE_PINS=pins, **(env or {}))
        out = os.path.join(self.tmp, "out")
        return subprocess.run(["bash", PACKAGE, self.project, "1.0.0", "--out", out, "--pack", *extra],
                              capture_output=True, text=True, env=e)

    def calls(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log) as f:
            return f.read().splitlines()

    def requires_call(self):
        return [c for c in self.calls() if "gs_requires.gd" in c]

    def test_no_lock_passes_no_pins(self):
        r = self.run_package()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(any("lock_pins.gd" in c for c in self.calls()))
        self.assertEqual(len(self.requires_call()), 1)
        self.assertNotIn("--pin", self.requires_call()[0])

    def test_host_lock_flag_passes_the_pins(self):
        r = self.run_package("--host-lock", self.lock)
        self.assertEqual(r.returncode, 0, r.stderr)
        pins_call = [c for c in self.calls() if "lock_pins.gd" in c]
        self.assertEqual(len(pins_call), 1)
        self.assertIn("-- " + self.lock, pins_call[0])
        self.assertIn("--pin gs_net=3 --pin gs_core=7", self.requires_call()[0])
        self.assertIn("floors judged against 2 addon levels", r.stderr)

    def test_host_lock_env_passes_the_pins(self):
        r = self.run_package(env={"HOST_LOCK": self.lock})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--pin gs_net=3", self.requires_call()[0])

    def test_missing_lock_fails_before_anything(self):
        r = self.run_package("--host-lock", os.path.join(self.tmp, "nope.lock"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("no such host lock", r.stderr)
        self.assertEqual(self.calls(), [])

    def test_lock_reading_to_nothing_fails(self):
        r = self.run_package("--host-lock", self.lock, pins="")
        self.assertEqual(r.returncode, 1)
        self.assertIn("reads to no addon level", r.stderr)
        self.assertEqual(self.requires_call(), [])

    def test_old_gs_core_fails_rather_than_ignoring_pins(self):
        self.gs_core(pins=False)
        r = self.run_package("--host-lock", self.lock)
        self.assertEqual(r.returncode, 1)
        self.assertIn("cannot judge floors against a lock", r.stderr)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()

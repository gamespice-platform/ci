"""package.sh with a source.lock.json: the files git does not track are restored and shipped.
Run: python3 -m unittest discover -s tests

A stub lock_verify.sh writes every file the lock names (what --fetch does), so nothing is downloaded.
"""
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(ROOT, "scripts", "package.sh")

STUB = r"""#!/bin/bash
[ "$1" = --lock ] && [ "$3" = --fetch ] || exit 2
python3 -I -c '
import json, os, sys
for files in json.load(open(sys.argv[1]))["source_files"].values():
    for p in files:
        os.makedirs(os.path.dirname(os.path.join(sys.argv[2], p)), exist_ok=True)
        open(os.path.join(sys.argv[2], p), "w").write("bytes of " + p)
' "$2" "$4"
"""

LOCKED = ["assets/sword.glb", "addons/thing/model.glb"]


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def git(cwd, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
               GIT_COMMITTER_NAME="fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid")
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=env)


class PackageSourceLock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gsci-srclock-")
        self.cloud = os.path.join(self.tmp, "cloud")
        write(os.path.join(self.cloud, "tools", "lock_verify.sh"), STUB)
        self.out = os.path.join(self.tmp, "out")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def project(self, addon):
        proj = os.path.join(self.tmp, "game")
        write(os.path.join(proj, "project.godot"), "config_version=5\n")
        write(os.path.join(proj, "main.gd"), "extends Node\n")
        write(os.path.join(proj, "source.lock.json"),
              json.dumps({"source_files": {"pack": {p: "0" * 64 for p in LOCKED}}}))
        if addon:
            write(os.path.join(proj, "addons", "thing", "plugin.cfg"), 'version="0"\n')
        os.makedirs(os.path.join(proj, ".godot", "imported"))
        git(proj, "init", "-q")
        git(proj, "add", ".")
        git(proj, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture")
        return proj

    def run_package(self, proj, *extra, cloud=True):
        env = {k: v for k, v in os.environ.items() if k != "GS_CLOUD"}
        if cloud:
            env["GS_CLOUD"] = self.cloud
        return subprocess.run(["bash", PACKAGE, proj, "1.0.0", "--out", self.out, "--name", "game", *extra],
                              capture_output=True, text=True, env=env)

    def test_tarball_holds_the_untracked_files(self):
        r = self.run_package(self.project(addon=False))
        self.assertEqual(r.returncode, 0, r.stderr)
        with tarfile.open(os.path.join(self.out, "game-1.0.0.tar.gz")) as t:
            names = set(t.getnames())
        for p in LOCKED:
            self.assertIn("game-1.0.0/" + p, names)
        self.assertIn("game-1.0.0/main.gd", names)

    def test_addon_zip_and_pack_hold_them(self):
        r = self.run_package(self.project(addon=True), "--pack", "--pack-owned-addons")
        self.assertEqual(r.returncode, 0, r.stderr)
        with zipfile.ZipFile(os.path.join(self.out, "thing-1.0.0.zip")) as z:
            self.assertIn("addons/thing/model.glb", z.namelist())
        with zipfile.ZipFile(os.path.join(self.out, "game-1.0.0-pack.zip")) as z:
            self.assertIn("assets/sword.glb", z.namelist())
            self.assertIn("addons/thing/model.glb", z.namelist())

    def test_no_cloud_checkout_fails_loudly(self):
        r = self.run_package(self.project(addon=False), cloud=False)
        self.assertEqual(r.returncode, 2)
        self.assertIn("FAIL", r.stderr)

    def test_no_lock_is_unchanged(self):
        proj = self.project(addon=False)
        os.remove(os.path.join(proj, "source.lock.json"))
        git(proj, "rm", "-q", "--cached", "source.lock.json")
        git(proj, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "no lock")
        r = self.run_package(proj, cloud=False)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()

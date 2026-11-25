"""The source-lock restore: fetch-source-lock.sh, its use in resolve-deps.sh and in validate.yml.
Run: python3 -m unittest discover -s tests

A stub lock_verify.sh stands in for gs-cloud's (it only records that it was asked), so nothing is downloaded.
"""
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(__file__)
FETCH = os.path.join(HERE, "..", "scripts", "fetch-source-lock.sh")
RESOLVE = os.path.join(HERE, "..", "scripts", "resolve-deps.sh")
WORKFLOW = os.path.join(HERE, "..", ".github", "workflows", "validate.yml")

STUB = '#!/bin/bash\n[ "$1" = --lock ] && [ "$3" = --fetch ] || exit 2\nprintf restored > "$4/restored.bin"\n'


def fake_cloud(root, exit_code=0):
    os.makedirs(os.path.join(root, "tools"))
    p = os.path.join(root, "tools", "lock_verify.sh")
    with open(p, "w") as f:
        f.write(STUB + ("exit %d\n" % exit_code))


class FetchScript(unittest.TestCase):
    def test_no_lock_is_a_quiet_success(self):
        with tempfile.TemporaryDirectory() as t:
            out = subprocess.run(["bash", FETCH, t, os.path.join(t, "none")], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertFalse(os.path.exists(os.path.join(t, "restored.bin")))

    def test_lock_restores_through_lock_verify(self):
        with tempfile.TemporaryDirectory() as t:
            cloud, proj = os.path.join(t, "cloud"), os.path.join(t, "proj")
            os.makedirs(proj)
            fake_cloud(cloud)
            open(os.path.join(proj, "source.lock.json"), "w").write("{}")
            out = subprocess.run(["bash", FETCH, proj, cloud], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertTrue(os.path.exists(os.path.join(proj, "restored.bin")))

    def test_lock_without_the_fetcher_fails(self):
        with tempfile.TemporaryDirectory() as t:
            open(os.path.join(t, "source.lock.json"), "w").write("{}")
            out = subprocess.run(["bash", FETCH, t, os.path.join(t, "none")], capture_output=True, text=True)
            self.assertEqual(out.returncode, 2)
            self.assertIn("FAIL", out.stderr)

    def test_a_failed_download_fails(self):
        with tempfile.TemporaryDirectory() as t:
            cloud, proj = os.path.join(t, "cloud"), os.path.join(t, "proj")
            os.makedirs(proj)
            fake_cloud(cloud, 1)
            open(os.path.join(proj, "source.lock.json"), "w").write("{}")
            out = subprocess.run(["bash", FETCH, proj, cloud], capture_output=True, text=True)
            self.assertEqual(out.returncode, 1)


class ResolveDeps(unittest.TestCase):
    def run_resolve(self, t, cloud_code):
        proj, cloud = os.path.join(t, "proj"), os.path.join(t, "gs-cloud")
        fake_cloud(cloud, cloud_code)
        clone = os.path.join(proj, ".deps", "zz-medieval-weapons")
        os.makedirs(os.path.join(clone, ".git"))
        os.makedirs(os.path.join(clone, "addons", "zz_medieval_weapons"))
        open(os.path.join(clone, "source.lock.json"), "w").write("{}")
        open(os.path.join(proj, ".gitignore"), "w").write("/addons/zz_medieval_weapons\n")
        out = subprocess.run(["bash", RESOLVE, proj], capture_output=True, text=True,
                             env={**os.environ, "GIT_HOST": "invalid.invalid", "GS_CLOUD": cloud})
        return out, clone

    def test_a_locked_addon_clone_is_restored_before_it_is_linked(self):
        with tempfile.TemporaryDirectory() as t:
            out, clone = self.run_resolve(t, 0)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertTrue(os.path.exists(os.path.join(clone, "restored.bin")))
            self.assertTrue(os.path.islink(os.path.join(t, "proj", "addons", "zz_medieval_weapons")))

    def test_a_failed_restore_fails_the_resolve(self):
        with tempfile.TemporaryDirectory() as t:
            out, _ = self.run_resolve(t, 1)
            self.assertEqual(out.returncode, 1)
            self.assertIn("could not restore", out.stderr)


class WorkflowStep(unittest.TestCase):
    def setUp(self):
        self.text = open(WORKFLOW).read()

    def test_restore_runs_after_gs_cloud_is_checked_out_and_before_the_import(self):
        t = self.text
        self.assertLess(t.index("Check out gs-cloud"), t.index("Restore the untracked source files"))
        self.assertLess(t.index("Restore the untracked source files"), t.index("Resolve the addons this project declares"))
        self.assertLess(t.index("Resolve the addons this project declares"), t.index("Import, parse, and run every suite"))

    def test_restore_is_not_conditional_and_resolve_deps_gets_gs_cloud(self):
        i = self.text.index("- name: Restore the untracked source files")
        body = self.text[i:self.text.index("run:", i) + 80].split("\n")[1:3]
        self.assertFalse(any("if:" in ln for ln in body))
        self.assertIn("fetch-source-lock.sh project gs-cloud", "\n".join(body))
        self.assertIn("GS_CLOUD: ${{ github.workspace }}/gs-cloud", self.text)


if __name__ == "__main__":
    unittest.main()

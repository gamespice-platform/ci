"""resolve-deps.sh links a renamed addon under the directory its ref holds. Run: python3 -m unittest discover -s tests

fc-weapons (Fatal Contact's weapons) holds addons/fc_weapons; its tags up to v1.4.51 hold the legacy addons/arena_weapons.
The clones are made ready in .deps beforehand, so nothing is fetched.
"""
import os
import subprocess
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "resolve-deps.sh")


def project(root, lock=None, gitignore="", clone="fc-weapons", holds="fc_weapons"):
    os.makedirs(os.path.join(root, ".deps", clone, ".git"))
    os.makedirs(os.path.join(root, ".deps", clone, "addons", holds))
    with open(os.path.join(root, ".gitignore"), "w") as f:
        f.write(gitignore)
    if lock is not None:
        with open(os.path.join(root, "addons.lock"), "w") as f:
            f.write(lock)
    out = subprocess.run(["bash", SCRIPT, root], capture_output=True, text=True,
                         env={**os.environ, "GIT_HOST": "invalid.invalid"})
    return out


class RenamedDir(unittest.TestCase):
    def test_lock_at_a_legacy_ref_links_the_legacy_dir_and_says_so(self):
        with tempfile.TemporaryDirectory() as t:
            out = project(t, lock="fc-weapons\tv1.4.51\n", clone="fc-weapons@v1.4.51", holds="arena_weapons")
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertTrue(os.path.islink(os.path.join(t, "addons", "arena_weapons")))
            self.assertFalse(os.path.lexists(os.path.join(t, "addons", "fc_weapons")))
            self.assertIn("WRN", out.stderr)
            self.assertIn("v1.4.51", out.stderr)
            self.assertIn("legacy addons/arena_weapons", out.stderr)

    def test_lock_at_a_renamed_ref_links_fc_weapons_quietly(self):
        with tempfile.TemporaryDirectory() as t:
            out = project(t, lock="fc-weapons\tv1.5.0\n", clone="fc-weapons@v1.5.0", holds="fc_weapons")
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertTrue(os.path.islink(os.path.join(t, "addons", "fc_weapons")))
            self.assertNotIn("WRN", out.stderr)

    def test_a_project_naming_the_legacy_dir_on_a_renamed_ref_fails(self):
        with tempfile.TemporaryDirectory() as t:
            out = project(t, gitignore="/addons/arena_weapons\n", holds="fc_weapons")
            self.assertNotEqual(out.returncode, 0)
            self.assertIn("names the legacy addons/arena_weapons", out.stderr)
            self.assertFalse(os.path.lexists(os.path.join(t, "addons", "arena_weapons")))

    def test_a_project_naming_fc_weapons_on_a_legacy_ref_fails(self):
        with tempfile.TemporaryDirectory() as t:
            out = project(t, gitignore="/addons/fc_weapons\n", holds="arena_weapons")
            self.assertNotEqual(out.returncode, 0)
            self.assertIn("still holds the legacy addons/arena_weapons", out.stderr)

    def test_a_project_naming_the_legacy_dir_on_a_legacy_ref_links_and_warns(self):
        with tempfile.TemporaryDirectory() as t:
            out = project(t, gitignore="/addons/arena_weapons\n", holds="arena_weapons")
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertTrue(os.path.islink(os.path.join(t, "addons", "arena_weapons")))
            self.assertIn("WRN   addons/arena_weapons is the legacy name", out.stderr)


if __name__ == "__main__":
    unittest.main()

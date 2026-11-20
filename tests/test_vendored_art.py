"""scripts/check-vendored-art.py on fixture repositories: an addon with an art table and games that vendor its art."""
import os
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "check-vendored-art.py")
TABLE = 'const GUNS := "res://assets/guns/"\nstatic func a(): return GUNS + "a.glb"\nstatic func b(): return GUNS + "b.glb"\n'


def run(root, *cmd):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                            GIT_COMMITTER_EMAIL="t@t", GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null"))


class VendoredArt(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.addon = self.repo("zee-x", {"assets/guns/a.glb": "A1", "assets/guns/a.glb.import": "uid=1\nx=1\n",
                                         "assets/guns/b.glb": "B1", "assets/guns/b.glb.import": "uid=2\n",
                                         "addons/zee_weapons/art/zee_weapon_art_table.gd": TABLE,
                                         "tools/sync-art.sh": "#!/bin/sh\n"})

    def repo(self, name, files):
        path = os.path.join(self.root, name)
        for rel, text in files.items():
            os.makedirs(os.path.dirname(os.path.join(path, rel)), exist_ok=True)
            open(os.path.join(path, rel), "w").write(text)
        if name.startswith("game-"):
            os.makedirs(os.path.join(path, "addons", "zee_weapons"))
        run(path, "git", "init", "-q", "-b", "main")
        run(path, "git", "add", "-A", "-f")
        run(path, "git", "commit", "-q", "-m", "x")
        return path

    def check(self):
        return subprocess.run(["python3", SCRIPT, "--addon", self.addon], capture_output=True, text=True)

    def test_current_game_passes_and_import_uid_is_ignored(self):
        self.repo("game-ok", {"assets/guns/a.glb": "A1", "assets/guns/a.glb.import": "uid=9\nx=1\n",
                              "assets/guns/b.glb": "B1", "assets/guns/b.glb.import": "uid=8\n"})
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("1 game(s)", r.stdout)

    def test_changed_files_are_listed(self):
        self.repo("game-old", {"assets/guns/a.glb": "A0", "assets/guns/a.glb.import": "uid=1\nx=1\n"})
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("stale:   assets/guns/a.glb", r.stdout)
        self.assertNotIn("assets/guns/a.glb.import", r.stdout)
        self.assertIn("sync-art.sh", r.stdout)

    def test_game_without_the_art_dir_or_the_addon_is_not_a_consumer(self):
        self.repo("game-other", {"readme": "x"})
        self.repo("lib-y", {"assets/guns/a.glb": "old"})
        self.assertEqual(self.check().returncode, 0)


if __name__ == "__main__":
    unittest.main()

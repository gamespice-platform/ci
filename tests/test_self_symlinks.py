import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "check-self-symlinks.py")


def run(root):
    return subprocess.run([sys.executable, SCRIPT, root], capture_output=True, text=True)


class SelfSymlinks(unittest.TestCase):
    def repo(self, d, link, target):
        subprocess.run(["git", "init", "-q", d], check=True)
        os.makedirs(os.path.join(d, "addons"))
        os.symlink(target, os.path.join(d, link))
        subprocess.run(["git", "-C", d, "add", link], check=True)

    def test_self_link_fails(self):
        with tempfile.TemporaryDirectory() as d:
            self.repo(d, "addons/maps", os.path.join(d, "addons/maps"))
            self.assertEqual(run(d).returncode, 1)

    def test_relative_link_passes(self):
        with tempfile.TemporaryDirectory() as d:
            self.repo(d, "addons/x", "../../gs-x/addons/x")
            self.assertEqual(run(d).returncode, 0)


if __name__ == "__main__":
    unittest.main()

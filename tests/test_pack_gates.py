"""scripts/pack-gates.sh and pre-tag.sh: static gate hard, server-compat advisory or strict.
Run: python3 -m unittest discover -s tests

server-compat.sh needs the network, so each test runs a copy of scripts/ whose server-compat.sh is a stub."""
import os, shutil, subprocess, tempfile, unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
RELEASE_YML = """jobs:
    release:
        uses: x/ci/.github/workflows/release.yml@v1
        with:
            pack: true
            pack-deny: 'tmcdev'
"""


class Gates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.scripts = os.path.join(self.tmp, "scripts")
        shutil.copytree(os.path.join(ROOT, "scripts"), self.scripts, ignore=shutil.ignore_patterns("__pycache__"))

    def stub_compat(self, rc):
        p = os.path.join(self.scripts, "server-compat.sh")
        with open(p, "w") as f:
            f.write('#!/usr/bin/env bash\necho "  FAIL  need level 45, server has 44"\nexit %d\n' % rc)
        os.chmod(p, 0o755)

    def game(self, lock="{}"):
        g = os.path.join(self.tmp, "game-x")
        os.makedirs(os.path.join(g, ".github", "workflows"))
        os.makedirs(os.path.join(g, ".godot", "imported"))
        open(os.path.join(g, "project.godot"), "w").write("config_version=5\n")
        open(os.path.join(g, "content.lock.json"), "w").write(lock)
        open(os.path.join(g, ".github", "workflows", "release.yml"), "w").write(RELEASE_YML)
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        for c in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "x"]):
            subprocess.run(["git", *c], cwd=g, env=env, check=True)
        return g

    def run_script(self, name, *args):
        r = subprocess.run([os.path.join(self.scripts, name), *args], capture_output=True, text=True,
                           env={**os.environ, "GITHUB_STEP_SUMMARY": os.path.join(self.tmp, "summary")})
        return r.returncode, r.stdout + r.stderr

    def test_clean_lock_passes_with_unmet_compat_advisory(self):
        self.stub_compat(1)
        g = self.game('{"origin": "https://example.org"}')
        rc, out = self.run_script("pack-gates.sh", g, "--no-import", "--compat", "advisory", "--deny", "tmcdev")
        self.assertEqual(rc, 0, out)
        self.assertIn("::warning::server-compat", out)
        self.assertIn("advisory", open(os.path.join(self.tmp, "summary")).read())

    def test_deny_match_fails_even_in_advisory(self):
        self.stub_compat(0)
        g = self.game('{"origin": "https://x.tmcdev.net"}')
        rc, out = self.run_script("pack-gates.sh", g, "--no-import", "--compat", "advisory", "--deny", "tmcdev")
        self.assertNotEqual(rc, 0, out)
        self.assertIn("pack-static gate failed", out)

    def test_strict_fails_on_unmet_compat(self):
        self.stub_compat(1)
        g = self.game()
        rc, out = self.run_script("pack-gates.sh", g, "--no-import", "--compat", "strict")
        self.assertNotEqual(rc, 0, out)
        self.assertIn("::error::server-compat", out)

    def test_pre_tag_reads_release_yml(self):
        self.stub_compat(0)
        g = self.game('{"origin": "https://example.org"}')
        os.makedirs(os.path.join(self.tmp, "bin"))
        godot = os.path.join(self.tmp, "bin", "godot")
        open(godot, "w").write("#!/bin/sh\nexit 0\n")
        os.chmod(godot, 0o755)
        env = {**os.environ, "GODOT": godot}
        r = subprocess.run([os.path.join(self.scripts, "pre-tag.sh"), g], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        open(os.path.join(g, "content.lock.json"), "w").write('{"o": "x-tmc-dev tmcdev"}')
        subprocess.run(["git", "-C", g, "commit", "-qam", "bad"], check=True,
                       env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
        r = subprocess.run([os.path.join(self.scripts, "pre-tag.sh"), g], capture_output=True, text=True, env=env)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_validate_calls_it_advisory_after_the_import(self):
        t = open(os.path.join(ROOT, ".github", "workflows", "validate.yml")).read()
        self.assertIn("pack-gates.sh project", t)
        self.assertIn("--compat advisory", t)
        self.assertLess(t.index("check.sh project"), t.index("pack-gates.sh project"))


if __name__ == "__main__":
    unittest.main()

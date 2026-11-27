"""The owner-identity / efficiency-gate git hook (scripts/owner-identity-hook), run as pre-push on fixture repositories.

Each case is a defect the hook had (vjudge-solid review): a no-op or docs-only push blocked by debt already on main, a
crashing gate read as a failure, a new branch gated on every file. Run: python3 -m unittest discover -s tests"""
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "..", "scripts", "owner-identity-hook")
SCRIPTS = os.path.join(HERE, "..", "scripts")
OWNER = ("Christian Deacon", "christianmdeacon@gmail.com")
ZERO = "0" * 40


def long_func(name, n):
    return "func %s():\n" % name + "".join("\tvar a%d = %d\n" % (i, i) for i in range(n)) + "\n"


class OwnerHook(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.repo = os.path.join(self.root, "game")
        os.makedirs(self.repo)
        self.git("init", "-q", "-b", "main")
        self.git("remote", "add", "origin", "ssh://git@example.invalid/org/game.git")
        self.hooks = os.path.join(self.root, "hooks")
        os.makedirs(self.hooks)
        os.symlink(os.path.abspath(HOOK), os.path.join(self.hooks, "pre-push"))
        self.siblings = os.path.join(self.root, "siblings")
        os.makedirs(self.siblings)
        self.write("a.gd", long_func("small", 10))
        self.write("README.md", "game\n")
        self.assertEqual(subprocess.run(["python3", os.path.join(SCRIPTS, "check-size.py"), "--init", "."], cwd=self.repo,
                                        capture_output=True).returncode, 0)
        self.base = self.commit("baseline")

    def git(self, *args, env=None):
        e = dict(os.environ, GIT_AUTHOR_NAME=OWNER[0], GIT_AUTHOR_EMAIL=OWNER[1], GIT_COMMITTER_NAME=OWNER[0],
                 GIT_COMMITTER_EMAIL=OWNER[1])
        e.update(env or {})
        r = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args], cwd=self.repo, env=e, capture_output=True,
                           text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def write(self, name, body):
        with open(os.path.join(self.repo, name), "w") as fh:
            fh.write(body)

    def commit(self, msg, env=None):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg, env=env)
        return self.git("rev-parse", "HEAD")

    def push(self, lsha, rsha, scripts=SCRIPTS):
        env = dict(os.environ, OWNER_HOOK_GATE_SCRIPTS=scripts, OWNER_HOOK_SIBLINGS=self.siblings)
        r = subprocess.run([os.path.join(self.hooks, "pre-push"), "origin", "ssh://git@example.invalid/org/game.git"],
                           cwd=self.repo, env=env, input="refs/heads/main %s refs/heads/main %s\n" % (lsha, rsha),
                           capture_output=True, text=True)
        return r.returncode, r.stderr

    def debt(self):
        """main (the remote) already fails check-size: a function over the limit that the baseline does not list."""
        self.write("debt.gd", long_func("big", 90))
        return self.commit("debt on main")

    def test_new_violation_refused(self):
        self.write("b.gd", long_func("huge", 90))
        code, err = self.push(self.commit("adds a long function"), self.base)
        self.assertEqual(code, 1, err)
        self.assertIn("adds failures", err)
        self.assertIn("b.gd::huge", err)

    def test_noop_push_with_debt_passes(self):
        main = self.debt()
        code, err = self.push(main, main)
        self.assertEqual(code, 0, err)

    def test_docs_only_push_with_debt_passes(self):
        main = self.debt()
        self.write("README.md", "game, now documented\n")
        code, err = self.push(self.commit("docs only"), main)
        self.assertEqual(code, 0, err)
        self.assertNotIn("refusing", err)

    def test_gd_push_over_existing_debt_reports_not_refuses(self):
        main = self.debt()
        self.write("a.gd", long_func("small", 12))
        code, err = self.push(self.commit("touch a.gd, no new violation"), main)
        self.assertEqual(code, 0, err)
        self.assertIn("already fails", err)
        self.assertIn("debt.gd::big", err)

    def test_worse_debt_refused(self):
        main = self.debt()
        self.write("debt.gd", long_func("big", 95))
        code, err = self.push(self.commit("makes the debt worse"), main)
        self.assertEqual(code, 1, err)
        self.assertIn("debt.gd::big", err)

    def listed_debt(self):
        """main's debt is listed in its baseline: big.gd::big at 90 lines (CI passes)."""
        self.write("big.gd", long_func("big", 90))
        self.git("rm", "-q", "ci/efficiency/size.tsv")
        self.git("add", "-A")   # --init lists tracked files
        self.assertEqual(subprocess.run(["python3", os.path.join(SCRIPTS, "check-size.py"), "--init", "."], cwd=self.repo,
                                        capture_output=True).returncode, 0)
        return self.commit("listed debt on main")

    def test_moved_debt_function_is_known(self):
        """vjudge-second-review point 3: moving a function the baseline lists to another file changes its key
        (big.gd::big -> moved.gd::big); that is the same debt, not a new violation."""
        for listed in (False, True):
            with self.subTest(listed=listed):
                main = self.listed_debt() if listed else self.debt()
                src = "big.gd" if listed else "debt.gd"
                os.remove(os.path.join(self.repo, src))
                self.write("moved.gd", long_func("big", 90))
                code, err = self.push(self.commit("move the function"), main)
                self.assertEqual(code, 0, err)
                self.assertIn("moved.gd::big", err)
                self.assertIn("(moved)", err)
                self.git("reset", "-q", "--hard", self.base)

    def test_moved_debt_grown_or_copied_refused(self):
        main = self.listed_debt()
        self.write("other.gd", long_func("big", 90))   # a second big() while big.gd::big stays: new debt
        code, err = self.push(self.commit("copy, not move"), main)
        self.assertEqual(code, 1, err)
        self.assertIn("other.gd::big", err)
        self.git("reset", "-q", "--hard", main)
        os.remove(os.path.join(self.repo, "big.gd"))
        self.write("moved.gd", long_func("big", 95))   # moved and grown
        code, err = self.push(self.commit("move and grow"), main)
        self.assertEqual(code, 1, err)
        self.assertIn("moved.gd::big", err)

    def test_raised_baseline_refused(self):
        """A push that adds or raises a baseline entry passes its own gates; it is refused as what it is."""
        main = self.listed_debt()
        self.write("b.gd", long_func("huge", 90))
        with open(os.path.join(self.repo, "ci/efficiency/size.tsv"), "a") as fh:
            fh.write("b.gd::huge\t90\n")
        code, err = self.push(self.commit("adds a long function and lists it"), main)
        self.assertEqual(code, 1, err)
        self.assertIn("baseline raised or added: size b.gd::huge 90", err)

    def test_baseline_shrink_and_first_init_pass(self):
        main = self.listed_debt()
        self.write("big.gd", long_func("big", 85))
        subprocess.run(["python3", os.path.join(SCRIPTS, "check-size.py"), "--update", "."], cwd=self.repo,
                       capture_output=True)
        main = self.push_ok(self.commit("shrinks the debt"), main)
        self.assertEqual(subprocess.run(["python3", os.path.join(SCRIPTS, "check-frame-hazards.py"), "--init", "."],
                                        cwd=self.repo, capture_output=True).returncode, 0)
        self.write("c.gd", long_func("ok", 5))
        self.push_ok(self.commit("opts in to another gate"), main)

    def push_ok(self, sha, main):
        code, err = self.push(sha, main)
        self.assertEqual(code, 0, err)
        self.assertNotIn("refusing", err)
        return sha

    def test_crashing_gate_warns(self):
        fake = os.path.join(self.root, "fake-scripts")
        shutil.copytree(SCRIPTS, fake, ignore=shutil.ignore_patterns("__pycache__"))
        with open(os.path.join(fake, "check-size.py"), "w") as fh:
            fh.write("raise SystemExit('boom: the gate broke')\n")
        self.write("b.gd", long_func("ok", 5))
        code, err = self.push(self.commit("small change"), self.base, scripts=fake)
        self.assertEqual(code, 0, err)
        self.assertIn("did not run", err)

    def hot_tick(self, body):
        self.write("ci/efficiency/gd-perf-hot.txt", "hot.gd\n")
        self.write("hot.gd", "func tick(n: int) -> int:\n" + body + "\treturn n\n")
        self.git("add", "-A")   # the gate lists tracked files

    def test_gd_perf_new_violation_refused(self):
        """A hot function that starts allocating per tick is refused like an over-long one."""
        self.hot_tick("")
        main = self.push_ok(self.commit("a clean hot script"), self.base)
        self.hot_tick("\tvar d: Dictionary[int, int] = {}\n")
        code, err = self.push(self.commit("allocates in the tick"), main)
        self.assertEqual(code, 1, err)
        self.assertIn("hot.gd::tick::alloc", err)

    def test_gd_perf_baselined_debt_passes(self):
        """gd-perf debt the baseline lists is not refused; only new or worse is."""
        self.hot_tick("\tvar d: Dictionary[int, int] = {}\n")
        self.assertEqual(subprocess.run(["python3", os.path.join(SCRIPTS, "check-gd-perf.py"), "--init", "."],
                                        cwd=self.repo, capture_output=True).returncode, 0)
        main = self.push_ok(self.commit("hot script with listed debt"), self.base)
        self.write("a.gd", long_func("small", 12))
        self.push_ok(self.commit("unrelated .gd change"), main)

    def test_new_branch_gates_unpushed_commits(self):
        self.write("b.gd", long_func("huge", 90))
        code, err = self.push(self.commit("first push of a branch to main"), ZERO)
        self.assertEqual(code, 1, err)
        self.assertIn("b.gd::huge", err)

    def test_foreign_identity_refused(self):
        self.write("c.gd", long_func("ok", 5))
        sha = self.commit("wrong author", env={"GIT_AUTHOR_NAME": "agent", "GIT_AUTHOR_EMAIL": "a@b"})
        code, err = self.push(sha, self.base)
        self.assertEqual(code, 1, err)
        self.assertIn("not authored and committed", err)


if __name__ == "__main__":
    unittest.main()

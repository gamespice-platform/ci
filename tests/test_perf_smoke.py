"""perf-smoke.sh: warm-up value validation and the budget's warmup_frames key."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SMOKE = os.path.join(ROOT, "scripts", "perf-smoke.sh")
BUDGET = os.path.join(ROOT, "scripts", "perf-budget.py")


def project(budget=None):
    d = tempfile.mkdtemp()
    open(os.path.join(d, "project.godot"), "w").write('run/main_scene="res://m.tscn"\n')
    if budget is not None:
        os.makedirs(os.path.join(d, "ci", "perf"))
        json.dump(budget, open(os.path.join(d, "ci", "perf", "smoke.json"), "w"))
    return d


class PerfSmoke(unittest.TestCase):
    def run_smoke(self, *args, env=None):
        e = dict(os.environ, GODOT="/bin/false", **(env or {}))
        return subprocess.run(["bash", SMOKE, *args], capture_output=True, text=True, env=e)

    def test_bad_flag_value_fails_loudly(self):
        for bad in ("-1", "abc", "1.5"):
            r = self.run_smoke("--warmup", bad, project())
            self.assertEqual(r.returncode, 2, bad)
            self.assertIn("not an integer", r.stderr)

    def test_bad_env_value_fails_loudly(self):
        r = self.run_smoke(project(), env={"PERF_WARMUP_FRAMES": "x"})
        self.assertEqual(r.returncode, 2)

    def test_bad_budget_key_fails_loudly(self):
        r = self.run_smoke(project({"warmup_frames": "many"}))
        self.assertEqual(r.returncode, 2)

    def test_zero_and_default_pass_validation(self):
        for args in (["--warmup", "0"], []):
            r = self.run_smoke(*args, project())
            self.assertNotIn("not an integer", r.stderr)

    def test_read_warmup_key(self):
        p = os.path.join(project({"warmup_frames": 4}), "ci", "perf", "smoke.json")
        r = subprocess.run([sys.executable, BUDGET, "read", p, "warmup_frames"], capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "4")


if __name__ == "__main__":
    unittest.main()

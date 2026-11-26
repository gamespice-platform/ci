"""Fixtures for check-no-uid-loads.py. Run: python3 -m unittest discover -s tests"""
import importlib.util
import os
import unittest

spec = importlib.util.spec_from_file_location(
    "nu", os.path.join(os.path.dirname(__file__), "..", "scripts", "check-no-uid-loads.py"))
nu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nu)


class NoUidLoads(unittest.TestCase):
    def test_load_and_preload_fail(self):
        self.assertEqual(len(nu.problems("addons/x/a.gd", 'var s = load("uid://b0h67pyeqben")\n')), 1)
        self.assertEqual(len(nu.problems("addons/x/a.gd", "const S := preload('uid://cb3jej8cfm0h0')\n")), 1)

    def test_load_in_examples_fails(self):
        self.assertEqual(len(nu.problems("examples/t.gd", 'var s = load("uid://b0h67pyeqben")\n')), 1)

    def test_const_literal_fails_outside_fixtures(self):
        self.assertEqual(len(nu.problems("addons/x/a.gd", 'const _P_UID := "uid://d1wk1ddon2tyq"\n')), 1)
        self.assertEqual(nu.problems("examples/demo.gd", 'var id := ResourceUID.text_to_id("uid://b7prob3th1ng")\n'), [])

    def test_prefix_check_comment_and_path_pass(self):
        text = ('if path.begins_with("uid://"):\n'
                '# load("uid://abcd1234") was the old way\n'
                'var s = load("res://addons/x/b.gd")\n')
        self.assertEqual(nu.problems("addons/x/a.gd", text), [])

    def test_allow_and_non_gd(self):
        self.assertEqual(nu.problems("addons/x/a.gd", 'load("uid://abcd1234")  # uid-load: allow probe\n'), [])
        self.assertEqual(nu.problems("scenes/a.tscn", '[ext_resource uid="uid://abcd1234"]\n'), [])


if __name__ == "__main__":
    unittest.main()

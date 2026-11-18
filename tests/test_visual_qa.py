"""Fixtures for check-visual-qa.py. Run: python3 -m unittest discover -s tests"""
import importlib.util
import os
import unittest

spec = importlib.util.spec_from_file_location(
    "vq", os.path.join(os.path.dirname(__file__), "..", "scripts", "check-visual-qa.py"))
vq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vq)

GAME = {"game.sh", "project.godot"}


class VisualQa(unittest.TestCase):
    def test_not_a_game(self):
        self.assertEqual(vq.problems({"project.godot"}, {}), [])

    def test_missing(self):
        self.assertTrue(vq.problems(GAME, {}))

    def test_allowed(self):
        self.assertEqual(vq.problems(GAME, {}, True), [])

    def test_present(self):
        self.assertEqual(vq.problems(GAME | {"tools/visual_qa.gd"}, {}), [])

    def test_wrapper_must_be_executable(self):
        f = GAME | {"tools/visual_qa.gd", "tools/visual_qa_shot.sh"}
        self.assertTrue(vq.problems(f, {"tools/visual_qa_shot.sh": "100644"}))
        self.assertEqual(vq.problems(f, {"tools/visual_qa_shot.sh": "100755"}), [])

"""Fixtures for check-split-names.py. Run: python3 -m unittest discover -s tests"""
import importlib.util
import os
import unittest

spec = importlib.util.spec_from_file_location(
    "sn", os.path.join(os.path.dirname(__file__), "..", "scripts", "check-split-names.py"))
sn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sn)

GOOD = ["game/fc_game_combat.gd", "examples/headless_match_modes_and_drops.gd", "docs/partition.md",
        "addons/x/gs_partner.gd", "a/departure_2d.gd", "x/gs_spawn_area_3d.gd", "x/gs_browser_a2s.gd", "x/bake_e2e.gd",
        "avatars/body_kenney_a.tscn", "x/net_v2.gd", "x/blob_2d.tscn", "x/helpers.gd", "x/gs_misc_tools.gd",
        "dir/counterpart.gd", "x/spart1.gd", "x/rhino_pt_hull.gd"]
BAD = ["game/fc_game_part1.gd", "game/fc_game_part2a.gd", "game/fc_game_part2a.gd.uid",
       "examples/headless_net_part10.gd", "part3.gd", "x/foo-part2.md", "x/foo_pt4.py",
       "x/misc.gd", "misc/a.gd", "x/helpers2.gd", "x/Utils3.gd", "x/stuff.md", "a_part1/b.gd",
       "examples/selftest/tests_a.gd", "x/tests_a.gd.uid", "x/dedicated_tests_a2.gd", "game/arena_presentation_b2a.gd",
       "x/foo_2.gd", "x/foo_b1.rs", "tools/screenshot_b1.py", "x/loadout_demo_g.sh"]


class SplitNames(unittest.TestCase):
    def test_good(self):
        for p in GOOD:
            self.assertEqual(sn.problems([p]), [], p)

    def test_bad(self):
        for p in BAD:
            self.assertTrue(sn.problems([p]), p)

    def test_allowlist(self):
        self.assertEqual(sn.problems(["x/vendor_part1.gd"], {"x/vendor_part1.gd"}), [])

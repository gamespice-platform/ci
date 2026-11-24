"""Fixtures for check-pack-static.py. Run: python3 -m unittest discover -s tests"""
import importlib.util, os, re, tempfile, unittest, zipfile

spec = importlib.util.spec_from_file_location(
    "cps", os.path.join(os.path.dirname(__file__), "..", "scripts", "check-pack-static.py"))
cps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cps)


def run(files, deny=()):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "x-pack.zip")
        with zipfile.ZipFile(p, "w") as z:
            for k, v in files.items():
                z.writestr(k, v)
        with zipfile.ZipFile(p) as z:
            return cps.judge(z, [re.compile(x) for x in deny])


class PackStatic(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(run({"a.gd": "class_name Foo\n", "a.gd.uid": "uid://aaa\n"})[1], [])

    def test_stale_dot_addon(self):
        self.assertTrue(run({"addons/dot_combat/x.gd": ""})[1])

    def test_dot_class(self):
        self.assertTrue(run({"a.gd": "class_name DotThing\n"})[1])

    def test_duplicate_uid(self):
        bad = run({"a.gd.uid": "uid://same\n", "b.gd.uid": "uid://same\n"})[1]
        self.assertTrue(any("duplicate uid" in b for b in bad))

    def test_deny(self):
        self.assertTrue(run({"cfg/x.json": '{"u":"https://dev.example.test"}'}, ["dev\\.example"])[1])
        self.assertEqual(run({"cfg/x.json": '{"u":"https://x.test"}'}, ["dev\\.example"])[1], [])


if __name__ == "__main__":
    unittest.main()

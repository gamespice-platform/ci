"""Fixtures for web-build-report.py. Run: python3 -m unittest discover -s tests"""
import importlib.util
import os
import struct
import tempfile
import unittest

here = os.path.dirname(__file__)
spec = importlib.util.spec_from_file_location("wbr", os.path.join(here, "..", "scripts", "web-build-report.py"))
wbr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wbr)


def pck_v3(entries):
    """A format 3 pck directory holding [(path, size)]; the file bodies are not written."""
    head = b"GDPC" + struct.pack("<5I", 3, 4, 7, 2, 0) + struct.pack("<Q", 0)
    diroff = len(head) + 8
    d = struct.pack("<I", len(entries))
    for name, size in entries:
        raw = name.encode()
        raw += b"\0" * (-len(raw) % 4)
        d += struct.pack("<I", len(raw)) + raw + struct.pack("<QQ", 0, size) + b"\0" * 16 + struct.pack("<I", 0)
    return head + struct.pack("<Q", diroff) + d


class ReadPck(unittest.TestCase):
    def test_lists_paths_and_sizes(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.pck")
            with open(p, "wb") as fh:
                fh.write(pck_v3([("res://a/b.gd", 10), ("res://.godot/x.ctex", 99)]))
            self.assertEqual(wbr.read_pck(p), [("res://a/b.gd", 10), ("res://.godot/x.ctex", 99)])

    def test_rejects_a_non_pck(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.pck")
            with open(p, "wb") as fh:
                fh.write(b"nope")
            with self.assertRaises(SystemExit):
                wbr.read_pck(p)


if __name__ == "__main__":
    unittest.main()

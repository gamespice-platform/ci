"""release.yml wires its optional host-lock input through to package.sh --host-lock."""
import os
import unittest

yml = open(os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "release.yml")).read()


class HostLock(unittest.TestCase):
    def test_input_optional_default_empty(self):
        i = yml.index("            host-lock:")
        block = yml[i:yml.index("        secrets:", i)]
        self.assertIn("type: string", block)
        self.assertIn("default: ''", block)

    def test_passed_to_package_sh_only_when_set(self):
        self.assertIn("HOST_LOCK_IN: ${{ inputs.host-lock }}", yml)
        self.assertIn('[ -n "$HOST_LOCK_IN" ] && args+=(--host-lock "project/$HOST_LOCK_IN")', yml)

    def test_uses_refs_stay_on_gamespice(self):
        self.assertNotIn("uses: modcommunity/", yml)


if __name__ == "__main__":
    unittest.main()

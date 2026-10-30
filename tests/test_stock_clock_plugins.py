# SPDX-License-Identifier: Apache-2.0
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from stock_clock_plugins import MODULE, REGISTRY, ORIGINAL, PATCHED, PACKAGES, prepare


class StockClockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.rom = Path(self.temp.name)
        for relative in (MODULE, REGISTRY):
            (self.rom / relative).parent.mkdir(parents=True, exist_ok=True)
        self.source = "// retained local edit\n" + ORIGINAL + "\n            return PackageConfig(*privilegedPlugins)\n"
        (self.rom / MODULE).write_text(self.source)
        (self.rom / REGISTRY).write_text("\n".join(f'"{p}" to listOf()' for p in PACKAGES))

    def test_check_apply_and_repeat_preserve_existing_policy(self):
        self.assertTrue(prepare(self.rom))
        self.assertEqual(self.source, (self.rom / MODULE).read_text())
        self.assertTrue(prepare(self.rom, write=True))
        expected = self.source.replace(ORIGINAL, PATCHED)
        self.assertEqual(expected, (self.rom / MODULE).read_text())
        self.assertFalse(prepare(self.rom, write=True))
        self.assertEqual(expected, (self.rom / MODULE).read_text())

    def test_changed_registry_rejected_without_writing(self):
        path = self.rom / REGISTRY
        path.write_text(path.read_text() + '\n"com.android.systemui.clocks.unreviewed" to listOf()')
        with self.assertRaisesRegex(ValueError, "providers changed"):
            prepare(self.rom, write=True)
        self.assertEqual(self.source, (self.rom / MODULE).read_text())

    def test_existing_local_policy_extension_preserved(self):
        changed = self.source.replace(ORIGINAL, ORIGINAL + ' + arrayOf("vendor.existing")')
        (self.rom / MODULE).write_text(changed)
        with self.assertRaisesRegex(ValueError, "policy changed"):
            prepare(self.rom, write=True)
        self.assertEqual(changed, (self.rom / MODULE).read_text())

    def test_ambiguous_policy_rejected(self):
        (self.rom / MODULE).write_text(self.source * 2)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            prepare(self.rom, write=True)


if __name__ == "__main__":
    unittest.main()

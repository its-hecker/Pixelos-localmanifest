# SPDX-License-Identifier: Apache-2.0
"""Source preparation must reject drift without leaving a half-patched SystemUI."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import tap_to_sleep


class TapToSleepPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.rom = Path(self.temp.name)
        self.rules = self.rom / "rules.json"
        # Cover both an insertion containing the original anchor and a deletion.
        self.rules.write_text(json.dumps({
            "first.kt": [{"old": "original", "new": "original + extension"}],
            "second.kt": [{"old": "import first\nimport unused\nimport last",
                           "new": "import first\nimport last"}],
        }))
        self.original = {"first.kt": "// local edit\noriginal\n",
                         "second.kt": "import first\nimport unused\nimport last\n"}
        for name, content in self.original.items():
            (self.rom / name).write_text(content)
        patcher = patch.object(tap_to_sleep, "PATCHES", self.rules)
        patcher.start()
        self.addCleanup(patcher.stop)

    def contents(self):
        return {name: (self.rom / name).read_text() for name in self.original}

    def test_check_apply_repeat_and_exact_revert_preserve_local_edits(self):
        self.assertEqual(2, tap_to_sleep.prepare(self.rom))
        self.assertEqual(self.original, self.contents())
        self.assertEqual(2, tap_to_sleep.prepare(self.rom, write=True))
        applied = self.contents()
        self.assertIn("// local edit", applied["first.kt"])
        self.assertNotIn("import unused", applied["second.kt"])
        self.assertEqual(0, tap_to_sleep.prepare(self.rom, write=True))
        self.assertEqual(applied, self.contents())
        self.assertEqual(2, tap_to_sleep.prepare(self.rom, write=True, revert=True))
        self.assertEqual(self.original, self.contents())
        self.assertEqual(0, tap_to_sleep.prepare(self.rom, write=True, revert=True))

    def test_later_source_drift_leaves_every_file_untouched(self):
        (self.rom / "second.kt").write_text("unfamiliar source")
        saved = self.contents()
        with self.assertRaises(ValueError):
            tap_to_sleep.prepare(self.rom, write=True)
        self.assertEqual(saved, self.contents())

    def test_duplicate_anchor_is_rejected_without_writes(self):
        (self.rom / "first.kt").write_text("original\noriginal\n")
        saved = self.contents()
        with self.assertRaises(ValueError):
            tap_to_sleep.prepare(self.rom, write=True)
        self.assertEqual(saved, self.contents())

    def test_partial_apply_is_completed_and_reversible(self):
        (self.rom / "first.kt").write_text(self.original["first.kt"].replace("original", "original + extension"))
        self.assertEqual(1, tap_to_sleep.prepare(self.rom, write=True))
        self.assertEqual(2, tap_to_sleep.prepare(self.rom, write=True, revert=True))
        self.assertEqual(self.original, self.contents())


if __name__ == "__main__":
    unittest.main()

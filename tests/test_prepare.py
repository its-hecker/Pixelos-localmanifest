# SPDX-License-Identifier: Apache-2.0
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("suite_prepare", ROOT / "tools/prepare.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.rom = Path(self.temp.name)
        base = self.rom / prepare.FRAMEWORK
        for relative, markers in prepare.CAPABILITIES.items():
            file = base / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("\n".join(markers))
        for relative, (old, _) in prepare.PATCHES.items():
            file = base / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(old + "\n")
        (base / "core/res/AndroidManifest.xml").write_text('''<manifest xmlns:android="http://schemas.android.com/apk/res/android">
''' + prepare.MANIFEST_OLD + '''
    <permission android:name="android.permission.LOCK_APPS" android:protectionLevel="internal|role|recents" />
</manifest>''')

    def contents(self):
        return {str(p.relative_to(self.rom)): p.read_bytes()
                for p in (self.rom / prepare.FRAMEWORK).rglob("*") if p.is_file()}

    def test_idempotent_and_reversible_without_touching_native_guards(self):
        before = self.contents()
        prepare.apply(self.rom, "check")
        self.assertEqual(before, self.contents())
        prepare.apply(self.rom, "apply")
        applied = self.contents()
        manifest = (self.rom / prepare.FRAMEWORK / "core/res/AndroidManifest.xml").read_text()
        self.assertIn(prepare.MANIFEST_OLD + '\n    <permission android:name="android.permission.LOCK_APPS"', manifest)
        prepare.apply(self.rom, "verify")
        prepare.apply(self.rom, "apply")
        self.assertEqual(applied, self.contents())
        for relative in prepare.CAPABILITIES:
            if relative not in prepare.PATCHES:
                self.assertEqual(before[str(prepare.FRAMEWORK / relative)],
                                 applied[str(prepare.FRAMEWORK / relative)])
        prepare.apply(self.rom, "revert")
        self.assertEqual(before, self.contents())

    def test_all_inputs_validated_before_any_writes(self):
        bad = self.rom / prepare.FRAMEWORK / "services/core/java/com/android/server/pm/ComputerEngine.java"
        bad.write_text("unknown implementation")
        before = self.contents()
        with self.assertRaises(ValueError): prepare.apply(self.rom, "apply")
        self.assertEqual(before, self.contents())

    def test_refuses_broadened_native_permission(self):
        manifest = self.rom / prepare.FRAMEWORK / "core/res/AndroidManifest.xml"
        manifest.write_text(manifest.read_text().replace("internal|role|recents", "normal"))
        before = self.contents()
        with self.assertRaises(ValueError): prepare.apply(self.rom, "apply")
        self.assertEqual(before, self.contents())

    def test_preserves_unrelated_edits_on_revert(self):
        prepare.apply(self.rom, "apply")
        file = self.rom / prepare.FRAMEWORK / "services/core/java/com/android/server/pm/ComputerEngine.java"
        file.write_text(file.read_text() + "\n// unrelated maintainer change\n")
        prepare.apply(self.rom, "revert")
        self.assertTrue(file.read_text().endswith("// unrelated maintainer change\n"))

    def test_refuses_to_overwrite_foreign_helper(self):
        file = self.rom / prepare.FRAMEWORK / prepare.HELPER
        file.write_text("foreign helper")
        before = self.contents()
        with self.assertRaises(ValueError): prepare.apply(self.rom, "apply")
        self.assertEqual(before, self.contents())

    def test_verify_rejects_unapplied_source(self):
        with self.assertRaises(ValueError): prepare.apply(self.rom, "verify")


if __name__ == "__main__": unittest.main()

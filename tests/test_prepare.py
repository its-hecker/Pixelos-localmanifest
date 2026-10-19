# SPDX-License-Identifier: Apache-2.0
import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

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
                for root in (prepare.FRAMEWORK, prepare.MOTION)
                for p in (self.rom / root).rglob("*") if p.is_file()}

    def stage_motion(self):
        settings = self.rom / prepare.MOTION
        settings.mkdir(parents=True)
        (settings / "Android.bp.in").write_text(prepare.MOTION_BP_OLD + '''
    srcs: ["src/**/*.java"],
    privileged: true,
    system_ext_specific: true,
    required: ["FloralMotionSensePrivappPermissions"],
}
''')
        (settings / "Android.bp").write_bytes((settings / "Android.bp.in").read_bytes())
        (settings / "AndroidManifest.xml").write_text('''<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="org.hecker.floral.motionsense" android:sharedUserId="android.uid.system">
    <uses-permission android:name="android.permission.WRITE_SECURE_SETTINGS" />
    <application android:persistent="true">
        <activity android:name=".motionsense.MotionSenseActivity" android:exported="true">
            <intent-filter>
                <action android:name="com.android.settings.action.IA_SETTINGS" />
                <category android:name="android.intent.category.DEFAULT" />
            </intent-filter>
            <meta-data android:name="com.android.settings.category" android:value="com.android.settings.category.ia.system" />
            <meta-data android:name="keep.custom.metadata" android:value="keep" />
        </activity>
        <activity android:name=".motionsense.GlowActivity" android:exported="false" />
        <service android:name=".motionsense.MotionSenseTileService" android:exported="true"
            android:permission="android.permission.BIND_QUICK_SETTINGS_TILE">
            <intent-filter><action android:name="android.service.quicksettings.action.QS_TILE" /></intent-filter>
        </service>
    </application>
</manifest>''')
        return settings

    def test_motion_navigation_is_reversible_and_preserves_controls_tile_and_source_manifest(self):
        settings = self.stage_motion()
        before = self.contents()
        source = (settings / "AndroidManifest.xml").read_bytes()
        prepare.apply(self.rom, "apply")
        self.assertEqual(source, (settings / "AndroidManifest.xml").read_bytes())
        manifest = ET.parse(settings / prepare.MOTION_MANIFEST).getroot()
        activity = manifest.find("application/activity")
        self.assertEqual(activity.get(prepare.ANDROID + "exported"), "true")
        self.assertEqual(activity.find("meta-data").get(prepare.ANDROID + "name"), "keep.custom.metadata")
        self.assertIsNone(activity.find("intent-filter"))
        self.assertEqual(len(manifest.findall("application/activity")), 2)
        self.assertEqual(manifest.find("application/service").get(prepare.ANDROID + "permission"),
                         "android.permission.BIND_QUICK_SETTINGS_TILE")
        self.assertEqual(manifest.get(prepare.ANDROID + "sharedUserId"), "android.uid.system")
        applied = self.contents()
        prepare.apply(self.rom, "verify")
        prepare.apply(self.rom, "apply")
        self.assertEqual(applied, self.contents())
        prepare.apply(self.rom, "revert")
        self.assertEqual(before, self.contents())

    def test_invalid_motion_input_refuses_before_any_framework_changes(self):
        settings = self.stage_motion()
        manifest = settings / "AndroidManifest.xml"
        manifest.write_text(manifest.read_text().replace('android:exported="true"', 'android:exported="false"', 1))
        before = self.contents()
        with self.assertRaisesRegex(ValueError, "exported settings activity"):
            prepare.apply(self.rom, "apply")
        self.assertEqual(before, self.contents())

    def test_foreign_generated_motion_manifest_is_preserved(self):
        settings = self.stage_motion()
        generated = settings / prepare.MOTION_MANIFEST
        generated.parent.mkdir(parents=True)
        generated.write_text("unrelated local file")
        before = self.contents()
        with self.assertRaisesRegex(ValueError, "unfamiliar generated Motion Sense manifest"):
            prepare.apply(self.rom, "apply")
        self.assertEqual(before, self.contents())

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

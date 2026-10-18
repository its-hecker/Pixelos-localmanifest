# SPDX-License-Identifier: Apache-2.0
"""Reject missing, misplaced and overbroad Motion Sense privileged grants."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from validate import motion_permissions


class MotionPermissionsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.plugin = self.root / "vendor/hecker/floral/motionsense"
        self.settings = self.plugin / "settings"
        self.xml = self.plugin / "configs/privapp-permissions-floral-motionsense.xml"
        self.xml.parent.mkdir(parents=True)
        self.settings.mkdir(parents=True)
        self.xml.write_text('<permissions><privapp-permissions package="org.hecker.floral.motionsense">'
                            '<permission name="android.permission.WRITE_SECURE_SETTINGS" />'
                            '</privapp-permissions></permissions>')
        (self.settings / "AndroidManifest.xml").write_text(
            '<manifest package="org.hecker.floral.motionsense" />')
        (self.settings / "Android.bp.in").write_text(
            'android_app { privileged: true, system_ext_specific: true, '
            'required: ["FloralMotionSensePrivappPermissions"], }')
        self.blueprint = self.plugin / "Android.bp.in"
        self.blueprint.write_text('prebuilt_etc {\n'
            '    name: "FloralMotionSensePrivappPermissions",\n'
            '    src: "configs/privapp-permissions-floral-motionsense.xml",\n'
            '    filename: "privapp-permissions-floral-motionsense.xml",\n'
            '    sub_dir: "permissions",\n'
            '    system_ext_specific: true,\n}\n')

    def test_expected_package_and_system_ext_grant(self):
        motion_permissions(self.root)

    def test_wrong_partition_or_missing_or_duplicate_module_fails(self):
        content = self.blueprint.read_text()
        for value in ("", content.replace("system_ext_specific", "product_specific"), content * 2):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "install once on system_ext"):
                self.blueprint.write_text(value)
                motion_permissions(self.root)

    def test_missing_wrong_package_or_extra_privileged_grants_fail(self):
        original = self.xml.read_text()
        for value in (original.replace("org.hecker.floral.motionsense", "wrong.package"),
                      original.replace('android.permission.WRITE_SECURE_SETTINGS', 'android.permission.OTHER'),
                      original.replace('</privapp-permissions>', '<permission name="android.permission.OTHER" />'
                                       '</privapp-permissions>')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.xml.write_text(value)
                motion_permissions(self.root)


if __name__ == "__main__":
    unittest.main()

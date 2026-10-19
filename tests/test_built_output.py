# SPDX-License-Identifier: Apache-2.0
"""Reject the missing runtime init script found in the phone bug report."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from check_built_output import check, check_motion_sense, check_suite, SERVICE


class BuiltOutputTests(unittest.TestCase):
    def test_selected_camera_needs_its_exact_init_binary_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            source = root / "vendor/google/coral/proprietary/vendor/etc/init" / (SERVICE + ".rc")
            source.parent.mkdir(parents=True)
            source.write_text("service camera /vendor/bin/hw/" + SERVICE + "\n")
            with self.assertRaisesRegex(ValueError, "init script"):
                check(root, output)
            init = output / "vendor/etc/init" / source.name
            init.parent.mkdir(parents=True)
            init.write_bytes(source.read_bytes())
            with self.assertRaisesRegex(ValueError, "provider binary"):
                check(root, output)
            binary = output / "vendor/bin/hw" / SERVICE
            binary.parent.mkdir(parents=True)
            binary.touch()
            with self.assertRaisesRegex(ValueError, "VINTF"):
                check(root, output)
            manifest = output / "vendor/etc/vintf/manifest" / (SERVICE + ".xml")
            manifest.parent.mkdir(parents=True)
            manifest.touch()
            properties = output / "product/etc/build.prop"
            properties.parent.mkdir(parents=True)
            properties.write_text("pixel.oslo.allowed_override=1\n")
            with patch("check_built_output.verify_installed") as apks, patch("check_built_output.check_suite"):
                check(root, output)
                apks.assert_called_once_with(root, output)
            init.write_text("service camera /wrong/binary\n")
            with self.assertRaisesRegex(ValueError, "exact camera provider init"):
                check(root, output)

    def test_motion_sense_requires_the_country_override_in_built_product_properties(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with self.assertRaisesRegex(ValueError, "missing Motion Sense"):
                check_motion_sense(output)
            properties = output / "product/etc/build.prop"
            properties.parent.mkdir(parents=True)
            for value in ("", "pixel.oslo.allowed_override=0\n",
                          "pixel.oslo.allowed_override=1\npixel.oslo.allowed_override=1\n"):
                with self.subTest(properties=value):
                    properties.write_text(value)
                    with self.assertRaisesRegex(ValueError, "exactly one"):
                        check_motion_sense(output)
            properties.write_text("# pixel.oslo.allowed_override=0\npixel.oslo.allowed_override=1\n")
            check_motion_sense(output)
            legacy = output / "product/build.prop"
            properties.rename(legacy)
            check_motion_sense(output)

    def test_suite_requires_installed_apk_and_matching_permission_xml(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            with self.assertRaisesRegex(ValueError, "HeckerSuite.apk"):
                check_suite(root, output)
            apk = output / "system_ext/priv-app/HeckerSuite/HeckerSuite.apk"
            apk.parent.mkdir(parents=True)
            apk.write_bytes(b"suite test artifact")
            with self.assertRaisesRegex(ValueError, "Suite permission"):
                check_suite(root, output)
            original = root / "vendor/hecker/floral/suite/configs/privapp-permissions-hecker-suite.xml"
            original.parent.mkdir(parents=True)
            original.write_text("<permissions />")
            installed = output / "system_ext/etc/permissions/privapp-permissions-hecker-suite.xml"
            installed.parent.mkdir(parents=True)
            installed.write_text("<wrong />")
            with self.assertRaisesRegex(ValueError, "Suite permission"):
                check_suite(root, output)
            installed.write_bytes(original.read_bytes())
            check_suite(root, output)


if __name__ == "__main__":
    unittest.main()

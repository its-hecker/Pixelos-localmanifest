# SPDX-License-Identifier: Apache-2.0
"""Guard the source camera patch and preserve neighboring/local source edits."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from camera_install import configure, SOURCE, suppress_source_installs


FIXTURE = b'''// SPDX-License-Identifier: Apache-2.0
vintf_fragment {
    name: "hardware_camera_vintf",
    src: "android.hardware.camera.provider@2.7-service-google.xml",
    soc_specific: true,
}
cc_binary {
    name: "android.hardware.camera.provider@2.7-service-google",
    init_rc: ["android.hardware.camera.provider@2.7-service-google.rc"],
    defaults: ["hardware_camera_service_defaults"],
    // Keep this unrelated local change.
    cflags: ["-DLOCAL_CAMERA_CHANGE"],
}
cc_binary {
    name: "android.hardware.camera.provider@2.7-service-google-lazy",
    defaults: ["camera_service_lazy_hal_defaults"],
}
'''


class CameraInstallTests(unittest.TestCase):
    def test_only_the_eager_service_and_its_manifest_lose_full_installs(self):
        result = suppress_source_installs(FIXTURE)
        self.assertEqual(result.count(b"no_full_install: true,"), 2)
        expected = FIXTURE.replace(b'init_rc: ["android.hardware.camera.provider@2.7-service-google.rc"]',
                                   b'init_rc: []')
        self.assertEqual(result.replace(b"    no_full_install: true,\n", b""), expected)
        self.assertEqual(suppress_source_installs(result), result)

    def test_crlf_and_an_existing_false_flag_are_preserved_except_the_boolean(self):
        content = FIXTURE.replace(b'    defaults:', b'    no_full_install: false, // local comment\n    defaults:', 1)
        content = content.replace(b"\n", b"\r\n")
        result = suppress_source_installs(content)
        self.assertIn(b"no_full_install: true, // local comment\r\n", result)
        self.assertNotIn(b"\n", result.replace(b"\r\n", b""))

    def test_unfamiliar_flags_or_missing_modules_are_refused(self):
        for field in (b"some_variable", b"true,\n    no_full_install: true"):
            content = FIXTURE.replace(b'    defaults:', b'    no_full_install: ' + field + b',\n    defaults:', 1)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "unfamiliar"):
                suppress_source_installs(content)
        with self.assertRaisesRegex(ValueError, "changed camera module"):
            suppress_source_installs(FIXTURE.replace(b'"hardware_camera_vintf"', b'"different_manifest"'))

    def test_check_does_not_write_and_apply_backs_up_then_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            rom = Path(directory)
            path = rom / SOURCE
            path.parent.mkdir(parents=True)
            path.write_bytes(FIXTURE)
            path.chmod(0o644)
            self.assertEqual(configure(rom), "patch available")
            self.assertEqual(path.read_bytes(), FIXTURE)
            self.assertFalse((rom / "out").exists())
            self.assertTrue(configure(rom, write=True).startswith("configured"))
            backups = list((rom / "out/floral-camera-install").glob("*.original"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), FIXTURE)
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)
            self.assertEqual(configure(rom, write=True), "already configured")


if __name__ == "__main__":
    unittest.main()

# SPDX-License-Identifier: Apache-2.0
"""Guard the PixelOS Face initialization patch and its source backups."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import face_init


class FaceInitTests(unittest.TestCase):
    def fixture(self, root):
        for path, content in ((face_init.SOURCE, face_init.ORIGINAL_METHOD),
                              (face_init.HIDL_SOURCE,
                               "private int mCurrentUserId = UserHandle.USER_NULL;"),
                              (face_init.SENSOR_LIST,
                               "mSensors.put(sensorId, sensor);\n        registerUserSwitchObserver")):
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        return root / face_init.SOURCE

    def test_preserves_other_methods_local_edits_and_crlf(self):
        content = ("// local customization\n" + face_init.ORIGINAL_METHOD +
                   "    private void addAidlSensors() { /* unchanged */ }\n").replace("\n", "\r\n").encode()
        fixed = face_init.transform(content)
        self.assertEqual(fixed, content.replace(face_init.LAZY_USER.replace("\n", "\r\n").encode(),
                                               face_init.FIXED_USER.replace("\n", "\r\n").encode(), 1))
        self.assertEqual(face_init.transform(fixed), fixed)

    def test_unknown_or_ambiguous_methods_are_refused(self):
        for content in (face_init.ORIGINAL_METHOD.replace("sensor.init(", "sensor.changedInit("),
                        face_init.ORIGINAL_METHOD * 2,
                        face_init.ORIGINAL_METHOD + face_init.FIXED_METHOD):
            with self.subTest(content=len(content)), self.assertRaisesRegex(ValueError, "Review changed"):
                face_init.transform(content.encode())

    def test_check_apply_backup_and_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = self.fixture(root)
            target.chmod(0o640)
            original = target.read_bytes()
            self.assertEqual(face_init.configure(root), "patch available")
            self.assertEqual(target.read_bytes(), original)
            self.assertFalse((root / "out").exists())
            self.assertTrue(face_init.configure(root, write=True).startswith("configured"))
            backups = list((root / "out/pixelos-face-init").glob("*.original"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)
            self.assertEqual(target.stat().st_mode & 0o777, 0o640)
            mtime = target.stat().st_mtime_ns
            self.assertEqual(face_init.configure(root, write=True), "already configured")
            self.assertEqual(target.stat().st_mtime_ns, mtime)

    def test_unknown_sensor_user_state_or_registration_order_stops_writes(self):
        for contract in (face_init.HIDL_SOURCE, face_init.SENSOR_LIST):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                target = self.fixture(root)
                (root / contract).write_text("// changed contract\n")
                with self.assertRaisesRegex(ValueError, "Review"):
                    face_init.configure(root, write=True)
                self.assertEqual(target.read_text(), face_init.ORIGINAL_METHOD)
                self.assertFalse((root / "out").exists())

    def test_symlinked_provider_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = self.fixture(root)
            original = root / "original.java"
            target.rename(original)
            target.symlink_to(original)
            with self.assertRaisesRegex(ValueError, "symlinked"):
                face_init.configure(root, write=True)
            self.assertEqual(original.read_text(), face_init.ORIGINAL_METHOD)


if __name__ == "__main__":
    unittest.main()

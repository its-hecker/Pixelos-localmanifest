# SPDX-License-Identifier: Apache-2.0
"""Exercise the real device boot capture without touching host /metadata."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


DEVICE = None


class BootCaptureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / "capture"
        self.mounts = self.root / "proc-mounts"
        self.mounts.write_text("/dev/block/dm-0 /metadata ext4 rw 0 0\n")
        source = (DEVICE / "boot_diagnostics/boot_capture.sh").read_text()
        source = source.replace("/metadata/pixelos-boot-debug", str(self.output))
        source = source.replace("/proc/mounts", str(self.mounts))
        self.script = self.root / "capture.sh"
        self.script.write_text(source)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        helper = self.bin / "helper.py"
        helper.write_text('''#!''' + sys.executable + '''
import json, os, pathlib, sys, time
name = pathlib.Path(sys.argv[0]).name
if name == "getprop":
    key = sys.argv[1] if len(sys.argv) > 1 else ""
    value = {"ro.debuggable": os.environ.get("CAPTURE_TEST_DEBUG", "1"),
             "ro.bootmode": os.environ.get("CAPTURE_TEST_MODE", "normal"),
             "ro.boot.mode": os.environ.get("CAPTURE_TEST_MODE", "normal"),
             "sys.boot_completed": os.environ.get("CAPTURE_TEST_COMPLETED", "1")}.get(key)
    if value is None:
        try: sys.stdout.write("[ro.debuggable]: [1]\\n" + "P" * 200000)
        except BrokenPipeError: pass
    else:
        if key == "sys.boot_completed" and value == "1":
            for _ in range(100):
                if (pathlib.Path(os.environ["CAPTURE_TEST_OUTPUT"]) / "logcat.txt").exists(): break
                time.sleep(0.005)
        print(value)
elif name == "stat":
    print(os.environ.get("CAPTURE_TEST_STAT", "4096 4096"))
elif name == "dmesg":
    sys.stdout.write("K" * 300000)
elif name == "ps":
    sys.stdout.write("S" * 200000)
elif name == "sleep":
    pass
elif name == "logcat":
    args = sys.argv[1:]
    target = pathlib.Path(args[args.index("-f") + 1])
    target.write_text("Android startup fixture\\n")
    (target.parent / "test-logcat-args.json").write_text(json.dumps(args))
    (target.parent / "test-logcat-pid").write_text(str(os.getpid()))
    while True: time.sleep(1)
''')
        helper.chmod(0o755)
        for name in ("getprop", "stat", "dmesg", "ps", "sleep", "logcat"):
            (self.bin / name).symlink_to(helper.name)
        self.environment = os.environ.copy()
        self.environment.update(PATH=str(self.bin) + ":" + self.environment["PATH"],
                                CAPTURE_TEST_OUTPUT=str(self.output))

    def invoke(self, **environment):
        return subprocess.run(["sh", str(self.script)], cwd=self.root,
                              env=self.environment | environment, text=True,
                              capture_output=True, timeout=30)

    def test_release_boot_and_recovery_do_not_replace_saved_evidence(self):
        self.output.mkdir()
        saved = self.output / "status.txt"
        saved.write_text("previous failed Android boot\n")
        for values in ({"CAPTURE_TEST_DEBUG": "0"}, {"CAPTURE_TEST_MODE": "recovery"},
                       {"CAPTURE_TEST_MODE": "fastboot"}):
            with self.subTest(values=values):
                result = self.invoke(**values)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(saved.read_text(), "previous failed Android boot\n")

    def test_missing_metadata_mount_is_refused(self):
        self.mounts.write_text("rootfs / rootfs rw 0 0\n")
        self.assertNotEqual(self.invoke().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_low_free_space_and_invalid_stat_are_refused_without_writes(self):
        for value in ("128 4096", "not-a-filesystem", "0 4096"):
            with self.subTest(value=value):
                self.assertNotEqual(self.invoke(CAPTURE_TEST_STAT=value).returncode, 0)
                self.assertFalse(self.output.exists())

    def test_capture_bounds_snapshots_and_stops_its_logger(self):
        import json
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("result=boot_completed", (self.output / "status.txt").read_text())
        self.assertEqual((self.output / "kernel.txt").stat().st_size, 131072)
        self.assertEqual((self.output / "properties.txt").stat().st_size, 65536)
        self.assertEqual((self.output / "processes.txt").stat().st_size, 65536)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)
        args = json.loads((self.output / "test-logcat-args.json").read_text())
        self.assertEqual(args[args.index("-r") + 1], "192")
        self.assertEqual(args[args.index("-n") + 1], "3")
        pid = int((self.output / "test-logcat-pid").read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_symlinked_capture_directory_is_refused(self):
        destination = self.root / "unrelated"
        destination.mkdir()
        marker = destination / "status.txt"
        marker.write_text("keep this")
        self.output.symlink_to(destination)
        self.assertNotEqual(self.invoke().returncode, 0)
        self.assertEqual(marker.read_text(), "keep this")

    def test_failed_boot_capture_stops_after_its_bounded_sample_count(self):
        result = self.invoke(CAPTURE_TEST_COMPLETED="0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("result=capture_timeout_300_seconds", (self.output / "status.txt").read_text())

    def test_make_installs_capture_only_on_debug_variants(self):
        path = DEVICE / "boot_diagnostics/boot_capture.mk"
        for variant in ("user", "userdebug", "eng"):
            source = ("TARGET_COPY_OUT_SYSTEM := system\nTARGET_BUILD_VARIANT := " + variant +
                      "\ninclude " + str(path) + "\n$(info COPIES=$(PRODUCT_COPY_FILES))\n"
                      "$(info ALLOWED=$(PRODUCT_ARTIFACT_PATH_REQUIREMENT_ALLOWED_LIST))\nall:;@:\n")
            result = subprocess.run(["make", "--no-print-directory", "-f", "-", "all"],
                                    input=source, text=True, capture_output=True, check=True)
            copies = next(line[7:] for line in result.stdout.splitlines() if line.startswith("COPIES="))
            allowed = next(line[8:] for line in result.stdout.splitlines() if line.startswith("ALLOWED="))
            self.assertEqual(len(copies.split()), 0 if variant == "user" else 2)
            self.assertEqual(len(allowed.split()), 0 if variant == "user" else 2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-root", type=Path, required=True)
    args = parser.parse_args()
    DEVICE = args.device_root.resolve()
    unittest.main(argv=[sys.argv[0]], verbosity=2)

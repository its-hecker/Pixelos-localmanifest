# SPDX-License-Identifier: Apache-2.0
"""Ensure broken Repo copies stop before build preparation or network use."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

from namespace_fixture import stage


BUILD = Path(__file__).resolve().parents[1] / "build.sh"


class BuildPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.rom = Path(self.temporary.name)
        (self.rom / ".repo").mkdir()
        make = self.rom / "build/make"
        (make / "core").mkdir(parents=True)
        (make / "envsetup.sh").write_text("true\n")
        (make / "core/envsetup.mk").write_text("# root marker\n")
        (self.rom / "build/envsetup.sh").symlink_to("make/envsetup.sh")
        self.source = self.rom / "trusty/vendor/google/aosp/lk_inc.mk"
        self.source.parent.mkdir(parents=True)
        self.source.write_text("# Trusty source\n")
        self.copy = self.rom / "lk_inc.mk"
        self.copy.write_bytes(self.source.read_bytes())
        binary = self.rom / "test-bin"
        binary.mkdir()
        git = binary / "git"
        git.write_text("#!/bin/sh\necho REACHED_LFS_BOUNDARY >&2\nexit 47\n")
        git.chmod(0o755)
        self.namespace_source, manifest = stage(self.rom)
        repo = binary / "repo"
        repo.write_text("#!/bin/sh\ncat <<'FLORAL_MANIFEST'\n" +
                        ET.tostring(manifest, encoding="unicode") + "\nFLORAL_MANIFEST\n")
        repo.chmod(0o755)
        self.environment = os.environ.copy()
        self.environment["PATH"] = str(binary) + ":" + self.environment["PATH"]

    def invoke(self):
        return subprocess.run(["bash", str(BUILD)], cwd=self.rom,
                              env=self.environment, text=True, capture_output=True)

    def rejected(self, message):
        result = self.invoke()
        self.assertEqual(result.returncode, 1)
        self.assertIn(message, result.stderr)
        self.assertNotIn("REACHED_LFS_BOUNDARY", result.stderr)
        return result

    def test_missing_root_marker_stops_before_preparation(self):
        (self.rom / "build/make/core/envsetup.mk").unlink()
        result = self.rejected("Missing Android environment files")
        self.assertIn("--project build/make --restore", result.stderr)

    def test_missing_trusty_source_stops_before_preparation(self):
        self.source.unlink()
        result = self.rejected("Trusty lk_inc.mk")
        self.assertIn("--project trusty/vendor/google/aosp --restore", result.stderr)
        self.assertTrue(self.copy.is_file())

    def test_missing_root_copy_stops_before_preparation(self):
        self.copy.unlink()
        self.rejected("Trusty lk_inc.mk")
        self.assertTrue(self.source.is_file())

    def test_different_root_copy_is_preserved_and_rejected(self):
        self.copy.write_text("local root copy\n")
        self.rejected("Trusty lk_inc.mk")
        self.assertEqual(self.copy.read_text(), "local root copy\n")

    def test_matching_copy_reaches_the_existing_lfs_stage(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 47)
        self.assertIn("REACHED_LFS_BOUNDARY", result.stderr)
        self.assertNotIn("Missing or mismatched Trusty", result.stderr)

    def test_missing_chipset_namespace_stops_before_preparation(self):
        (self.rom / "hardware/qcom-caf/sm8250/Android.bp").unlink()
        result = self.rejected("Missing or mismatched Qualcomm chipset namespace exports")
        self.assertIn("repo sync -l -j1 --fail-fast hardware/qcom-caf/common", result.stderr)

    def test_missing_namespace_source_stops_before_preparation(self):
        self.namespace_source.unlink()
        self.rejected("Missing Qualcomm namespace source")

    def test_different_namespace_file_is_preserved_and_rejected(self):
        path = self.rom / "hardware/qcom-caf/sm8650/Android.bp"
        path.unlink()
        path.write_text("local namespace\n")
        self.rejected("Missing or mismatched Qualcomm chipset namespace exports")
        self.assertEqual(path.read_text(), "local namespace\n")


if __name__ == "__main__":
    unittest.main()

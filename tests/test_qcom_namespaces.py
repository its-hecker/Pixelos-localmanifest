# SPDX-License-Identifier: Apache-2.0
"""Check missing namespace exports without replacing local files."""

from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import check_qcom_namespaces
from namespace_fixture import CONTENT, stage


class QcomNamespaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.rom = Path(self.temporary.name)
        self.source, self.manifest = stage(self.rom)
        self.destination = self.rom / "hardware/qcom-caf/sm8250/Android.bp"

    def test_all_upstream_chipset_links_are_valid(self):
        self.assertEqual(check_qcom_namespaces.check(self.rom, self.manifest), 10)

    def test_local_common_namespace_is_rejected_even_when_all_chipset_links_match(self):
        path = self.source.parent / "Android.bp"
        edited = "soong_namespace {}\n" + path.read_text()
        path.write_text(edited)
        with self.assertRaisesRegex(ValueError, "hides shared audio defaults") as error:
            check_qcom_namespaces.check(self.rom, self.manifest)
        self.assertIn("recover_namespace_edits.py", str(error.exception))
        self.assertEqual(path.read_text(), edited)

    def test_missing_common_blueprint_is_rejected(self):
        (self.source.parent / "Android.bp").unlink()
        with self.assertRaisesRegex(ValueError, "Missing Qualcomm shared module definitions"):
            check_qcom_namespaces.check(self.rom, self.manifest)

    def test_missing_shared_audio_default_is_rejected(self):
        (self.source.parent / "Android.bp").write_text('cc_defaults { name: "different_defaults", }\n')
        with self.assertRaisesRegex(ValueError, "Missing shared Qualcomm audio defaults"):
            check_qcom_namespaces.check(self.rom, self.manifest)

    def test_renamed_chipset_still_inside_source_tree_is_rejected(self):
        disabled = self.rom / "hardware/qcom-caf/sm8250.disabled"
        disabled.mkdir()
        with self.assertRaisesRegex(ValueError, "sm8250.disabled"):
            check_qcom_namespaces.check(self.rom, self.manifest)
        self.assertTrue(disabled.is_dir())

    def test_missing_chipset_namespace_reports_the_local_sync_repair(self):
        self.destination.unlink()
        with self.assertRaisesRegex(ValueError, "hardware/qcom-caf/sm8250/Android.bp") as error:
            check_qcom_namespaces.check(self.rom, self.manifest)
        self.assertIn("repo sync -l -j1 --fail-fast hardware/qcom-caf/common", str(error.exception))
        self.assertFalse(self.destination.exists())

    def test_broken_link_is_rejected_and_preserved(self):
        self.destination.unlink()
        self.destination.symlink_to("../common/missing.bp")
        with self.assertRaisesRegex(ValueError, "namespace exports"):
            check_qcom_namespaces.check(self.rom, self.manifest)
        self.assertEqual(self.destination.readlink(), Path("../common/missing.bp"))

    def test_mismatched_local_namespace_is_preserved(self):
        self.destination.unlink()
        self.destination.write_text("local namespace edit\n")
        with self.assertRaisesRegex(ValueError, "namespace exports"):
            check_qcom_namespaces.check(self.rom, self.manifest)
        self.assertEqual(self.destination.read_text(), "local namespace edit\n")

    def test_identical_regular_namespace_file_is_valid(self):
        self.destination.unlink()
        self.destination.write_text(CONTENT)
        self.assertEqual(check_qcom_namespaces.check(self.rom, self.manifest), 10)

    def test_missing_common_source_reports_indexed_file_recovery(self):
        self.source.unlink()
        with self.assertRaisesRegex(ValueError, "Missing Qualcomm namespace source") as error:
            check_qcom_namespaces.check(self.rom, self.manifest)
        self.assertIn("--project hardware/qcom-caf/common --restore", str(error.exception))

    def test_common_source_must_define_a_namespace(self):
        self.source.write_text("// no namespace\n")
        with self.assertRaisesRegex(ValueError, "no soong_namespace"):
            check_qcom_namespaces.check(self.rom, self.manifest)

    def test_exports_follow_the_active_manifest_instead_of_a_fixed_chipset_list(self):
        project = self.manifest.find("project")
        ET.SubElement(project, "linkfile", src="os_pickup_qssi.bp",
                      dest="hardware/qcom-caf/new-chip/Android.bp")
        destination = self.rom / "hardware/qcom-caf/new-chip/Android.bp"
        destination.parent.mkdir()
        destination.symlink_to("../common/os_pickup_qssi.bp")
        self.assertEqual(check_qcom_namespaces.check(self.rom, self.manifest), 11)

    def test_invalid_export_path_is_rejected(self):
        self.manifest.find("project/linkfile").set("dest", "../../outside/Android.bp")
        with self.assertRaisesRegex(ValueError, "Invalid Qualcomm namespace destination"):
            check_qcom_namespaces.check(self.rom, self.manifest)

    def test_missing_namespace_exports_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            check_qcom_namespaces.check(self.rom, ET.Element("manifest"))


if __name__ == "__main__":
    unittest.main()

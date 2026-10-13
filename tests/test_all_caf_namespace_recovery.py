# SPDX-License-Identifier: Apache-2.0
"""Regress the hidden sibling libraries and retain unrelated/index changes."""

import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import recover_caf_namespaces as recovery


def git(project, *args):
    return subprocess.check_output(["git", "-C", str(project), *args], stderr=subprocess.STDOUT)


class AllCafNamespaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.rom = root / "pixelos"
        self.rom.mkdir()
        self.backups = root / "backups"
        self.backups.mkdir()
        self.manifest = ET.Element("manifest")
        self.original = 'cc_library_shared {\n    name: "libar-gsl",\n    shared_libs: ["libar-gpr", "liblx-osal"],\n}\n'
        self.gsl = self.project("hardware/qcom-caf/sm8750/audio/graphservices", {
            "gsl/Android.bp": self.original,
            "gpr/Android.bp": 'cc_library_shared { name: "libar-gpr", }\n',
            "ar_osal/Android.bp": 'cc_library_shared { name: "liblx-osal", }\n',
            "legitimate/Android.bp": 'soong_namespace { imports: ["vendor/qcom/opensource/display"], }\n',
        })
        self.util = self.project("hardware/qcom-caf/sm8550/audio/graphservices", {
            "ar_util/Android.bp": 'cc_library_shared { name: "liblx-ar_util", }\n',
        })

    def project(self, relative, files):
        location = self.rom / relative
        location.mkdir(parents=True)
        git(location, "init", "--quiet")
        for filename, content in files.items():
            path = location / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        git(location, "add", ".")
        git(location, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "commit", "--quiet", "-m", "CAF fixture")
        ET.SubElement(self.manifest, "project", path=relative)
        return location

    def apply(self, actions):
        with contextlib.redirect_stdout(io.StringIO()):
            return recovery.apply(self.rom, actions, self.backups)

    def test_all_added_child_scopes_are_removed_and_sibling_definitions_retained(self):
        for path in [self.gsl / "gsl/Android.bp", self.util / "ar_util/Android.bp"]:
            path.write_text("soong_namespace {}\n\n" + path.read_text() + "// keep unrelated local edit\n")
        actions = recovery.inventory(self.rom, self.manifest)
        self.assertEqual(len(actions), 2)
        backup = self.apply(actions)
        self.assertNotIn("soong_namespace", (self.gsl / "gsl/Android.bp").read_text())
        self.assertIn('shared_libs: ["libar-gpr", "liblx-osal"]', (self.gsl / "gsl/Android.bp").read_text())
        self.assertIn("keep unrelated local edit", (self.gsl / "gsl/Android.bp").read_text())
        self.assertIn("keep unrelated local edit", (self.util / "ar_util/Android.bp").read_text())
        self.assertIn('name: "libar-gpr"', (self.gsl / "gpr/Android.bp").read_text())
        self.assertIn('name: "liblx-osal"', (self.gsl / "ar_osal/Android.bp").read_text())
        self.assertEqual(recovery.inventory(self.rom, self.manifest), [])
        with tarfile.open(backup / "edited-files.tar.gz") as archive:
            original = archive.extractfile("worktree/hardware/qcom-caf/sm8750/audio/graphservices/gsl/Android.bp").read()
            self.assertIn(b"soong_namespace {}", original)

    def test_upstream_namespaces_and_local_changes_to_them_are_preserved(self):
        path = self.gsl / "legitimate/Android.bp"
        edited = path.read_text().replace("vendor/qcom/opensource/display", "vendor/custom/display")
        path.write_text(edited)
        self.assertEqual(recovery.inventory(self.rom, self.manifest), [])
        self.assertEqual(path.read_text(), edited)

    def test_namespace_edits_are_removed_from_index_without_losing_other_staged_or_working_edits(self):
        path = self.gsl / "gsl/Android.bp"
        staged = self.original + "// unrelated staged edit\n"
        path.write_text("soong_namespace {}\n" + staged)
        git(self.gsl, "add", "--", "gsl/Android.bp")
        path.write_text("soong_namespace {}\n" + staged + "// unrelated working edit\n")
        backup = self.apply(recovery.inventory(self.rom, self.manifest))
        self.assertEqual(git(self.gsl, "show", ":gsl/Android.bp").decode(), staged)
        self.assertEqual(path.read_text(), staged + "// unrelated working edit\n")
        with tarfile.open(backup / "edited-files.tar.gz") as archive:
            saved = archive.extractfile("index/hardware/qcom-caf/sm8750/audio/graphservices/gsl/Android.bp").read()
            self.assertEqual(saved.decode(), "soong_namespace {}\n" + staged)

    def test_comment_and_string_literals_are_not_namespace_declarations(self):
        content = (b'// soong_namespace {}\n/* soong_namespace { } */\n'
                   b'cc_defaults { name: "soong_namespace { literal }", }\n')
        self.assertEqual(recovery.namespace_blocks(content), [])
        content = (b'soong_namespace { imports: ["namespace}path"], /* { } */ }\r\n' + content)
        self.assertEqual(len(recovery.namespace_blocks(content)), 1)
        self.assertTrue(recovery.without_namespaces(content).startswith(b"// soong_namespace {}"))

    def test_namespace_only_untracked_file_is_cleared_and_new_module_file_is_preserved(self):
        empty = self.gsl / "Android.bp"
        empty.write_text("// inserted local scope\nsoong_namespace {}\n")
        new = self.gsl / "new/Android.bp"
        new.parent.mkdir()
        new.write_text('soong_namespace {}\ncc_defaults { name: "UserAdded", }\n')
        self.apply(recovery.inventory(self.rom, self.manifest))
        self.assertEqual(empty.read_text(), "// inserted local scope\n")
        self.assertIn("soong_namespace", new.read_text())
        self.assertIn("UserAdded", new.read_text())

    def test_report_is_read_only_and_skip_worktree_edits_are_still_detected(self):
        path = self.gsl / "gsl/Android.bp"
        git(self.gsl, "update-index", "--skip-worktree", "--", "gsl/Android.bp")
        edited = "soong_namespace {}\n" + self.original
        path.write_text(edited)
        actions = recovery.inventory(self.rom, self.manifest)
        self.assertEqual(len(actions), 1)
        self.assertEqual(path.read_text(), edited)
        self.assertFalse(list(self.backups.iterdir()))
        self.apply(actions)
        self.assertEqual(path.read_text(), self.original)

    def test_changed_snapshot_is_rejected_before_any_source_is_modified(self):
        path = self.gsl / "gsl/Android.bp"
        path.write_text("soong_namespace {}\n" + self.original)
        actions = recovery.inventory(self.rom, self.manifest)
        path.write_text("soong_namespace {}\n" + self.original + "// concurrent edit\n")
        with self.assertRaisesRegex(ValueError, "changed during recovery"):
            self.apply(actions)
        self.assertIn("soong_namespace", path.read_text())
        self.assertIn("concurrent edit", path.read_text())

    def test_missing_caf_project_and_escaping_manifest_path_stop_recovery(self):
        ET.SubElement(self.manifest, "project", path="hardware/qcom-caf/missing/audio")
        with self.assertRaisesRegex(ValueError, "Missing or moved CAF project"):
            recovery.inventory(self.rom, self.manifest)
        bad = ET.Element("manifest")
        ET.SubElement(bad, "project", path="hardware/qcom-caf/../../../outside")
        with self.assertRaisesRegex(ValueError, "Invalid CAF project path"):
            recovery.inventory(self.rom, bad)


if __name__ == "__main__":
    unittest.main()

# SPDX-License-Identifier: Apache-2.0
"""Exercise recovery against real disposable Git repositories."""

import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import restore_checkout


class CheckoutRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Recovery test")
        self.git("config", "user.email", "recovery@example.invalid")
        for name in ("BoardConfig-common.mk", "custom_coral.mk", "keep.txt", "staged.txt",
                     "remove.txt", "file*.txt", "file-extra.txt", "name with spaces.txt"):
            (self.project / name).write_text("original\n")
        (self.project / "nested").mkdir()
        (self.project / "nested/missing.txt").write_text("nested original\n")
        os.symlink("absent-target", self.project / "dangling-link")
        self.git("add", ".")
        self.git("commit", "-qm", "Baseline")

    def git(self, *arguments, payload=None):
        return restore_checkout.git(self.project, *arguments, payload=payload)

    def test_restore_preserves_existing_edits_outputs_and_staged_deletions(self):
        (self.project / "BoardConfig-common.mk").unlink()
        (self.project / "custom_coral.mk").unlink()
        (self.project / "keep.txt").write_text("local edit\n")
        (self.project / "out").mkdir()
        (self.project / "out/result.zip").write_bytes(b"build output")
        self.git("rm", "-q", "remove.txt")
        before_index = self.git("ls-files", "--stage", "-z")
        self.assertEqual(restore_checkout.recover_project(self.project, True), 2)
        self.assertEqual((self.project / "BoardConfig-common.mk").read_text(), "original\n")
        self.assertEqual((self.project / "keep.txt").read_text(), "local edit\n")
        self.assertEqual((self.project / "out/result.zip").read_bytes(), b"build output")
        self.assertFalse((self.project / "remove.txt").exists())
        self.assertEqual(self.git("ls-files", "--stage", "-z"), before_index)
        self.assertEqual(restore_checkout.recover_project(self.project, True), 0)

    def test_sparse_excluded_files_are_restored(self):
        self.git("sparse-checkout", "init", "--no-cone")
        self.git("sparse-checkout", "set", "--no-cone", "--stdin", payload=b"/keep.txt\n")
        self.assertFalse((self.project / "BoardConfig-common.mk").exists())
        self.assertGreater(restore_checkout.recover_project(self.project, True), 0)
        self.assertTrue((self.project / "BoardConfig-common.mk").is_file())
        self.assertTrue((self.project / "nested/missing.txt").is_file())
        self.assertTrue(os.path.lexists(self.project / "dangling-link"))

    def test_missing_staged_file_is_restored_from_the_index(self):
        (self.project / "staged.txt").write_text("staged edit\n")
        self.git("add", "staged.txt")
        (self.project / "staged.txt").unlink()
        restore_checkout.recover_project(self.project, True)
        self.assertEqual((self.project / "staged.txt").read_text(), "staged edit\n")

    def test_literal_paths_do_not_overwrite_matching_existing_files(self):
        (self.project / "file*.txt").unlink()
        (self.project / "name with spaces.txt").unlink()
        (self.project / "file-extra.txt").write_text("preserve me\n")
        restore_checkout.recover_project(self.project, True)
        self.assertEqual((self.project / "file*.txt").read_text(), "original\n")
        self.assertEqual((self.project / "name with spaces.txt").read_text(), "original\n")
        self.assertEqual((self.project / "file-extra.txt").read_text(), "preserve me\n")

    def test_report_only_does_not_change_the_checkout(self):
        (self.project / "BoardConfig-common.mk").unlink()
        self.assertEqual(restore_checkout.recover_project(self.project), 1)
        self.assertFalse((self.project / "BoardConfig-common.mk").exists())

    def test_initialized_submodule_recovers_files_without_changing_its_revision(self):
        source = self.root / "submodule-source"
        source.mkdir()
        restore_checkout.git(source, "init", "-q")
        restore_checkout.git(source, "config", "user.name", "Recovery test")
        restore_checkout.git(source, "config", "user.email", "recovery@example.invalid")
        (source / "Kconfig").write_text("config KSU\n")
        restore_checkout.git(source, "add", ".")
        restore_checkout.git(source, "commit", "-qm", "Submodule baseline")
        self.git("-c", "protocol.file.allow=always", "submodule", "add", "-q",
                 str(source), "KernelSU")
        self.git("commit", "-qm", "Add submodule")
        child = self.project / "KernelSU"
        revision = restore_checkout.git(child, "rev-parse", "HEAD")
        (child / "Kconfig").unlink()
        self.assertEqual(restore_checkout.recover_project(self.project, True), 1)
        self.assertEqual((child / "Kconfig").read_text(), "config KSU\n")
        self.assertEqual(restore_checkout.git(child, "rev-parse", "HEAD"), revision)

    def test_project_paths_cannot_escape_the_checkout(self):
        with self.assertRaisesRegex(ValueError, "Invalid project path"):
            restore_checkout.projects(self.root, ["../outside"])
        outside = self.root.parent / (self.root.name + "-not-a-checkout")
        os.symlink(outside, self.root / "shared-source")
        with self.assertRaisesRegex(ValueError, "outside the Android checkout"):
            restore_checkout.projects(self.root, ["shared-source"])

    def test_directory_symlink_is_preserved_and_not_followed(self):
        (self.project / "nested/missing.txt").unlink()
        (self.project / "nested").rmdir()
        outside = self.root / "outside"
        outside.mkdir()
        os.symlink(outside, self.project / "nested")
        with self.assertRaisesRegex(ValueError, "directory symlink"):
            restore_checkout.recover_project(self.project, True)
        self.assertTrue((self.project / "nested").is_symlink())
        self.assertFalse((outside / "missing.txt").exists())


if __name__ == "__main__":
    unittest.main()

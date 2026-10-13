# SPDX-License-Identifier: Apache-2.0
"""Check selective restoration, complete backups, and safe directory handling."""

import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from recover_namespace_edits import FILES, recover


def git(project, *args):
    return subprocess.check_output(["git", "-C", str(project), *args], stderr=subprocess.STDOUT)


class NamespaceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.rom = root / "pixelos"
        (self.rom / ".repo").mkdir(parents=True)
        self.backups = root / "backups"
        self.backups.mkdir()
        for project, relative in FILES:
            location = self.rom / project
            target = location / relative
            target.parent.mkdir(parents=True)
            git(location, "init", "--quiet")
            target.write_text("upstream original\n")
            (location / "keep.txt").write_text("original unrelated file\n")
            git(location, "add", "--", relative, "keep.txt")
            git(location, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "--quiet", "-m", "Fixture")
            target.write_text("local namespace workaround\n")
            (location / "keep.txt").write_text("keep this unrelated edit\n")
        for plugin in ("faceid", "motionsense"):
            (self.rom / "vendor/hecker/floral" / plugin / "Android.bp").write_text(
                "locally edited generated blueprint\n")

    def run_recovery(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return recover(self.rom, self.backups)

    def test_selective_restore_preserves_all_edited_file_contents_and_unrelated_changes(self):
        backup = self.run_recovery()
        with tarfile.open(backup / "edited-files.tar.gz") as archive:
            for project, relative in FILES:
                path = self.rom / project / relative
                self.assertEqual(path.read_text(), "upstream original\n")
                self.assertEqual(archive.extractfile(project + "/" + relative).read(),
                                 b"local namespace workaround\n")
                self.assertEqual((self.rom / project / "keep.txt").read_text(),
                                 "keep this unrelated edit\n")
            for plugin in ("faceid", "motionsense"):
                path = "vendor/hecker/floral/" + plugin + "/Android.bp"
                self.assertEqual(archive.extractfile(path).read(), b"locally edited generated blueprint\n")
                self.assertEqual((self.rom / path).read_text(), "locally edited generated blueprint\n")
        self.assertIn("local namespace workaround", (backup / "1-tracked.patch").read_text())

    def test_renamed_chipset_is_reinstated_before_git_restore(self):
        path = self.rom / "hardware/qcom-caf/sm8250"
        disabled = path.with_name("sm8250.disabled")
        path.rename(disabled)
        backup = self.run_recovery()
        self.assertTrue(path.is_dir())
        self.assertFalse(disabled.exists())
        self.assertEqual((path / "media/mm-core/Android.bp").read_text(), "upstream original\n")
        self.assertEqual(len(json.loads((backup / "recovery.json").read_text())["directory_moves"]), 1)

    def test_colliding_directory_names_stop_before_any_file_is_changed(self):
        path = self.rom / "hardware/qcom-caf/sm8250"
        path.with_name("sm8250.disabled").mkdir()
        with self.assertRaisesRegex(ValueError, "Both chipset paths exist"):
            self.run_recovery()
        self.assertFalse(list(self.backups.iterdir()))
        for project, relative in FILES:
            self.assertEqual((self.rom / project / relative).read_text(), "local namespace workaround\n")

    def test_missing_tracked_file_stops_before_restoring_other_projects(self):
        project, relative = FILES[-1]
        git(self.rom / project, "rm", "--cached", "--", relative)
        git(self.rom / project, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "commit", "--quiet", "-m", "Remove fixture file")
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_recovery()
        self.assertFalse(list(self.backups.iterdir()))
        project, relative = FILES[0]
        self.assertEqual((self.rom / project / relative).read_text(), "local namespace workaround\n")

    def test_staged_and_skip_worktree_edits_have_backups_and_are_restored(self):
        project, relative = FILES[0]
        git(self.rom / project, "add", "--", relative)
        (self.rom / project / relative).write_text("additional working edit\n")
        project, relative = FILES[1]
        git(self.rom / project, "update-index", "--skip-worktree", "--", relative)
        backup = self.run_recovery()
        self.assertIn("local namespace workaround", (backup / "1-staged.patch").read_text())
        with tarfile.open(backup / "edited-files.tar.gz") as archive:
            self.assertEqual(archive.extractfile(FILES[0][0] + "/" + FILES[0][1]).read(),
                             b"additional working edit\n")
            self.assertEqual(archive.extractfile(FILES[1][0] + "/" + FILES[1][1]).read(),
                             b"local namespace workaround\n")
        self.assertEqual((self.rom / project / relative).read_text(), "upstream original\n")

    def test_backup_inside_rom_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside the Android source tree"):
            recover(self.rom, self.rom)

    def test_shared_defaults_and_gsl_namespace_workarounds_are_backed_up_and_removed(self):
        originals = {
            ("hardware/qcom-caf/common", "Android.bp"):
                'cc_defaults {\n    name: "android_hardware_qtiaudio_config_defaults",\n}\n',
            ("hardware/qcom-caf/sm8450/audio/graphservices", "gsl/Android.bp"):
                'cc_library_shared {\n    name: "libar-gsl",\n'
                '    defaults: ["android_hardware_qtiaudio_config_defaults"],\n}\n',
        }
        for (project, relative), original in originals.items():
            location = self.rom / project
            target = location / relative
            target.write_text(original)
            git(location, "add", "--", relative)
            git(location, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "--quiet", "-m", "Use real shared audio dependency shape")
            target.write_text("soong_namespace {}\n" + original)
        backup = self.run_recovery()
        with tarfile.open(backup / "edited-files.tar.gz") as archive:
            for (project, relative), original in originals.items():
                self.assertEqual((self.rom / project / relative).read_text(), original)
                self.assertEqual(archive.extractfile(project + "/" + relative).read(),
                                 ("soong_namespace {}\n" + original).encode())


if __name__ == "__main__":
    unittest.main()

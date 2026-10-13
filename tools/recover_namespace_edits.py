#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Back up and undo the specific ServerHive namespace workarounds before sync."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

FILES = (
    ("hardware/qcom-caf/sm8150/media", "mm-core/Android.bp"),
    ("hardware/qcom-caf/sm8250/media", "mm-core/Android.bp"),
    ("hardware/qcom-caf/sm8150/display", "Android.bp"),
    ("hardware/qcom-caf/msm8953/display", "Android.bp"),
    ("hardware/qcom-caf/common", "Android.bp"),
    ("hardware/qcom-caf/sm8450/audio/graphservices", "gsl/Android.bp"),
    ("vendor/hecker/floral/faceid", "Android.bp.in"),
    ("vendor/hecker/floral/motionsense", "Android.bp.in"),
)
CHIPSETS = ("sm8250", "sm8350", "sm8450", "sm8450-6.6", "sm8550", "sm8650", "sm8750")


def git(project, *args):
    return subprocess.check_output(["git", "-C", str(project), *args])


def recover(rom, backup_parent=None):
    rom = rom.resolve()
    if not (rom / ".repo").is_dir():
        raise ValueError("Run from the PixelOS source root containing .repo")
    parent = (backup_parent or Path.home()).resolve()
    if parent.is_relative_to(rom):
        raise ValueError("Backups must be outside the Android source tree")
    moves = []
    for chipset in CHIPSETS:
        original = rom / "hardware/qcom-caf" / chipset
        disabled = original.with_name(chipset + ".disabled")
        if not os.path.lexists(disabled):
            continue
        if os.path.lexists(original):
            raise ValueError("Both chipset paths exist; resolve without overwriting either: " +
                             str(original) + " and " + str(disabled))
        if disabled.is_symlink() or not disabled.is_dir():
            raise ValueError("Expected a renamed chipset directory: " + str(disabled))
        moves.append((disabled, original))

    def current(path):
        for disabled, original in moves:
            if path.is_relative_to(original):
                return disabled / path.relative_to(original)
        return path

    # Validate every project/file before creating backups or changing sources.
    records = []
    for project, relative in FILES:
        location = current(rom / project)
        if not location.resolve().is_relative_to(rom):
            raise ValueError("Project escapes this checkout: " + str(location))
        top = Path(git(location, "rev-parse", "--show-toplevel").decode().strip())
        if top.resolve() != location.resolve():
            raise ValueError("Expected a separate Repo project: " + str(location))
        git(location, "ls-files", "--error-unmatch", "--", relative)
        records.append({"project": project, "file": relative,
                        "head": git(location, "rev-parse", "HEAD").decode().strip()})

    backup = Path(tempfile.mkdtemp(prefix="pixelos-namespaces-", dir=parent))
    metadata = {"source_root": str(rom), "files": records,
                "directory_moves": [{"from": str(a), "to": str(b)} for a, b in moves]}
    (backup / "recovery.json").write_text(json.dumps(metadata, indent=2) + "\n")
    archive_paths = [Path(project) / relative for project, relative in FILES]
    archive_paths += [Path("vendor/hecker/floral") / plugin / "Android.bp"
                     for plugin in ("faceid", "motionsense")]
    with tarfile.open(backup / "edited-files.tar.gz", "w:gz") as archive:
        for relative in archive_paths:
            path = current(rom / relative)
            if os.path.lexists(path):
                archive.add(path, arcname=str(relative), recursive=False)
    for index, record in enumerate(records, 1):
        location = current(rom / record["project"])
        relative = record["file"]
        (backup / (str(index) + "-tracked.patch")).write_bytes(
            git(location, "diff", "--binary", "HEAD", "--", relative))
        (backup / (str(index) + "-staged.patch")).write_bytes(
            git(location, "diff", "--binary", "--cached", "--", relative))

    print("Namespace edits saved in:", backup, flush=True)
    for disabled, original in moves:
        disabled.rename(original)
    for project, relative in FILES:
        git(rom / project, "restore", "--source=HEAD", "--staged", "--worktree",
            "--ignore-skip-worktree-bits", "--", relative)
    print("Restored six CAF files and both plugin templates to their current HEADs.")
    print("Next: locally sync hardware/qcom-caf/common; sync plugins if their pins changed.")
    print("Plugin preparation will regenerate Android.bp from the updated templates.")
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom-root", type=Path, default=Path.cwd())
    parser.add_argument("--backup-parent", type=Path, default=Path.home())
    args = parser.parse_args()
    try:
        recover(args.rom_root, args.backup_parent)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print("Namespace recovery stopped:", error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

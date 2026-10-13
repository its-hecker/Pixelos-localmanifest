#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Restore missing indexed files without replacing existing checkout files."""

import argparse
import os
from pathlib import Path
import subprocess
import sys


def git(project, *arguments, payload=None):
    return subprocess.run(
        ["git", "--literal-pathspecs", "-C", str(project), *arguments],
        input=payload, stdout=subprocess.PIPE, check=True,
    ).stdout


def indexed_files(project):
    files, submodules = [], []
    for entry in git(project, "ls-files", "--stage", "-z").split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        mode, _, stage = metadata.split()
        if stage != b"0":
            raise ValueError("Unresolved merge in " + str(project) + "; resolve it before recovery")
        if mode == b"160000":
            submodules.append(os.fsdecode(name))
        elif mode in (b"100644", b"100755", b"120000"):
            files.append(os.fsdecode(name))
    return files, submodules


def missing_files(project, files):
    missing = []
    for name in files:
        path = project / name
        if os.path.lexists(path):
            continue
        # Preserve locally created directory symlinks rather than writing through them.
        parent = path.parent
        while parent != project:
            if parent.is_symlink():
                raise ValueError("Cannot restore through directory symlink: " + str(parent))
            parent = parent.parent
        missing.append(name)
    return missing


def recover_project(project, restore=False, seen=None):
    project = project.resolve()
    if seen is None:
        seen = set()
    if project in seen:
        return 0
    seen.add(project)
    # Do not accidentally run against an enclosing repository if this checkout is absent.
    if not (project / ".git").exists():
        raise ValueError("Missing Git checkout: " + str(project) + "; run repo sync for it")
    top = Path(os.fsdecode(git(project, "rev-parse", "--show-toplevel")).strip()).resolve()
    if top != project:
        raise ValueError("Unexpected Git working tree for " + str(project))
    files, submodules = indexed_files(project)
    missing = missing_files(project, files)
    if missing:
        print(("Restoring " if restore else "Missing ") + str(len(missing))
              + " tracked files: " + str(project), flush=True)
        for name in missing[:5]:
            print("  " + name, flush=True)
        if restore:
            # Use the current index, preserving staged edits and staged deletions.
            # Literal, NUL-delimited paths cannot expand into files that already exist.
            payload = b"\0".join(os.fsencode(name) for name in missing) + b"\0"
            git(project, "restore", "--worktree", "--ignore-skip-worktree-bits",
                "--pathspec-from-file=-", "--pathspec-file-nul", payload=payload)
            remaining = missing_files(project, files)
            if remaining:
                raise ValueError("Files remain missing after restoration in " + str(project))
    total = len(missing)
    for name in submodules:
        child = project / name
        if (child / ".git").exists():
            if not child.resolve().is_relative_to(project):
                raise ValueError("Submodule worktree is outside its project: " + str(child))
            total += recover_project(child, restore, seen)
    return total


def projects(rom, selected):
    if selected:
        names = selected
    else:
        result = subprocess.run(["repo", "list", "-p"], cwd=rom, text=True,
                                stdout=subprocess.PIPE, check=True)
        names = [name for name in result.stdout.splitlines() if name]
    if not names:
        raise ValueError("No projects found; finish repo init and install floral.xml")
    result = []
    for name in names:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or ".repo" in relative.parts:
            raise ValueError("Invalid project path: " + name)
        project = (rom / relative).resolve()
        if not project.is_relative_to(rom):
            raise ValueError("Project worktree is outside the Android checkout: " + name)
        result.append(project)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom-root", type=Path, default=Path.cwd())
    parser.add_argument("--project", action="append", default=[],
                        help="Limit recovery to this project path; repeatable")
    parser.add_argument("--restore", action="store_true",
                        help="Restore missing files from the Git index; otherwise report only")
    args = parser.parse_args()
    try:
        rom = args.rom_root.resolve()
        if not (rom / ".repo").is_dir():
            raise ValueError("Run this command from the Android source root")
        selected = projects(rom, args.project)
        seen, total = set(), 0
        for number, project in enumerate(selected, 1):
            if number == 1 or number % 100 == 0:
                print("Checking project " + str(number) + "/" + str(len(selected)), flush=True)
            total += recover_project(project, args.restore, seen)
        print(("Restored " if args.restore else "Found ") + str(total)
              + " missing tracked files across " + str(len(seen)) + " Git checkouts.")
        if total and not args.restore:
            print("Rerun with --restore to materialize these files.")
            return 1
        print("Existing files and untracked build outputs were preserved.")
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print("Checkout recovery:", error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Remove locally added CAF namespaces while retaining other working/index edits."""

import argparse
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET


def git(project, *args, input=None):
    result = subprocess.run(["git", "-C", str(project), *args], input=input,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise ValueError("Git failed in " + str(project) + ": " + result.stderr.decode(errors="replace").strip())
    return result.stdout


def code_mask(content):
    # Preserve byte offsets while masking quoted strings and both comment forms.
    tokens = rb'"(?:\\.|[^"\\])*"|//[^\r\n]*|/\*[\s\S]*?\*/'
    return re.sub(tokens, lambda match: b" " * len(match.group()), content)


def namespace_blocks(content):
    masked = code_mask(content)
    blocks = []
    for match in re.finditer(rb"\bsoong_namespace\s*\{", masked):
        prefix = masked[:match.start()]
        if prefix.count(b"{") != prefix.count(b"}"):
            continue
        depth = 1
        end = match.end()
        while end < len(masked) and depth:
            if masked[end] == ord("{"):
                depth += 1
            elif masked[end] == ord("}"):
                depth -= 1
            end += 1
        if depth:
            raise ValueError("Unclosed local soong_namespace; inspect the Blueprint before recovery")
        start = match.start()
        line_start = content.rfind(b"\n", 0, start) + 1
        if not content[line_start:start].strip():
            start = line_start
        suffix = re.match(rb"[ \t]*(?:\r?\n|$)", content[end:])
        if suffix:
            end += suffix.end()
        blocks.append((start, end))
    return blocks


def without_namespaces(content):
    for start, end in reversed(namespace_blocks(content)):
        content = content[:start] + content[end:]
    return content


def project_paths(manifest):
    paths = []
    for node in manifest.findall("project"):
        path = Path(node.get("path", node.get("name", "")))
        if path.parts[:2] != ("hardware", "qcom-caf"):
            continue
        if path.is_absolute() or ".." in path.parts or len(path.parts) < 3:
            raise ValueError("Invalid CAF project path: " + str(path))
        paths.append(path)
    if not paths or len(paths) != len(set(paths)):
        raise ValueError("The active manifest must contain distinct CAF project paths")
    return paths


def inventory(rom, manifest):
    rom = rom.resolve()
    actions = []
    for project in project_paths(manifest):
        location = rom / project
        if not location.is_dir() or not location.resolve().is_relative_to(rom):
            raise ValueError("Missing or moved CAF project: " + str(project))
        top = Path(git(location, "rev-parse", "--show-toplevel").decode().strip())
        if top.resolve() != location.resolve():
            raise ValueError("Expected a separate Repo project: " + str(project))
        head = git(location, "rev-parse", "HEAD").decode().strip()
        tracked = {}
        for entry in git(location, "ls-files", "--stage", "-z", "--", "*.bp").split(b"\0"):
            if not entry:
                continue
            metadata, name = entry.split(b"\t", 1)
            relative = Path(os.fsdecode(name))
            if relative.name != "Android.bp":
                continue
            mode, _, stage = metadata.decode().split()
            if stage != "0":
                raise ValueError("Unmerged CAF Blueprint: " + str(project / relative))
            if mode not in ("100644", "100755"):
                continue
            tracked[relative] = mode
        untracked = [Path(os.fsdecode(name)) for name in
                     git(location, "ls-files", "--others", "--exclude-standard", "-z", "--", "*.bp").split(b"\0")
                     if name and Path(os.fsdecode(name)).name == "Android.bp"]
        for relative in sorted(set(tracked) | set(untracked)):
            path = location / relative
            if not path.is_file() or path.is_symlink():
                continue
            if not path.resolve().is_relative_to(location.resolve()):
                raise ValueError("Blueprint escapes its CAF project: " + str(project / relative))
            before = path.read_bytes()
            index_before = git(location, "show", ":" + relative.as_posix()) if relative in tracked else None
            if not namespace_blocks(before) and not (index_before and namespace_blocks(index_before)):
                continue
            head_entry = git(location, "ls-tree", "-z", "HEAD", "--", relative.as_posix())
            upstream = git(location, "show", "HEAD:" + relative.as_posix()) if head_entry else None
            if upstream is not None and namespace_blocks(upstream):
                continue  # Preserve all scopes already present in this project's HEAD.
            after = without_namespaces(before)
            index_after = without_namespaces(index_before) if index_before is not None else None
            if upstream is None and (code_mask(after).strip() or
                                     (index_after is not None and code_mask(index_after).strip())):
                continue  # New module-bearing files need review; namespace-only files are recoverable.
            if before == after and index_before == index_after:
                continue
            actions.append(dict(project=project.as_posix(), file=relative.as_posix(), head=head,
                                before=before, after=after, index_before=index_before, index_after=index_after,
                                mode=tracked.get(relative), file_mode=stat.S_IMODE(path.stat().st_mode)))
    return actions


def apply(rom, actions, backup_parent):
    rom = rom.resolve()
    parent = backup_parent.resolve()
    if parent.is_relative_to(rom):
        raise ValueError("Backups must be outside the Android source tree")
    if not actions:
        print("No recoverable CAF namespace additions found.")
        return None
    backup = Path(tempfile.mkdtemp(prefix="pixelos-caf-scopes-", dir=parent))
    records = [{k: v for k, v in action.items() if k not in
                ("before", "after", "index_before", "index_after")} for action in actions]
    (backup / "recovery.json").write_text(json.dumps({"source_root": str(rom), "files": records}, indent=2) + "\n")
    with tarfile.open(backup / "edited-files.tar.gz", "w:gz") as archive:
        for action in actions:
            for kind, data in (("worktree", action["before"]), ("index", action["index_before"])):
                if data is None:
                    continue
                member = tarfile.TarInfo(kind + "/" + action["project"] + "/" + action["file"])
                member.size = len(data)
                member.mode = action["file_mode"]
                archive.addfile(member, io.BytesIO(data))
    projects = sorted({action["project"] for action in actions})
    for number, project in enumerate(projects, 1):
        files = [action["file"] for action in actions if action["project"] == project]
        for label, args in (("tracked", ["diff", "--binary", "HEAD"]),
                            ("staged", ["diff", "--binary", "--cached"])):
            (backup / (str(number) + "-" + label + ".patch")).write_bytes(
                git(rom / project, *args, "--", *files))
    print("CAF namespace edits saved in:", backup, flush=True)
    # Check all input snapshots before the first modification.
    for project in projects:
        expected = next(action["head"] for action in actions if action["project"] == project)
        if git(rom / project, "rev-parse", "HEAD").decode().strip() != expected:
            raise ValueError("CAF HEAD changed during recovery: " + project)
    for action in actions:
        project = rom / action["project"]
        path = project / action["file"]
        if path.is_symlink() or path.read_bytes() != action["before"]:
            raise ValueError("Blueprint changed during recovery: " + str(path))
        if action["mode"] and git(project, "show", ":" + action["file"]) != action["index_before"]:
            raise ValueError("Git index changed during recovery: " + str(path))
    for action in actions:
        project = rom / action["project"]
        if action["before"] != action["after"]:
            (project / action["file"]).write_bytes(action["after"])
        if action["index_before"] != action["index_after"]:
            digest = git(project, "hash-object", "-w", "--stdin", input=action["index_after"]).decode().strip()
            git(project, "update-index", "--cacheinfo", action["mode"], digest, action["file"])
    print("Removed locally added namespaces from", len(actions), "CAF Blueprints; other edits retained.")
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom-root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, help="Use an exported Repo manifest")
    parser.add_argument("--backup-parent", type=Path, default=Path.home())
    parser.add_argument("--apply", action="store_true", help="Back up and remove the discovered added namespaces")
    args = parser.parse_args()
    try:
        rom = args.rom_root.resolve()
        if not (rom / ".repo").is_dir():
            raise ValueError("Run from the PixelOS source root containing .repo")
        manifest = ET.parse(args.manifest).getroot() if args.manifest else ET.fromstring(
            subprocess.check_output(["repo", "manifest", "-o", "-"], cwd=rom))
        actions = inventory(rom, manifest)
        for action in actions:
            print("Added CAF namespace:", action["project"] + "/" + action["file"])
        if args.apply:
            apply(rom, actions, args.backup_parent)
        else:
            print("Report only:", len(actions), "locally added namespace files; use --apply to recover them.")
        return 0
    except (OSError, ValueError, ET.ParseError, subprocess.CalledProcessError) as error:
        print("CAF namespace recovery stopped:", error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

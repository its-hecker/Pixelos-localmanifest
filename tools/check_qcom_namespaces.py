#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the Qualcomm chipset namespaces exported by the active Repo manifest."""

import argparse
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

COMMON = "hardware/qcom-caf/common"
SOURCE = "os_pickup_qssi.bp"
SHARED_AUDIO_DEFAULT = "android_hardware_qtiaudio_config_defaults"
REPAIR = ("python3 .repo/local_manifests/tools/restore_checkout.py "
          "--project " + COMMON + " --restore\n"
          "repo sync -l -j1 --fail-fast " + COMMON)


def namespace_links(manifest):
    projects = [p for p in manifest.findall("project") if p.get("path") == COMMON]
    if len(projects) != 1:
        raise ValueError("The active manifest must select exactly one " + COMMON + " project")
    links = []
    for node in projects[0].findall("linkfile"):
        if node.get("src") != SOURCE:
            continue
        destination = Path(node.get("dest", ""))
        if (destination.is_absolute() or ".." in destination.parts or
                destination.parts[:2] != ("hardware", "qcom-caf") or
                destination.name != "Android.bp"):
            raise ValueError("Invalid Qualcomm namespace destination: " + str(destination))
        links.append(destination)
    if not links or len(set(links)) != len(links):
        raise ValueError("Missing or duplicate Qualcomm namespace exports in the active manifest")
    return links


def check(rom, manifest):
    rom = rom.resolve()
    links = namespace_links(manifest)
    renamed = [str(path.relative_to(rom)) for path in
               (rom / "hardware/qcom-caf").glob("*.disabled")]
    if renamed:
        raise ValueError("Renamed Qualcomm directories remain inside the source tree:\n  " +
                         "\n  ".join(sorted(renamed)) +
                         "\nRestore their original paths before regenerating Repo namespace links.")
    source = rom / COMMON / SOURCE
    if not source.resolve().is_relative_to(rom) or not source.is_file():
        raise ValueError("Missing Qualcomm namespace source: " + str(source) + "\nRun:\n" + REPAIR)
    content = source.read_bytes()
    if not re.search(rb"(?m)^\s*soong_namespace\s*\{", content):
        raise ValueError("Qualcomm namespace source has no soong_namespace declaration")
    invalid = []
    for relative in links:
        destination = rom / relative
        if (not destination.resolve().is_relative_to(rom) or not destination.is_file() or
                destination.read_bytes() != content):
            invalid.append(str(relative))
    if invalid:
        raise ValueError("Missing or mismatched Qualcomm chipset namespace exports:\n  " +
                         "\n  ".join(invalid) + "\nRun:\n" + REPAIR)
    common_bp = rom / COMMON / "Android.bp"
    if not common_bp.resolve().is_relative_to(rom) or not common_bp.is_file():
        raise ValueError("Missing Qualcomm shared module definitions: " + str(common_bp) +
                         "\nRun:\n" + REPAIR)
    shared = common_bp.read_bytes()
    # Upstream places these defaults in the implicit root namespace, reachable
    # from all chipset scopes. A local namespace here hides them from every
    # chipset whose os_pickup_qssi.bp does not import common explicitly.
    if re.search(rb"(?m)^\s*soong_namespace\s*\{", shared):
        raise ValueError("Qualcomm common Android.bp has a local namespace that hides shared audio defaults.\n"
                         "Back up and restore the local namespace edits:\n"
                         "python3 .repo/local_manifests/tools/recover_namespace_edits.py")
    if not re.search(rb'name\s*:\s*"' + SHARED_AUDIO_DEFAULT.encode() + rb'"', shared):
        raise ValueError("Missing shared Qualcomm audio defaults: " + SHARED_AUDIO_DEFAULT)
    return len(links)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom-root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, help="Check an exported manifest XML instead of invoking Repo")
    args = parser.parse_args()
    try:
        rom = args.rom_root.resolve()
        if args.manifest:
            manifest = ET.parse(args.manifest).getroot()
        else:
            result = subprocess.run(["repo", "manifest", "-o", "-"], cwd=rom,
                                    stdout=subprocess.PIPE, text=True, check=True)
            manifest = ET.fromstring(result.stdout)
        count = check(rom, manifest)
        print("Qualcomm chipset namespace exports: PASS (" + str(count) + ")")
        return 0
    except (OSError, ValueError, ET.ParseError, subprocess.CalledProcessError) as error:
        print("Checkout namespace check:", error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

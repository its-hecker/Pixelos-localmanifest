#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Prepare the real Floral plugins against the selected PixelOS configuration."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET


OVERLAY_ROOTS = [
    "vendor/lineage/overlay/common",
    "vendor/custom/overlay/common",
    "device/google/coral/overlay",
    "device/google/coral/overlay-lineage",
    "device/google/coral/coral/overlay",
]


def active_arrays(rom, package, array):
    """Selected static overlays, in order from common to device-specific."""
    files = []
    for root in OVERLAY_ROOTS:
        directory = rom / root / package / "res/values"
        for file in sorted(directory.glob("*.xml")):
            if any(node.get("name") == array for node in ET.parse(file).getroot()):
                files.append(file)
    # PixelOS also selects this framework RRO from vendor/custom/config/common.mk.
    if package == "frameworks/base/core/res":
        directory = rom / "vendor/custom/overlay/rro_packages/FrameworkOverlayCustom/res/values"
        for file in sorted(directory.glob("*.xml")):
            if any(node.get("name") == array for node in ET.parse(file).getroot()):
                files.append(file)
    return files


def run(rom, plugin, tool, *arguments):
    subprocess.run([sys.executable, str(rom / plugin / "tools" / tool), *map(str, arguments)],
                   cwd=rom, check=True)


def prepare(rom, offline=False, allowlists=(), biometrics=()):
    motion = "vendor/hecker/floral/motionsense"
    face = "vendor/hecker/floral/faceid"
    required = [
        "device/google/coral/custom_coral.mk",
        "device/google/coral/BoardConfig-common.mk",
        "vendor/google/coral/Android.bp",
        "vendor/google/coral/proprietary/vendor/firmware/faceauth_config.yaml",
        "vendor/google/coral/proprietary/vendor/firmware/faceauth_v1.mdt",
        "vendor/custom/config/common_full_phone.mk",
        "vendor/lineage/overlay/common/frameworks/base/packages/SystemUI/res/values/config.xml",
        "frameworks/base/packages/SystemUI/res/values/config.xml",
        "frameworks/base/core/res/res/values/config.xml",
        motion + "/tools/prepare.py", face + "/tools/prepare.py",
    ]
    for relative in required:
        if not (rom / relative).is_file():
            raise ValueError("Missing source input: " + relative + "; finish repo sync first")
    product = (rom / "device/google/coral/custom_coral.mk").read_text()
    if "TARGET_FACE_UNLOCK_SUPPORTED := false" not in product:
        raise ValueError("Disable PixelOS ParanoidSense before using the IR Face HAL")
    # Refuse unfamiliar framework methods before making any framework changes.
    run(rom, face, "apply_framework_fixes.py", "--rom-root", rom, "--check")
    fetch_arguments = ["--verify-only"] if offline else []
    for plugin in [motion, face]:
        run(rom, plugin, "fetch_prebuilts.py", *fetch_arguments)
        run(rom, plugin, "check_port.py")
    run(rom, face, "apply_framework_fixes.py", "--rom-root", rom, "--apply")
    motion_files = active_arrays(rom, "frameworks/base/packages/SystemUI", "config_pluginAllowlist")
    face_files = active_arrays(rom, "frameworks/base/core/res", "config_biometric_sensors")
    motion_files += [path if path.is_absolute() else rom / path for path in allowlists]
    face_files += [path if path.is_absolute() else rom / path for path in biometrics]
    motion_arguments = ["--rom-root", rom, "--policy-dir", rom / "device/google/coral/sepolicy"]
    for path in motion_files:
        motion_arguments += ["--allowlist-xml", path]
    run(rom, motion, "prepare.py", *motion_arguments)
    face_arguments = ["--rom-root", rom, "--vendor-tree", rom / "vendor/google/coral"]
    for path in face_files:
        face_arguments += ["--biometrics-xml", path]
    run(rom, face, "prepare.py", *face_arguments)
    for plugin in [motion, face]:
        run(rom, plugin, "verify_ready.py")
    print("PixelOS Floral plugin preparation passed.")
    print("Motion allowlist overlays:", *[str(p.relative_to(rom)) for p in motion_files], sep="\n  ")
    print("Face sensor overlays:", *[str(p.relative_to(rom)) for p in face_files], sep="\n  ")
    profile = json.loads((rom / face / "generated/profile.json").read_text())
    print("Hardware biometric sensors:", profile["sensors"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom-root", type=Path, default=Path.cwd())
    parser.add_argument("--offline", action="store_true", help="Use already cached, checksum-verified binaries")
    parser.add_argument("--allowlist-xml", type=Path, action="append", default=[],
                        help="Additional active SystemUI overlays, in increasing priority")
    parser.add_argument("--biometrics-xml", type=Path, action="append", default=[],
                        help="Additional active framework overlays, in increasing priority")
    args = parser.parse_args()
    try:
        prepare(args.rom_root.resolve(), args.offline, args.allowlist_xml, args.biometrics_xml)
    except (OSError, ValueError, ET.ParseError, subprocess.CalledProcessError) as error:
        print("PixelOS Floral setup:", error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

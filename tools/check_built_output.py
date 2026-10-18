#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check installed camera files, original APKs and the Motion Sense country override."""

from pathlib import Path
import re
import sys

from camera_install import SERVICE
from google_camera import verify_installed


def check_motion_sense(output):
    paths = [output / "product/etc/build.prop", output / "product/build.prop"]
    properties = next((path for path in paths if path.is_file()), None)
    if properties is None:
        raise ValueError("Built product image is missing Motion Sense's product properties")
    values = re.findall(r"(?m)^\s*pixel\.oslo\.allowed_override\s*=\s*(\S+)\s*$",
                        properties.read_text())
    if values != ["1"]:
        raise ValueError("Built product image needs exactly one pixel.oslo.allowed_override=1")


def check(rom, output):
    filename = SERVICE + ".rc"
    original = rom / "vendor/google/coral/proprietary/vendor/etc/init" / filename
    installed = output / "vendor/etc/init" / filename
    if not installed.is_file() or installed.read_bytes() != original.read_bytes():
        raise ValueError("Built vendor image is missing Coral's exact camera provider init script")
    if not (output / "vendor/bin/hw" / SERVICE).is_file():
        raise ValueError("Built vendor image is missing the Coral camera provider binary")
    if not (output / "vendor/etc/vintf/manifest" / (SERVICE + ".xml")).is_file():
        raise ValueError("Built vendor image is missing the camera VINTF declaration")
    verify_installed(rom, output)
    check_motion_sense(output)
    print("Built output: camera provider binary/init/VINTF, original ten-APK Google Camera set "
          "and Motion Sense country override: PASS")


if __name__ == "__main__":
    root = Path.cwd()
    try:
        check(root, root / (sys.argv[1] if len(sys.argv) > 1 else "out/target/product/coral"))
    except (OSError, ValueError) as error:
        print("PixelOS built output:", error, file=sys.stderr)
        sys.exit(1)

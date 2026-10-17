#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the installed camera startup files and unchanged Google Camera APKs."""

from pathlib import Path
import sys

from camera_install import SERVICE
from google_camera import verify_installed


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
    print("Built output: camera provider binary/init/VINTF and original ten-APK Google Camera set: PASS")


if __name__ == "__main__":
    root = Path.cwd()
    try:
        check(root, root / (sys.argv[1] if len(sys.argv) > 1 else "out/target/product/coral"))
    except (OSError, ValueError) as error:
        print("PixelOS built output:", error, file=sys.stderr)
        sys.exit(1)

# SPDX-License-Identifier: Apache-2.0
"""Fetch the unchanged, checksum-pinned Camera split set before Android builds."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request


CAMERA = Path("device/google/coral/camera")
PREFIX = "GoogleCameraCoral.apks."


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def matches(path, expected):
    return (path.is_file() and path.stat().st_size == expected["size"]
            and digest(path) == expected["sha256"])


def fetch_chunk(url, path, expected):
    if path.is_symlink():
        raise ValueError("Refusing a symlinked Camera chunk: " + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".gcam-download-", delete=False) as target:
            temporary = Path(target.name)
            request = urllib.request.Request(url, headers={"User-Agent": "PixelOS-Coral-Camera"})
            with urllib.request.urlopen(request, timeout=60) as source:
                copied = 0
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    copied += len(block)
                    if copied > expected["size"]:
                        raise ValueError("Camera download exceeds its pinned size")
                    target.write(block)
        if not matches(temporary, expected):
            raise ValueError("Camera download differs from its pinned hash: " + path.name)
        temporary.chmod(0o644)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prepare(rom, offline=False):
    camera = rom / CAMERA
    origin = json.loads((camera / "ORIGIN.json").read_text())
    payload = json.loads((camera / "prebuilt/payload.json").read_text())
    if (origin["repository"] != "its-hecker/infinity_cnb_proprietary_vendor_google_coral"
            or origin["revision"] != "d1409c6066f977639a99d276709e3a70e7a9b3c0"
            or origin["path"] != "camera/prebuilt"):
        raise ValueError("Review the changed Google Camera payload origin")
    chunks = payload["chunks"]
    expected_names = [PREFIX + f"{i:02d}" for i in range(3)]
    if sorted(chunks) != expected_names:
        raise ValueError("Review the changed Google Camera chunk set")
    unexpected = {p.name for p in (camera / "prebuilt").glob(PREFIX + "*")} - set(chunks)
    if unexpected:
        raise ValueError("Unexpected Camera chunk files: " + ", ".join(sorted(unexpected)))
    base = ("https://raw.githubusercontent.com/" + origin["repository"] + "/" +
            origin["revision"] + "/" + origin["path"] + "/")
    for name in expected_names:
        target = camera / "prebuilt" / name
        if not matches(target, chunks[name]):
            if offline:
                raise ValueError("Camera cache missing or damaged: " + str(target)
                                 + "; rerun build.sh without --offline")
            print("Fetching pinned Google Camera chunk:", name, flush=True)
            fetch_chunk(base + name, target, chunks[name])
    # Reuse the stable importer: validate the APK-set TOC, all ten exact APK
    # hashes and the complete split selection, including its startup JNI split.
    subprocess.run([sys.executable, str(camera / "tools/prepare_camera.py"), "--check-hashes"],
                   cwd=rom, check=True)


def verify_installed(rom, output):
    camera = rom / CAMERA
    payload = json.loads((camera / "prebuilt/payload.json").read_text())
    source = json.loads((camera / "source.json").read_text())
    expected = sorted((source["files"][name]["size"], source["files"][name]["sha256"])
                      for name in payload["files"])
    directory = output / "product/app/GoogleCameraCoral"
    actual = sorted((path.stat().st_size, digest(path)) for path in directory.rglob("*.apk"))
    if actual != expected:
        raise ValueError("Built GoogleCameraCoral APKs differ from the tested ten-APK split package")
    for partition in ("system", "system_ext", "product", "vendor"):
        for name in ("Aperture", "Camera2"):
            if any((output / partition / kind / name).exists() for kind in ("app", "priv-app")):
                raise ValueError(f"Stale {name} remains in the built output; run m installclean and rebuild")


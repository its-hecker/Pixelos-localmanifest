#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise real PixelOS/plugin setup using small, pinned source checkouts."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from prepare import prepare
from validate import ROOT, manifest, require
from check_qcom_namespaces import check as check_namespaces, namespace_links


def git(*args, cwd=None):
    subprocess.run(["git", *map(str, args)], cwd=cwd, check=True)


def checkout(rom, path, repository, revision, files=None):
    destination = rom / path
    destination.mkdir(parents=True)
    git("init", "--quiet", destination)
    git("remote", "add", "origin", "https://github.com/" + repository + ".git", cwd=destination)
    if files:
        git("config", "core.sparseCheckout", "true", cwd=destination)
        (destination / ".git/info/sparse-checkout").write_text("\n".join("/" + p for p in files) + "\n")
    git("fetch", "--quiet", "--depth=1", "--filter=blob:none", "origin", revision, cwd=destination)
    git("-c", "filter.lfs.required=false", "-c", "filter.lfs.process=", "-c", "filter.lfs.smudge=",
        "checkout", "--quiet", "--detach", "FETCH_HEAD", cwd=destination)


def profiles(rom):
    result = {}
    for name in ["motionsense", "faceid"]:
        root = rom / "vendor/hecker/floral" / name
        data = json.loads((root / "generated/profile.json").read_text())
        for item in data["output_files"]:
            result[name + "/" + item["path"]] = hashlib.sha256((root / item["path"]).read_bytes()).hexdigest()
    return result


def check_product_make(rom):
    # Android's pre-product configuration pass has not defined my-dir yet.
    # Parse the real prepared entries with their real readiness verifiers.
    motion = "vendor/hecker/floral/motionsense"
    face = "vendor/hecker/floral/faceid"
    source = "\n".join([
        "TARGET_COPY_OUT_VENDOR := vendor",
        "PRODUCT_PACKAGES := KeepMe android.hardware.biometrics.face@1.0-service.google OsloFeedback",
        "PRODUCT_COPY_FILES := keep:vendor/etc/keep",
        "include " + motion + "/motionsense.mk",
        "include " + face + "/faceid.mk",
        "include " + motion + "/BoardConfigMotionSense.mk",
        "include " + face + "/BoardConfigFaceID.mk",
        "$(info MAKE_NAMESPACES=$(PRODUCT_SOONG_NAMESPACES))",
        "$(info MAKE_PACKAGES=$(PRODUCT_PACKAGES))",
        "$(info MAKE_COPIES=$(PRODUCT_COPY_FILES))",
        "$(info MAKE_POLICY=$(BOARD_VENDOR_SEPOLICY_DIRS))",
        ".PHONY: all", "all:", "\t@:",
    ]) + "\n"
    result = subprocess.run(["make", "--no-print-directory", "-f", "-", "all"],
                            cwd=rom, input=source, text=True, capture_output=True)
    require(result.returncode == 0, "Plugin product/board Make parsing failed:\n" +
            result.stdout + result.stderr)
    values = dict(line.split("=", 1) for line in result.stdout.splitlines()
                  if line.startswith("MAKE_"))
    namespaces = values.get("MAKE_NAMESPACES", "").split()
    packages = values.get("MAKE_PACKAGES", "").split()
    copies = values.get("MAKE_COPIES", "").split()
    require(motion in namespaces and face in namespaces, "Plugin Soong namespaces are missing")
    require({"KeepMe", "FloralOsloFeedback", "FloralFaceIDHal", "FloralFaceIDManifest"} <=
            set(packages), "Prepared plugin packages are missing")
    require(not {"android.hardware.biometrics.face@1.0-service.google", "OsloFeedback"} &
            set(packages), "Replaced stock plugin packages were retained")
    require("keep:vendor/etc/keep" in copies and face +
            "/configs/android.hardware.biometrics.face.xml:vendor/etc/permissions/android.hardware.biometrics.face.xml"
            in copies, "Plugin permission copy or unrelated product copy was lost")
    require(face + "/sepolicy/vendor" in values.get("MAKE_POLICY", "").split(),
            "Face ID vendor policy is missing")
    print("PASS: real prepared product and board entries parse before Android's my-dir helper.")


def check_namespace_setup(rom):
    reference = rom / "out/floral-manifest-reference/snippets/lineage.xml"
    upstream = ET.parse(reference).getroot()
    source = rom / "hardware/qcom-caf/common/os_pickup_qssi.bp"
    for relative in namespace_links(upstream):
        destination = rom / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not os.path.lexists(destination):
            destination.symlink_to(os.path.relpath(source, destination.parent))
    count = check_namespaces(rom, upstream)
    print("PASS: " + str(count) + " chipset namespace exports from pinned PixelOS/common sources.")


def test(rom, fetch=True):
    manifest()
    lock = json.loads((ROOT / "source-revisions.json").read_text())
    if fetch:
        projects = {p.get("path"): p for p in ET.parse(ROOT / "floral.xml").getroot().findall("project")}
        for path in ["device/google/coral", "vendor/google/coral", "vendor/hecker/floral/motionsense",
                     "vendor/hecker/floral/faceid"]:
            project = projects[path]
            sparse = ["Android.bp", "proprietary/vendor/firmware/faceauth_config.yaml",
                      "proprietary/vendor/firmware/faceauth_v1.mdt"] if path == "vendor/google/coral" else None
            checkout(rom, path, project.get("name"), project.get("revision"), sparse)
        for path, item in lock["pixelos_inputs"].items():
            checkout(rom, path, item["repository"], item["revision"], item["files"])
        reference = lock["pixelos_manifest"]
        checkout(rom, "out/floral-manifest-reference", reference["repository"],
                 reference["revision"], ["snippets/lineage.xml"])
    check_namespace_setup(rom)
    references = rom / "out/floral-framework-reference"
    references.mkdir(parents=True, exist_ok=True)
    java_root = rom / "frameworks/base/services/core/java/com/android/server/biometrics/sensors/face"
    for name, directory in [("HidlToAidlSessionAdapter.java", "hidl"),
                            ("FaceRevokeChallengeClient.java", "aidl"),
                            ("FaceEnrollClient.java", "aidl"),
                            ("AidlConversionUtils.java", "aidl")]:
        content = (java_root / directory / name).read_bytes()
        if name == "HidlToAidlSessionAdapter.java" and b"onChallengeRevoked(challenge)" in content:
            backup = list((rom / "out/face-framework-patches").glob("*.java.original"))
            require(len(backup) == 1, "Original framework reference is ambiguous")
            content = backup[0].read_bytes()
        (references / name).write_bytes(content)
    prepare(rom, offline=not fetch)
    first = profiles(rom)
    prepare(rom, offline=True)
    require(profiles(rom) == first, "Repeated setup changed generated outputs")
    check_product_make(rom)
    motion = rom / "vendor/hecker/floral/motionsense"
    face = rom / "vendor/hecker/floral/faceid"
    allowlist = ET.parse(motion / "overlay/res/values/config.xml").getroot().find("string-array")
    values = [node.text for node in allowlist]
    active = rom / "vendor/lineage/overlay/common/frameworks/base/packages/SystemUI/res/values/config.xml"
    original = ET.parse(active).getroot().find("string-array[@name='config_pluginAllowlist']")
    require({node.text for node in original} <= set(values), "PixelOS plugin allowlist entries were lost")
    require(values.count("com.google.oslo/com.google.oslo.OsloOverlay") == 1, "Duplicate Oslo overlay component")
    sensor_profile = json.loads((face / "generated/profile.json").read_text())
    require(sensor_profile["sensors"] == ["0:8:15"], "Coral's hardware Face sensor was changed")
    require(sensor_profile["add_vintf"], "Face VINTF provider is not selected")
    framework = rom / "frameworks/base/services/core/java/com/android/server/biometrics/sensors/face/hidl/HidlToAidlSessionAdapter.java"
    require("onChallengeRevoked(challenge)" in framework.read_text(), "Framework fix was not applied")
    # A changed active ROM overlay must invalidate build-time verification.
    saved = active.read_bytes()
    active.write_bytes(saved + b"\n<!-- smoke: source changed after preparation -->\n")
    check = subprocess.run([sys.executable, str(motion / "tools/verify_ready.py")], cwd=rom,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    require(check.returncode != 0, "Stale generated setup was accepted")
    active.write_bytes(saved)
    subprocess.run([sys.executable, str(motion / "tools/verify_ready.py")], cwd=rom, check=True)
    java_arguments = [] if shutil.which("javac") and shutil.which("java") else ["--python-only"]
    if java_arguments:
        print("Java regression execution unavailable on this host; CI runs it with Temurin 17.")
    subprocess.run([sys.executable, str(face / "tests/check_framework_fixes.py"),
                    "--reference-dir", str(references), *java_arguments], cwd=rom, check=True)
    print("PASS: real PixelOS framework patch, immutable native/APK inputs, setup idempotence,")
    print("allowlist preservation, Coral hardware Face sensor, and stale-input rejection.")
    print("This is a source/setup test. It does not compile or boot Android.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--existing-root", type=Path, help="Test an already staged root without network cloning")
    args = parser.parse_args()
    if args.existing_root:
        test(args.existing_root.resolve(), fetch=False)
    else:
        with tempfile.TemporaryDirectory(prefix="pixelos-floral-") as folder:
            test(Path(folder))


if __name__ == "__main__":
    main()

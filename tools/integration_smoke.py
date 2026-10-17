#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise real PixelOS/plugin setup using small, pinned source checkouts."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from prepare import prepare
from validate import ROOT, FACE_REPLACEMENTS, camera_prebuilt, init_installers, manifest, require, replaced_vendor_installers
from camera_install import SOURCE as CAMERA_SOURCE, SERVICE as CAMERA_SERVICE
from check_qcom_namespaces import check as check_namespaces, namespace_links
from recover_caf_namespaces import inventory as caf_inventory, apply as recover_caf, namespace_blocks


def git(*args, cwd=None):
    subprocess.run(["git", *map(str, args)], cwd=cwd, check=True)


def checkout(rom, path, repository, revision, files=None):
    destination = rom / path
    destination.mkdir(parents=True)
    git("init", "--quiet", destination)
    remote = repository if repository.startswith("https://") else "https://github.com/" + repository + ".git"
    git("remote", "add", "origin", remote, cwd=destination)
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
        "include vendor/google/coral/coral-vendor.mk",
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
    require({"libbase-v33", "libcrypto-v33", "libstagefright_foundation-v33"} <= set(packages) and
            not {"FloralFaceIDV33Base", "FloralFaceIDV33Crypto", "FloralFaceIDV33Foundation"} & set(packages),
            "Face ID must select the shared multilib v33 providers")
    require("keep:vendor/etc/keep" in copies and face +
            "/configs/android.hardware.biometrics.face.xml:vendor/etc/permissions/android.hardware.biometrics.face.xml"
            in copies, "Plugin permission copy or unrelated product copy was lost")
    require(face + "/sepolicy/vendor" in values.get("MAKE_POLICY", "").split(),
            "Face ID vendor policy is missing")
    owners = init_installers(rom, copies)
    camera_destination = "vendor/etc/init/" + CAMERA_SERVICE + ".rc"
    require(owners.get(camera_destination) == {
            "Soong:" + str(Path(CAMERA_SOURCE).parent / (CAMERA_SERVICE + ".rc"))},
            "The camera init script must have its single Soong installer")
    # Restore the actual Make entry from the failed build: the source binary's
    # no_full_install flag must not hide this duplicate from the audit.
    duplicate = ("vendor/google/coral/proprietary/vendor/etc/init/" + CAMERA_SERVICE +
                 ".rc:" + camera_destination)
    try:
        init_installers(rom, copies + [duplicate])
    except ValueError as error:
        require("Two init installers for " + camera_destination in str(error),
                "Init regression failed for an unrelated reason: " + str(error))
    else:
        raise ValueError("The camera init PRODUCT_COPY_FILES regression was accepted")
    print("PASS: real prepared product and board entries parse before Android's my-dir helper.")
    print("PASS: init_rc and resolved vendor/product copies have one installer per path;")
    print("the removed camera init Make entry reproduces and rejects the duplicate.")


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
    print("PASS: " + str(count) + " chipset namespace exports and globally visible shared audio defaults")
    print("from pinned PixelOS/common sources.")


def check_plugin_blueprints(rom):
    # Regress the actual Soong error: a namespace after a named license module.
    # Comments (including SPDX headers) may precede the namespace declaration.
    for name in ("faceid", "motionsense"):
        path = rom / "vendor/hecker/floral" / name / "Android.bp"
        source = path.read_text()
        modules = re.findall(r"(?m)^([A-Za-z_]\w*)\s*\{", source)
        require(modules and modules[0] == "soong_namespace" and
                modules.count("soong_namespace") == 1,
                str(path) + ": soong_namespace must be the first and only namespace module")
        require("package" in modules and "license" in modules,
                str(path) + ": plugin package/license metadata was lost")
    print("PASS: both generated plugin namespaces precede their license modules.")


def check_face_library_ownership(rom):
    face = rom / "vendor/hecker/floral/faceid"
    bp = (face / "Android.bp").read_text()
    base = (rom / "vendor/google/coral/Android.bp").read_text()
    for module, original in FACE_REPLACEMENTS.items():
        block = re.search(r'(?ms)^cc_prebuilt_(?:binary|library_shared)\s*\{\s*name:\s*"' +
                          re.escape(module) + r'",.*?^\}', bp)
        require(block is not None and 'overrides: ["' + original + '"]' in block.group(),
                module + ": missing override for a transitively installed stock library")
        require('name: "' + original + '"' in base,
                "Pinned vendor fixture no longer covers the replaced library: " + original)
    profile = json.loads((face / "generated/profile.json").read_text())
    expected = {"FloralFaceIDV33Base": "libbase-v33", "FloralFaceIDV33Crypto": "libcrypto-v33",
                "FloralFaceIDV33Foundation": "libstagefright_foundation-v33"}
    require(profile["compat_modules"] == expected and all(
            'name: "' + alias + '"' not in bp for alias in expected),
            "Face ID retained a second owner for an existing v33 library")
    require('"libstagefright_foundation-v33"' in (face / "native/camera/Android.bp").read_text(),
            "Camera compatibility library does not use the shared foundation provider")
    print("PASS: all eight Face ID replacements have packaging overrides;")
    print("the identical v33 base, crypto and foundation providers retain both architectures.")


def check_native_installs(rom):
    # Reproduce the unconditional full-install export that happens before
    # Make's product/override filtering. Check destinations, not module names.
    destinations = {}
    selected = {CAMERA_SERVICE: "vendor/bin/hw/" + CAMERA_SERVICE,
                CAMERA_SERVICE + "-coral": "vendor/bin/hw/" + CAMERA_SERVICE,
                "hardware_camera_vintf": "vendor/etc/vintf/manifest/" + CAMERA_SERVICE + ".xml",
                CAMERA_SERVICE + ".xml": "vendor/etc/vintf/manifest/" + CAMERA_SERVICE + ".xml"}
    for alias, original in FACE_REPLACEMENTS.items():
        destination = ("vendor/bin/hw/" + original if "service" in original else
                       "vendor/lib64/" + original + ".so")
        selected[alias] = selected[original] = destination
    for alias, name in {"Base": "libbase-v33", "Crypto": "libcrypto-v33",
                        "Foundation": "libstagefright_foundation-v33"}.items():
        selected["FloralFaceIDV33" + alias] = selected[name] = "vendor/lib64/" + name + ".so"
    seen = set()
    for relative in ("vendor/google/coral/Android.bp", CAMERA_SOURCE,
                     "vendor/hecker/floral/faceid/Android.bp", "hardware/lineage/compat/Android.bp"):
        text = (rom / relative).read_text()
        for block in re.findall(r'(?ms)^[A-Za-z_]\w*\s*\{.*?^\}', text):
            name = re.search(r'(?m)^    name:\s*"([^"]+)"', block)
            if not name or name[1] not in selected:
                continue
            module = name[1]
            seen.add(module)
            if re.search(r'(?m)^    no_full_install: true,', block):
                continue
            destination = selected[module]
            require(destination not in destinations,
                    "Two full installers for " + destination + ": " + destinations.get(destination, "") + " and " + module)
            destinations[destination] = module
    require(set(selected) - {"FloralFaceIDV33Base", "FloralFaceIDV33Crypto", "FloralFaceIDV33Foundation"} <= seen,
            "Native installation fixture is missing a provider")
    require(len(destinations) == 13, "Unexpected native install destination count")
    # A product override alone must not pass this regression check.
    vendor = rom / "vendor/google/coral/Android.bp"
    original = vendor.read_bytes()
    try:
        for name in FACE_REPLACEMENTS.values():
            pattern = (rb'(?ms)(^cc_prebuilt_(?:binary|library_shared)\s*\{\s*name:\s*"' +
                       re.escape(name.encode()) + rb'",\s*)no_full_install: true,')
            broken, count = re.subn(pattern, rb'\g<1>no_full_install: false,', original)
            require(count == 1, "Missing real replaced-provider fixture: " + name)
            vendor.write_bytes(broken)
            try:
                replaced_vendor_installers(rom)
            except ValueError:
                pass
            else:
                raise ValueError("A restored duplicate install rule was accepted: " + name)
    finally:
        vendor.write_bytes(original)
    print("PASS: 13 native destinations have one full installer; all eight restored duplicates are rejected.")


def check_dolby_sysconfig(rom):
    # Soong namespaces are exported into Make's shared ETC module registry.
    # Check the installed paths too: renaming a module alone can leave a
    # second conflict when both sysconfig files are packaged.
    names, destinations = set(), set()
    for directory in (rom / "packages/apps/DolbyAtmos",
                      rom / "vendor/lunaris/dolby/LunarisDolby"):
        bp = (directory / "Android.bp").read_text()
        declared = set()
        for block in re.findall(r'(?ms)^prebuilt_etc\s*\{.*?^\}', bp):
            values = dict(re.findall(r'(\w+):\s*"([^"]+)"', block))
            name = values["name"]
            require(name not in names, "Dolby apps export the same Make ETC module: " + name)
            names.add(name)
            declared.add(name)
            require("system_ext_specific: true" in block and values["sub_dir"] == "sysconfig",
                    "Review the changed Dolby sysconfig partition or directory")
            destination = values.get("filename", name)
            require(destination not in destinations, "Dolby sysconfig destination collision: " + destination)
            destinations.add(destination)
            ET.parse(directory / values["src"])
        required = re.search(r'required:\s*\[([^\]]+)\]', bp)
        require(required is not None and set(re.findall(r'"([^"]+)"', required.group(1))) <= declared,
                "Dolby app required files do not reference its own sysconfig modules")
    print("PASS: both Dolby apps have distinct Make ETC modules and sysconfig filenames.")


def check_boot_capture(rom):
    device = rom / "device/google/coral"
    service = (device / "boot_diagnostics/boot_capture.rc").read_text()
    require("on early-fs && property:ro.debuggable=1" in service and
            "seclabel u:r:su:s0" in service and "    disabled" in service and
            "    oneshot" in service, "Review the boot capture's startup/domain guards")
    fstab = (device / "init/fstab.hardware").read_text()
    require(re.search(r'(?m)^\S+\s+/metadata\s+ext4\s+\S+\s+\S*first_stage_mount', fstab),
            "Boot capture requires Coral's first-stage Metadata mount")
    init = (rom / "system/core/rootdir/init.rc").read_text()
    phase = re.search(r'(?ms)^on late-init\n(.*?)(?=^on |\Z)', init)
    require(phase is not None and phase[1].index("trigger early-fs") <
            phase[1].index("trigger late-fs"), "Android's filesystem phase order changed")
    policy = rom / "system/sepolicy/private"
    require("allow init su:process transition;" in (policy / "init.te").read_text() and
            "permissive su;" in (policy / "su.te").read_text(),
            "Existing AOSP debug service permission/domain changed; review before building")
    subprocess.run(["sh", "-n", str(device / "boot_diagnostics/boot_capture.sh")], check=True)
    subprocess.run([sys.executable, str(ROOT / "tests/check_boot_capture.py"),
                    "--device-root", str(device)], check=True)
    print("PASS: early Metadata logging uses the existing AOSP debug domain;")
    print("runtime, recovery, storage bounds and user-build exclusion checks passed.")


def check_caf_scope_recovery(rom):
    relative = "hardware/qcom-caf/sm8750/audio/graphservices"
    project = rom / relative
    caf_manifest = ET.Element("manifest")
    ET.SubElement(caf_manifest, "project", path=relative)
    expected = {}
    for filename in ("gsl/Android.bp", "gpr/Android.bp"):
        path = project / filename
        original = path.read_bytes()
        require(not namespace_blocks(original), "Pinned graphservice has an unexpected upstream namespace")
        kept = original + b"\n// smoke: unrelated local edit retained\n"
        path.write_bytes(b"soong_namespace {}\n" + kept)
        expected[filename] = kept
    git("add", "--", "gsl/Android.bp", cwd=project)
    path = project / "gsl/Android.bp"
    path.write_bytes(path.read_bytes() + b"// smoke: unrelated working edit retained\n")
    expected["gsl/Android.bp"] += b"// smoke: unrelated working edit retained\n"
    actions = caf_inventory(rom, caf_manifest)
    require(len(actions) == 2, "Both real graphservice scope additions must be detected")
    with tempfile.TemporaryDirectory(prefix="caf-scope-backup-") as folder:
        recover_caf(rom, actions, Path(folder))
        for filename, content in expected.items():
            require((project / filename).read_bytes() == content,
                    "CAF recovery changed a module definition or an unrelated local edit")
        index = subprocess.check_output(["git", "-C", str(project), "show", ":gsl/Android.bp"])
        require(index + b"// smoke: unrelated working edit retained\n" == expected["gsl/Android.bp"],
                "CAF recovery did not preserve unrelated staged changes")
        require(not caf_inventory(rom, caf_manifest), "CAF scope recovery is not idempotent")
    print("PASS: real pinned SM8750 graphservice namespaces recover without losing module or index edits.")


def test(rom, fetch=True):
    manifest()
    lock = json.loads((ROOT / "source-revisions.json").read_text())
    if fetch:
        projects = {p.get("path"): p for p in ET.parse(ROOT / "floral.xml").getroot().findall("project")}
        for path in ["device/google/coral", "vendor/google/coral", "vendor/hecker/floral/motionsense",
                     "vendor/hecker/floral/faceid"]:
            project = projects[path]
            sparse = ["Android.bp", "coral-vendor.mk",
                      "proprietary/vendor/etc/init/android.hardware.camera.provider@2.7-service-google.rc",
                      "proprietary/vendor/etc/vintf/manifest/android.hardware.camera.provider@2.7-service-google.xml",
                      "proprietary/vendor/firmware/faceauth_config.yaml",
                      "proprietary/vendor/firmware/faceauth_v1.mdt"] if path == "vendor/google/coral" else None
            checkout(rom, path, project.get("name"), project.get("revision"), sparse)
        dolby = projects["vendor/lunaris/dolby"]
        checkout(rom, "vendor/lunaris/dolby", dolby.get("name"), dolby.get("revision"),
                 ["LunarisDolby/Android.bp", "LunarisDolby/preinstalled-packages-platform-dolby.xml",
                  "LunarisDolby/privapp-permissions-dolby.xml"])
        for path, item in lock["pixelos_inputs"].items():
            checkout(rom, path, item["repository"], item["revision"], item["files"])
        reference = lock["pixelos_manifest"]
        checkout(rom, "out/floral-manifest-reference", reference["repository"],
                 reference["revision"], ["snippets/lineage.xml"])
    camera_prebuilt(rom)
    check_boot_capture(rom)
    check_dolby_sysconfig(rom)
    check_namespace_setup(rom)
    check_caf_scope_recovery(rom)
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
    check_plugin_blueprints(rom)
    check_face_library_ownership(rom)
    check_native_installs(rom)
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

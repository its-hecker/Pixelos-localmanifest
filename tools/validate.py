#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the manifest, Floral product wiring and resolved firmware before building."""

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

from camera_install import configure as configure_camera, SOURCE as CAMERA_SOURCE, SERVICE as CAMERA_SERVICE


ROOT = Path(__file__).resolve().parents[1]
PROJECTS = {
    "device/google/coral": "its-hecker/pixelos_android_device_google_coral",
    "vendor/google/coral": "its-hecker/pixelos_proprietary_vendor_google_coral",
    "kernel/google/msm-4.14": "its-hecker/infinity_cnb_kernel_google_msm-4.14",
    "packages/apps/ElmyraService": "LineageOS/android_packages_apps_ElmyraService",
    "vendor/lunaris/dolby": "its-hecker/vendor_lunaris_dolby",
    "vendor/hecker/floral/motionsense": "its-hecker/floral-motionsense-plugin",
    "vendor/hecker/floral/faceid": "its-hecker/floral-3D-faceid-plugin",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def manifest(root=ROOT):
    xml = ET.parse(root / "floral.xml").getroot()
    projects = xml.findall("project")
    require(len(projects) == len(PROJECTS), "Unexpected project count")
    require(len({p.get('path') for p in projects}) == len(projects), "Duplicate project path")
    removals = {p.get("path") for p in xml.findall("remove-project") if p.get("optional") == "true"}
    require(removals == set(PROJECTS), "Every replacement needs an optional path removal")
    for project in projects:
        path = project.get("path")
        require(project.get("name") == PROJECTS[path], "Incorrect repository for " + path)
        revision = project.get("revision", "")
        require(revision and revision != "cnb", "Missing or obsolete branch: " + path)
        if path not in ["device/google/coral", "vendor/google/coral"]:
            require(re.fullmatch(r"[0-9a-f]{40}", revision), "Unpinned dependency: " + path)
            require(project.get("upstream", "").startswith("refs/heads/"), "Missing upstream ref")
        if path.startswith("kernel/"):
            require(project.get("sync-s") == "true", "KernelSU submodule sync is disabled")
            require(project.get("upstream") == "refs/heads/cnb-Latest-stable", "Wrong CNB kernel branch")
    print("Local manifest paths, dependency pins and kernel submodule sync: PASS")


def camera_prebuilt(rom):
    # Pairing this V1 prebuilt with the newer AOSP service makes Soong traverse
    # both camera metadata versions, even when prefer: true selects the blob.
    stock = "android.hardware.camera.provider@2.7-service-google"
    module = stock + "-coral"
    device = rom / "device/google/coral"
    vendor = rom / "vendor/google/coral"
    bp = (vendor / "Android.bp").read_text()
    matches = re.findall(r'(?ms)^cc_prebuilt_binary\s*\{\s*name:\s*"' +
                         re.escape(module) + r'",.*?^\}', bp)
    require(len(matches) == 1, "Missing distinct Coral camera prebuilt module; sync device/vendor sources")
    block = matches[0]
    require('overrides: ["' + stock + '"]' in block and
            'no_full_install: true' not in block,
            "Sync vendor/google/coral: the stock camera must own its full install rules")
    require('stem: "' + stock + '"' in block and
            '"proprietary/vendor/bin/hw/' + stock + '"' in block and
            'relative_install_path: "hw"' in block and 'soc_specific: true' in block,
            "Coral camera prebuilt does not install at its stock vendor service path")
    aidl = set(re.findall(r'"(android\.hardware\.camera\.[^"/]+-V\d+-ndk)"', block))
    require(aidl == {"android.hardware.camera.device-V1-ndk",
                     "android.hardware.camera.common-V1-ndk",
                     "android.hardware.camera.provider-V1-ndk"},
            "Stock Coral camera prebuilt must retain its AIDL V1 dependencies")
    for path in (device / "device-common.mk", vendor / "coral-vendor.mk"):
        text = path.read_text()
        require(re.search(r'(?m)^\s*' + re.escape(module) + r'\s*(?:\\)?\s*$', text) and
                not re.search(r'(?m)^\s*' + re.escape(stock) + r'\s*(?:\\)?\s*$', text),
                str(path) + ": select only the distinct Coral camera prebuilt")
    entry = "vendor/bin/hw/" + stock + ";MODULE_SUFFIX=-coral"
    require(entry in (device / "coral/proprietary-files-vendor.txt").read_text().splitlines(),
            "Camera extraction would recreate the AOSP/prebuilt module collision")
    init = vendor / "proprietary/vendor/etc/init" / (stock + ".rc")
    require("/vendor/bin/hw/" + stock in init.read_text(), "Camera init executable path differs")
    camera_init(rom)
    declaration = vendor / "proprietary/vendor/etc/vintf/manifest" / (stock + ".xml")
    hal = ET.parse(declaration).getroot().find("hal")
    require(hal is not None and hal.get("format") == "aidl" and
            hal.findtext("name") == "android.hardware.camera.provider" and
            hal.findtext("version") == "1", "Stock camera VINTF provider changed")
    print("Coral camera prebuilt identity, stock service path and AIDL V1 packaging: PASS")


def camera_init(rom):
    # Attach startup to the selected prebuilt, so override/package filtering
    # cannot drop the only init script with the unused source service.
    filename = CAMERA_SERVICE + ".rc"
    source_bp = rom / CAMERA_SOURCE
    block = re.search(r'(?ms)^cc_binary\s*\{\s*name:\s*"' +
                      re.escape(CAMERA_SERVICE) + r'",.*?^\}', source_bp.read_text())
    require(block is not None and re.search(r'init_rc:\s*\[(?:\s*"' +
            re.escape(filename) + r'"\s*,?)?\s*\]', block.group()),
            "Review the AOSP camera init installer before building Coral")
    vendor_bp = (rom / "vendor/google/coral/Android.bp").read_text()
    selected = re.search(r'(?ms)^cc_prebuilt_binary\s*\{\s*name:\s*"' +
                         re.escape(CAMERA_SERVICE + "-coral") + r'",.*?^\}', vendor_bp)
    relative = "proprietary/vendor/etc/init/" + filename
    require(selected is not None and re.search(r'init_rc:\s*\[\s*"' +
            re.escape(relative) + r'"\s*,?\s*\]', selected.group()),
            "Sync vendor/google/coral: the selected camera prebuilt must install its init script")
    stock = rom / "vendor/google/coral/proprietary/vendor/etc/init" / filename
    require((source_bp.parent / filename).read_bytes() == stock.read_bytes(),
            "AOSP camera init differs from Coral's stock script; review startup configuration")
    copy_prefix = "vendor/google/coral/proprietary/vendor/etc/init/" + filename + ":"
    make = (rom / "vendor/google/coral/coral-vendor.mk").read_text()
    require(not any(line.lstrip().startswith(copy_prefix) for line in make.splitlines()),
            "Sync vendor/google/coral: remove the duplicate camera init PRODUCT_COPY_FILES entry")


def init_installers(rom, copies):
    """Audit init_rc exports independently of binary full-install ownership."""
    owners = {}

    def add(destination, owner):
        owners.setdefault(destination, set()).add(owner)

    for relative in ("vendor/google/coral/Android.bp", CAMERA_SOURCE,
                     "vendor/hecker/floral/faceid/Android.bp"):
        path = rom / relative
        for block in re.findall(r'(?ms)^cc_(?:prebuilt_)?binary\s*\{.*?^\}', path.read_text()):
            # Identical source/destination pairs shared by variants or modules
            # are deduplicated by Soong. no_full_install does not gate init_rc.
            for value in re.findall(r'(?ms)^    init_rc:\s*\[([^\]]*)\]', block):
                for filename in re.findall(r'"([^"]+)"', value):
                    destination = "vendor/etc/init/" + Path(filename).name
                    add(destination, "Soong:" + (path.parent / filename).relative_to(rom).as_posix())
    for entry in copies:
        fields = entry.split(":")
        if len(fields) >= 2 and fields[1].startswith("vendor/etc/init/"):
            add(fields[1], "PRODUCT_COPY_FILES:" + fields[0])
    for destination, providers in owners.items():
        require(len(providers) == 1,
                "Two init installers for " + destination + ": " + ", ".join(sorted(providers)))
    return owners


FACE_REPLACEMENTS = {
    "FloralFaceIDCitadelImpl": "android.hardware.keymaster@4.1-impl.nos",
    "FloralFaceIDCalibrationProto": "libface-calibration-proto",
    "FloralFaceIDEnrollmentProto": "libface-enroll-proto",
    "FloralFaceIDAuthUtil": "libfaceauth-util",
    "FloralFaceIDAirbrushClient": "libairbrush-pixel",
    "FloralFaceIDCitadelKeymaster": "android.hardware.keymaster@4.1-service.citadel",
    "FloralFaceIDNeuralNetworks": "android.hardware.neuralnetworks@1.2-service-noronha",
    "FloralFaceIDAirbrushService": "vendor.google.airbrush@1.0-service",
}


def replaced_vendor_installers(rom):
    source = (rom / "vendor/google/coral/Android.bp").read_text()
    for name in FACE_REPLACEMENTS.values():
        blocks = re.findall(r'(?ms)^cc_prebuilt_(?:binary|library_shared)\s*\{\s*name:\s*"' +
                            re.escape(name) + r'",.*?^\}', source)
        require(len(blocks) == 1 and re.search(r'(?m)^    no_full_install: true,', blocks[0]),
                "Sync vendor/google/coral: suppress the replaced stock install rule for " + name)


def motion_permissions(rom):
    plugin = rom / "vendor/hecker/floral/motionsense"
    bp = (plugin / "Android.bp.in").read_text()
    blocks = re.findall(r'(?ms)^prebuilt_etc\s*\{\s*name:\s*"FloralMotionSensePrivappPermissions",.*?^\}', bp)
    required = ['src: "configs/privapp-permissions-floral-motionsense.xml"',
                'filename: "privapp-permissions-floral-motionsense.xml"',
                'sub_dir: "permissions"', 'system_ext_specific: true']
    require(len(blocks) == 1 and all(value in blocks[0] for value in required),
            "Motion Sense plugin permission XML must install once on system_ext")
    manifest = ET.parse(plugin / "settings/AndroidManifest.xml").getroot()
    allowlist = ET.parse(plugin / "configs/privapp-permissions-floral-motionsense.xml").getroot()
    package = manifest.get("package")
    entries = allowlist.findall("privapp-permissions")
    require(len(entries) == 1 and package == "org.hecker.floral.motionsense" and
            entries[0].get("package") == package,
            "Motion Sense permission allowlist does not match the installed package")
    granted = {node.get("name") for node in entries[0].findall("permission")}
    require(granted == {"android.permission.WRITE_SECURE_SETTINGS"},
            "Motion Sense needs exactly its WRITE_SECURE_SETTINGS privileged allowlist entry")
    settings = (plugin / "settings/Android.bp.in").read_text()
    require("system_ext_specific: true" in settings and "privileged: true" in settings and
            'required: ["FloralMotionSensePrivappPermissions"]' in settings,
            "Review Motion Sense app partition before installing its permission allowlist")


def hardware_setup(rom):
    device = rom / "device/google/coral"
    product = (device / "custom_coral.mk").read_text()
    flag = "PRODUCT_NO_CAMERA := true"
    require(flag in product and product.index(flag) < product.index(
            "$(call inherit-product, vendor/custom/config/common_full_phone.mk)"),
            "Disable the inherited Aperture package before PixelOS common inheritance")
    require("$(call inherit-product, device/google/coral/camera/camera.mk)" in product,
            "Google Camera product configuration is missing")
    camera = (device / "camera/Android.bp").read_text()
    sets = re.findall(r'(?ms)^android_app_set\s*\{\s*name:\s*"GoogleCameraCoral",.*?^\}', camera)
    require(len(sets) == 1, "GoogleCameraCoral must have one APK-set module")
    overrides = re.findall(r'(?s)\boverrides:\s*\[([^\]]*)\]', sets[0])
    require(len(overrides) == 1 and set(re.findall(r'"([^"]+)"', overrides[0])) == {"Aperture", "Camera2"},
            "GoogleCameraCoral must replace both Aperture and AOSP Camera2")
    policy = (device / "sepolicy/vendor/google/vendor_init.te").read_text()
    require("set_prop(vendor_init, vendor_aware_available_prop)" in policy,
            "Motion Sense capability cannot be published by vendor_init")
    settings = ET.parse(rom / "vendor/hecker/floral/motionsense/settings/AndroidManifest.xml").getroot()
    android = "{http://schemas.android.com/apk/res/android}"
    names = {node.get(android + "name") for node in settings.findall(".//action")}
    categories = {node.get(android + "name") for node in settings.findall(".//category")}
    require("com.android.settings.action.IA_SETTINGS" in names and
            "android.intent.category.LAUNCHER" not in categories,
            "Motion Sense must retain its Settings entry without a launcher duplicate")
    oslo_country_override = re.findall(r"(?m)^\s*pixel\.oslo\.allowed_override\s*=\s*(\S+)\s*$",
                                      (device / "product.prop").read_text())
    require(oslo_country_override == ["1"],
            "Motion Sense needs exactly one pixel.oslo.allowed_override=1 product property")


def source(rom):
    required = [
        "device/google/coral/custom_coral.mk", "device/google/coral/BoardConfig-common.mk",
        "vendor/google/coral/Android.mk", "vendor/google/coral/Android.bp",
        "vendor/google/coral/proprietary/vendor/dsp/sdsp/oslo.so",
        "vendor/google/coral/proprietary/vendor/dsp/sdsp/oslo.napp_header",
        "vendor/pixel/gms/products/gms.mk", "vendor/custom/config/common_full_phone.mk",
        "kernel/google/msm-4.14/arch/arm64/configs/floral_defconfig",
        "kernel/google/msm-4.14/KernelSU/kernel/Kconfig",
        "packages/apps/ElmyraService/Android.bp", "vendor/lunaris/dolby/BoardConfigDolby.mk",
    ]
    for path in required:
        require((rom / path).is_file(), "Missing build dependency: " + path)
    kernel = rom / "kernel/google/msm-4.14"
    expected_kernel = ET.parse(ROOT / "floral.xml").getroot().find("project[@path='kernel/google/msm-4.14']").get("revision")
    kernel_revision = subprocess.check_output(["git", "-C", str(kernel), "rev-parse", "HEAD"], text=True).strip()
    require(kernel_revision == expected_kernel, "Kernel checkout does not match the pinned CNB source")
    gitlink = subprocess.check_output(["git", "-C", str(kernel), "ls-tree", "HEAD", "KernelSU"], text=True).split()
    submodule_revision = subprocess.check_output(["git", "-C", str(kernel / "KernelSU"), "rev-parse", "HEAD"], text=True).strip()
    require(len(gitlink) == 4 and gitlink[0] == "160000" and gitlink[2] == submodule_revision,
            "KernelSU checkout differs from the kernel's gitlink; run repo sync")
    device = rom / "device/google/coral"
    camera_prebuilt(rom)
    replaced_vendor_installers(rom)
    motion_permissions(rom)
    hardware_setup(rom)
    face_check = subprocess.run([sys.executable, str(rom / "vendor/hecker/floral/faceid/tools/apply_framework_fixes.py"),
                                 "--rom-root", str(rom), "--check"], text=True, capture_output=True)
    require(face_check.returncode == 0 and "already applied" in face_check.stdout,
            "Run build.sh preparation to apply all HIDL Face startup/enrollment fixes: " +
            face_check.stdout + face_check.stderr)
    require(configure_camera(rom) == "already configured",
            "Run build.sh preparation to select the stock camera install rules")
    product = (device / "custom_coral.mk").read_text()
    common = "$(call inherit-product, vendor/custom/config/common_full_phone.mk)"
    vendor = "$(call inherit-product, vendor/google/coral/coral-vendor.mk)"
    require(product.index("TARGET_FACE_UNLOCK_SUPPORTED := false") < product.index(common),
            "PixelOS software face provider is not disabled before common inheritance")
    require("PRODUCT_NAME := custom_coral" in product, "Wrong PixelOS product name")
    require("vendor/infinity" not in product, "Infinity product inherited")
    for feature, name, board in [("motionsense", "motionsense.mk", "BoardConfigMotionSense.mk"),
                                 ("faceid", "faceid.mk", "BoardConfigFaceID.mk")]:
        relative = "vendor/hecker/floral/" + feature
        include = "$(call inherit-product, " + relative + "/" + name + ")"
        require(product.index(include) > product.index(vendor), "Plugin inheritance precedes vendor")
        require("include " + relative + "/" + board in (device / "BoardConfig-common.mk").read_text(),
                "Plugin board policy is not included")
        subprocess.run([sys.executable, str(rom / relative / "tools/verify_ready.py")],
                       cwd=rom, check=True)
    require(not (device / "faceunlock").exists(), "Integrated Face compatibility source was copied")
    require(not (device / "parts/src/org/lineageos/settings/motionsense").exists(),
            "Duplicate integrated Motion Sense settings were copied")
    parts = (device / "parts/Android.bp").read_text()
    require("org.lineageos.settings.resources" not in parts, "GoogleParts still needs disabled Lineage SDK")
    require("ro.hwui.render_ahead=5" in (device / "system.prop").read_text(), "HWUI property fix missing")
    require("ro.hwui.render_ahead" not in (device / "vendor.prop").read_text(), "HWUI property is in vendor")
    require("domain, coredomain" in (device / "sepolicy/system_ext/public/hardware_info_app.te").read_text(),
            "HardwareInfo platform policy fix missing")
    manifest_xml = ET.parse(device / "manifest.xml").getroot()
    registrations = [hal for hal in manifest_xml.findall("hal")
                     if hal.findtext("name") == "android.hardware.biometrics.face"]
    require(not registrations, "Base device manifest duplicates the plugin Face provider")
    print("PixelOS product, standalone plugin wiring and general device fixes: PASS")
    radio_make = (rom / "vendor/google/coral/Android.mk").read_text()
    images = re.findall(r"add-radio-file-sha1-checked,(radio/[^,]+),([0-9a-f]{40})", radio_make)
    require(len(images) == 11, "Unexpected stock Coral radio image list; review the changed base")
    for relative, expected in images:
        path = rom / "vendor/google/coral" / relative
        digest = hashlib.sha1()
        with path.open("rb") as handle:
            prefix = handle.read(128)
            require(not prefix.startswith(b"version https://git-lfs.github.com/spec/v1"),
                    "Git LFS pointer is unresolved: " + relative + "; run git lfs pull")
            digest.update(prefix)
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        require(digest.hexdigest() == expected, "Radio image SHA-1 differs: " + relative)
    print("All 11 stock radio images resolved and checked against Android.mk: PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom-root", type=Path)
    args = parser.parse_args()
    try:
        manifest()
        if args.rom_root:
            source(args.rom_root.resolve())
    except (OSError, ValueError, KeyError, ET.ParseError, subprocess.CalledProcessError) as error:
        print("Source validation:", error, file=sys.stderr)
        return 1
    print("These checks cover source integration; a full ROM build and phone test are required.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

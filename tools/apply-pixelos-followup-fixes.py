#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Apply local PixelOS Coral camera-app and HIDL Face callback fixes.

Run from ~/pixelos with --apply. Without --apply, this only checks the sources.
Every original is backed up under out/pixelos-followup-backups before any edit.
Only reviewed source fragments are changed. No keys, APKs, kernel, firmware,
Git remotes or GitHub branches are modified.
"""
import argparse
import hashlib
import os
from pathlib import Path
import stat
import tempfile

PATCHES = [{'after': 'android_app_set {\n'
           '    name: "GoogleCameraCoral",\n'
           '    owner: "google",\n'
           '    overrides: [\n'
           '        "Aperture",\n'
           '        "Camera2",\n'
           '    ],\n'
           '    set: ":coral_google_camera_apk_set",\n'
           '    product_specific: true,\n'
           '}\n',
  'before': 'android_app_set {\n'
            '    name: "GoogleCameraCoral",\n'
            '    owner: "google",\n'
            '    set: ":coral_google_camera_apk_set",\n'
            '    product_specific: true,\n'
            '}\n',
  'path': 'device/google/coral/camera/Android.bp'},
 {'after': '\n'
           '# Use the original signed Camera package tested on Infinity-X Coral.\n'
           '$(call inherit-product, device/google/coral/camera/camera.mk)\n'
           'PRODUCT_PACKAGES := $(filter-out Aperture Camera2,$(PRODUCT_PACKAGES))\n'
           '\n'
           "# Privileged permissions must be allowlisted on the app's own partition.\n"
           'PRODUCT_COPY_FILES += \\\n',
  'before': '\n'
            '# Use the original signed Camera package tested on Infinity-X Coral.\n'
            '$(call inherit-product, device/google/coral/camera/camera.mk)\n'
            'PRODUCT_PACKAGES := $(filter-out Aperture,$(PRODUCT_PACKAGES))\n'
            '\n'
            "# Privileged permissions must be allowlisted on the app's own partition.\n"
            'PRODUCT_COPY_FILES += \\\n',
  'path': 'device/google/coral/custom_coral.mk'},
 {'after': 'source build/envsetup.sh\n'
           'breakfast coral "${PIXEL_BUILD_VARIANT:-userdebug}"\n'
           'floral_product_out="$(get_build_var PRODUCT_OUT)"\n'
           'floral_stale_camera=false\n'
           'for floral_partition in system system_ext product vendor; do\n'
           '    for floral_app_type in app priv-app; do\n'
           '        for floral_stock_camera in Aperture Camera2; do\n'
           '            if [[ -d '
           '"$floral_product_out/$floral_partition/$floral_app_type/$floral_stock_camera" ]]; '
           'then\n'
           '                floral_stale_camera=true\n'
           '            fi\n'
           '        done\n'
           '    done\n'
           'done\n'
           'if [[ "$floral_stale_camera" == true ]]; then\n'
           '    echo "Removing previous stock camera installations from build outputs '
           '(installclean)."\n'
           '    m installclean\n'
           'fi\n'
           'm -j"${PIXEL_BUILD_JOBS:-$(nproc)}" pixelos\n',
  'before': 'source build/envsetup.sh\n'
            'breakfast coral "${PIXEL_BUILD_VARIANT:-userdebug}"\n'
            'floral_product_out="$(get_build_var PRODUCT_OUT)"\n'
            'floral_stale_aperture=false\n'
            'for floral_partition in system system_ext product vendor; do\n'
            '    for floral_app_type in app priv-app; do\n'
            '        if [[ -d "$floral_product_out/$floral_partition/$floral_app_type/Aperture" '
            ']]; then\n'
            '            floral_stale_aperture=true\n'
            '        fi\n'
            '    done\n'
            'done\n'
            'if [[ "$floral_stale_aperture" == true ]]; then\n'
            '    echo "Removing the previous Aperture installation from build outputs '
            '(installclean)."\n'
            '    m installclean\n'
            'fi\n'
            'm -j"${PIXEL_BUILD_JOBS:-$(nproc)}" pixelos\n',
  'path': '.repo/local_manifests/build.sh'},
 {'after': '    if actual != expected:\n'
           '        raise ValueError("Built GoogleCameraCoral APKs differ from the tested ten-APK '
           'split package")\n'
           '    for partition in ("system", "system_ext", "product", "vendor"):\n'
           '        for name in ("Aperture", "Camera2"):\n'
           '            if any((output / partition / kind / name).exists() for kind in ("app", '
           '"priv-app")):\n'
           '                raise ValueError(f"Stale {name} remains in the built output; run m '
           'installclean and rebuild")\n'
           '\n',
  'before': '    if actual != expected:\n'
            '        raise ValueError("Built GoogleCameraCoral APKs differ from the tested ten-APK '
            'split package")\n'
            '    for partition in ("system", "system_ext", "product", "vendor"):\n'
            '        if any((output / partition / kind / "Aperture").exists() for kind in ("app", '
            '"priv-app")):\n'
            '            raise ValueError("Stale Aperture remains in the built output; run m '
            'installclean and rebuild")\n'
            '\n',
  'path': '.repo/local_manifests/tools/google_camera.py'},
 {'after': '            "Disable the inherited Aperture package before PixelOS common '
           'inheritance")\n'
           '    require("$(call inherit-product, device/google/coral/camera/camera.mk)" in '
           'product,\n'
           '            "Google Camera product configuration is missing")\n'
           '    camera = (device / "camera/Android.bp").read_text()\n'
           '    sets = '
           're.findall(r\'(?ms)^android_app_set\\s*\\{\\s*name:\\s*"GoogleCameraCoral",.*?^\\}\', '
           'camera)\n'
           '    require(len(sets) == 1, "GoogleCameraCoral must have one APK-set module")\n'
           "    overrides = re.findall(r'(?s)\\boverrides:\\s*\\[([^\\]]*)\\]', sets[0])\n"
           '    require(len(overrides) == 1 and set(re.findall(r\'"([^"]+)"\', overrides[0])) == '
           '{"Aperture", "Camera2"},\n'
           '            "GoogleCameraCoral must replace both Aperture and AOSP Camera2")\n'
           '    policy = (device / "sepolicy/vendor/google/vendor_init.te").read_text()\n'
           '    require("set_prop(vendor_init, vendor_aware_available_prop)" in policy,\n'
           '            "Motion Sense capability cannot be published by vendor_init")\n',
  'before': '            "Disable the inherited Aperture package before PixelOS common '
            'inheritance")\n'
            '    require("$(call inherit-product, device/google/coral/camera/camera.mk)" in '
            'product,\n'
            '            "Google Camera product configuration is missing")\n'
            '    policy = (device / "sepolicy/vendor/google/vendor_init.te").read_text()\n'
            '    require("set_prop(vendor_init, vendor_aware_available_prop)" in policy,\n'
            '            "Motion Sense capability cannot be published by vendor_init")\n',
  'path': '.repo/local_manifests/tools/validate.py'},
 {'after': '    private FaceUpdateActiveUserClient getFaceUpdateActiveUserClient(int userId) {\n'
           '        return new FaceUpdateActiveUserClient(getContext(), () -> {\n'
           '                    // Register the HIDL callback before the HAL activates a user.\n'
           '                    getSession();\n'
           '                    return getIBiometricsFace();\n'
           '                },\n'
           '                mUserStartedCallback, userId, TAG, getSensorProperties().sensorId,\n'
           '                BiometricLogger.ofUnknown(getContext(), getHandler()), '
           'getBiometricContext(),\n'
           '                !getFaceUtilsInstance().getBiometricsForUser(getContext(), '
           'userId).isEmpty(),\n'
           '                getAuthenticatorIds());\n'
           '    }\n',
  'before': '    private FaceUpdateActiveUserClient getFaceUpdateActiveUserClient(int userId) {\n'
            '        return new FaceUpdateActiveUserClient(getContext(), '
            'this::getIBiometricsFace,\n'
            '                mUserStartedCallback, userId, TAG, getSensorProperties().sensorId,\n'
            '                BiometricLogger.ofUnknown(getContext(), getHandler()), '
            'getBiometricContext(),\n'
            '                !getFaceUtilsInstance().getBiometricsForUser(getContext(), '
            'userId).isEmpty(),\n'
            '                getAuthenticatorIds());\n'
            '    }\n',
  'path': 'frameworks/base/services/core/java/com/android/server/biometrics/sensors/face/hidl/HidlToAidlSensorAdapter.java'}]

def prepare(root):
    if not (root / ".repo/local_manifests/build.sh").is_file():
        raise ValueError("Run from the synced PixelOS root containing .repo/local_manifests/build.sh")
    planned = {}
    for patch in PATCHES:
        path = root / patch["path"]
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("Refusing a symlinked or external source: " + patch["path"])
        if path not in planned:
            original = path.read_bytes()
            planned[path] = [original, original]
        content = planned[path][1]
        newline = "\r\n" if b"\r\n" in content else "\n"
        before = patch["before"].replace("\n", newline).encode()
        after = patch["after"].replace("\n", newline).encode()
        if content.count(after) == 1 and content.count(before) == 0:
            continue
        if content.count(before) != 1 or content.count(after) != 0:
            raise ValueError("Review changed source before applying fix: " + patch["path"])
        planned[path][1] = content.replace(before, after, 1)
    return [(path, original, updated) for path, (original, updated) in planned.items()
            if original != updated]


def apply(root, planned):
    staged = []
    try:
        for path, original, updated in planned:
            relative = path.relative_to(root)
            backup = root / "out/pixelos-followup-backups" / hashlib.sha256(original).hexdigest() / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            try:
                with backup.open("xb") as handle:
                    handle.write(original)
            except FileExistsError:
                if backup.read_bytes() != original:
                    raise ValueError("Original-source backup differs: " + str(backup))
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".pixelos-followup-", delete=False) as handle:
                temporary = Path(handle.name)
                staged.append((path, original, temporary))
                handle.write(updated)
            temporary.chmod(stat.S_IMODE(path.stat().st_mode))
        for path, original, temporary in staged:
            if path.read_bytes() != original:
                raise ValueError("Source changed during preparation: " + str(path))
        for path, original, temporary in staged:
            os.replace(temporary, path)
            print("Updated:", path.relative_to(root))
    finally:
        for path, original, temporary in staged:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom-root", type=Path, default=Path.cwd())
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = args.rom_root.resolve()
    try:
        planned = prepare(root)
        if not planned:
            print("All camera-app and Face callback fixes are already applied.")
        elif args.apply:
            apply(root, planned)
            print("Fixes applied. Originals saved under out/pixelos-followup-backups.")
            print("Run the normal userdebug build.sh to rebuild and check the camera output.")
        else:
            for path, original, updated in planned:
                print("Would update:", path.relative_to(root))
            print("Check passed; rerun with --apply to back up and apply these source changes.")
    except (OSError, ValueError) as error:
        parser.exit(1, "PixelOS follow-up fix: " + str(error) + "\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Guarded, reversible access wiring for Android 17 native App Lock."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK = Path("frameworks/base")
ANDROID = "{http://schemas.android.com/apk/res/android}"
PERMISSION = "android.permission.HECKER_SUITE_APP_LOCK"
HELPER = "services/core/java/com/android/server/pm/HeckerSuiteAppLockAccess.java"

MANIFEST_OLD = '''    <!-- Permission granted to apps holding the {@link android.app.role.RoleManager#ROLE_HOME} role
         that allows them to enable app lock. This is also granted to the recents component, which
         is typically the system launcher, to ensure a consistent user experience. App Lock is a
         feature that allows users to require authentication before opening apps.
         <p>Protection level: internal|role|recents
         @FlaggedApi(android.security.Flags.FLAG_APP_LOCK_APIS) -->'''
MANIFEST_NEW = '''    <!-- @hide Hecker's Suite may request the native authenticated App Lock setup flow.
         Package identity is additionally checked by HeckerSuiteAppLockAccess. -->
    <permission android:name="android.permission.HECKER_SUITE_APP_LOCK"
        android:protectionLevel="signature"
        android:featureFlag="android.security.app_lock_apis" />

''' + MANIFEST_OLD

AIDL_OLD = '''    @EnforcePermission("LOCK_APPS")
    @nullable PendingIntent getEnableAppLockIntentForPackage(String packageName, boolean enabled);'''
AIDL_NEW = '''    @EnforcePermission(anyOf={"LOCK_APPS", "HECKER_SUITE_APP_LOCK"})
    @nullable PendingIntent getEnableAppLockIntentForPackage(String packageName, boolean enabled);'''

PMS_OLD = '''        @android.annotation.EnforcePermission(Manifest.permission.LOCK_APPS)
        @Nullable
        public PendingIntent getEnableAppLockIntentForPackage(String pkgName, boolean enabled) {
            getEnableAppLockIntentForPackage_enforcePermission();'''
PMS_NEW = '''        @android.annotation.EnforcePermission(anyOf = {Manifest.permission.LOCK_APPS,
                "android.permission.HECKER_SUITE_APP_LOCK"})
        @Nullable
        public PendingIntent getEnableAppLockIntentForPackage(String pkgName, boolean enabled) {
            getEnableAppLockIntentForPackage_enforcePermission();
            if (mContext.checkCallingPermission(Manifest.permission.LOCK_APPS)
                    != PackageManager.PERMISSION_GRANTED
                    && !HeckerSuiteAppLockAccess.isSuite(mContext, Binder.getCallingUid())) {
                throw new SecurityException("Only the privileged Hecker Suite may use Suite access");
            }'''

COMPUTER_OLD = '''            } else if (!hasPermission(Manifest.permission.LOCK_APPS, Binder.getCallingUid())) {'''
COMPUTER_NEW = '''            } else if (!hasPermission(Manifest.permission.LOCK_APPS, Binder.getCallingUid())
                    && !HeckerSuiteAppLockAccess.isSuite(mContext, Binder.getCallingUid())) {'''

PATCHES = {
    "core/res/AndroidManifest.xml": (MANIFEST_OLD, MANIFEST_NEW),
    "core/java/android/content/pm/IPackageManager.aidl": (AIDL_OLD, AIDL_NEW),
    "services/core/java/com/android/server/pm/PackageManagerService.java": (PMS_OLD, PMS_NEW),
    "services/core/java/com/android/server/pm/ComputerEngine.java": (COMPUTER_OLD, COMPUTER_NEW),
}

CAPABILITIES = {
    "core/java/android/content/pm/PackageManager.java": [
        "getEnableAppLockIntentForPackage", "GET_APP_LOCK_INFO = 1L << 35"],
    "core/java/android/content/pm/ApplicationInfo.java": ["isAppLockSupported", "isAppLockEnabled"],
    "core/java/android/security/flags.aconfig": ['name: "app_lock_apis"', 'name: "app_lock_core"'],
    "core/java/com/android/internal/app/LockedAppActivity.java": [
        "Authenticators.BIOMETRIC_STRONG | Authenticators.DEVICE_CREDENTIAL",
        "setAppLockEnabledPackageSuccessfullyAuthenticated"],
    "core/java/com/android/internal/app/AppLockActivity.java": [
        "setPackageAppLockEnabled", "Authenticators.BIOMETRIC_STRONG"],
    "services/core/java/com/android/server/wm/ActivityStartInterceptor.java": [
        "interceptLockedByAppLockPackageIfNeeded", "createIntentSenderForOriginalIntent"],
    "services/core/java/com/android/server/wm/AppLockController.java": [
        "setHiddenWhileLockedByAppLock", "isPackageLockedByAppLockLocked"],
    "services/core/java/com/android/server/am/AppLockLocalService.java": [
        "DeviceLockedStateListener", "setAppLockEnabledPackageSuccessfullyAuthenticated"],
    "services/core/java/com/android/server/pm/AppLockPackageHelper.java": [
        "PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_ONE_SHOT", "isDeviceSecure"],
}


def replace_guarded(content, old, new, relative, revert=False):
    # The new manifest text intentionally includes the old anchor at its end.
    if new in content:
        if content.count(new) != 1:
            raise ValueError("Duplicate Suite patch in " + relative)
        return content.replace(new, old, 1) if revert else content
    if content.count(old) != 1:
        raise ValueError("Unfamiliar source; review instead of forcing: " + relative)
    return content if revert else content.replace(old, new, 1)


def plan(rom, revert=False):
    base = rom / FRAMEWORK
    if not revert:
        for relative, markers in CAPABILITIES.items():
            content = (base / relative).read_text()
            if not all(marker in content for marker in markers):
                raise ValueError("Missing reviewed Android 17 App Lock interface: " + relative)
        manifest = ET.parse(base / "core/res/AndroidManifest.xml").getroot()
        native = [p for p in manifest.findall("permission")
                  if p.get(ANDROID + "name") == "android.permission.LOCK_APPS"]
        if len(native) != 1 or native[0].get(ANDROID + "protectionLevel") != "internal|role|recents":
            raise ValueError("Native LOCK_APPS protection changed; review before integration")
    changes = {}
    for relative, (old, new) in PATCHES.items():
        path = base / relative
        current = path.read_text()
        target = replace_guarded(current, old, new, relative, revert)
        if target != current:
            changes[path] = target
    helper = base / HELPER
    expected = (ROOT / "framework/HeckerSuiteAppLockAccess.java").read_text()
    if helper.exists() and helper.read_text() != expected:
        raise ValueError("Preserving an unfamiliar Suite access helper: " + str(helper))
    if revert:
        if helper.exists(): changes[helper] = None
    elif not helper.exists():
        changes[helper] = expected
    return changes


def apply(rom, mode):
    changes = plan(rom, mode == "revert")
    if mode == "verify":
        if changes:
            raise ValueError("Suite access patches are missing; run tools/prepare.py --apply")
        print("Hecker Suite native App Lock access: already applied and verified")
        return
    if mode == "check":
        print("Hecker Suite native App Lock access:", "ready to apply" if changes else "already applied")
        return
    if changes:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = rom / "out/hecker-suite-source-backups" / stamp
        # Validate the complete plan before changing any file. Back up original tracked content.
        for path in changes:
            if path.exists():
                destination = backup / path.relative_to(rom)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
        written = []
        originals = {path: path.read_text() if path.exists() else None for path in changes}
        try:
            for path, target in changes.items():
                if target is None:
                    path.unlink()
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_suffix(path.suffix + ".hecker-tmp")
                    temporary.write_text(target)
                    temporary.replace(path)
                written.append(path)
        except OSError:
            for path in reversed(written):
                original = originals[path]
                if original is None: path.unlink(missing_ok=True)
                else: path.write_text(original)
            raise
    print("Hecker Suite native App Lock access:", "reverted" if mode == "revert" else "applied")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom-root", type=Path, default=Path.cwd())
    group = parser.add_mutually_exclusive_group(required=True)
    for mode in ("check", "apply", "verify", "revert"):
        group.add_argument("--" + mode, action="store_true")
    args = parser.parse_args()
    mode = next(mode for mode in ("check", "apply", "verify", "revert") if getattr(args, mode))
    try:
        apply(args.rom_root.resolve(), mode)
    except (ValueError, OSError, ET.ParseError) as error:
        print("Hecker Suite setup:", error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

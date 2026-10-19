#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate plugin resources, selected features and least-privilege packaging."""
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
A = "{http://schemas.android.com/apk/res/android}"


def main():
    for file in (ROOT / "app/res").rglob("*.xml"):
        ET.parse(file)
    for file in (ROOT / "app/res/raw").glob("*.json"):
        document = json.loads(file.read_text())
        assert document["layers"] and document["assets"] == [], file
        assert document["op"] > document["ip"] and document["fr"] == 30, file
    manifest = ET.parse(ROOT / "app/AndroidManifest.xml").getroot()
    assert manifest.get("package") == "org.hecker.suite"
    assert A + "sharedUserId" not in manifest.attrib
    permissions = {node.get(A + "name") for node in manifest.findall("uses-permission")}
    assert permissions == {
        "android.permission.CAMERA", "android.permission.SYSTEM_CAMERA",
        "android.permission.HIDE_OVERLAY_WINDOWS", "android.permission.USE_BIOMETRIC",
        "android.permission.QUERY_ALL_PACKAGES", "android.permission.HECKER_SUITE_APP_LOCK"}
    assert not any("INTERNET" in p or "TEST_LOCK_APPS" in p for p in permissions)
    app = manifest.find("application")
    assert app.get(A + "allowBackup") == "false"
    exported = [node.get(A + "name") for node in app.findall("activity")
                if node.get(A + "exported") == "true"]
    assert exported == [".SuiteActivity"]
    assert not manifest.findall(".//category[@" + A + "name='android.intent.category.LAUNCHER']")
    assert not app.findall("service") and not app.findall("receiver")
    allowlist = ET.parse(ROOT / "configs/privapp-permissions-hecker-suite.xml").getroot()
    assert {node.get("name") for node in allowlist.findall(".//permission")} == {"android.permission.SYSTEM_CAMERA"}
    release = (ROOT / "release/release_configs/hecker_suite.textproto").read_text()
    assert 'inherits: "cp2a"' in release and 'name: "hecker_suite"' in release
    for name in ("app_lock_apis", "app_lock_core"):
        flag = (ROOT / "flags/security" / (name + "_flag_values.textproto")).read_text()
        assert 'name: "' + name + '"' in flag and "state: ENABLED" in flag
        assert "permission: READ_ONLY" in flag
    print("Suite resources, original Lottie assets, Settings entry and permissions: PASS")


if __name__ == "__main__": main()

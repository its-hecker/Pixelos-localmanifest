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
        "android.permission.QUERY_ALL_PACKAGES", "android.permission.HECKER_SUITE_APP_LOCK",
        "android.permission.ACCESS_FPS_COUNTER", "android.permission.REAL_GET_TASKS",
        "android.permission.MANAGE_ACTIVITY_TASKS", "android.permission.START_ACTIVITIES_FROM_BACKGROUND",
        "android.permission.SYSTEM_ALERT_WINDOW", "android.permission.KILL_BACKGROUND_PROCESSES",
        "android.permission.KILL_ALL_BACKGROUND_PROCESSES", "android.permission.CONTROL_DISPLAY_BRIGHTNESS",
        "android.permission.MODIFY_AUDIO_SETTINGS", "android.permission.ACCESS_NETWORK_STATE",
        "android.permission.ACCESS_NOTIFICATION_POLICY", "android.permission.READ_FRAME_BUFFER",
        "android.permission.POST_NOTIFICATIONS", "android.permission.FOREGROUND_SERVICE",
        "android.permission.FOREGROUND_SERVICE_SPECIAL_USE", "android.permission.FOREGROUND_SERVICE_MEDIA_PROJECTION",
        "android.permission.RECEIVE_BOOT_COMPLETED"}
    assert not any("INTERNET" in p or "TEST_LOCK_APPS" in p for p in permissions)
    app = manifest.find("application")
    assert app.get(A + "allowBackup") == "false"
    exported = [node.get(A + "name") for node in app.findall("activity")
                if node.get(A + "exported") == "true"]
    assert exported == [".SuiteActivity"]
    assert not manifest.findall(".//category[@" + A + "name='android.intent.category.LAUNCHER']")
    services = {node.get(A + "name"): node for node in app.findall("service")}
    assert set(services) == {".GamingService", ".GamingRecordingService"}
    assert all(node.get(A + "exported") == "false" for node in services.values())
    assert services[".GamingService"].get(A + "foregroundServiceType") == "specialUse"
    assert services[".GamingRecordingService"].get(A + "foregroundServiceType") == "mediaProjection"
    receivers = app.findall("receiver")
    assert len(receivers) == 1 and receivers[0].get(A + "exported") == "false"
    allowlist = ET.parse(ROOT / "configs/privapp-permissions-hecker-suite.xml").getroot()
    assert {node.get("name") for node in allowlist.findall(".//permission")} == {
        "android.permission.SYSTEM_CAMERA", "android.permission.ACCESS_FPS_COUNTER",
        "android.permission.REAL_GET_TASKS", "android.permission.START_ACTIVITIES_FROM_BACKGROUND",
        "android.permission.KILL_ALL_BACKGROUND_PROCESSES"}
    freeform = ET.parse(ROOT / "configs/hecker-suite-freeform.xml").getroot()
    assert [node.get("name") for node in freeform.findall("feature")] == ["android.software.freeform_window_management"]
    assert '"HeckerSuiteFreeformFeature"' in (ROOT / "Android.bp").read_text()
    assert 'tests/' not in re.search(r'(?ms)^android_app\s*\{.*?^\}', (ROOT / "Android.bp").read_text()).group()
    release = (ROOT / "release/release_configs/hecker_suite.textproto").read_text()
    assert 'inherits: "cp2a"' in release and 'name: "hecker_suite"' in release
    for name in ("app_lock_apis", "app_lock_core"):
        flag = (ROOT / "flags/security" / (name + "_flag_values.textproto")).read_text()
        assert 'name: "' + name + '"' in flag and "state: ENABLED" in flag
        assert "permission: READ_ONLY" in flag
    print("Suite resources, Lottie, gaming service/capture boundaries, freeform feature and permissions: PASS")


if __name__ == "__main__": main()

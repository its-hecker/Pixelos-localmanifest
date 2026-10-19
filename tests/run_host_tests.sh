#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -eo pipefail
suite_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$suite_root"
python3 tools/check_source.py
python3 -m unittest discover -s tests -p 'test_*.py'
suite_test_output="$(mktemp -d)"
trap 'rm -rf -- "$suite_test_output"' EXIT
java -m jdk.compiler/com.sun.tools.javac.Main -d "$suite_test_output" \
    app/src/org/hecker/suite/RawFrameDecoder.java tests/RawFrameDecoderTest.java
java -cp "$suite_test_output" org.hecker.suite.RawFrameDecoderTest
java -m jdk.compiler/com.sun.tools.javac.Main -d "$suite_test_output" \
    tests/host-stubs/android/content/Context.java \
    tests/host-stubs/android/content/pm/ApplicationInfo.java \
    tests/host-stubs/android/content/pm/PackageManager.java \
    tests/host-stubs/android/os/Binder.java tests/host-stubs/android/os/UserHandle.java \
    framework/HeckerSuiteAppLockAccess.java tests/HeckerSuiteAccessTest.java
java -cp "$suite_test_output" com.android.server.pm.HeckerSuiteAccessTest

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the patched test-package filter with PixelOS's real Go path functions."""

import argparse
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("noksu", ROOT / "tools/build_noksu_boot.py")
noksu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(noksu)
REF = "321ecf4fc740482603b917c5de30a0e27e97595e"
RAW = f"https://raw.githubusercontent.com/PixelOS-AOSP/android_build_soong/{REF}/"


def function(source, name):
    start = source.index("func " + name + "(")
    # The path functions under test end with a top-level closing brace.
    return source[start:source.index("\n}\n", start) + 3]


def stage_function(name, block):
    return f'''func {name}(productOut, installed string) (string, error) {{
        var ctx android.PathContext
        _ = ctx
        for _, installedFile := range []installedPath{{installedPath(installed)}} {{
            {block}
            return android.StagePath("STAGING", f)
        }}
        return "", nil
    }}
'''


MAIN = r'''
package main
import (
    "fmt"
    "strings"
    "noksupaths/android"
)
type installedPath string
func (p installedPath) String() string { return string(p) }
STAGE_FUNCTIONS
func main() {
    product := "/home/itsheckurrr/pixelos/out-noksu/target/product/coral"
    host := "/home/itsheckurrr/pixelos/out-noksu/host/linux-x86/bin/perfetto_trace_processor_shell"
    _, err := oldStage(product, host)
    if err == nil || !strings.Contains(err.Error(), "Path is outside directory") {
        panic(fmt.Sprintf("Original absolute host path did not reproduce failure: %v", err))
    }
    cases := []struct{ product, file, want string }{
        {product, host, ""},
        {product, product+"/system/app/Test/Test.apk", "STAGING/system/app/Test/Test.apk"},
        {"out/target/product/coral", "out/host/linux-x86/bin/perfetto_trace_processor_shell", ""},
        {"out-noksu/target/product/coral", "out-noksu/target/product/coral/vendor/bin/test", "STAGING/vendor/bin/test"},
        {"build-custom/target/product/coral", "build-custom/host/linux-x86/bin/perfetto_trace_processor_shell", ""},
        {product, product+"-other/system/app/Test.apk", ""},
        {product, product+"/../other/vendor/bin/test", ""},
    }
    for _, test := range cases {
        got, err := newStage(test.product, test.file)
        if err != nil || got != test.want {
            panic(fmt.Sprintf("product=%q file=%q: got %q, %v; want %q", test.product, test.file, got, err, test.want))
        }
    }
    fmt.Printf("Original Soong path error reproduced; %d patched path cases passed.\n", len(cases))
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go", default="go")
    args = parser.parse_args()
    sources = {}
    for path in ("ci_tests/ci_test_package_zip.go", "android/paths.go"):
        with urllib.request.urlopen(RAW + path, timeout=60) as response:
            sources[path] = response.read().decode("utf-8")
    with tempfile.TemporaryDirectory(prefix="noksu-soong-paths-") as directory:
        root = Path(directory)
        source = root / noksu.SOONG_TEST_PACKAGE
        source.parent.mkdir(parents=True)
        source.write_text(sources["ci_tests/ci_test_package_zip.go"])
        output = root / "out-noksu"
        noksu.prepare_soong_host_paths(root, output)
        patched = source.read_text()
        assert noksu.SOONG_NEW_HOST_FILTER in patched
        assert noksu.prepare_soong_host_paths(root, output) == "already applied"
        backup = output / "source-backups" / noksu.SOONG_TEST_PACKAGE
        assert backup.read_text() == sources["ci_tests/ci_test_package_zip.go"]
        # Parse the complete patched Go file with the same toolchain's formatter.
        gofmt = Path(args.go).resolve().with_name("gofmt") if Path(args.go).is_absolute() else Path("gofmt")
        subprocess.run([str(gofmt)], input=patched, text=True, stdout=subprocess.PIPE, check=True)
        (root / "go.mod").write_text("module noksupaths\n\ngo 1.21\n")
        android = root / "android"
        android.mkdir()
        paths = sources["android/paths.go"]
        functions = "\n".join(function(paths, name) for name in
                              ("MaybeRel", "maybeRelErr", "validatePathInternal"))
        (android / "paths.go").write_text('''// Copyright The Android Open Source Project. Apache-2.0.
package android
import ("fmt"; "path/filepath"; "strings")
type PathContext interface{}
func reportPathError(ctx PathContext, err error) { panic(err) }
func StagePath(parts ...string) (string, error) { return validatePathInternal(false, parts...) }
''' + functions)
        stages = stage_function("oldStage", noksu.SOONG_OLD_HOST_FILTER)
        stages += stage_function("newStage", noksu.SOONG_NEW_HOST_FILTER)
        (root / "main.go").write_text(MAIN.replace("STAGE_FUNCTIONS", stages))
        subprocess.run([args.go, "run", "."], cwd=root, check=True)


if __name__ == "__main__":
    main()

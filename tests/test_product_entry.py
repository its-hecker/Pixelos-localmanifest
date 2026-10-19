# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProductEntryTests(unittest.TestCase):
    def test_release_map_is_available_before_android_defines_my_dir(self):
        with tempfile.TemporaryDirectory() as temp:
            rom = Path(temp)
            suite = rom / "vendor/hecker/floral/suite"
            suite.mkdir(parents=True)
            (suite / "suite.mk").write_bytes((ROOT / "suite.mk").read_bytes())
            source = "\n".join([
                "include vendor/hecker/floral/suite/suite.mk",
                "$(info MAPS=$(PRODUCT_RELEASE_CONFIG_MAPS))",
                "$(info PACKAGES=$(PRODUCT_PACKAGES))",
                "all:", "\t@:", ""])
            result = subprocess.run(["make", "--no-print-directory", "-f", "-", "all"],
                                    cwd=rom, input=source, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("MAPS=vendor/hecker/floral/suite/release/release_config_map.textproto", result.stdout)
            self.assertIn("PACKAGES=HeckerSuite", result.stdout)


if __name__ == "__main__": unittest.main()

# SPDX-License-Identifier: Apache-2.0
"""Regress the camera Make copy conflict that survives no_full_install."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from camera_install import SOURCE, SERVICE
from validate import camera_init, init_installers


class InitInstallerTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.rom = Path(directory.name)
        self.source = self.rom / SOURCE
        self.source.parent.mkdir(parents=True)
        self.source.write_text('cc_binary {\n    name: "' + SERVICE + '",\n'
                               '    no_full_install: true,\n'
                               '    init_rc: ["' + SERVICE + '.rc"],\n}\n')
        for relative in ("vendor/google/coral/Android.bp", "vendor/hecker/floral/faceid/Android.bp"):
            path = self.rom / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        vendor_bp = self.rom / "vendor/google/coral/Android.bp"
        vendor_bp.write_text('cc_prebuilt_binary {\n    name: "' + SERVICE + '-coral",\n'
                             '    init_rc: ["proprietary/vendor/etc/init/' + SERVICE + '.rc"],\n}\n')
        self.make = self.rom / "vendor/google/coral/coral-vendor.mk"
        self.make.write_text("PRODUCT_COPY_FILES += keep:vendor/etc/init/keep.rc\n")
        self.stock = self.rom / "vendor/google/coral/proprietary/vendor/etc/init" / (SERVICE + ".rc")
        self.stock.parent.mkdir(parents=True)
        self.stock.write_text("service camera /vendor/bin/hw/" + SERVICE + "\n    user system\n")
        (self.source.parent / self.stock.name).write_bytes(self.stock.read_bytes())
        self.destination = "vendor/etc/init/" + SERVICE + ".rc"
        self.copy = self.stock.relative_to(self.rom).as_posix() + ":" + self.destination

    def test_selected_prebuilt_owns_init_and_an_independent_product_copy_is_rejected(self):
        camera_init(self.rom)
        self.source.write_text(self.source.read_text().replace(
            'init_rc: ["' + SERVICE + '.rc"]', 'init_rc: []'))
        owners = init_installers(self.rom, ["keep:vendor/etc/init/keep.rc"])
        self.assertEqual(len(owners[self.destination]), 1)
        self.assertIn("vendor/etc/init/keep.rc", owners)
        with self.assertRaisesRegex(ValueError, "Two init installers"):
            init_installers(self.rom, [self.copy])
        self.make.write_text("PRODUCT_COPY_FILES += \\\n    " + self.copy + "\n")
        with self.assertRaisesRegex(ValueError, "duplicate camera init"):
            camera_init(self.rom)

    def test_unused_source_is_not_accepted_as_the_only_runtime_installer(self):
        (self.rom / "vendor/google/coral/Android.bp").write_text("")
        with self.assertRaisesRegex(ValueError, "selected camera prebuilt must install"):
            camera_init(self.rom)

    def test_two_soong_owners_are_rejected_even_when_source_full_install_is_suppressed(self):
        with self.assertRaisesRegex(ValueError, "Two init installers"):
            init_installers(self.rom, [])

    def test_a_different_source_init_is_refused(self):
        (self.source.parent / self.stock.name).write_text("service camera /vendor/bin/other\n")
        with self.assertRaisesRegex(ValueError, "differs from Coral"):
            camera_init(self.rom)


if __name__ == "__main__":
    unittest.main()

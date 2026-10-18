# SPDX-License-Identifier: Apache-2.0
"""Boot header, root removal, module compatibility and isolated-output guards."""

import importlib.util
import gzip
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[1] / "tools/build_noksu_boot.py"
spec = importlib.util.spec_from_file_location("noksu", SOURCE)
noksu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(noksu)

CONFIG = """CONFIG_ARM64=y
CONFIG_IKCONFIG=y
CONFIG_MODVERSIONS=y
CONFIG_KSU=y
CONFIG_KSU_MANUAL_HOOK=y
CONFIG_KSU_SUSFS=y
CONFIG_KSU_SUSFS_SUS_MOUNT=y
CONFIG_KSU_FULL_NAME_FORMAT="%KSU_VERSION%"
# CONFIG_LOCALVERSION_AUTO is not set
CONFIG_LOCALVERSION="-CNB"
"""

LZ4 = os.environ.get("PIXEL_NOKSU_TEST_LZ4") or shutil.which("lz4") or shutil.which("lz4c")


def kernel_data(config=CONFIG):
    compressed = gzip.compress(config.encode(), mtime=0)
    # Reuse the gzip bytes before the real IKCONFIG so LZ4 can encode the
    # actual config with back-references; scanning compressed bytes cannot work.
    return compressed * 8 + b"\0" * 256 + b"IKCFG_ST" + compressed + b"IKCFG_ED" + b"\0" * 256


def boot(kernel=b"kernel", dtb=b"dtb", recovery=b"", second=b""):
    header = bytearray(4096)
    header[:8] = b"ANDROID!"
    struct.pack_into("<5I", header, 8, len(kernel), 0, 7, 0, len(second))
    struct.pack_into("<2I", header, 36, 4096, 2)
    struct.pack_into("<I", header, 1648, len(dtb))
    pad = lambda data: data + b"\0" * (-len(data) % 4096)
    body = pad(kernel) + pad(b"ramdisk") + pad(second)
    if recovery:
        struct.pack_into("<IQ", header, 1632, len(recovery), 4096 + len(body))
        body += pad(recovery)
    return bytes(header) + body + pad(dtb)


class NoKsuTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.rom = Path(self.temporary.name)

    def test_disables_every_root_option_and_preserves_other_config(self):
        config = noksu.no_ksu_config(CONFIG)
        values = noksu.config_values(config)
        self.assertTrue(all(value == "n" for name, value in values.items() if name.startswith("CONFIG_KSU")))
        self.assertEqual(values["CONFIG_LOCALVERSION"], '"-CNB"')
        noksu.check_config(CONFIG, config)

    def test_accepts_kconfig_removing_hidden_dependent_options(self):
        config = noksu.no_ksu_config(CONFIG)
        config = "\n".join(line for line in config.splitlines() if "CONFIG_KSU_" not in line)
        noksu.check_config(CONFIG, config)

    def test_rejects_enabled_susfs(self):
        config = noksu.no_ksu_config(CONFIG).replace("# CONFIG_KSU_SUSFS is not set", "CONFIG_KSU_SUSFS=y")
        with self.assertRaisesRegex(ValueError, "remain enabled"):
            noksu.check_config(CONFIG, config)

    def test_rejects_unrelated_configuration_change(self):
        config = noksu.no_ksu_config(CONFIG).replace("CONFIG_MODVERSIONS=y", "# CONFIG_MODVERSIONS is not set")
        with self.assertRaisesRegex(ValueError, "CONFIG_MODVERSIONS"):
            noksu.check_config(CONFIG, config)

    def test_rejects_baseline_already_without_ksu(self):
        with self.assertRaisesRegex(ValueError, "does not enable"):
            noksu.no_ksu_config(noksu.no_ksu_config(CONFIG))

    def test_extracts_header_v2_with_optional_second_and_recovery(self):
        path = self.rom / "boot.img"
        for second, recovery in ((b"", b""), (b"second", b"overlay")):
            path.write_bytes(boot(b"newkernel", b"device-tree", recovery, second))
            result = noksu.boot_parts(path)
            self.assertEqual(result["kernel"], b"newkernel")
            self.assertEqual(result["dtb"], b"device-tree")

    def test_rejects_unsupported_boot_header(self):
        data = bytearray(boot())
        struct.pack_into("<I", data, 40, 4)
        path = self.rom / "boot.img"
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "header v2"):
            noksu.boot_parts(path)

    def test_rejects_truncated_boot_image(self):
        path = self.rom / "boot.img"
        path.write_bytes(boot()[:12000])
        with self.assertRaisesRegex(ValueError, "Truncated"):
            noksu.boot_parts(path)

    def test_checks_exported_symbol_crcs_including_missing_symbols(self):
        old, new = self.rom / "old", self.rom / "new"
        old.write_text("0x1234 regular vmlinux EXPORT_SYMBOL\n0x5555 ksu_private vmlinux EXPORT_SYMBOL\n")
        new.write_text("0x1234 regular vmlinux EXPORT_SYMBOL\n")
        noksu.check_abi(old, new)
        for text in ("0x4321 regular vmlinux EXPORT_SYMBOL\n", "0x5555 unrelated vmlinux EXPORT_SYMBOL\n"):
            new.write_text(text)
            with self.assertRaisesRegex(ValueError, "module ABI differs"):
                noksu.check_abi(old, new)

    def test_resolves_existing_output_environment(self):
        self.assertEqual(noksu.baseline_out(self.rom, {}), self.rom / "out")
        self.assertEqual(noksu.baseline_out(self.rom, {"OUT_DIR": "custom"}), self.rom / "custom")
        self.assertEqual(noksu.baseline_out(self.rom, {"OUT_DIR_COMMON_BASE": "/builds"}),
                         Path("/builds") / self.rom.name)

    def test_reads_config_from_actual_uncompressed_kernel(self):
        image = self.rom / "Image"
        image.write_bytes(kernel_data())
        self.assertEqual(noksu.embedded_config(self.rom, image), CONFIG)

    def test_rejects_damaged_gzip_or_missing_end_marker(self):
        image = self.rom / "Image"
        data = b"IKCFG_ST" + gzip.compress(CONFIG.encode(), mtime=0) + b"IKCFG_ED"
        damaged = bytearray(data)
        damaged[-9] ^= 1  # Corrupt the gzip length trailer.
        for value in (bytes(damaged), data[:-8], b"CONFIG_IKCONFIG=y\n"):
            image.write_bytes(value)
            with self.subTest(value=value[:20]), self.assertRaisesRegex(ValueError, "no intact IKCONFIG"):
                noksu.embedded_config(self.rom, image)

    def test_skips_false_start_markers_before_the_real_config(self):
        image = self.rom / "Image"
        image.write_bytes(b"IKCFG_ST\x1f\x8b\x08garbage" + kernel_data())
        self.assertEqual(noksu.embedded_config(self.rom, image), CONFIG)

    @unittest.skipUnless(LZ4, "requires the lz4/lz4c test executable")
    def test_reads_both_modern_and_legacy_lz4_frames_with_real_decoder(self):
        binary = self.rom / "prebuilts/kernel-build-tools/linux-x86/bin/lz4"
        binary.parent.mkdir(parents=True)
        binary.symlink_to(Path(LZ4).resolve())
        image = self.rom / "Image.lz4"
        for flags, magic in (([], b"\x04\x22\x4d\x18"), (["-l"], b"\x02\x21\x4c\x18")):
            for config in (CONFIG, noksu.no_ksu_config(CONFIG)):
                with self.subTest(flags=flags, rooted="CONFIG_KSU=y" in config):
                    data = subprocess.run([LZ4, *flags, "-9", "-c"], input=kernel_data(config),
                                          capture_output=True, check=True).stdout
                    self.assertEqual(data[:4], magic)
                    image.write_bytes(data)
                    self.assertEqual(noksu.embedded_config(self.rom, image), config)

    @unittest.skipUnless(LZ4, "requires the lz4/lz4c test executable")
    def test_uses_lz4c_and_reports_decompression_errors(self):
        binary = self.rom / "prebuilts/kernel-build-tools/linux-x86/bin/lz4c"
        binary.parent.mkdir(parents=True)
        binary.symlink_to(Path(LZ4).resolve())
        image = self.rom / "Image.lz4"
        data = subprocess.run([LZ4, "-9", "-c"], input=kernel_data(), capture_output=True, check=True).stdout
        image.write_bytes(data)
        with mock.patch.dict(os.environ, {"PATH": ""}):
            self.assertEqual(noksu.embedded_config(self.rom, image), CONFIG)
            image.write_bytes(data[:10])
            with self.assertRaisesRegex(ValueError, "Cannot decompress"):
                noksu.embedded_config(self.rom, image)

    def test_reports_missing_decoder_without_using_config_file(self):
        image = self.rom / "Image.lz4"
        image.write_bytes(b"\x04\x22\x4d\x18dummy")
        (self.rom / ".config").write_text(CONFIG)
        with mock.patch.dict(os.environ, {"PATH": str(self.rom / "no-tools")}):
            with self.assertRaisesRegex(ValueError, "no executable lz4 or lz4c"):
                noksu.embedded_config(self.rom, image)

    @unittest.skipUnless(LZ4, "requires the lz4/lz4c test executable")
    def test_falls_back_from_unusable_prebuilt_to_other_build_tools(self):
        broken = self.rom / "prebuilts/kernel-build-tools/linux-x86/bin/lz4"
        broken.parent.mkdir(parents=True)
        broken.write_bytes(b"not an executable file format")
        broken.chmod(0o755)
        image = self.rom / "Image.lz4"
        image.write_bytes(subprocess.run([LZ4, "-9", "-c"], input=kernel_data(),
                                         capture_output=True, check=True).stdout)
        for relative in ("prebuilts/tools-lineage/linux-x86/bin/lz4c",
                         "prebuilts/build-tools/linux-x86/bin/lz4"):
            with self.subTest(relative=relative):
                binary = self.rom / relative
                binary.parent.mkdir(parents=True, exist_ok=True)
                binary.symlink_to(Path(LZ4).resolve())
                with mock.patch.dict(os.environ, {"PATH": ""}):
                    self.assertEqual(noksu.embedded_config(self.rom, image), CONFIG)
                binary.unlink()

    def stage(self):
        (self.rom / ".repo").mkdir()
        (self.rom / "build").mkdir()
        (self.rom / "build/envsetup.sh").touch()
        self.base = self.rom / "out"
        self.output = self.rom / "out-noksu"
        product = self.base / "target/product/coral"
        self.stage_product(product, CONFIG, b"kernel")
        return product

    def stage_product(self, product, config, kernel):
        obj = product / noksu.KERNEL_OBJ
        for relative, data in {
            ".config": config.encode(), noksu.KERNEL_IMAGE: kernel,
            "Module.symvers": b"0x1234 regular vmlinux EXPORT_SYMBOL\n",
            "include/config/kernel.release": b"4.14.349-CNB\n",
        }.items():
            path = obj / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (product / "boot.img").write_bytes(boot(kernel))

    def test_rejects_overlapping_outputs_before_starting_build(self):
        self.stage()
        for output in (self.base, self.base / "nested", self.rom):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "separate|source root"):
                noksu.build(self.rom, self.base, output, 8)

    def test_rejects_baseline_boot_that_does_not_match_compiled_kernel(self):
        product = self.stage()
        (product / "boot.img").write_bytes(boot(b"wrong"))
        with self.assertRaisesRegex(ValueError, "do not match"):
            noksu.build(self.rom, self.base, self.output, 8)

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_isolated_build_exports_verified_image_without_changing_baseline(self):
        product = self.stage()
        original = {str(path): path.read_bytes() for path in self.base.rglob("*") if path.is_file()}

        def config(rom, image):
            return CONFIG if image.is_relative_to(self.base) else noksu.no_ksu_config(CONFIG)

        def run(command, **kwargs):
            self.assertEqual(command[:2], ["bash", "-c"])
            env = kwargs["env"]
            self.assertEqual(env["OUT_DIR"], str(self.output))
            self.assertEqual(env["TARGET_KERNEL_ADDITIONAL_FLAGS"], "-j8")
            fragment = Path(env["TARGET_KERNEL_CONFIG_EXT"]).read_text()
            noksu.check_config(CONFIG, fragment)
            self.stage_product(self.output / "target/product/coral", fragment, b"no-root-kernel")

        with mock.patch.object(noksu, "embedded_config", side_effect=config), \
                mock.patch.object(noksu.subprocess, "check_output", return_value="source-sha\n"), \
                mock.patch.object(noksu.subprocess, "run", side_effect=run):
            noksu.build(self.rom, self.base, self.output, 8)
        self.assertEqual(original, {str(path): path.read_bytes() for path in self.base.rglob("*") if path.is_file()})
        image = self.output / noksu.IMAGE
        self.assertTrue(image.is_file())
        self.assertIn(noksu.sha256(image), image.with_suffix(".img.sha256").read_text())

    def test_verification_rejects_a_rooted_kernel_in_the_new_boot(self):
        product = self.stage()
        new_product = self.output / "target/product/coral"
        self.stage_product(new_product, noksu.no_ksu_config(CONFIG), b"no-root-kernel")
        (new_product / "boot.img").write_bytes(boot(b"kernel"))
        with self.assertRaisesRegex(ValueError, "newly built kernel"):
            noksu.verify(self.rom, product, new_product)

    def test_verification_rejects_different_dtb(self):
        product = self.stage()
        new_product = self.output / "target/product/coral"
        self.stage_product(new_product, noksu.no_ksu_config(CONFIG), b"no-root-kernel")
        (new_product / "boot.img").write_bytes(boot(b"no-root-kernel", b"other-dtb"))
        with self.assertRaisesRegex(ValueError, "DTB changed"):
            noksu.verify(self.rom, product, new_product)


if __name__ == "__main__":
    unittest.main()

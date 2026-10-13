#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Test real template key formats using disposable keys, never production keys."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import signing

TEMPLATE = None
AVB_TOOL = None


class SigningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="pixelos-test-signing-")
        cls.base = Path(cls.temporary.name)
        cls.rom = cls.base / "rom"
        cls.rom.mkdir()
        cls.source = cls.base / "private-template"
        shutil.copytree(TEMPLATE, cls.source, ignore=shutil.ignore_patterns(".git", "__pycache__"), symlinks=True)
        link = cls.source / "gen_keys_py/avbtool.py"
        link.unlink()
        link.symlink_to(AVB_TOOL.resolve())
        cls.source.chmod(0o700)
        sys.path.insert(0, str(cls.source))
        spec = importlib.util.spec_from_file_location("gen_keys", cls.source / "gen_keys.py")
        cls.generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.generator)
        cls.generator.CERTS_PATH = cls.base / "temporary-platform-pem"
        cls.generator.CERTS_PATH.mkdir(mode=0o700)
        cls.names = ["releasekey", "platform", "com.android.nfcservices.certificate.override",
                     "com.android.vndk.certificate.override"]
        old_dir, old_mask = Path.cwd(), os.umask(0o077)
        try:
            os.chdir(cls.source)
            for name in ["releasekey", "platform", "com.android.nfcservices", "com.android.vndk"]:
                cls.generator.generate_key(name)
            cls.generator.generate_android_bp()
            cls.generator.generate_keys_mk()
        finally:
            os.chdir(old_dir)
            os.umask(old_mask)
        cls.real_lock = signing.lock()
        cls.test_lock = dict(cls.real_lock, certificate_bases=cls.names)
        with mock.patch.object(signing, "lock", return_value=cls.test_lock):
            signing.install(cls.rom, cls.source)

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(str(cls.source))
        cls.temporary.cleanup()

    def test_real_template_key_pairs_and_apex_public_keys(self):
        values = signing.validate_pairs(self.source, self.names, self.rom)
        self.assertEqual(set(values), set(self.names))

    def test_generated_product_mappings_match_the_reviewed_template(self):
        content = (self.source / "keys.mk").read_text()
        self.assertIn("PRODUCT_DEFAULT_DEV_CERTIFICATE := " + signing.DEFAULT_CERT, content)
        for override in self.real_lock["certificate_overrides"]:
            self.assertIn(override, content)

    def test_build_signer_and_overrides_are_enforced(self):
        with mock.patch.object(signing, "lock", return_value=self.test_lock):
            signing.check(self.rom, signing.DEFAULT_CERT, " ".join(self.real_lock["certificate_overrides"]))
            with self.assertRaisesRegex(ValueError, "active default certificate"):
                signing.check(self.rom, "build/make/target/product/security/testkey")
            with self.assertRaisesRegex(ValueError, "active APK/APEX"):
                signing.check(self.rom, signing.DEFAULT_CERT, "")

    def test_mismatched_certificate_is_rejected(self):
        target = self.source / "releasekey.x509.pem"
        saved = target.read_bytes()
        try:
            target.write_bytes((self.source / "platform.x509.pem").read_bytes())
            with self.assertRaisesRegex(ValueError, "key/certificate mismatch"):
                signing.validate_pairs(self.source, ["releasekey"], self.rom)
        finally:
            target.write_bytes(saved)

    def test_apex_payload_mismatch_is_rejected(self):
        target = self.source / "com.android.nfcservices.pem"
        saved = target.read_bytes()
        try:
            target.write_bytes((self.source / "com.android.vndk.pem").read_bytes())
            with self.assertRaisesRegex(ValueError, "payload/container"):
                signing.validate_pairs(self.source, [self.names[2]], self.rom)
        finally:
            target.write_bytes(saved)

    def test_stale_apex_public_key_is_rejected(self):
        target = self.source / "com.android.nfcservices.avbpubkey"
        saved = target.read_bytes()
        try:
            target.write_bytes(saved[:-1] + bytes([saved[-1] ^ 1]))
            with self.assertRaisesRegex(ValueError, "AVB public/private"):
                signing.validate_pairs(self.source, [self.names[2]], self.rom)
        finally:
            target.write_bytes(saved)

    def test_missing_private_key_is_rejected(self):
        key = self.source / "platform.pk8"
        temporary = key.with_suffix(".pk8.saved")
        key.rename(temporary)
        try:
            with self.assertRaisesRegex(ValueError, "Missing signing pair"):
                signing.validate_pairs(self.source, ["platform"], self.rom)
        finally:
            temporary.rename(key)

    def test_private_bytes_are_outside_the_checkout(self):
        directory = self.rom / signing.KEY_PATH
        for name in self.names:
            key = directory / (name + ".pk8")
            self.assertTrue(key.is_symlink())
            self.assertFalse(key.resolve().is_relative_to(self.rom))
        self.assertEqual((directory / ".gitignore").read_text(), "*\n")
        with self.assertRaisesRegex(ValueError, "outside"):
            signing.outside(self.rom / "should-not-store-secrets", self.rom)

    def test_changed_certificate_identity_is_rejected(self):
        path = self.rom / signing.KEY_PATH / signing.PROFILE
        original = path.read_bytes()
        try:
            profile = json.loads(original)
            profile["certificates"]["releasekey"] = "0" * 64
            path.write_text(json.dumps(profile))
            with mock.patch.object(signing, "lock", return_value=self.test_lock):
                with self.assertRaisesRegex(ValueError, "identity changed"):
                    signing.check(self.rom)
        finally:
            path.write_bytes(original)

    def test_public_aosp_certificate_is_rejected(self):
        tests = self.rom / "build/make/target/product/security"
        tests.mkdir(parents=True)
        file = tests / "testkey.x509.pem"
        shutil.copyfile(self.source / "releasekey.x509.pem", file)
        try:
            with self.assertRaisesRegex(ValueError, "Public AOSP test"):
                signing.validate_pairs(self.source, ["releasekey"], self.rom)
        finally:
            file.unlink()


def main():
    global TEMPLATE, AVB_TOOL
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--avb-tool", type=Path, required=True)
    args = parser.parse_args()
    TEMPLATE, AVB_TOOL = args.template.resolve(), args.avb_tool.resolve()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SigningTests)
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Prepare PixelOS's recommended signing template and check private signing inputs."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
KEY_PATH = Path("vendor/lineage-priv/keys")
DEFAULT_CERT = (KEY_PATH / "releasekey").as_posix()
PROFILE = ".pixelos-signing.json"


def lock():
    return json.loads((ROOT / "signing-template.lock.json").read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def command(arguments, cwd=None):
    return subprocess.check_output(arguments, cwd=cwd, stdin=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE)


def outside(path, rom):
    require(not path.resolve().is_relative_to(rom.resolve()),
            "Private signing material must be stored outside the Android checkout")


def template(store, rom):
    outside(store, rom)
    destination = store / "template"
    store.mkdir(parents=True, exist_ok=True, mode=0o700)
    store.chmod(0o700)
    if not destination.exists():
        subprocess.run(["git", "clone", "--quiet", "--no-checkout", lock()["url"], str(destination)],
                       check=True)
        subprocess.run(["git", "-C", str(destination), "checkout", "--quiet", "--detach",
                        lock()["revision"]], check=True)
    revision = command(["git", "-C", str(destination), "rev-parse", "HEAD"]).decode().strip()
    require(revision == lock()["revision"], "Signing template differs from the reviewed revision")
    destination.chmod(0o700)
    avb_source = rom / "external/avb/avbtool.py"
    require(avb_source.is_file(), "Missing external/avb/avbtool.py; finish the Android source sync")
    avb_link = destination / "gen_keys_py/avbtool.py"
    require(avb_link.is_symlink(), "Signing template's AVB helper must be its expected symlink")
    expected_link = lock()["generator_symlinks"]["gen_keys_py/avbtool.py"]
    require(os.readlink(avb_link) == expected_link or avb_link.resolve() == avb_source.resolve(),
            "Signing template's AVB helper points to an unrecognized source")
    if avb_link.resolve() != avb_source.resolve():
        avb_link.unlink()
        avb_link.symlink_to(avb_source.resolve())
    return destination


def certificate(path):
    return command(["openssl", "x509", "-in", str(path), "-outform", "DER"])


def validate_pairs(directory, names, rom):
    """Compare certificate/key identities without printing private bytes."""
    fingerprints = {}
    public_test_certs = set()
    for path in (rom / "build/make/target/product/security").glob("*.x509.pem"):
        public_test_certs.add(hashlib.sha256(certificate(path)).hexdigest())
    for name in names:
        key = directory / (name + ".pk8")
        cert = directory / (name + ".x509.pem")
        require(key.is_file() and cert.is_file(), "Missing signing pair: " + name)
        outside(key, rom)
        require(key.resolve().stat().st_mode & 0o077 == 0, "Private-key file permissions must be 600: " + name)
        key_public = command(["openssl", "pkey", "-inform", "DER", "-in", str(key), "-pubout"])
        cert_public = command(["openssl", "x509", "-in", str(cert), "-pubkey", "-noout"])
        require(key_public == cert_public, "Private key/certificate mismatch: " + name)
        if name.endswith(".certificate.override"):
            payload_name = name.removesuffix(".certificate.override")
            payload = directory / (payload_name + ".pem")
            outside(payload, rom)
            require(payload.is_file() and payload.resolve().stat().st_mode & 0o077 == 0,
                    "Missing or unprotected APEX payload key: " + payload_name)
            payload_public = command(["openssl", "pkey", "-in", str(payload), "-pubout"])
            require(payload_public == key_public, "APEX payload/container key mismatch: " + payload_name)
            modulus = command(["openssl", "rsa", "-inform", "DER", "-in", str(key),
                               "-noout", "-modulus"]).decode().strip()
            require(modulus.startswith("Modulus="), "APEX key must be RSA: " + payload_name)
            number = int(modulus.split("=", 1)[1], 16)
            bits = number.bit_length()
            require(bits >= 2048 and bits % 8 == 0, "Unexpected APEX RSA key size")
            avb_bytes = struct.pack("!II", bits, (-pow(number, -1, 2**32)) % 2**32)
            avb_bytes += number.to_bytes(bits // 8, "big")
            avb_bytes += pow(2, bits * 2, number).to_bytes(bits // 8, "big")
            suffix = ".pubkey" if payload_name == "com.android.vndk" else ".avbpubkey"
            require((directory / (payload_name + suffix)).read_bytes() == avb_bytes,
                    "APEX AVB public/private key mismatch: " + payload_name)
        fingerprint = hashlib.sha256(certificate(cert)).hexdigest()
        require(fingerprint not in public_test_certs, "Public AOSP test certificate selected: " + name)
        fingerprints[name] = fingerprint
    return fingerprints


def install(rom, directory):
    target = rom / KEY_PATH
    require(not target.is_symlink(), "Existing signing directory symlink needs explicit migration")
    require(not target.exists() or (target / PROFILE).is_file() or not any(target.iterdir()),
            "Existing signing folder found; preserve it and review migration before using this helper")
    fingerprints = validate_pairs(directory, lock()["certificate_bases"], rom)
    if (target / PROFILE).is_file():
        previous = json.loads((target / PROFILE).read_text())
        require(previous["certificates"] == fingerprints,
                "Signing identity changed; refusing to replace the existing configuration")
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.chmod(0o700)
    for name in ["Android.bp", "keys.mk", "BUILD.bazel"]:
        shutil.copyfile(directory / name, target / name)
    # Actual key bytes remain in the protected external directory. Soong sees
    # ordinary build files and file symlinks at the template's expected path.
    for path in directory.iterdir():
        if path.name.endswith((".pk8", ".pem", ".avbpubkey", ".pubkey")):
            destination = target / path.name
            if destination.is_symlink():
                require(destination.resolve() == path.resolve(), "Existing key link differs: " + path.name)
                continue
            require(not destination.exists(), "Refusing to replace an existing signing file: " + path.name)
            destination.symlink_to(path.absolute())
    (target / ".gitignore").write_text("*\n")
    (target / PROFILE).write_text(json.dumps({"template_revision": lock()["revision"],
                                           "store": str(directory.resolve()),
                                           "certificates": fingerprints}, indent=2) + "\n")


def generate(rom, store):
    destination = template(store, rom)
    # Only the subject configuration may be edited before executing the pinned generator.
    for name, expected in lock()["generator_inputs"].items():
        require(hashlib.sha256((destination / name).read_bytes()).hexdigest() == expected,
                "Reviewed signing generator input changed: " + name)
    previous_mask = os.umask(0o077)
    try:
        platform_pem = Path("~/.android-certs").expanduser()
        platform_pem.mkdir(parents=True, exist_ok=True, mode=0o700)
        platform_pem.chmod(0o700)
        outside(platform_pem, rom)
        subprocess.run([sys.executable, str(destination / "gen_keys.py")], cwd=destination, check=True)
    finally:
        os.umask(previous_mask)
    install(rom, destination)
    check(rom)


def check(rom, active_cert=None, active_overrides=None):
    target = rom / KEY_PATH
    require((target / PROFILE).is_file(),
            "Private signing is not configured. Follow README.md -> Private signing before building")
    profile = json.loads((target / PROFILE).read_text())
    require(profile["template_revision"] == lock()["revision"], "Signing template revision differs")
    require(set(profile["certificates"]) == set(lock()["certificate_bases"]), "Incomplete signing profile")
    current = validate_pairs(target, lock()["certificate_bases"], rom)
    require(current == profile["certificates"], "Signing identity changed; restore the original key backup")
    makefile = (target / "keys.mk").read_text()
    require("PRODUCT_DEFAULT_DEV_CERTIFICATE := " + DEFAULT_CERT in makefile,
            "Default certificate is not the private release key")
    if active_cert is not None:
        actual = Path(active_cert.strip())
        if not actual.is_absolute():
            actual = rom / actual
        require(actual.resolve() == (rom / DEFAULT_CERT).resolve(),
                "PixelOS's active default certificate was overridden; private signing is not active")
    if active_overrides is not None:
        require(set(lock()["certificate_overrides"]) <= set(active_overrides.split()),
                "PixelOS's active APK/APEX certificate overrides differ from the private template")
    print("Private signing pairs and stable certificate fingerprints: PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["setup", "generate", "check"])
    parser.add_argument("--rom-root", type=Path, default=Path.cwd())
    parser.add_argument("--store", type=Path, default=Path("~/.pixelos-signing/coral"))
    parser.add_argument("--active-cert")
    parser.add_argument("--active-overrides")
    args = parser.parse_args()
    rom, store = args.rom_root.expanduser().resolve(), args.store.expanduser().resolve()
    try:
        if args.action == "setup":
            location = template(store, rom)
            print("Edit certificate subject values in:", location / "gen_keys_py/config.py")
            print("Then run this helper's generate action with the signing virtualenv Python.")
        elif args.action == "generate":
            generate(rom, store)
        else:
            check(rom, args.active_cert, args.active_overrides)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        # Do not dump captured subprocess input/output from signing operations.
        print("PixelOS signing:", type(error).__name__, str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

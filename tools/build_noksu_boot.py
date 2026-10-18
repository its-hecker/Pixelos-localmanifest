#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build an additional Coral boot image without KernelSU, using an isolated OUT_DIR."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import zlib


IMAGE = "PixelOS-coral-noKSU-boot.img"
KERNEL_OBJ = "obj/KERNEL_OBJ"
KERNEL_IMAGE = "arch/arm64/boot/Image.lz4"
KSU_OPTION = re.compile(r"^(?:# )?(CONFIG_KSU(?:_\w+)?)(?:=| is not set)")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def config_values(text):
    result = {}
    for line in text.splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            name, value = line.split("=", 1)
            result[name] = value
        elif line.startswith("# CONFIG_") and line.endswith(" is not set"):
            result[line[2:-11]] = "n"
    return result


def no_ksu_config(text):
    require(config_values(text).get("CONFIG_KSU") == "y",
            "The baseline kernel config does not enable KernelSU.")
    lines = []
    for line in text.splitlines():
        match = KSU_OPTION.match(line)
        lines.append(f"# {match[1]} is not set" if match else line)
    return "\n".join(lines) + "\n"


def check_config(baseline, candidate):
    old, new = config_values(baseline), config_values(candidate)
    require(new.get("CONFIG_KSU") == "n", "CONFIG_KSU was not disabled.")
    enabled = [name for name, value in new.items()
               if name.startswith("CONFIG_KSU") and value in ("y", "m")]
    require(not enabled, "KernelSU/SUSFS options remain enabled: " + ", ".join(enabled))
    # Kconfig can remove dependent options entirely when their parent is disabled.
    differences = [name for name in old.keys() | new.keys()
                   if not name.startswith("CONFIG_KSU") and
                   old.get(name, "n") != new.get(name, "n")]
    require(not differences, "Unrelated kernel configuration changed: " +
            ", ".join(sorted(differences)))


def boot_parts(path):
    """Coral uses the documented Android boot header v2, with a separate DTB."""
    data = path.read_bytes()
    require(len(data) >= 1660 and data[:8] == b"ANDROID!", "Invalid Android boot image.")
    kernel_size, _, ramdisk_size, _, second_size = struct.unpack_from("<5I", data, 8)
    pagesize, version = struct.unpack_from("<2I", data, 36)
    require(version == 2 and pagesize == 4096,
            "This helper requires Coral's boot header v2 and 4096-byte pages.")
    recovery_size = struct.unpack_from("<I", data, 1632)[0]
    recovery_offset = struct.unpack_from("<Q", data, 1636)[0]
    dtb_size = struct.unpack_from("<I", data, 1648)[0]
    require(kernel_size and ramdisk_size and dtb_size, "Missing kernel, ramdisk or DTB.")
    align = lambda size: (size + pagesize - 1) // pagesize * pagesize
    end = pagesize + align(kernel_size) + align(ramdisk_size) + align(second_size)
    if recovery_size:
        require(recovery_offset == end, "Unexpected recovery DTBO offset.")
        end += align(recovery_size)
    require(end + dtb_size <= len(data), "Truncated boot image.")
    return {"kernel": data[pagesize:pagesize + kernel_size],
            "dtb": data[end:end + dtb_size], "header_version": version,
            "os_version": struct.unpack_from("<I", data, 44)[0],
            "cmdline": data[64:576] + data[608:1632]}


def symvers(path):
    symbols = {}
    for line in path.read_text().splitlines():
        fields = line.split()
        require(len(fields) >= 4, f"Invalid Module.symvers entry in {path}")
        symbols[fields[1]] = int(fields[0], 16)
    require(symbols, f"Empty Module.symvers: {path}")
    return symbols


def check_abi(baseline, candidate):
    old, new = symvers(baseline), symvers(candidate)
    # Root-only exports disappear; every other existing exported ABI must remain.
    changes = [name for name, crc in old.items()
               if not name.startswith(("ksu_", "susfs_")) and new.get(name) != crc]
    require(not changes, "Kernel module ABI differs; do not use this as a boot-only update: " +
            ", ".join(sorted(changes)[:20]))


def decompress_lz4(rom, image):
    # The 4.14 shell extractor only recognizes legacy LZ4. This kernel's
    # scripts/Makefile.lib runs `lz4c -9`, which can produce modern frames.
    # Both command names accept -d -c for either format; use the build's
    # prebuilts first and fall back to executable host tools.
    search = [str(rom / relative) for relative in (
        "prebuilts/kernel-build-tools/linux-x86/bin",
        "prebuilts/tools-lineage/linux-x86/bin",
        "prebuilts/build-tools/linux-x86/bin",
    )]
    search += os.environ.get("PATH", os.defpath).split(os.pathsep)
    attempted, errors = set(), []
    for directory in search:
        for name in ("lz4", "lz4c"):
            tool = (Path(directory) / name).resolve()
            if tool in attempted or not tool.is_file() or not os.access(tool, os.X_OK):
                continue
            attempted.add(tool)
            try:
                result = subprocess.run([str(tool), "-d", "-c", str(image)], capture_output=True)
            except OSError as error:
                errors.append(f"{tool}: {error}")
                continue
            if result.returncode == 0:
                return result.stdout
            errors.append(f"{tool}: " + result.stderr.decode("utf-8", errors="replace").strip()[-500:])
    require(attempted, "Cannot decompress the kernel: no executable lz4 or lz4c found in the build prebuilts or PATH.")
    raise ValueError("Cannot decompress " + str(image) + ": " + "; ".join(errors))


def embedded_config(rom, image):
    data = image.read_bytes()
    if data[:4] in (b"\x04\x22\x4d\x18", b"\x02\x21\x4c\x18"):
        data = decompress_lz4(rom, image)
    # Read IKCONFIG from the actual image, including gzip CRC/length checking
    # and the kernel's end marker. Never substitute a possibly stale .config.
    marker, offset = b"IKCFG_ST\x1f\x8b\x08", 0
    while True:
        start = data.find(marker, offset)
        if start == -1:
            break
        offset = start + len(marker)
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            config = decoder.decompress(data[start + 8:]).decode("utf-8")
        except (zlib.error, UnicodeError):
            continue
        if (decoder.eof and decoder.unused_data.startswith(b"IKCFG_ED") and
                config_values(config).get("CONFIG_IKCONFIG") == "y"):
            return config
    raise ValueError("Cannot verify the configuration embedded in " + str(image) +
                     ": no intact IKCONFIG gzip stream with an end marker was found.")


def baseline_out(rom, environment):
    if environment.get("OUT_DIR"):
        path = Path(environment["OUT_DIR"])
    elif environment.get("OUT_DIR_COMMON_BASE"):
        path = Path(environment["OUT_DIR_COMMON_BASE"]) / rom.name
    else:
        path = Path("out")
    return (rom / path).resolve()


def verify(rom, baseline, product):
    old_obj, new_obj = baseline / KERNEL_OBJ, product / KERNEL_OBJ
    old_parts, new_parts = boot_parts(baseline / "boot.img"), boot_parts(product / "boot.img")
    require(new_parts["kernel"] == (new_obj / KERNEL_IMAGE).read_bytes(),
            "The new boot image does not contain the newly built kernel.")
    require(old_parts["dtb"] == new_parts["dtb"], "The DTB changed from the working ROM.")
    for field in ("os_version", "cmdline"):
        require(old_parts[field] == new_parts[field], f"Boot {field} changed from the working ROM.")
    check_config((old_obj / ".config").read_text(), (new_obj / ".config").read_text())
    check_config((old_obj / ".config").read_text(), embedded_config(rom, new_obj / KERNEL_IMAGE))
    check_abi(old_obj / "Module.symvers", new_obj / "Module.symvers")
    release = "include/config/kernel.release"
    require((old_obj / release).read_text() == (new_obj / release).read_text(),
            "Kernel release changed; the installed ROM's modules would not match.")
    return (new_obj / release).read_text().strip()


BUILD = r"""
set -eo pipefail
source build/envsetup.sh
breakfast coral "${PIXEL_BUILD_VARIANT:-userdebug}"
test "$(get_build_var TARGET_DEVICE)" = coral
test "$(get_build_var TARGET_PRODUCT)" = custom_coral
test "$(get_build_var TARGET_KERNEL_CONFIG_EXT)" = "$PIXEL_NOKSU_FRAGMENT" || {
    echo "The device configuration did not accept the no-KSU fragment." >&2
    exit 1
}
m -j"$PIXEL_BUILD_JOBS" bootimage
"""


def build(rom, base_out, output, jobs):
    require(rom.is_dir() and (rom / ".repo").is_dir() and
            (rom / "build/envsetup.sh").is_file(), "Run from the existing PixelOS source root.")
    require(output != base_out and output not in base_out.parents and base_out not in output.parents,
            "The no-KSU output must be separate from the normal build output.")
    require(output != rom and output not in rom.parents,
            "The source root cannot be used as the output directory.")
    require(not os.environ.get("TARGET_KERNEL_CONFIG_EXT") and
            not os.environ.get("KERNEL_CONFIG_OVERRIDE"),
            "Unset TARGET_KERNEL_CONFIG_EXT and KERNEL_CONFIG_OVERRIDE before running this helper.")
    require(os.environ.get("PIXEL_BUILD_VARIANT", "userdebug") in ("userdebug", "eng"),
            "Use the same userdebug or eng variant as the working ROM.")
    require(jobs > 0, "Build jobs must be positive.")
    baseline = base_out / "target/product/coral"
    obj = baseline / KERNEL_OBJ
    inputs = [baseline / "boot.img", obj / ".config", obj / KERNEL_IMAGE,
              obj / "Module.symvers", obj / "include/config/kernel.release"]
    for path in inputs:
        require(path.is_file(), "Missing completed-ROM build input: " + str(path))
    require(boot_parts(baseline / "boot.img")["kernel"] == (obj / KERNEL_IMAGE).read_bytes(),
            "The baseline boot image and kernel output do not match. Use the completed ROM build.")
    config = (obj / ".config").read_text()
    require(config_values(config) == config_values(embedded_config(rom, obj / KERNEL_IMAGE)),
            "The baseline .config does not match its compiled kernel.")
    require(config_values(config).get("CONFIG_MODVERSIONS") == "y",
            "The baseline must provide module version CRCs for compatibility checks.")
    require(config_values(config).get("CONFIG_MODULE_SIG", "n") == "n",
            "This boot-only helper requires the Coral configuration with module signing disabled.")
    hashes = {str(path.relative_to(base_out)): sha256(path) for path in inputs}
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".noksu-build.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("A no-KSU build is already using this output directory.") from None
        state = output / "noksu-baseline.json"
        source_revision = subprocess.check_output(
            ["git", "-C", str(rom / "kernel/google/msm-4.14"), "rev-parse", "HEAD"], text=True).strip()
        identity = {"baseline_out": str(base_out), "inputs": hashes, "kernel_source": source_revision,
                    "variant": os.environ.get("PIXEL_BUILD_VARIANT", "userdebug")}
        if state.exists():
            require(json.loads(state.read_text()) == identity,
                    "This output belongs to another baseline. Choose a fresh --out directory.")
        else:
            require(not (output / "target").exists() and not (output / "soong").exists(),
                    "Choose a fresh --out directory for the no-KSU build.")
            state.write_text(json.dumps(identity, indent=2) + "\n")
        fragment = output / "coral-noksu.config"
        fragment.write_text(no_ksu_config(config))
        environment = os.environ.copy()
        environment.update(OUT_DIR=str(output), TARGET_KERNEL_CONFIG_EXT=str(fragment),
                           PIXEL_NOKSU_FRAGMENT=str(fragment), PIXEL_BUILD_JOBS=str(jobs))
        # Override only the kernel's parallel job count; retain the provider's RBE setup.
        environment["TARGET_KERNEL_ADDITIONAL_FLAGS"] = (
            environment.get("TARGET_KERNEL_ADDITIONAL_FLAGS", "") + f" -j{jobs}").strip()
        print(f"Building no-KSU boot image in {output}", flush=True)
        subprocess.run(["bash", "-c", BUILD], cwd=rom, env=environment, check=True)
        require(all(sha256(path) == hashes[str(path.relative_to(base_out))] for path in inputs),
                "The baseline changed during this build; rerun against a completed ROM build.")
        product = output / "target/product/coral"
        release = verify(rom, baseline, product)
        artifact = output / IMAGE
        shutil.copyfile(product / "boot.img", artifact)
        digest = sha256(artifact)
        artifact.with_suffix(".img.sha256").write_text(f"{digest}  {IMAGE}\n")
        report = {**identity, "image": IMAGE, "sha256": digest, "kernel_release": release,
                  "CONFIG_KSU": "n", "module_abi": "compatible", "dtb": "matches baseline"}
        artifact.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"Verified CONFIG_KSU=n, SUSFS disabled, matching module ABI and DTB.\nImage: {artifact}\nSHA256: {digest}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom-root", type=Path, default=Path.cwd())
    parser.add_argument("--base-out", type=Path, help="Existing completed ROM's OUT_DIR (default: current OUT_DIR or out)")
    parser.add_argument("--out", type=Path, help="Separate output directory (default: out-noksu)")
    parser.add_argument("--jobs", type=int, default=int(os.environ.get("PIXEL_BUILD_JOBS", "8")))
    args = parser.parse_args()
    rom = args.rom_root.resolve()
    try:
        base = (rom / args.base_out).resolve() if args.base_out else baseline_out(rom, os.environ)
        output = (rom / (args.out or Path("out-noksu"))).resolve()
        build(rom, base, output, args.jobs)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print("No-KSU boot build stopped: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

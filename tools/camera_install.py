# SPDX-License-Identifier: Apache-2.0
"""Keep the stock Coral camera as the sole full installer for its service files."""

import hashlib
import os
from pathlib import Path
import re
import stat
import tempfile


SOURCE = "hardware/google/camera/common/hal/aidl_service/Android.bp"
SERVICE = "android.hardware.camera.provider@2.7-service-google"
REPLACED = {"cc_binary": SERVICE, "vintf_fragment": "hardware_camera_vintf"}


def suppress_source_installs(content):
    text = content.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    for kind, name in REPLACED.items():
        pattern = (r'(?ms)^' + kind + r'\s*\{\s*name:\s*"' +
                   re.escape(name) + r'",[^\n]*\n.*?^\}')
        matches = list(re.finditer(pattern, text))
        if len(matches) != 1:
            raise ValueError("Review changed camera module before suppressing its install: " + name)
        block = matches[0].group()
        flags = list(re.finditer(r'(?m)^    no_full_install:\s*(true|false),[^\r\n]*', block))
        if len(re.findall(r'\bno_full_install\s*:', block)) != len(flags) or len(flags) > 1:
            raise ValueError("Review unfamiliar camera no_full_install property: " + name)
        if flags:
            flag = flags[0]
            replacement = block[:flag.start(1)] + "true" + block[flag.end(1):]
        else:
            end = block.index("\n") + 1
            # The module's name is the first property in the checked upstream layout.
            end = block.index("\n", end) + 1
            replacement = block[:end] + "    no_full_install: true," + newline + block[end:]
        if kind == "cc_binary":
            # The selected -coral prebuilt must install its init script. Keeping
            # it on this overridden source module produced no runtime service.
            inits = list(re.finditer(r'(?m)^    init_rc:\s*(\[[^\]]*\]),[^\r\n]*', replacement))
            if len(inits) != 1:
                raise ValueError("Review the source camera init_rc before transferring ownership")
            field = inits[0]
            values = re.findall(r'"([^"]+)"', field.group(1))
            if values not in ([], [SERVICE + ".rc"]):
                raise ValueError("Review changed camera init_rc files before transferring ownership")
            replacement = replacement[:field.start(1)] + "[]" + replacement[field.end(1):]
        text = text[:matches[0].start()] + replacement + text[matches[0].end():]
    return text.encode("utf-8")


def configure(rom, write=False):
    path = rom / SOURCE
    if path.is_symlink():
        raise ValueError("Refusing to replace a symlinked camera Blueprint: " + str(path))
    original = path.read_bytes()
    replacement = suppress_source_installs(original)
    if replacement == original:
        return "already configured"
    if not write:
        return "patch available"
    backup = rom / "out/floral-camera-install" / (hashlib.sha256(original).hexdigest() + ".Android.bp.original")
    backup.parent.mkdir(parents=True, exist_ok=True)
    try:
        with backup.open("xb") as handle:
            handle.write(original)
    except FileExistsError:
        if backup.read_bytes() != original:
            raise ValueError("Camera backup differs from the original source: " + str(backup))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".camera-install-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(replacement)
        temporary.chmod(stat.S_IMODE(path.stat().st_mode))
        if path.read_bytes() != original:
            raise ValueError("Camera Blueprint changed during preparation; retry after reviewing the edit")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return "configured; original saved at " + str(backup)
